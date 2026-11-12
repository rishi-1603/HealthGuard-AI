#!/usr/bin/env python
"""CLI entry point — run the full HealthGuard AI data pipeline.

Usage:
    python scripts/run_pipeline.py          # normal run
    python scripts/run_pipeline.py --verbose  # debug logging
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.orchestrator import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(
        description="HealthGuard AI — Data Engineering Pipeline"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable DEBUG logging"
    )
    args = parser.parse_args()

    try:
        result = run_pipeline(verbose=args.verbose)
        print("\n[OK] Pipeline completed successfully")
        print(f"    Bronze rows : {result['bronze']['rows_loaded']}")
        print(f"    Silver rows : {result['silver']['rows_written']}")
        print(f"    Gold marts  : {len(result['gold'])} tables populated")
        print(f"    Manifest    : {result.get('manifest_path', 'n/a')}\n")
        sys.exit(0)
    except Exception as exc:
        print(f"\n[FAIL] Pipeline failed: {exc}\n", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
