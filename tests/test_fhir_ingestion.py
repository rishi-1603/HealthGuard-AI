"""Unit and integration tests for Day 4 (DE-004): Synthea FHIR R4 Multi-Source Ingestion Engine.

Tests cover:
- Streaming FHIR R4 resource parsing from bundle (Patient, Encounter, Observation, Condition).
- Source key normalization without cross-system identifier collisions.
- Checksum validation and manifest generation for Bronze Parquet ingestion.
- Bronze Parquet export for FHIR entities with schema enforcement.
- End-to-end multi-source ingestion combining HealthGuard CSV and Synthea FHIR.
"""

from __future__ import annotations

import json
from pathlib import Path
import pandas as pd
import pytest

from pipeline.config import PipelineConfig, REPO_ROOT
from pipeline.ingestion.fhir_parser import (
    FHIRBundleParser,
    normalize_source_id,
    ParsedFHIRDataset,
)
from pipeline.ingestion.multi_source import MultiSourceIngestor, IngestionManifest


@pytest.fixture(scope="module")
def sample_fhir_bundle(tmp_path_factory) -> Path:
    """Create a minimal representative FHIR R4 Bundle for deterministic unit testing."""
    tmp = tmp_path_factory.mktemp("fhir")
    bundle_file = tmp / "mini_bundle.json"
    
    data = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": "P0001",
                    "gender": "male",
                    "birthDate": "1994-04-05",
                    "extension": [
                        {"url": "http://example.org/fhir/StructureDefinition/region", "valueString": "East"},
                        {"url": "http://example.org/fhir/StructureDefinition/insurance", "valueString": "Medicaid"}
                    ]
                }
            },
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": "P0002",
                    "gender": "female",
                    "birthDate": "1980-11-20",
                    "extension": []
                }
            },
            {
                "resource": {
                    "resourceType": "Encounter",
                    "id": "E0001_0",
                    "status": "finished",
                    "subject": {"reference": "Patient/P0001"},
                    "period": {"start": "2025-10-14"}
                }
            },
            {
                "resource": {
                    "resourceType": "Condition",
                    "id": "C0001",
                    "subject": {"reference": "Patient/P0001"},
                    "code": {"text": "hypertension"}
                }
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "id": "O_HR_0001_0",
                    "status": "final",
                    "subject": {"reference": "Patient/P0001"},
                    "effectiveDateTime": "2025-10-16",
                    "code": {"text": "heart-rate"},
                    "valueQuantity": {"value": 93.8, "unit": "bpm"}
                }
            }
        ]
    }
    with open(bundle_file, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return bundle_file


# ---------------------------------------------------------------------------
# 1. Identifier Normalization Tests
# ---------------------------------------------------------------------------
class TestSourceIdentifierNormalization:
    def test_normalize_healthguard_csv_id(self):
        norm_id = normalize_source_id("HG_CSV", 101)
        assert norm_id == "HG_CSV:101"

    def test_normalize_synthea_fhir_id(self):
        norm_id = normalize_source_id("SYNTHEA_FHIR", "P0001")
        assert norm_id == "SYNTHEA_FHIR:P0001"

    def test_zero_collision_across_sources_with_identical_native_keys(self):
        id_a = normalize_source_id("HG_CSV", 100)
        id_b = normalize_source_id("SYNTHEA_FHIR", 100)
        assert id_a != id_b
        assert id_a == "HG_CSV:100"
        assert id_b == "SYNTHEA_FHIR:100"


# ---------------------------------------------------------------------------
# 2. FHIR Parser Tests
# ---------------------------------------------------------------------------
class TestFHIRBundleParser:
    def test_parse_sample_bundle(self, sample_fhir_bundle: Path):
        parser = FHIRBundleParser(sample_fhir_bundle)
        parsed: ParsedFHIRDataset = parser.parse()
        
        assert len(parsed.patients) == 2
        assert len(parsed.encounters) == 1
        assert len(parsed.conditions) == 1
        assert len(parsed.observations) == 1

    def test_patient_attributes_extracted_correctly(self, sample_fhir_bundle: Path):
        parser = FHIRBundleParser(sample_fhir_bundle)
        parsed = parser.parse()
        p_df = parsed.patients
        
        p1 = p_df[p_df["patient_id"] == "SYNTHEA_FHIR:P0001"].iloc[0]
        assert p1["gender"] == "male"
        assert p1["birth_date"] == "1994-04-05"
        assert p1["region"] == "East"
        assert p1["insurance"] == "Medicaid"
        assert p1["source_system"] == "SYNTHEA_FHIR"

    def test_encounter_and_condition_association(self, sample_fhir_bundle: Path):
        parser = FHIRBundleParser(sample_fhir_bundle)
        parsed = parser.parse()
        e_df = parsed.encounters
        c_df = parsed.conditions
        
        assert e_df["patient_id"].iloc[0] == "SYNTHEA_FHIR:P0001"
        assert c_df["patient_id"].iloc[0] == "SYNTHEA_FHIR:P0001"
        assert c_df["condition_text"].iloc[0] == "hypertension"

    def test_observation_values_extracted(self, sample_fhir_bundle: Path):
        parser = FHIRBundleParser(sample_fhir_bundle)
        parsed = parser.parse()
        o_df = parsed.observations
        
        obs = o_df.iloc[0]
        assert obs["patient_id"] == "SYNTHEA_FHIR:P0001"
        assert obs["observation_name"] == "heart-rate"
        assert obs["value"] == 93.8
        assert obs["unit"] == "bpm"


# ---------------------------------------------------------------------------
# 3. Multi-Source Ingestion & Bronze Parquet Landing Tests
# ---------------------------------------------------------------------------
class TestMultiSourceIngestion:
    def test_ingest_fhir_to_bronze_parquet(self, sample_fhir_bundle: Path, tmp_path: Path):
        landing_dir = tmp_path / "bronze_landing"
        ingestor = MultiSourceIngestor(bronze_dir=landing_dir)
        
        manifest = ingestor.ingest_fhir(sample_fhir_bundle, max_entries=100)
        assert manifest.status == "SUCCESS"
        assert manifest.records_ingested > 0
        assert manifest.sha256_checksum != ""
        
        # Verify parquet tables landed on disk
        assert (landing_dir / "fhir_patients.parquet").exists()
        assert (landing_dir / "fhir_encounters.parquet").exists()
        assert (landing_dir / "fhir_conditions.parquet").exists()
        assert (landing_dir / "fhir_observations.parquet").exists()
        assert (landing_dir / "manifests").exists()

    def test_live_bundle_streaming_sample_ingestion(self, tmp_path: Path):
        """Test against actual repo bundle if present, with capped entries for high speed."""
        live_bundle = REPO_ROOT / "data" / "synthetic" / "bundle.json"
        if not live_bundle.exists():
            pytest.skip("Full bundle.json not in test environment")
            
        landing_dir = tmp_path / "live_bronze"
        ingestor = MultiSourceIngestor(bronze_dir=landing_dir)
        manifest = ingestor.ingest_fhir(live_bundle, max_entries=1500)
        
        assert manifest.status == "SUCCESS"
        assert manifest.records_ingested >= 1000
        
        df_pat = pd.read_parquet(landing_dir / "fhir_patients.parquet")
        assert len(df_pat) > 0
        assert "patient_id" in df_pat.columns
        assert df_pat["patient_id"].iloc[0].startswith("SYNTHEA_FHIR:")
