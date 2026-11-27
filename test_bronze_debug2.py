import tempfile
from pathlib import Path
import sys
sys.path.insert(0, '.')

from src.healthguard.bronze.orchestrator import BronzeOrchestrator

with tempfile.TemporaryDirectory() as tmpdir:
    tmpdir = Path(tmpdir)
    source_dir = tmpdir / 'source'
    source_dir.mkdir()
    (source_dir / 'Patient.ndjson').write_text('{"resourceType": "Patient", "id": "P1"}\n')
    bronze_root = tmpdir / 'bronze'
    manifest_dir = tmpdir / 'manifests'
    
    orchestrator = BronzeOrchestrator(
        source_dir=source_dir,
        bronze_root=bronze_root,
        manifest_dir=manifest_dir,
        config_path=Path('config/resource_contracts'),
    )
    
    # First run
    batch_id1 = orchestrator.ingest_all()
    print(f'First run: {batch_id1}')
    
    # Check manifest
    manifest_file = manifest_dir / f"manifest_{batch_id1}.json"
    print(f"Manifest file: {manifest_file}")
    print(f"Manifest exists: {manifest_file.exists()}")
    
    # Second run
    batch_id2 = orchestrator.ingest_all()
    print(f'Second run: {batch_id2}')
    
    # Check _is_committed directly
    committed = orchestrator._is_committed(batch_id1)
    print(f"_is_committed: {committed}")