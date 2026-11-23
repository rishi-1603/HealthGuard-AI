"""
Unit and integration tests for Day 14 (DE-014):
Cloud Infrastructure, Docker Compose, Terraform IaC, and GitHub Actions CI/CD.
"""

from pathlib import Path
from typing import Any, Dict
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestDockerComposeArchitecture:
    """Verifies docker-compose.yml multi-container topology, networks, volumes, and health checks."""

    @pytest.fixture
    def compose_data(self) -> Dict[str, Any]:
        compose_file = REPO_ROOT / "docker-compose.yml"
        assert compose_file.exists(), "docker-compose.yml must exist at repo root"
        with open(compose_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict), "docker-compose.yml must parse as a dictionary"
        return data

    def test_required_services_declared(self, compose_data: Dict[str, Any]) -> None:
        """T01: Multi-container spec includes postgres, kafka, airflow, and dashboard."""
        services = compose_data.get("services", {})
        required = [
            "postgres",
            "zookeeper",
            "kafka",
            "airflow-init",
            "airflow-webserver",
            "airflow-scheduler",
            "dashboard",
        ]
        for s in required:
            assert s in services, f"Required service '{s}' missing from docker-compose.yml"

    def test_networks_and_volumes_declared(self, compose_data: Dict[str, Any]) -> None:
        """T02: Dedicated bridge network and persistent volumes are declared."""
        networks = compose_data.get("networks", {})
        assert "healthguard-net" in networks

        volumes = compose_data.get("volumes", {})
        required_vols = ["postgres_data", "kafka_data", "airflow_logs", "lakehouse_storage"]
        for v in required_vols:
            assert v in volumes, f"Required volume '{v}' missing from docker-compose.yml"

    def test_postgres_container_spec(self, compose_data: Dict[str, Any]) -> None:
        """T03: Postgres service has valid ports, environment, and pg_isready healthcheck."""
        pg = compose_data["services"]["postgres"]
        assert "5432:5432" in pg.get("ports", [])
        assert "healthcheck" in pg
        assert "pg_isready" in " ".join(pg["healthcheck"].get("test", []))
        assert "healthguard-net" in pg.get("networks", [])

    def test_kafka_and_zookeeper_coordination(self, compose_data: Dict[str, Any]) -> None:
        """T04: Kafka broker declares ports, advertised listeners, and depends on zookeeper."""
        kafka = compose_data["services"]["kafka"]
        assert "9092:9092" in kafka.get("ports", [])
        assert "zookeeper" in kafka.get("depends_on", {})
        assert "healthcheck" in kafka

    def test_dashboard_service_spec(self, compose_data: Dict[str, Any]) -> None:
        """T05: Dashboard exposes Streamlit port 8501 and defines healthcheck."""
        dash = compose_data["services"]["dashboard"]
        assert "8501:8501" in dash.get("ports", [])
        assert "healthcheck" in dash
        assert "healthguard-net" in dash.get("networks", [])


class TestDockerfileCompliance:
    """Verifies production Dockerfile hygiene, healthchecks, and exposed ports."""

    @pytest.fixture
    def dockerfile_content(self) -> str:
        dockerfile = REPO_ROOT / "Dockerfile"
        assert dockerfile.exists(), "Dockerfile must exist at repo root"
        return dockerfile.read_text(encoding="utf-8")

    def test_python_base_image(self, dockerfile_content: str) -> None:
        """T06: Dockerfile uses official Python slim base image."""
        assert "FROM python:3.11-slim" in dockerfile_content

    def test_exposed_ports(self, dockerfile_content: str) -> None:
        """T07: Port 8501 is exposed for Streamlit."""
        assert "EXPOSE" in dockerfile_content
        assert "8501" in dockerfile_content

    def test_dockerfile_healthcheck_directive(self, dockerfile_content: str) -> None:
        """T08: Production HEALTHCHECK instruction is present in Dockerfile."""
        assert "HEALTHCHECK" in dockerfile_content


