"""
Batch Manager — Deterministic batch IDs, SHA-256 checksums, and ingestion manifests.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionManifest:
    """Immutable manifest recording a Bronze ingestion batch."""
    batch_id: str
    source_system: str
    source_format: str  # FHIR_R4_NDJSON
    status: str  # COMMITTED, FAILED, PENDING
    source_files: list[dict]  # [{"path": str, "sha256": str, "size_bytes": int, "records": int}]
    resource_counts: dict[str, int]  # {"Patient": 1136, "Encounter": 64096, ...}
    total_records: int
    started_at: str
    completed_at: Optional[str] = None
    code_version: Optional[str] = None
    config_hash: Optional[str] = None


def compute_sha256(filepath: Path) -> str:
    """Compute hex SHA-256 digest of input file."""
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def compute_config_hash(config_path: Path) -> str:
    """Compute hash of configuration directory (all YAML files) for reproducibility."""
    if config_path.is_file():
        return compute_sha256(config_path)
    
    # Hash all YAML files in directory for deterministic config hash
    yaml_files = sorted(config_path.glob("*.yaml"))
    if not yaml_files:
        return ""
    
    sha = hashlib.sha256()
    for f in yaml_files:
        with open(f, "rb") as fp:
            for chunk in iter(lambda: fp.read(65536), b""):
                sha.update(chunk)
    return sha.hexdigest()


def compute_batch_id(
    source_files: list[Path],
    config_hash: str,
) -> str:
    """
    Compute deterministic batch ID from source file checksums + config hash.
    
    Same inputs always produce same batch_id, enabling idempotent re-runs.
    """
    # Sort files for deterministic ordering
    file_infos = []
    for f in sorted(source_files):
        if f.exists():
            sha = compute_sha256(f)
            size = f.stat().st_size
            file_infos.append(f"{f.name}:{sha}:{size}")
    
    content = "|".join(file_infos) + "|" + config_hash
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def build_manifest(
    batch_id: str,
    source_files: list[Path],
    resource_counts: dict[str, int],
    config_hash: str,
    source_system: str = "SYNTHEA_FHIR",
    source_format: str = "FHIR_R4_NDJSON",
) -> IngestionManifest:
    """Build ingestion manifest from batch metadata."""
    
    file_metadata = []
    for f in source_files:
        if f.exists():
            file_metadata.append({
                "path": str(f),
                "sha256": compute_sha256(f),
                "size_bytes": f.stat().st_size,
                "resource_type": f.stem,
            })
    
    return IngestionManifest(
        batch_id=batch_id,
        source_system=source_system,
        source_format=source_format,
        status="COMMITTED",
        source_files=file_metadata,
        resource_counts=resource_counts,
        total_records=sum(resource_counts.values()),
        started_at=datetime.now(timezone.utc).isoformat(),
        config_hash=config_hash,
    )


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