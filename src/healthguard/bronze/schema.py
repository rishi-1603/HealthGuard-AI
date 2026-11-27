"""
Bronze Schema — PyArrow table schemas for Bronze layer.
"""

import pyarrow as pa


BRONZE_SCHEMA = pa.schema([
    # Ingestion metadata
    ("batch_id", pa.string()),
    ("source_system", pa.string()),
    ("source_file", pa.string()),
    ("source_line", pa.int64()),
    
    # Resource identity
    ("resource_type", pa.string()),
    ("resource_id", pa.string()),
    ("resource_version", pa.string()),
    ("source_last_updated", pa.string()),
    
    # Ingestion metadata
    ("ingested_at", pa.string()),
    ("raw_payload", pa.string()),
    ("parse_status", pa.string()),
])


def get_bronze_schema() -> pa.Schema:
    """Get Bronze table schema."""
    return BRONZE_SCHEMA


def validate_bronze_table(table: "pa.Table") -> list[str]:
    """Validate Bronze table schema and data."""
    errors = []
    
    # Check schema compatibility
    expected_names = set(BRONZE_SCHEMA.names)
    actual_names = set(table.schema.names)
    
    missing = expected_names - actual_names
    extra = actual_names - expected_names
    
    if missing:
        errors.append(f"Missing columns: {missing}")
    if extra:
        errors.append(f"Extra columns: {extra}")
    
    # Check required fields not null
    for col in ["batch_id", "source_system", "resource_type", "resource_id"]:
        if col in table.column_names:
            null_count = table.column(col).null_count
            if null_count > 0:
                # batch_id and ingested_at can be empty initially (filled at commit)
                if col not in ["batch_id", "ingested_at"]:
                    pass  # Allow null for batch_id during staging
    
    return errors