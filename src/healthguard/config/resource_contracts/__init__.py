"""
HealthGuard Resource Contracts - YAML contract loading
"""

# Import from source_validator directly to avoid circular import with resource_router
# The actual load_contract/ResourceContract are defined in source_validator.py
# and re-exported here for convenience
from src.healthguard.ingestion.source_validator import (
    ResourceContract, load_contract, validate_resource, normalize_resource
)

__all__ = [
    "ResourceContract",
    "load_contract",
    "validate_resource",
    "normalize_resource",
]