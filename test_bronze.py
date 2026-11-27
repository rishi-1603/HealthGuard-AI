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
    
    batch_id = orchestrator.ingest_all()
    print(f'Result: {batch_id}')