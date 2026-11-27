"""
Unit tests for Bronze ingestion layer.
"""

import json
import tempfile
from pathlib import Path
from collections import namedtuple
import pytest

from src.healthguard.ingestion.ndjson_reader import read_ndjson_stream, NDJSONRecord, count_ndjson_records
from src.healthguard.ingestion.resource_router import ResourceRouter, CORE_RESOURCE_TYPES
from src.healthguard.ingestion.batch_manager import compute_batch_id, IngestionManifest, compute_config_hash
from src.healthguard.ingestion.source_validator import validate_resource, load_contract
from src.healthguard.bronze.schema import BRONZE_SCHEMA, validate_bronze_table
from src.healthguard.bronze.manifest import IngestionManifest, save_manifest, load_manifest, is_batch_committed


# Test record factory
Record = namedtuple("Record", ["parse_status", "resource_type", "resource_id", "resource", "line_number", "raw_line"])


class TestNDJSONReader:
    """Tests for NDJSON streaming reader."""
    
    def test_read_valid_ndjson(self):
        """Read valid NDJSON file line by line."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ndjson", delete=False) as f:
            f.write('{"resourceType": "Patient", "id": "1"}\n')
            f.write('{"resourceType": "Encounter", "id": "2"}\n')
            f.write('{"resourceType": "Condition", "id": "3"}\n')
            temp_path = Path(f.name)
        
        try:
            records = list(read_ndjson_stream(temp_path))
            assert len(records) == 3
            assert records[0].resource_type == "Patient"
            assert records[1].resource_type == "Encounter"
            assert records[2].resource_type == "Condition"
            assert all(r.parse_status == "VALID" for r in records)
        finally:
            temp_path.unlink()
    
    def test_read_ndjson_with_invalid_json(self):
        """Handle malformed JSON lines gracefully."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ndjson", delete=False) as f:
            f.write('{"resourceType": "Patient", "id": "1"}\n')
            f.write('not valid json\n')
            f.write('{"resourceType": "Encounter", "id": "2"}\n')
            temp_path = Path(f.name)
        
        try:
            records = list(read_ndjson_stream(temp_path))
            assert len(records) == 3
            assert records[0].parse_status == "VALID"
            assert records[1].parse_status == "INVALID_JSON"
            assert records[2].parse_status == "VALID"
        finally:
            temp_path.unlink()
    
    def test_read_ndjson_missing_resource_type(self):
        """Handle resources missing resourceType field."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ndjson", delete=False) as f:
            f.write('{"id": "1"}\n')  # Missing resourceType
            f.write('{"resourceType": "Patient", "id": "2"}\n')
            temp_path = Path(f.name)
        
        try:
            records = list(read_ndjson_stream(temp_path))
            assert len(records) == 2
            assert records[0].parse_status == "MISSING_RESOURCE_TYPE"
            assert records[1].parse_status == "VALID"
        finally:
            temp_path.unlink()
    
    def test_count_ndjson_records(self):
        """Count records without loading all into memory."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ndjson", delete=False) as f:
            f.write('{"resourceType": "Patient", "id": "1"}\n')
            f.write('{"resourceType": "Patient", "id": "2"}\n')
            f.write('invalid\n')
            temp_path = Path(f.name)
        
        try:
            valid, invalid = count_ndjson_records(temp_path)
            assert valid == 2
            assert invalid == 1
        finally:
            temp_path.unlink()


class TestResourceRouter:
    """Tests for resource routing."""
    
    def test_route_core_resources(self):
        """Route core resource types to buffers."""
        router = ResourceRouter()
        
        # Valid Patient
        router.route_record(Record(
            parse_status="VALID",
            resource_type="Patient",
            resource_id="1",
            resource={"id": "1", "resourceType": "Patient"},
            line_number=1,
            raw_line='{"resourceType":"Patient"}',
        ))
        
        # Valid Encounter
        router.route_record(Record(
            parse_status="VALID",
            resource_type="Encounter",
            resource_id="2",
            resource={"id": "2", "resourceType": "Encounter"},
            line_number=2,
            raw_line='{"resourceType":"Encounter"}',
        ))
        
        summary = router.get_summary()
        assert summary["core_counts"]["Patient"] == 1
        assert summary["core_counts"]["Encounter"] == 1
        assert summary["total_core"] == 2
    
    def test_route_out_of_scope(self):
        """Track out-of-scope resources separately."""
        router = ResourceRouter()
        
        router.route_record(Record(
            parse_status="VALID",
            resource_type="Claim",
            resource_id="1",
            resource={"id": "1", "resourceType": "Claim"},
            line_number=1,
            raw_line='{"resourceType":"Claim"}',
        ))
        
        summary = router.get_summary()
        assert summary["out_of_scope_counts"]["Claim"] == 1
        assert summary["total_out_of_scope"] == 1
        assert summary["total_core"] == 0
    
    def test_invalid_records_not_routed(self):
        """Invalid records go to invalid count, not buffers."""
        router = ResourceRouter()
        
        router.route_record(Record(
            parse_status="INVALID_JSON",
            resource_type=None,
            resource_id=None,
            resource={},
            line_number=1,
            raw_line="invalid",
        ))
        
        summary = router.get_summary()
        assert summary["invalid_count"] == 1
        assert summary["total_core"] == 0


