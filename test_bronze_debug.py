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
    
    # Debug: check what _is_committed returns
    source_files = orchestrator.discover_source_files()
    print(f"Source files: {source_files}")
    
    batch_id = orchestrator._compute_batch_id(source_files)
    print(f"Computed batch_id: {batch_id}")
    
    # Check manifest file
    manifest_file = Path("data/manifests") / f"manifest_{batch_id}.json"
    print(f"Manifest file path: {manifest_file}")
    print(f"Manifest exists: {manifest_file.exists()}")
    
    # Check _is_committed
    committed = orchestrator._is_committed(batch_id)
    print(f"_is_committed: {committed}")