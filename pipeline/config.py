"""Pipeline configuration — single source of truth for paths, constants, and schema contracts."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Root paths
# ---------------------------------------------------------------------------
REPO_ROOT: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = REPO_ROOT / "data"
WAREHOUSE_DIR: Path = REPO_ROOT / "warehouse"
REPORTS_DIR: Path = REPO_ROOT / "reports" / "pipeline"

WAREHOUSE_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Source CSVs (raw inputs — never modified by the pipeline)
RAW_HOSPITAL_CSV: Path = DATA_DIR / "hospital" / "hospital_data.csv"

# SQLite warehouse file (single-file DW; swappable to PostgreSQL via env)
WAREHOUSE_DB: Path = WAREHOUSE_DIR / "healthguard_warehouse.db"
WAREHOUSE_URI: str = os.getenv("WAREHOUSE_URI", f"sqlite:///{WAREHOUSE_DB}")

# ---------------------------------------------------------------------------
# Schema contract — the canonical column spec for the Bronze source
# ---------------------------------------------------------------------------
BRONZE_COLUMNS: list[str] = [
    "Patient_ID",
    "Age",
    "Gender",
    "Condition",
    "Procedure",
    "Cost",
    "Length_of_Stay",
    "Readmission",
    "Outcome",
    "Satisfaction",
]

BRONZE_DTYPES: dict[str, str] = {
    "Patient_ID": "int",
    "Age": "int",
    "Gender": "str",
    "Condition": "str",
    "Procedure": "str",
    "Cost": "int",
    "Length_of_Stay": "int",
    "Readmission": "str",
    "Outcome": "str",
    "Satisfaction": "int",
}

# Allowed categorical values (data contract)
ALLOWED_READMISSION: frozenset[str] = frozenset({"Yes", "No"})
ALLOWED_GENDER: frozenset[str] = frozenset({"Male", "Female", "Other"})
ALLOWED_OUTCOMES: frozenset[str] = frozenset(
    {"Recovered", "Stable", "Critical", "Deceased"}
)

# Numeric range constraints
CONSTRAINTS: dict[str, tuple[float, float]] = {
    "Age": (0, 120),
    "Cost": (0, 10_000_000),
    "Length_of_Stay": (0, 365),
    "Satisfaction": (1, 10),
}

# Age-band breakpoints (matches schema.sql and metrics.json)
AGE_BANDS: list[tuple[int, int, str]] = [
    (0, 30, "18-30"),
    (31, 45, "31-45"),
    (46, 60, "46-60"),
    (61, 75, "61-75"),
    (76, 999, "76+"),
]

# ---------------------------------------------------------------------------
# Pipeline run settings
# ---------------------------------------------------------------------------
@dataclass
class PipelineConfig:
    """Runtime configuration passed through all pipeline stages."""

    source_csv: Path = field(default_factory=lambda: RAW_HOSPITAL_CSV)
    warehouse_db: Path = field(default_factory=lambda: WAREHOUSE_DB)
    reports_dir: Path = field(default_factory=lambda: REPORTS_DIR)

    # Quality gate thresholds
    max_null_pct: float = 0.05        # fail if any column >5% null
    max_duplicate_pct: float = 0.01   # fail if >1% duplicate Patient_IDs
    min_row_count: int = 100          # fail if fewer than 100 rows survive

    # Bronze table name in warehouse
    bronze_table: str = "bronze_encounters"
    silver_table: str = "silver_encounters"

    # Gold mart table names
    gold_condition_mart: str = "gold_condition_mart"
    gold_age_band_mart: str = "gold_age_band_mart"
    gold_gender_mart: str = "gold_gender_mart"
    gold_outcome_mart: str = "gold_outcome_mart"
    gold_daily_summary: str = "gold_daily_summary"