class TestBatchManager:
    """Tests for batch ID computation and manifests."""
    
    def test_batch_id_deterministic(self):
        """Same inputs produce same batch ID."""
        with tempfile.NamedTemporaryFile(suffix=".ndjson", delete=False) as f1:
            f1.write(b'{"resourceType": "Patient"}')
            p1 = Path(f1.name)
        
        with tempfile.NamedTemporaryFile(suffix=".ndjson", delete=False) as f2:
            f2.write(b'{"resourceType": "Encounter"}')
            p2 = Path(f2.name)
        
        try:
            config_hash = "test_config_hash"
            
            batch_id1 = compute_batch_id([p1, p2], config_hash)
            batch_id2 = compute_batch_id([p1, p2], config_hash)
            
            assert batch_id1 == batch_id2
            assert len(batch_id1) == 16  # SHA256 truncated to 16 chars
        finally:
            Path(p1).unlink()
            Path(p2).unlink()
    
    def test_batch_id_changes_with_files(self):
        """Different files produce different batch IDs."""
        with tempfile.NamedTemporaryFile(suffix=".ndjson", delete=False) as f1:
            f1.write(b'{"resourceType": "Patient"}')
            p1 = Path(f1.name)
        
        with tempfile.NamedTemporaryFile(suffix=".ndjson", delete=False) as f2:
            f2.write(b'{"resourceType": "Encounter"}')
            p2 = Path(f2.name)
        
        with tempfile.NamedTemporaryFile(suffix=".ndjson", delete=False) as f3:
            f3.write(b'{"resourceType": "Condition"}')
            p3 = Path(f3.name)
        
        try:
            config_hash = "test_config_hash"
            
            batch_id1 = compute_batch_id([p1, p2], config_hash)
            batch_id2 = compute_batch_id([p1, p3], config_hash)
            
            assert batch_id1 != batch_id2
        finally:
            Path(p1).unlink()
            Path(p2).unlink()
            Path(p3).unlink()
    
    def test_manifest_serialization(self):
        """Manifest serializes and deserializes correctly."""
        from dataclasses import asdict
        
        manifest = IngestionManifest(
            batch_id="abc123",
            source_system="SYNTHEA_FHIR",
            source_format="FHIR_R4_NDJSON",
            status="COMMITTED",
            source_files=[{"path": "test.ndjson", "sha256": "abc", "size_bytes": 100}],
            resource_counts={"Patient": 10, "Encounter": 20},
            total_records=30,
            started_at="2026-01-01T00:00:00Z",
            completed_at="2026-01-01T00:01:00Z",
        )
        
        # Serialize
        data = asdict(manifest)
        
        # Deserialize
        manifest2 = IngestionManifest(**data)
        
        assert manifest.batch_id == manifest2.batch_id
        assert manifest.resource_counts == manifest2.resource_counts


class TestManifestStorage:
    """Tests for manifest file I/O."""
    
    def test_save_load_manifest(self):
        """Save and load manifest from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_dir = Path(tmpdir)
            
            manifest = IngestionManifest(
                batch_id="test_batch",
                source_system="SYNTHEA_FHIR",
                source_format="FHIR_R4_NDJSON",
                status="COMMITTED",
                source_files=[],
                resource_counts={"Patient": 10},
                total_records=10,
                started_at="2026-01-01T00:00:00Z",
            )
            
            # Save
            save_manifest(manifest, Path(tmpdir))
            
            # Load
            loaded = load_manifest(Path(tmpdir), "test_batch")
            
            assert loaded.batch_id == "test_batch"
            assert loaded.status == "COMMITTED"
    
    def test_is_batch_committed(self):
        """Check if batch is committed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_dir = Path(tmpdir)
            
            # Not committed initially
            assert not is_batch_committed(Path(tmpdir), "batch1")
            
            # Save committed manifest
            manifest = IngestionManifest(
                batch_id="batch1",
                source_system="SYNTHEA_FHIR",
                source_format="FHIR_R4_NDJSON",
                status="COMMITTED",
                source_files=[],
                resource_counts={},
                total_records=0,
                started_at="2026-01-01T00:00:00Z",
            )
            save_manifest(manifest, Path(tmpdir))
            
            # Now committed
            assert is_batch_committed(Path(tmpdir), "batch1")
            
            # Different batch not committed
            assert not is_batch_committed(Path(tmpdir), "batch2")


class TestBronzeSchema:
    """Tests for Bronze table schema validation."""
    
    def test_bronze_schema_exists(self):
        """Bronze schema is defined."""
        assert BRONZE_SCHEMA is not None
        assert "batch_id" in BRONZE_SCHEMA.names
        assert "resource_type" in BRONZE_SCHEMA.names
        assert "raw_payload" in BRONZE_SCHEMA.names
    
    def test_validate_bronze_table(self):
        """Validate Bronze table schema."""
        import pyarrow as pa
        
        # Create valid table
        table = pa.table({
            "batch_id": ["batch1", "batch1"],
            "source_system": ["SYNTHEA_FHIR", "SYNTHEA_FHIR"],
            "source_file": ["Patient.ndjson", "Patient.ndjson"],
            "source_line": [1, 2],
            "resource_type": ["Patient", "Patient"],
            "resource_id": ["1", "2"],
            "resource_version": [None, None],
            "source_last_updated": [None, None],
            "ingested_at": ["2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"],
            "raw_payload": ['{"id":"1"}', '{"id":"2"}'],
            "parse_status": ["VALID", "VALID"],
        })
        
        errors = validate_bronze_table(table)
        assert errors == []  # No errors for valid table


class TestConfigHash:
    """Tests for config hash computation."""
    
    def test_config_hash(self):
        """Config hash is deterministic."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("test: config\n")
            p = Path(f.name)
        
        try:
            hash1 = compute_config_hash(Path(f.name))
            hash2 = compute_config_hash(Path(f.name))
            assert hash1 == hash2
            assert len(hash1) == 64  # SHA256 hex
        finally:
            Path(f.name).unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])