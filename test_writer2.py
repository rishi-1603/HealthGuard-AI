import tempfile
from pathlib import Path
import sys
sys.path.insert(0, '.')

from src.healthguard.bronze.writer import BronzeWriter
from src.healthguard.ingestion.batch_manager import IngestionManifest

with tempfile.TemporaryDirectory() as tmpdir:
    tmpdir = Path(tmpdir)
    bronze_root = tmpdir / 'bronze'
    manifest_dir = tmpdir / 'manifests'
    
    writer = BronzeWriter(
        bronze_root=bronze_root,
        manifest_dir=manifest_dir,
        config_path=Path('config/resource_contracts'),
    )
    
    # Test write_batch with minimal records
    records_by_type = {
        "Patient": [{
            "batch_id": "test_batch",
            "source_system": "SYNTHEA_FHIR",
            "source_file": "Patient.ndjson",
            "source_line": 1,
            "resource_type": "Patient",
            "resource_id": "P1",
            "resource_version": None,
            "source_last_updated": None,
            "ingested_at": "2026-01-01T00:00:00Z",
            "raw_payload": '{"resourceType": "Patient", "id": "P1"}',
            "parse_status": "VALID",
        }]
    }
    
    source_files = [Path("test.ndjson")]
    
    print("Calling write_batch...")
    batch_id = writer.write_batch(source_files, records_by_type)
    print(f"Returned batch_id: {batch_id}")
    
    # Check manifest with the SAME batch_id
    manifest_file = manifest_dir / f"manifest_{batch_id}.json"
    print(f"Manifest file: {manifest_file}")
    print(f"Manifest exists: {manifest_file.exists()}")
    
    # Also check what files exist
    print(f"Files in manifest_dir: {list(manifest_dir.iterdir())}")