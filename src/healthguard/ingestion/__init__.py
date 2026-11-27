"""
HealthGuard Ingestion Layer - NDJSON Streaming and Validation
"""

from src.healthguard.ingestion.ndjson_reader import read_ndjson_stream, NDJSONRecord, count_ndjson_records
from src.healthguard.ingestion.resource_router import ResourceRouter, CORE_RESOURCE_TYPES, route_ndjson_file
from src.healthguard.ingestion.batch_manager import (
    IngestionManifest, compute_batch_id, build_manifest, save_manifest, 
    is_batch_committed, compute_config_hash
)
from src.healthguard.ingestion.source_validator import (
    ResourceContract, load_contract, validate_resource, normalize_resource
)
from src.healthguard.ingestion.resource_router import ResourceRouter

__all__ = [
    "read_ndjson_stream",
    "NDJSONRecord",
    "count_ndjson_records",
    "ResourceRouter",
    "CORE_RESOURCE_TYPES",
    "route_ndjson_file",
    "IngestionManifest",
    "compute_batch_id",
    "build_manifest",
    "save_manifest",
    "is_batch_committed",
    "compute_config_hash",
    "ResourceContract",
    "load_contract",
    "validate_resource",
    "normalize_resource",
]