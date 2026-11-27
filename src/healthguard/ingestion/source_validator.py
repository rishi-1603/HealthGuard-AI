"""
Source Validator — Validates FHIR resources against YAML contracts.
"""

import yaml
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of resource validation."""
    is_valid: bool
    errors: list[str]
    warnings: list[str]


class ResourceContract:
    """Parsed resource contract from YAML."""
    
    def __init__(self, contract_path: Path):
        with open(contract_path, "r", encoding="utf-8") as f:
            self.contract = yaml.safe_load(f)
        
        self.resource_type = self.contract["resource_type"]
        self.fields = self.contract.get("fields", [])
        self.validation = self.contract.get("validation", {})
        self.quarantine_policy = self.contract.get("quarantine_policy", {})
        self.normalization = self.contract.get("normalization", [])
        self.reference_resolution = self.contract.get("reference_resolution", {})
    
    def get_required_fields(self) -> list[str]:
        """Get list of required field names (target names)."""
        return [
            f["target"] for f in self.fields 
            if f.get("required", False)
        ]
    
    def get_field_spec(self, target_name: str) -> Optional[dict]:
        """Get field specification by target name."""
        for f in self.fields:
            if f["target"] == target_name:
                return f
        return None
    
    def get_enum_values(self, target_name: str) -> Optional[list]:
        """Get allowed enum values for a field."""
        spec = self.get_field_spec(target_name)
        if spec and "enum" in spec:
            return spec["enum"]
        return None


# Contract cache
_contract_cache: dict[str, ResourceContract] = {}


def load_contract(resource_type: str) -> ResourceContract:
    """Load and cache resource contract."""
    if resource_type in _contract_cache:
        return _contract_cache[resource_type]
    
    contract_path = Path(f"config/resource_contracts/{resource_type.lower()}.yaml")
    if not contract_path.exists():
        raise FileNotFoundError(f"Contract not found: {contract_path}")
    
    contract = ResourceContract(contract_path)
    _contract_cache[resource_type] = contract
    return contract


def validate_resource(
    resource: dict,
    resource_type: str,
) -> ValidationResult:
    """
    Validate a FHIR resource against its contract.
    
    Returns ValidationResult with errors and warnings.
    """
    contract = load_contract(resource_type)
    errors = []
    warnings = []
    
    # Check required fields
    required = contract.get_required_fields()
    for field in required:
        if field not in resource or resource[field] is None:
            errors.append(f"Missing required field: {field}")
    
    # Validate enum fields
    for field in contract.fields:
        target = field["target"]
        enum_values = field.get("enum")
        if enum_values and target in resource:
            value = resource[target]
            if value not in enum_values:
                warnings.append(f"Field '{target}' value '{value}' not in allowed enum: {enum_values}")
    
    # Validate reference formats
    ref_resolution = load_contract(resource_type).reference_resolution
    for ref_field, ref_spec in ref_resolution.items():
        if ref_field in resource and resource[ref_field]:
            ref = resource[ref_field]
            if isinstance(ref, dict) and "reference" in ref:
                ref_str = ref["reference"]
                expected_type = ref_spec.get("target_resource")
                if expected_type and not ref_str.startswith(f"{expected_type}/"):
                    errors.append(f"Invalid reference type for {ref_field}: expected {expected_type}/...")
    
    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


def normalize_resource(resource: dict, resource_type: str) -> dict:
    """Apply normalization rules from contract."""
    contract = load_contract(resource_type)
    normalized = resource.copy()
    
    for norm in contract.normalization:
        field = norm.get("field")
        if field not in normalized:
            continue
        
        value = normalized[field]
        if value is None:
            continue
        
        # Enum mapping
        if "mapping" in norm and value in norm["mapping"]:
            normalized[field] = norm["mapping"][value]
        
        # Format coercion (basic)
        if "format" in norm:
            # In production, use proper date parsing
            pass
    
    return normalized