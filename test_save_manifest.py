import tempfile
from pathlib import Path
import sys
sys.path.insert(0, '.')

from src.healthguard.ingestion.batch_manager import save_manifest, IngestionManifest
from datetime import datetime, timezone

with tempfile.TemporaryDirectory() as tmpdir:
    tmpdir = Path(tmpdir)
    manifest_dir = tmpdir / 'manifests'
    
    manifest = IngestionManifest(
        batch_id="test_batch",
        source_system="SYNTHEA_FHIR",
        source_format="FHIR_R4_NDJSON",
        status="COMMITTED",
        source_files=[],
        resource_counts={"Patient": 1},
        total_records=1,
        started_at=datetime.now(timezone.utc).isoformat(),
        completed_at=datetime.now(timezone.utc).isoformat(),
        config_hash="test",
    )
    
    print(f"Manifest dir: {manifest_dir}")
    print(f"Calling save_manifest...")
    
    try:
        result = save_manifest(manifest, manifest_dir)
        print(f"Save result: {result}")
        print(f"Result exists: {result.exists()}")
    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()
    
    # Check files in manifest_dir
    print(f"Files in manifest_dir: {list(manifest_dir.iterdir())}")