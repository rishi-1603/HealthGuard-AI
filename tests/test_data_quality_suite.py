"""Unit and integration tests for Day 5 (DE-005): Automated Data Quality Suite & Quarantine Engine.

Tests cover:
- Rule-based clinical quality validations: ranges, nulls, categoricals, referential consistency.
- Row-level quarantine routing: corrupt or boundary-violating records diverted to silver_quarantine.
- Clean pipeline continuation: valid records continue to silver_encounters without pipeline crash.
- Automated Scorecard generation: JSON and Markdown scorecards with 4 core quality pillars.
- Quarantined record inspection and recovery / reprocessing test.
"""

from __future__ import annotations

import json
from pathlib import Path
import pandas as pd
import pytest

from pipeline.config import PipelineConfig, RAW_HOSPITAL_CSV
from pipeline.bronze.ingestor import load_bronze
from pipeline.warehouse import apply_ddl, managed_connection
from pipeline.data_quality.rules import (
    ClinicalRuleSuite,
    RuleValidationResult,
    evaluate_record_quality,
)
from pipeline.data_quality.quarantine import (
    QuarantineEngine,
    QuarantineBatchResult,
)
from pipeline.data_quality.scorecard import (
    DataQualityScorecard,
    generate_scorecard,
)


@pytest.fixture(scope="module")
def base_warehouse(tmp_path_factory) -> tuple[PipelineConfig, pd.DataFrame]:
    """Setup a populated Bronze test warehouse."""
    tmp = tmp_path_factory.mktemp("dq_test")
    cfg = PipelineConfig(
        warehouse_db=tmp / "test_warehouse.db",
        source_csv=RAW_HOSPITAL_CSV,
        reports_dir=tmp / "reports",
    )
    apply_ddl(cfg)
    load_bronze(cfg)
    
    with managed_connection(cfg.warehouse_db) as conn:
        df = pd.read_sql_query("SELECT * FROM bronze_encounters", conn)
    return cfg, df


# ---------------------------------------------------------------------------
# 1. Clinical Rule Suite Tests
# ---------------------------------------------------------------------------
class TestClinicalRuleSuite:
    def test_clean_record_passes_all_rules(self):
        clean_record = {
            "Patient_ID": 101,
            "Age": 45,
            "Gender": "Female",
            "Condition": "Diabetes",
            "Procedure": "Insulin Therapy",
            "Cost": 1500,
            "Length_of_Stay": 4,
            "Readmission": "No",
            "Outcome": "Stable",
            "Satisfaction": 8,
        }
        res: RuleValidationResult = evaluate_record_quality(clean_record)
        assert res.is_valid is True
        assert len(res.violations) == 0

    def test_negative_cost_fails_rule(self):
        corrupt_record = {
            "Patient_ID": 102,
            "Age": 50,
            "Gender": "Male",
            "Condition": "Hypertension",
            "Procedure": "Checkup",
            "Cost": -500,  # Invalid
            "Length_of_Stay": 2,
            "Readmission": "No",
            "Outcome": "Stable",
            "Satisfaction": 5,
        }
        res = evaluate_record_quality(corrupt_record)
        assert res.is_valid is False
        assert any("Cost" in v.rule_name for v in res.violations)
        assert res.violations[0].severity == "CRITICAL"

    def test_impossible_age_fails_rule(self):
        corrupt_record = {
            "Patient_ID": 103,
            "Age": 165,  # Impossible human age
            "Gender": "Male",
            "Condition": "Asthma",
            "Procedure": "Inhaler",
            "Cost": 200,
            "Length_of_Stay": 1,
            "Readmission": "No",
            "Outcome": "Recovered",
            "Satisfaction": 9,
        }
        res = evaluate_record_quality(corrupt_record)
        assert res.is_valid is False
        assert any("Age" in v.rule_name for v in res.violations)

    def test_invalid_readmission_categorical(self):
        corrupt_record = {
            "Patient_ID": 104,
            "Age": 30,
            "Gender": "Female",
            "Condition": "Asthma",
            "Procedure": "Checkup",
            "Cost": 300,
            "Length_of_Stay": 1,
            "Readmission": "Maybe",  # Invalid enum
            "Outcome": "Recovered",
            "Satisfaction": 9,
        }
        res = evaluate_record_quality(corrupt_record)
        assert res.is_valid is False
        assert any("Readmission" in v.rule_name for v in res.violations)


# ---------------------------------------------------------------------------
# 2. Quarantine Routing & Warehouse Diversion Tests
# ---------------------------------------------------------------------------
class TestQuarantineRouting:
    def test_quarantine_diverts_corrupted_rows(self, base_warehouse):
        cfg, df_bronze = base_warehouse
        
        # Inject corrupted records into test batch
        corrupt_df = df_bronze.head(20).copy()
        corrupt_df.loc[0, "Cost"] = -9999          # Corrupt cost
        corrupt_df.loc[1, "Age"] = 250             # Corrupt age
        corrupt_df.loc[2, "Readmission"] = "UNKNOWN" # Corrupt categorical
        
        engine = QuarantineEngine(cfg)
        result: QuarantineBatchResult = engine.process_and_quarantine(corrupt_df)
        
        assert result.total_records == 20
        assert result.quarantined_count == 3
        assert result.valid_count == 17
        
        # Verify valid rows written to silver_encounters
        with managed_connection(cfg.warehouse_db) as conn:
            valid_db = pd.read_sql_query("SELECT * FROM silver_encounters WHERE patient_id IN (1, 2, 3)", conn)
            quarantined_db = pd.read_sql_query("SELECT * FROM silver_quarantine", conn)
            
        assert len(valid_db) == 0  # Corrupt IDs not in silver
        assert len(quarantined_db) >= 3
        assert set(quarantined_db["patient_id"].astype(int)).issuperset({1, 2, 3})

    def test_quarantine_reasons_logged_in_table(self, base_warehouse):
        cfg, _ = base_warehouse
        with managed_connection(cfg.warehouse_db) as conn:
            df_q = pd.read_sql_query("SELECT * FROM silver_quarantine WHERE patient_id = 1", conn)
            
        assert len(df_q) > 0
        assert "Cost" in df_q["quarantine_reason"].iloc[0]
        assert df_q["severity"].iloc[0] == "CRITICAL"


# ---------------------------------------------------------------------------
# 3. Scorecard & Quality Telemetry Tests
# ---------------------------------------------------------------------------
class TestDataQualityScorecard:
    def test_generate_scorecard_metrics(self, base_warehouse):
        cfg, df_bronze = base_warehouse
        engine = QuarantineEngine(cfg)
        batch_res = engine.process_and_quarantine(df_bronze.head(100))
        
        scorecard: DataQualityScorecard = generate_scorecard(batch_res, cfg)
        
        assert 0.0 <= scorecard.overall_trust_score <= 100.0
        assert 0.0 <= scorecard.validity_score <= 100.0
        assert 0.0 <= scorecard.completeness_score <= 100.0
        assert 0.0 <= scorecard.uniqueness_score <= 100.0
        
        # Verify JSON report file was generated
        json_path = cfg.reports_dir / "scorecards" / f"dq_scorecard_{scorecard.batch_id}.json"
        md_path = cfg.reports_dir / "scorecards" / f"dq_scorecard_{scorecard.batch_id}.md"
        assert json_path.exists()
        assert md_path.exists()
        
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert "overall_trust_score" in data
            assert "pillar_scores" in data
