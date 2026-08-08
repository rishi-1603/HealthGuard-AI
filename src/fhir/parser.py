"""Small FHIR R4-shaped resource helpers for the portfolio prototype."""
from typing import Any

def resources_by_type(bundle: dict[str, Any], resource_type: str) -> list[dict[str, Any]]:
    return [e["resource"] for e in bundle.get("entry", []) if e.get("resource", {}).get("resourceType") == resource_type]

def patient_ref(resource: dict[str, Any]) -> str | None:
    return (resource.get("subject") or {}).get("reference") or resource.get("id")

def normalize_bundle(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return [e["resource"] for e in bundle.get("entry", []) if "resource" in e]
