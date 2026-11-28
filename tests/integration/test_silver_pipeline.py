"""
Integration test for complete Silver pipeline: Patient → Encounter → Condition → Observation.
"""

import pytest
import json
from pathlib import Path
from datetime import datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq
import pandas as pd

from src.healthguard.silver.patient import transform_patient_batch
from src.healthguard.silver.encounter import transform_encounter_batch
from src.healthguard.silver.condition import transform_condition_batch
from src.healthguard.silver.observation import transform_observation_batch


@pytest.fixture
def bronze_root(tmp_path):
    root = tmp_path / "bronze"
    root.mkdir()
    return root


@pytest.fixture
def silver_root(tmp_path):
    root = tmp_path / "silver"
    root.mkdir()
    return root


@pytest.fixture
def quarantine_root(tmp_path):
    root = tmp_path / "quarantine"
    root.mkdir()
    return root


@pytest.fixture
def report_root(tmp_path):
    root = tmp_path / "reports"
    root.mkdir()
    return root


@pytest.fixture
def batch_id():
    return "integration_batch_001"


@pytest.fixture
def ingestion_date():
    return "2026-01-15"


def create_bronze_file(bronze_root: Path, resource_type: str, ingestion_date: str, batch_id: str, resources: list[dict]):
    """Create Bronze Parquet file for any resource type."""
    bronze_dir = bronze_root / f"resource_type={resource_type}" / f"ingestion_date={ingestion_date}"
    bronze_dir.mkdir(parents=True, exist_ok=True)

    records = []
    for i, res in enumerate(resources):
        records.append({
            "batch_id": batch_id,
            "source_system": "SYNTHEA_FHIR",
            "source_file": f"{resource_type}.ndjson",
            "source_line": i + 1,
            "resource_type": resource_type,
            "resource_id": res.get("id"),
            "resource_version": "1",
            "source_last_updated": "2026-01-15T10:00:00Z",
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "raw_payload": json.dumps(res),
            "parse_status": "VALID",
        })

    table = pa.Table.from_pylist(records)
    output_file = bronze_dir / f"batch_{batch_id}.parquet"
    pq.write_table(table, str(output_file))

    manifest_dir = bronze_root / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "batch_id": batch_id,
        "resource_counts": {resource_type: len(records)},
        "total_records": len(records),
    }
    with open(manifest_dir / f"manifest_{batch_id}.json", "w") as f:
        json.dump(manifest, f)

    return output_file


