"""
Resource Router — Routes FHIR resources to resource-specific handlers.
"""

import logging
from typing import Iterator
from pathlib import Path
from collections import defaultdict

from src.healthguard.ingestion.ndjson_reader import read_ndjson_stream, NDJSONRecord
from src.healthguard.config.resource_contracts import load_contract

logger = logging.getLogger(__name__)


# Core resource types we process
CORE_RESOURCE_TYPES = {"Patient", "Encounter", "Condition", "Observation"}


class ResourceRouter:
    """
    Routes FHIR resources to resource-specific output buffers.
    
    Separates core resources (processed) from out-of-scope (counted only).
    """
    
    def __init__(
        self,
        allowed_types: Optional[set[str]] = None,
        buffer_size: int = 10000,
    ):
        self.allowed_types = allowed_types or CORE_RESOURCE_TYPES
        self.buffer_size = buffer_size
        
        # In-memory buffers per resource type (flushed to Parquet when full)
        self.buffers: dict[str, list[dict]] = defaultdict(list)
        
        # Statistics
        self.counts: dict[str, int] = defaultdict(int)
        self.out_of_scope_counts: dict[str, int] = defaultdict(int)
        self.invalid_counts: int = 0
    
    def route_record(self, record: NDJSONRecord) -> None:
        """Route a single record to appropriate buffer."""
        
        if record.parse_status != "VALID":
            self.invalid_counts += 1
            return
        
        resource_type = record.resource_type
        
        if resource_type in self.allowed_types:
            # Prepare record for Bronze storage
            bronze_record = {
                "batch_id": "",  # Filled in later
                "source_system": "SYNTHEA_FHIR",
                "source_file": "",  # Filled in later
                "source_line": record.line_number,
                "resource_type": resource_type,
                "resource_id": record.resource_id,
                "resource_version": record.resource.get("meta", {}).get("versionId"),
                "source_last_updated": record.resource.get("meta", {}).get("lastUpdated"),
                "ingested_at": "",  # Filled in later
                "raw_payload": record.raw_line,
                "parse_status": record.parse_status,
            }
            self.buffers[resource_type].append(bronze_record)
            self.counts[resource_type] += 1
        else:
            # Out of scope but tracked
            self.out_of_scope_counts[resource_type] += 1
    
    def route_stream(
        self,
        filepath: Path,
        max_records: Optional[int] = None,
    ) -> dict[str, int]:
        """Route all records from an NDJSON file."""
        
        for record in read_ndjson_stream(
            filepath,
            max_records=max_records,
            allowed_resource_types=self.allowed_types | set(self.out_of_scope_counts.keys()),
        ):
            self.route_record(record)
        
        return dict(self.counts)
    
    def get_buffer(self, resource_type: str) -> list[dict]:
        """Get buffer for a resource type."""
        return self.buffers.get(resource_type, [])
    
    def clear_buffer(self, resource_type: str) -> None:
        """Clear buffer after flush."""
        if resource_type in self.buffers:
            self.buffers[resource_type].clear()
    
    def get_summary(self) -> dict:
        """Get routing summary."""
        return {
            "core_counts": dict(self.counts),
            "out_of_scope_counts": dict(self.out_of_scope_counts),
            "invalid_count": self.invalid_counts,
            "total_core": sum(self.counts.values()),
            "total_out_of_scope": sum(self.out_of_scope_counts.values()),
        }


def route_ndjson_file(
    filepath: Path,
    allowed_types: Optional[set[str]] = None,
    max_records: Optional[int] = None,
) -> dict[str, int]:
    """Convenience function to route entire file."""
    router = ResourceRouter(allowed_types)
    return router.route_stream(filepath, max_records)