class TestTerraformLakehouseIaC:
    """Verifies Azure ADLS Gen2 & Databricks Terraform IaC configurations."""

    @pytest.fixture
    def main_tf(self) -> str:
        p = REPO_ROOT / "infra" / "terraform" / "main.tf"
        assert p.exists(), "infra/terraform/main.tf must exist"
        return p.read_text(encoding="utf-8")

    @pytest.fixture
    def databricks_tf(self) -> str:
        p = REPO_ROOT / "infra" / "terraform" / "databricks.tf"
        assert p.exists(), "infra/terraform/databricks.tf must exist"
        return p.read_text(encoding="utf-8")

    @pytest.fixture
    def variables_tf(self) -> str:
        p = REPO_ROOT / "infra" / "terraform" / "variables.tf"
        assert p.exists(), "infra/terraform/variables.tf must exist"
        return p.read_text(encoding="utf-8")

    def test_adls_gen2_hierarchical_namespace_enabled(self, main_tf: str) -> None:
        """T09: Storage account enforces is_hns_enabled = true for ADLS Gen2 lakehouse."""
        assert "azurerm_storage_account" in main_tf
        assert "is_hns_enabled           = true" in main_tf or "is_hns_enabled = true" in main_tf

    def test_medallion_containers_declared(self, main_tf: str) -> None:
        """T10: Terraform creates bronze, silver, gold, and quarantine data lake filesystems."""
        for tier in ["bronze", "silver", "gold", "quarantine"]:
            assert f'resource "azurerm_storage_data_lake_gen2_filesystem" "{tier}"' in main_tf

    def test_databricks_premium_sku_and_unity_catalog(self, databricks_tf: str) -> None:
        """T11: Databricks workspace is configured with Unity Catalog and Access Connector."""
        assert "azurerm_databricks_workspace" in databricks_tf
        assert "azurerm_databricks_access_connector" in databricks_tf
        assert "databricks_catalog" in databricks_tf

    def test_databricks_lakehouse_cluster_autoscaling(self, databricks_tf: str) -> None:
        """T12: Databricks compute defines auto-scaling worker range and spark conf."""
        assert "databricks_cluster" in databricks_tf
        assert "autoscale" in databricks_tf
        assert "spark_conf" in databricks_tf


class TestGitHubActionsCI:
    """Verifies GitHub Actions CI workflow structure and step completeness."""

    @pytest.fixture
    def workflow_data(self) -> Dict[str, Any]:
        workflow_file = REPO_ROOT / ".github" / "workflows" / "ci.yml"
        assert workflow_file.exists(), ".github/workflows/ci.yml must exist"
        with open(workflow_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict), ".github/workflows/ci.yml must parse as a dictionary"
        return data

    def test_workflow_triggers_on_main(self, workflow_data: Dict[str, Any]) -> None:
        """T13: Workflow triggers on push and pull_request to main branch."""
        # Check push triggers (handle YAML 1.1 'on' parsed as string or boolean True)
        triggers = workflow_data.get("on") or workflow_data.get(True, {})
        push_branches = triggers.get("push", {}).get("branches", [])
        assert "main" in push_branches

    def test_required_ci_jobs_declared(self, workflow_data: Dict[str, Any]) -> None:
        """T14: Workflow defines code quality, contract checks, pytest runner, and infra checks."""
        jobs = workflow_data.get("jobs", {})
        expected_jobs = ["code-quality", "contracts-and-schemas", "test-suite", "infra-validation"]
        for j in expected_jobs:
            assert j in jobs, f"Expected CI job '{j}' missing from workflow"

    def test_test_suite_job_executes_pytest(self, workflow_data: Dict[str, Any]) -> None:
        """T15: test-suite job executes pytest across test directory."""
        steps = workflow_data["jobs"]["test-suite"].get("steps", [])
        run_commands = [s.get("run", "") for s in steps if "run" in s]
        assert any("pytest" in cmd for cmd in run_commands), "pytest execution command missing in test-suite"
