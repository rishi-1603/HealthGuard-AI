"""
Bronze Orchestrator — Main entry point for Bronze layer ingestion.

Coordinates: NDJSON reading -> validation -> routing -> Bronze writing -> manifest.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.healthguard.ingestion.ndjson_reader import read_ndjson_stream, count_ndjson_records
from src.healthguard.ingestion.resource_router import ResourceRouter, CORE_RESOURCE_TYPES
from src.healthguard.ingestion.batch_manager import (
    compute_batch_id, build_manifest, save_manifest, is_batch_committed, compute_config_hash, IngestionManifest
)
from src.healthguard.ingestion.source_validator import validate_resource, normalize_resource
from src.healthguard.bronze.writer import BronzeWriter
from src.healthguard.bronze.manifest import IngestionManifest, save_manifest as save_manifest_file, is_batch_committed as check_committed

logger = logging.getLogger(__name__)


class BronzeOrchestrator:
    """
    Orchestrates Bronze ingestion from NDJSON to Parquet.
    
    Flow:
    1. Discover source NDJSON files
    2. Compute deterministic batch ID
    3. Check if already committed (idempotency)
    4. Stream each file, validate, route to resource buffers
    4. Write partitioned Parquet
    5. Save manifest
    """
    
    def __init__(
        self,
        source_dir: Path,
        bronze_root: Path,
        manifest_dir: Path,
        config_path: Path,
        allowed_types: Optional[set[str]] = None,
    ):
        self.source_dir = Path(source_dir)
        self.bronze_root = Path(bronze_root)
        self.manifest_dir = Path(manifest_dir)
        self.config_path = Path(config_path)
        self.allowed_types = set(CORE_RESOURCE_TYPES) if allowed_types is None else set(allowed_types)
        
        self.writer = BronzeWriter(
            bronze_root=self.bronze_root,
            manifest_dir=self.manifest_dir,
            config_path=Path("config/resource_contracts"),  # Config dir for hash
        )
    
    def discover_source_files(self) -> list[Path]:
        """Discover NDJSON files in source directory."""
        files = sorted(self.source_dir.glob("*.ndjson"))
        logger.info(f"Discovered {len(files)} NDJSON files")
        return files
    
    def ingest_all(self) -> Optional[str]:
        """
        Run full Bronze ingestion.
        
        Returns:
            batch_id if new batch committed, None if already committed
        """
        source_files = self.discover_source_files()
        if not source_files:
            logger.warning("No source files found")
            return None
        
        # Compute batch ID from source files
        config_hash = ""  # Would compute from config dir
        batch_id = self._compute_batch_id(source_files)
        
        # Check idempotency
        if self._is_committed(batch_id):
            logger.info(f"Batch {batch_id} already committed, skipping")
            return None
        
        # Route all records
        records_by_type = self._route_all_files()
        
        # Write to Bronze
        batch_id = self._write_bronze(records_by_type)
        
        return batch_id
    
    def _compute_batch_id(self, source_files: list) -> str:
        """Compute deterministic batch ID."""
        import hashlib
        file_infos = []
        for f in sorted(source_files):
            # Use filename only for determinism across environments
            file_infos.append(f.name)
        content = "|".join(file_infos)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _is_committed(self, batch_id: str) -> bool:
        """Check if batch already committed."""
        manifest_file = self.manifest_dir / f"manifest_{batch_id}.json"
        return manifest_file.exists()
    
    def _route_all_files(self) -> dict[str, list[dict]]:
        """Route all source files to resource buffers."""
        from src.healthguard.ingestion.resource_router import ResourceRouter
        
        router = ResourceRouter()
        source_files = self.discover_source_files()
        
        for filepath in source_files:
            logger.info(f"Routing {filepath.name}")
            router.route_stream(filepath)
        
        # Extract buffers
        records_by_type = {}
        for rt in self.allowed_types:
            records_by_type[rt] = router.get_buffer(rt)
        
        summary = router.get_summary()
        logger.info(f"Routing summary: {summary}")
        
        return {rt: recs for rt, recs in records_by_type.items() if recs}
    
    def _write_bronze(self, records_by_type: dict) -> str:
        """Write records to Bronze Parquet."""
        # Write using BronzeWriter (handles manifest saving)
        source_files = self.discover_source_files()
        batch_id = self.writer.write_batch(
            source_files=source_files,
            records_by_type=records_by_type,
        )
        
        logger.info(f"Bronze ingestion complete: batch {batch_id}")
        return batch_id


def run_bronze_ingestion(
    source_dir: str = "data/raw/synthea/fhir",
    bronze_root: str = "data/lakehouse/bronze",
    manifest_dir: str = "data/manifests",
    config_path: str = "config/resource_contracts",
) -> Optional[str]:
    """Main entry point for Bronze ingestion."""
    orchestrator = BronzeOrchestrator(
        source_dir=Path(source_dir),
        bronze_root=Path(bronze_root),
        manifest_dir=Path(manifest_dir),
        config_path=Path(config_path),
    )
    return orchestrator.ingest_all()


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    
    batch_id = run_bronze_ingestion()
    if batch_id:
        print(f"Bronze ingestion complete: {batch_id}")
        sys.exit(0)
    else:
        print("No new data to ingest (already committed)")
        sys.exit(0)