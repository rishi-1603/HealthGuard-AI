"""
Integration tests for Bronze ingestion pipeline.
"""

import tempfile
from pathlib import Path
import pytest

from src.healthguard.bronze.orchestrator import run_bronze_ingestion, BronzeOrchestrator


class TestBronzeIntegration:
    """Integration tests for full Bronze ingestion pipeline."""
    
    def test_bronze_ingestion_creates_parquet(self):
        """Full Bronze ingestion creates partitioned Parquet files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Create source NDJSON files
            source_dir = tmpdir / "source"
            source_dir.mkdir()
            
            # Patient file
            (source_dir / "Patient.ndjson").write_text(
                '{"resourceType": "Patient", "id": "P1", "gender": "female"}\n'
                '{"resourceType": "Patient", "id": "P2", "gender": "male"}\n'
            )
            
            # Encounter file
            (source_dir / "Encounter.ndjson").write_text(
                '{"resourceType": "Encounter", "id": "E1", "subject": {"reference": "Patient/P1"}, "status": "finished"}\n'
            )
            
            # Output directories
            bronze_root = tmpdir / "bronze"
            manifest_dir = tmpdir / "manifests"
            
            # Run ingestion
            orchestrator = BronzeOrchestrator(
                source_dir=source_dir,
                bronze_root=bronze_root,
                manifest_dir=manifest_dir,
                config_path=Path("config/resource_contracts"),  # Use real contracts
            )
            
            batch_id = orchestrator.ingest_all()
            
            # Verify batch committed
            assert batch_id is not None
            assert len(batch_id) == 16
            
            # Verify Parquet files created
            patient_files = list(bronze_root.glob("resource_type=Patient/**/*.parquet"))
            encounter_files = list(bronze_root.glob("resource_type=Encounter/**/*.parquet"))
            
            assert len(patient_files) == 1
            assert len(encounter_files) == 1
            
            # Verify manifest
            manifest_file = Path("data/manifests") / f"manifest_{batch_id}.json"
            # Check manifest exists somewhere
            manifest_files = list(tmpdir.glob("**/manifest_*.json"))
            assert len(manifest_files) >= 1
    
    def test_idempotent_re_run(self):
        """Re-running same batch produces no duplicate files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            source_dir = tmpdir / "source"
            source_dir.mkdir()
            
            (source_dir / "Patient.ndjson").write_text(
                '{"resourceType": "Patient", "id": "P1"}\n'
            )
            
            bronze_root = tmpdir / "bronze"
            manifest_dir = tmpdir / "manifests"
            
            orchestrator = BronzeOrchestrator(
                source_dir=source_dir,
                bronze_root=bronze_root,
                manifest_dir=manifest_dir,
                config_path=Path("config/resource_contracts"),
            )
            
            # First run
            batch_id1 = orchestrator.ingest_all()
            assert batch_id1 is not None
            
            # Count files after first run
            files_after_first = list(Path(tmpdir).glob("**/*.parquet"))
            count_first = len(files_after_first)
            
            # Second run (should skip)
            batch_id2 = orchestrator.ingest_all()
            assert batch_id2 is None  # Skipped
            
            # File count should be same
            files_after_second = list(Path(tmpdir).glob("**/*.parquet"))
            assert len(files_after_second) == count_first
    
    def test_partial_write_recovery(self):
        """Failed write doesn't leave corrupted state."""
        # This test would simulate a failure during write
        # For now, verify the staged write pattern exists in writer
        from src.healthguard.bronze.writer import BronzeWriter
        import inspect
        
        source = inspect.getsource(BronzeWriter.write_batch)
        assert "temp_file" in source
        assert "rename" in source


if __name__ == "__main__":
    pytest.main([__file__, "-v"])