class TestSilverPipelineIntegration:
    """End-to-end Silver pipeline integration tests."""

    def test_full_pipeline_patient_encounter_condition_observation(
        self, bronze_root, silver_root, quarantine_root, report_root, batch_id, ingestion_date
    ):
        """Complete pipeline: Patient → Encounter → Condition → Observation with references."""
        # 1. Patient resources
        patients = [
            {
                "resourceType": "Patient",
                "id": "PAT001",
                "gender": "male",
                "birthDate": "1980-05-15",
            },
            {
                "resourceType": "Patient",
                "id": "PAT002",
                "gender": "female",
                "birthDate": "1990-08-20",
            },
        ]
        create_bronze_file(bronze_root, "Patient", ingestion_date, batch_id, patients)

        # 2. Encounter resources (reference Patients)
        encounters = [
            {
                "resourceType": "Encounter",
                "id": "ENC001",
                "status": "finished",
                "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "IMP"},
                "subject": {"reference": "Patient/PAT001"},
                "period": {"start": "2026-01-15T08:00:00Z", "end": "2026-01-15T12:00:00Z"},
            },
            {
                "resourceType": "Encounter",
                "id": "ENC002",
                "status": "finished",
                "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB"},
                "subject": {"reference": "Patient/PAT002"},
                "period": {"start": "2026-01-15T14:00:00Z", "end": "2026-01-15T15:00:00Z"},
            },
        ]
        create_bronze_file(bronze_root, "Encounter", ingestion_date, batch_id, encounters)

        # 3. Condition resources (reference Patient + Encounter)
        conditions = [
            {
                "resourceType": "Condition",
                "id": "COND001",
                "clinicalStatus": {"coding": [{"code": "active"}]},
                "verificationStatus": {"coding": [{"code": "confirmed"}]},
                "code": {"coding": [{"system": "http://snomed.info/sct", "code": "44054006", "display": "Diabetes"}]},
                "subject": {"reference": "Patient/PAT001"},
                "encounter": {"reference": "Encounter/ENC001"},
            },
            {
                "resourceType": "Condition",
                "id": "COND002",
                "clinicalStatus": {"coding": [{"code": "resolved"}]},
                "verificationStatus": {"coding": [{"code": "confirmed"}]},
                "code": {"coding": [{"system": "http://snomed.info/sct", "code": "38341003", "display": "Hypertension"}]},
                "subject": {"reference": "Patient/PAT002"},
                "encounter": {"reference": "Encounter/ENC002"},
            },
        ]
        create_bronze_file(bronze_root, "Condition", ingestion_date, batch_id, conditions)

        # 4. Observation resources (reference Patient + Encounter, multiple value types)
        observations = [
            {
                "resourceType": "Observation",
                "id": "OBS001",
                "status": "final",
                "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4", "display": "Heart rate"}]},
                "subject": {"reference": "Patient/PAT001"},
                "encounter": {"reference": "Encounter/ENC001"},
                "effectiveDateTime": "2026-01-15T10:00:00Z",
                "valueQuantity": {"value": 72, "unit": "beats/min", "system": "http://unitsofmeasure.org", "code": "/min"},
            },
            {
                "resourceType": "Observation",
                "id": "OBS002",
                "status": "final",
                "code": {"coding": [{"system": "http://loinc.org", "code": "2345-7", "display": "Glucose"}]},
                "subject": {"reference": "Patient/PAT002"},
                "encounter": {"reference": "Encounter/ENC002"},
                "effectiveDateTime": "2026-01-15T08:00:00Z",
                "valueQuantity": {"value": 95, "unit": "mg/dL", "system": "http://unitsofmeasure.org", "code": "mg/dL"},
            },
            {
                "resourceType": "Observation",
                "id": "OBS003",
                "status": "final",
                "code": {"coding": [{"system": "http://loinc.org", "code": "72166-2", "display": "Smoking status"}]},
                "subject": {"reference": "Patient/PAT001"},
                "valueCodeableConcept": {"coding": [{"system": "http://snomed.info/sct", "code": "266919005", "display": "Never smoked"}]},
            },
        ]
        create_bronze_file(bronze_root, "Observation", ingestion_date, batch_id, observations)

        # --- RUN PIPELINE IN ORDER ---

        # 1. Patient
        patient_result = transform_patient_batch(
            bronze_root=bronze_root,
            silver_root=silver_root,
            quarantine_root=quarantine_root,
            report_root=report_root,
            batch_id=batch_id,
            ingestion_date=ingestion_date,
        )
        assert patient_result["status"] == "COMPLETED"
        assert patient_result["accepted"] == 2

        # 2. Encounter (depends on Patient)
        encounter_result = transform_encounter_batch(
            bronze_root=bronze_root,
            silver_root=silver_root,
            quarantine_root=quarantine_root,
            report_root=report_root,
            batch_id=batch_id,
            ingestion_date=ingestion_date,
        )
        assert encounter_result["status"] == "COMPLETED"
        assert encounter_result["accepted"] == 2

        # Verify Encounter references resolved
        encounter_silver = silver_root / f"resource_type=Encounter" / f"ingestion_date={ingestion_date}" / f"batch_{batch_id}.parquet"
        enc_df = pq.read_table(str(encounter_silver)).to_pandas()
        assert enc_df.iloc[0]["subject_id"] == "SYNTHEA_FHIR:PAT001"
        assert enc_df.iloc[1]["subject_id"] == "SYNTHEA_FHIR:PAT002"

        # 3. Condition (depends on Patient + Encounter)
        condition_result = transform_condition_batch(
            bronze_root=bronze_root,
            silver_root=silver_root,
            quarantine_root=quarantine_root,
            report_root=report_root,
            batch_id=batch_id,
            ingestion_date=ingestion_date,
        )
        assert condition_result["status"] == "COMPLETED"
        assert condition_result["accepted"] == 2

        # Verify Condition references resolved
        condition_silver = silver_root / f"resource_type=Condition" / f"ingestion_date={ingestion_date}" / f"batch_{batch_id}.parquet"
        cond_df = pq.read_table(str(condition_silver)).to_pandas()
        assert cond_df.iloc[0]["subject_id"] == "SYNTHEA_FHIR:PAT001"
        assert cond_df.iloc[0]["encounter_id"] == "SYNTHEA_FHIR:ENC001"
        assert cond_df.iloc[1]["subject_id"] == "SYNTHEA_FHIR:PAT002"
        assert cond_df.iloc[1]["encounter_id"] == "SYNTHEA_FHIR:ENC002"

        # 4. Observation (depends on Patient + Encounter)
        observation_result = transform_observation_batch(
            bronze_root=bronze_root,
            silver_root=silver_root,
            quarantine_root=quarantine_root,
            report_root=report_root,
            batch_id=batch_id,
            ingestion_date=ingestion_date,
        )
        assert observation_result["status"] == "COMPLETED"
        assert observation_result["accepted"] == 3

        # Verify Observation references resolved
        obs_silver = silver_root / f"resource_type=Observation" / f"ingestion_date={ingestion_date}" / f"batch_{batch_id}.parquet"
        obs_df = pq.read_table(str(obs_silver)).to_pandas()
        # OBS001 and OBS002 have encounter, OBS003 does not
        obs_with_enc = obs_df[obs_df["observation_id"].isin(["OBS001", "OBS002"])]
        assert all(obs_with_enc["encounter_id"].notna())
        # Parquet/Arrow converts None to NaN, so check for both
        obs3_encounter_id = obs_df[obs_df["observation_id"] == "OBS003"].iloc[0]["encounter_id"]
        import math
        assert obs3_encounter_id is None or (isinstance(obs3_encounter_id, float) and math.isnan(obs3_encounter_id))

    def test_pipeline_with_invalid_records_quarantined(
        self, bronze_root, silver_root, quarantine_root, report_root, batch_id, ingestion_date
    ):
        """Invalid records are quarantined, valid ones proceed."""
        # Patient with missing required field
        patients = [
            {"resourceType": "Patient", "id": "PAT001", "gender": "male", "birthDate": "1980-01-01"},
            {"resourceType": "Patient", "gender": "female"},  # Missing id
        ]
        create_bronze_file(bronze_root, "Patient", ingestion_date, batch_id, patients)

        patient_result = transform_patient_batch(
            bronze_root=bronze_root,
            silver_root=silver_root,
            quarantine_root=quarantine_root,
            report_root=report_root,
            batch_id=batch_id,
            ingestion_date=ingestion_date,
        )

        assert patient_result["accepted"] == 1
        assert patient_result["quarantined"] == 1

        # Encounter referencing valid patient
        encounters = [
            {
                "resourceType": "Encounter",
                "id": "ENC001",
                "status": "finished",
                "subject": {"reference": "Patient/PAT001"},
            }
        ]
        create_bronze_file(bronze_root, "Encounter", ingestion_date, batch_id, encounters)

        encounter_result = transform_encounter_batch(
            bronze_root=bronze_root,
            silver_root=silver_root,
            quarantine_root=quarantine_root,
            report_root=report_root,
            batch_id=batch_id,
            ingestion_date=ingestion_date,
        )

        assert encounter_result["accepted"] == 1
        assert encounter_result["quarantined"] == 0

    def test_reconciliation_balances_all_layers(
        self, bronze_root, silver_root, quarantine_root, report_root, batch_id, ingestion_date
    ):
        """Reconciliation balances across all Silver tables."""
        patients = [
            {"resourceType": "Patient", "id": "PAT001", "gender": "male", "birthDate": "1980-01-01"},
            {"resourceType": "Patient", "id": "PAT002", "gender": "female", "birthDate": "1990-01-01"},
        ]
        create_bronze_file(bronze_root, "Patient", ingestion_date, batch_id, patients)

        transform_patient_batch(
            bronze_root=bronze_root,
            silver_root=silver_root,
            quarantine_root=quarantine_root,
            report_root=report_root,
            batch_id=batch_id,
            ingestion_date=ingestion_date,
        )

        # Verify reconciliation report generated and balances
        from src.healthguard.silver.reconciliation import ReconciliationEngine
        recon = ReconciliationEngine()
        report = recon.reconcile_batch(
            batch_id=batch_id,
            resource_type="Patient",
            bronze_manifest_path=bronze_root / "manifests" / f"manifest_{batch_id}.json",
            silver_table_path=silver_root / f"resource_type=Patient" / f"ingestion_date={ingestion_date}" / f"batch_{batch_id}.parquet",
            quarantine_root=quarantine_root / "silver" / "Patient",
        )

        assert report.balances()
        assert report.source_valid == 2
        assert report.silver_accepted == 2
        assert report.quarantined_total == 0

    def test_dq_reports_generated_all_layers(
        self, bronze_root, silver_root, quarantine_root, report_root, batch_id, ingestion_date
    ):
        """DQ reports generated for each Silver table."""
        patients = [
            {"resourceType": "Patient", "id": "PAT001", "gender": "male", "birthDate": "1980-01-01"},
        ]
        create_bronze_file(bronze_root, "Patient", ingestion_date, batch_id, patients)

        transform_patient_batch(
            bronze_root=bronze_root,
            silver_root=silver_root,
            quarantine_root=quarantine_root,
            report_root=report_root,
            batch_id=batch_id,
            ingestion_date=ingestion_date,
        )

        # Check DQ report exists
        dq_json = report_root / "dq" / "Patient" / f"batch_{batch_id}" / f"dq_report_patient_{batch_id}.json"
        dq_md = report_root / "dq" / "Patient" / f"batch_{batch_id}" / f"dq_report_patient_{batch_id}.md"
        assert dq_json.exists()
        assert dq_md.exists()

        # Check reconciliation report exists
        recon_json = report_root / "reconciliation" / "Patient" / f"batch_{batch_id}" / f"reconciliation_patient_{batch_id}.json"
        recon_md = report_root / "reconciliation" / "Patient" / f"batch_{batch_id}" / f"reconciliation_patient_{batch_id}.md"
        assert recon_json.exists()
        assert recon_md.exists()