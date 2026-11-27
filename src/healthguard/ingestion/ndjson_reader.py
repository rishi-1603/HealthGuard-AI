"""
Streaming NDJSON Reader for FHIR R4 Bulk Data Export.

Reads NDJSON files line-by-line with bounded memory, validates JSON,
and yields parsed resources with metadata.
"""

import json
import logging
from pathlib import Path
from typing import Iterator, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class NDJSONRecord:
    """Parsed NDJSON record with metadata."""
    line_number: int
    raw_line: str
    resource: Optional[dict] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    parse_status: str = "VALID"  # VALID, INVALID_JSON, MISSING_RESOURCE_TYPE
    error_message: Optional[str] = None


def read_ndjson_stream(
    filepath: Path,
    max_records: Optional[int] = None,
    allowed_resource_types: Optional[set[str]] = None,
) -> Iterator[NDJSONRecord]:
    """
    Stream NDJSON file line-by-line with bounded memory.
    
    Args:
        filepath: Path to .ndjson file
        max_records: Optional limit for testing
        allowed_resource_types: If set, only yield these resource types
        
    Yields:
        NDJSONRecord with parsed resource and metadata
    """
    if not filepath.exists():
        raise FileNotFoundError(f"NDJSON file not found: {filepath}")
    
    logger.info(f"Streaming NDJSON: {filepath}")
    records_yielded = 0
    
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            
            # Parse JSON
            try:
                resource = json.loads(line)
            except json.JSONDecodeError as e:
                yield NDJSONRecord(
                    line_number=line_num,
                    raw_line=line[:500],  # Truncate for storage
                    parse_status="INVALID_JSON",
                    error_message=str(e),
                )
                continue
            
            # Validate resource structure
            resource_type = resource.get("resourceType")
            resource_id = resource.get("id")
            
            if not resource_type:
                yield NDJSONRecord(
                    line_number=line_num,
                    raw_line=line[:500],
                    resource=resource,
                    parse_status="MISSING_RESOURCE_TYPE",
                    error_message="Missing required 'resourceType' field",
                )
                continue
            
            # Filter by allowed types if specified
            if allowed_resource_types and resource_type not in allowed_resource_types:
                continue
            
            yield NDJSONRecord(
                line_number=line_num,
                raw_line=line[:500],
                resource=resource,
                resource_type=resource_type,
                resource_id=resource_id,
                parse_status="VALID",
            )
            
            records_yielded += 1
            if max_records and records_yielded >= max_records:
                break
    
    logger.info(f"Streamed {records_yielded} valid records from {filepath}")


def count_ndjson_records(filepath: Path) -> tuple[int, int]:
    """Count valid and invalid records in NDJSON file without loading all."""
    valid = 0
    invalid = 0
    
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                resource = json.loads(line)
                if isinstance(resource, dict) and resource.get("resourceType"):
                    valid += 1
                else:
                    invalid += 1
            except json.JSONDecodeError:
                invalid += 1
    
    return valid, invalid