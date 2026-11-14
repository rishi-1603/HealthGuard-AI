"""Multi-source ingestion orchestrator and Bronze Parquet landing engine.

Coordinates batch file ingestion from legacy CSV and Synthea FHIR R4 sources,
computes cryptographic SHA-256 batch checksums, and records immutable manifests.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from pipeline.ingestion.fhir_parser import FHIRBundleParser, ParsedFHIRDataset

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionManifest:
    """Metadata manifest recording a Bronze ingestion batch."""
    source_name: str
    source_path: str
    destination_dir: str
    sha256_checksum: str
    records_ingested: int
    tables_generated: list[str]
    ingested_at: str
    status: str


def compute_file_sha256(path: Path | str) -> str:
    """Compute hex SHA-256 digest of input file."""
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()


class MultiSourceIngestor:
    """Ingestion engine landing heterogeneous healthcare sources into Bronze Parquet."""

    def __init__(self, bronze_dir: Path | str) -> None:
        self.bronze_dir = Path(bronze_dir)
        self.bronze_dir.mkdir(parents=True, exist_ok=True)
        self.manifests_dir = self.bronze_dir / "manifests"
        self.manifests_dir.mkdir(parents=True, exist_ok=True)

    def ingest_fhir(
        self,
        bundle_path: Path | str,
        max_entries: int | None = None,
        source_tag: str = "SYNTHEA_FHIR",
    ) -> IngestionManifest:
        """Parse FHIR bundle and land tables into Bronze Parquet."""
        path = Path(bundle_path)
        checksum = compute_file_sha256(path)
        ingested_at = datetime.now(timezone.utc).isoformat()

        parser = FHIRBundleParser(path, source_tag=source_tag)
        dataset: ParsedFHIRDataset = parser.parse(max_entries=max_entries)

        tables_written: list[str] = []
        total_records = 0

        entity_map = {
            "fhir_patients.parquet": dataset.patients,
            "fhir_encounters.parquet": dataset.encounters,
            "fhir_conditions.parquet": dataset.conditions,
            "fhir_observations.parquet": dataset.observations,
        }

        for filename, df in entity_map.items():
            out_file = self.bronze_dir / filename
            table = pa.Table.from_pandas(df, preserve_index=False)
            pq.write_table(table, str(out_file))
            tables_written.append(filename)
            total_records += len(df)

        manifest = IngestionManifest(
            source_name=source_tag,
            source_path=str(path),
            destination_dir=str(self.bronze_dir),
            sha256_checksum=checksum,
            records_ingested=total_records,
            tables_generated=tables_written,
            ingested_at=ingested_at,
            status="SUCCESS",
        )

        manifest_file = self.manifests_dir / f"manifest_{source_tag}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(asdict(manifest), f, indent=2)

        logger.info(f"Ingested {total_records} FHIR records into Bronze Parquet at {self.bronze_dir}")
        return manifest
