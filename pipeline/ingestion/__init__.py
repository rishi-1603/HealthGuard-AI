"""Multi-source ingestion package."""

from pipeline.ingestion.fhir_parser import (
    FHIRBundleParser,
    normalize_source_id,
    ParsedFHIRDataset,
)
from pipeline.ingestion.multi_source import (
    MultiSourceIngestor,
    IngestionManifest,
    compute_file_sha256,
)

__all__ = [
    "FHIRBundleParser",
    "normalize_source_id",
    "ParsedFHIRDataset",
    "MultiSourceIngestor",
    "IngestionManifest",
    "compute_file_sha256",
]
