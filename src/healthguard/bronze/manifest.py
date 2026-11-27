"""
Bronze Manifest — Ingestion manifest handling.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class IngestionManifest:
    """Immutable manifest recording a Bronze ingestion batch."""
    batch_id: str
    source_system: str
    source_format: str
    status: str  # COMMITTED, FAILED, PENDING
    source_files: list[dict]  # [{"path": str, "sha256": str, "size_bytes": int, "records": int}]
    resource_counts: dict[str, int]
    total_records: int
    started_at: str
    completed_at: Optional[str] = None
    code_version: Optional[str] = None
    config_hash: Optional[str] = None


def save_manifest(manifest: IngestionManifest, manifest_dir: Path) -> Path:
    """Save manifest as JSON file."""
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_file = manifest_dir / f"manifest_{manifest.batch_id}.json"
    
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(asdict(manifest), f, indent=2)
    
    logger.info(f"Saved manifest: {manifest_file}")
    return manifest_file


def load_manifest(manifest_dir: Path, batch_id: str) -> Optional[IngestionManifest]:
    """Load manifest from JSON file."""
    manifest_file = manifest_dir / f"manifest_{batch_id}.json"
    if not manifest_file.exists():
        return None
    
    with open(manifest_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return IngestionManifest(**data)


def is_batch_committed(manifest_dir: Path, batch_id: str) -> bool:
    """Check if a batch was already successfully committed."""
    manifest = load_manifest(manifest_dir, batch_id)
    return manifest is not None and manifest.status == "COMMITTED"


def list_committed_batches(manifest_dir: Path) -> list[str]:
    """List all committed batch IDs."""
    if not manifest_dir.exists():
        return []
    
    batches = []
    for f in manifest_dir.glob("manifest_*.json"):
        batch_id = f.stem.replace("manifest_", "")
        manifest = load_manifest(manifest_dir, batch_id)
        if manifest and manifest.status == "COMMITTED":
            batches.append(batch_id)
    return sorted(batches)