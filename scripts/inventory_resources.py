#!/usr/bin/env python3
"""
Synthea FHIR R4 Resource Inventory Generator

Scans NDJSON files in data/raw/synthea/fhir/, counts records per resource type,
computes SHA-256 checksums, and exports inventory.json + human-readable summary.
"""

import json
import hashlib
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone
import sys

SOURCE_DIR = Path("data/raw/synthea/fhir")
OUTPUT_JSON = Path("data/manifests/source_inventory.json")
OUTPUT_SUMMARY = Path("docs/DATA_PROVENANCE.md")

# Resource types we actively process (4 core)
CORE_RESOURCES = {"Patient", "Encounter", "Condition", "Observation"}


def compute_sha256(filepath: Path) -> str:
    """Compute SHA-256 hash of file."""
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def scan_ndjson(filepath: Path) -> tuple[int, int]:
    """Count valid JSON lines and malformed lines in NDJSON file."""
    valid = 0
    malformed = 0
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                resource = json.loads(line)
                # Validate it's a FHIR resource with resourceType
                if isinstance(resource, dict) and "resourceType" in resource:
                    valid += 1
                else:
                    malformed += 1
            except json.JSONDecodeError:
                malformed += 1
    return valid, malformed


def main():
    if not SOURCE_DIR.exists():
        print(f"ERROR: Source directory not found: {SOURCE_DIR}")
        sys.exit(1)

    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)

    ndjson_files = sorted(SOURCE_DIR.glob("*.ndjson"))
    if not ndjson_files:
        print(f"ERROR: No .ndjson files found in {SOURCE_DIR}")
        sys.exit(1)

    inventory = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_directory": str(SOURCE_DIR),
        "total_files": len(ndjson_files),
        "resources": {},
        "summary": {
            "total_records": 0,
            "total_malformed": 0,
            "total_bytes": 0,
            "core_resource_records": 0,
            "out_of_scope_resource_records": 0,
        }
    }

    print(f"Scanning {len(ndjson_files)} NDJSON files...")
    print("-" * 80)

    for filepath in ndjson_files:
        resource_type = filepath.stem
        file_size = filepath.stat().st_size
        checksum = compute_sha256(filepath)
        valid_count, malformed_count = scan_ndjson(filepath)

        is_core = resource_type in CORE_RESOURCES

        inventory["resources"][resource_type] = {
            "file": filepath.name,
            "resource_type": resource_type,
            "file_size_bytes": file_size,
            "sha256": checksum,
            "valid_records": valid_count,
            "malformed_records": malformed_count,
            "in_pipeline_scope": is_core,
        }

        inventory["summary"]["total_records"] += valid_count
        inventory["summary"]["total_malformed"] += malformed_count
        inventory["summary"]["total_bytes"] += file_size

        if is_core:
            inventory["summary"]["core_resource_records"] += valid_count
        else:
            inventory["summary"]["out_of_scope_resource_records"] += valid_count

        status = "[CORE]" if is_core else "[OUT OF SCOPE]"
        print(f"  {resource_type:30s} | {valid_count:>10,} records | {malformed_count:>6,} malformed | {file_size:>12,} bytes | {status}")

    print("-" * 80)
    print(f"  {'TOTAL':30s} | {inventory['summary']['total_records']:>10,} records | {inventory['summary']['total_malformed']:>6,} malformed | {inventory['summary']['total_bytes']:>12,} bytes")

    # Write JSON inventory
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(inventory, f, indent=2)

    # Write human-readable provenance markdown
    with open(OUTPUT_SUMMARY, "w", encoding="utf-8") as f:
        f.write("# HealthGuard 360 — Data Provenance\n\n")
        f.write(f"**Generated:** {inventory['generated_at']}\n\n")
        f.write("## Source Configuration\n\n")
        f.write("- **Generator:** MITRE Synthea\n")
        f.write("- **FHIR Version:** R4\n")
        f.write("- **Export Format:** Bulk FHIR NDJSON (`exporter.fhir.bulk_data=true`)\n")
        f.write("- **Source Directory:** `data/raw/synthea/fhir/`\n")
        f.write("- **Generation Command:** `./run_synthea -p 1000 -c healthguard.properties -s 424242 -r 20261125`\n")
        f.write("- **Synthea Version:** (record from synthea build)\n")
        f.write("- **Java Version:** Eclipse Temurin 17.0.21\n")
        f.write("- **Random Seed:** 424242\n")
        f.write("- **Reference Date:** 2026-11-25\n")
        f.write("- **Population Requested:** 1,000 patients\n")
        f.write("- **Population Generated:** 1,136 patients (136 deceased)\n\n")

        f.write("## Resource Inventory\n\n")
        f.write("| Resource Type | Records | Malformed | Size (MB) | In Scope |\n")
        f.write("|---------------|---------|-----------|-----------|----------|\n")

        for rt, info in sorted(inventory["resources"].items()):
            size_mb = info["file_size_bytes"] / (1024 * 1024)
            scope = "✅ CORE" if info["in_pipeline_scope"] else "⏭️ OUT OF SCOPE"
            f.write(f"| {rt} | {info['valid_records']:,} | {info['malformed_records']:,} | {size_mb:.2f} | {scope} |\n")

        f.write(f"\n**Total Records:** {inventory['summary']['total_records']:,}\n")
        f.write(f"**Total Malformed:** {inventory['summary']['total_malformed']:,}\n")
        f.write(f"**Core Pipeline Records:** {inventory['summary']['core_resource_records']:,}\n")
        f.write(f"**Out of Scope Records:** {inventory['summary']['out_of_scope_resource_records']:,}\n")
        f.write(f"**Total Source Size:** {inventory['summary']['total_bytes'] / (1024**3):.2f} GB\n\n")

        f.write("## Synthetic Data Disclaimer\n\n")
        f.write("> **IMPORTANT:** This data is **synthetic**, generated by MITRE Synthea for testing and development purposes. "
                "It does not represent real patients, real clinical events, or real healthcare outcomes. "
                "Any analysis, modeling, or conclusions drawn from this data are purely illustrative and "
                "must not be interpreted as clinically valid or representative of real populations.\n\n")

        f.write("## Pipeline Scope\n\n")
        f.write("The HealthGuard 360 pipeline processes **four core FHIR resource types**:\n\n")
        f.write("1. **Patient** — Demographics, identifiers, contacts\n")
        f.write("2. **Encounter** — Healthcare encounters (inpatient, outpatient, emergency)\n")
        f.write("3. **Condition** — Diagnoses, problems, clinical status\n")
        f.write("4. **Observation** — Vital signs, lab results, measurements\n\n")
        f.write(f"All other resource types ({inventory['summary']['out_of_scope_resource_records']:,} records) are counted, "
                "checksummed, and explicitly classified as **out of scope** for this pipeline version.\n\n")

        f.write("## File Checksums\n\n")
        f.write("| Resource | SHA-256 |\n")
        f.write("|----------|---------|\n")
        for rt, info in sorted(inventory["resources"].items()):
            f.write(f"| {rt} | `{info['sha256']}` |\n")

    print(f"\n[OK] Inventory written to {OUTPUT_JSON}")
    print(f"[OK] Provenance written to {OUTPUT_SUMMARY}")


if __name__ == "__main__":
    main()