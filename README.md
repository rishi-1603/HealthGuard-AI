# HealthGuard 360 — Healthcare Data Engineering Platform

[![CI](https://github.com/rishi-1603/HealthGuard-AI/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/rishi-1603/HealthGuard-AI/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![DuckDB](https://img.shields.io/badge/DuckDB-OLAP-brightgreen.svg)](https://duckdb.org/)
[![Apache Airflow 3.4](https://img.shields.io/badge/Apache%20Airflow-3.4-teal.svg)](https://airflow.apache.org/)

**HealthGuard 360** is a **Healthcare Data Engineering Platform** that ingests synthetic FHIR R4 healthcare records, processes them through a reliable Bronze-Silver-Gold medallion architecture, validates data quality, and exposes trusted analytical data through a governed AI Data Copilot.

> **⚠️ Synthetic Data Disclaimer:** This platform uses **MITRE Synthea** to generate synthetic healthcare data. It does not represent real patients, real clinical events, or real healthcare outcomes. All analysis is for engineering demonstration purposes only.

---

## Architecture

```
Synthea FHIR R4 NDJSON
        │
        ▼
┌───────────────────┐
│  Python Streaming │  ◄─── Line-by-line NDJSON ingestion (bounded memory)
│  Ingestion Engine │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│   Bronze Layer    │  ◄─── Immutable Parquet + SHA-256 manifests
│  (Raw FHIR Data)  │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│   Silver Layer    │  ◄─── Normalized, validated, referential integrity
│ (Cleaned Data)    │       Quarantine for invalid records
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│   Gold Layer      │  ◄─── DuckDB + dbt dimensional warehouse
│ (Analytics Marts) │       3 marts: patient_summary, encounter_utilization,
└─────────┬─────────┘       observation_trends
          │
          ▼
┌───────────────────┐
│  Airflow 3.4.0    │  ◄─── Real orchestration: retries, backfills, idempotency
│  Orchestration    │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  AI Data Copilot  │  ◄─── Governed NL→SQL (SQLGlot + allowlists + read-only)
│  (Streamlit)      │
└───────────────────┘
```

---

## Key Capabilities

| Layer | Technology | What It Does |
|-------|------------|--------------|
| **Ingestion** | Python + PyArrow | Streams 500K+ FHIR NDJSON records without loading into memory |
| **Bronze** | Parquet + Manifests | Immutable raw storage, SHA-256 manifests, deterministic batch IDs |
| **Silver** | Python + PyArrow | 4 transformers (Patient, Encounter, Condition, Observation), quarantine, DQ scorecards |
| **Gold** | DuckDB + dbt | 3 tested analytical marts, incremental models, schema tests |
| **Orchestration** | Apache Airflow 3.4 | Real DAG with retries, backfills, TaskGroups, idempotent tasks |
| **AI Copilot** | Streamlit + SQLGlot | Governed NL→SQL on Gold marts, read-only, table/column allowlists |

---

## Dataset

**Source:** MITRE Synthea FHIR R4 Bulk NDJSON Export  
**Scale (Development):** 1,136 synthetic patients → **622,322 core FHIR resources**
- Patient: 1,136
- Encounter: 64,096  
- Condition: 38,992
- Observation: 518,098

**Benchmark Profiles:**
| Profile | Patients | Est. Resources | Purpose |
|---------|----------|----------------|---------|
| Development | 1,000 | ~600K | Fast local dev |
| Integration | 10,000 | ~6M | Full workflow validation |
| Performance | 50,000 | ~30M | Throughput & memory benchmarking |

> **Note:** Synthea generates 24+ resource types. This pipeline processes 4 core types (Patient, Encounter, Condition, Observation). All others are inventoried, checksummed, and explicitly classified as out-of-scope.

---

## Quickstart

### Prerequisites
- Docker & Docker Compose
- Python 3.11+ (for local development)
- Git

### 1. Clone & Configure
```bash
git clone https://github.com/rishi-1603/HealthGuard-AI.git
cd HealthGuard-AI
cp .env.example .env
# Edit .env with secure passwords
```

### 2. Generate Synthetic Data (or use existing)
```bash
# Option A: Use pre-generated data in data/raw/synthea/fhir/
# Option B: Generate your own (requires Java 17+)
cd synthea
./gradlew run -Parms="['-p', '1000', '-c', 'healthguard.properties', '-s', '424242', '-r', '20261125']"
cp -r output/fhir/*.ndjson ../data/raw/synthea/fhir/
```

### 3. Run Local Stack
```bash
docker compose up -d --build
```

**Services:**
- **Airflow UI:** http://localhost:8080 (admin/admin)
- **Streamlit Dashboard:** http://localhost:8501
- **PostgreSQL:** localhost:5432

### 4. Run Pipeline
In Airflow UI: trigger `healthguard_fhir_pipeline` DAG

Or run manually:
```bash
# Install pipeline deps
pip install -r requirements-pipeline.txt

# Run inventory
python scripts/inventory_resources.py

# Run Bronze ingestion (implement in Day 2)
python -m src.healthguard.bronze.writer --help
```

### 5. Local Development
```bash
pip install -r requirements-dev.txt
pytest tests/ -v
ruff check .
black --check .
```

---

## Project Structure

```
HealthGuard-AI/
├── config/
│   └── resource_contracts/     # YAML contracts for Patient, Encounter, Condition, Observation
├── src/healthguard/
│   ├── ingestion/              # NDJSON reader, validator, batch manager, router
│   ├── bronze/                 # Parquet writer, manifests, schema
│   ├── silver/                 # 4 transformers, references, quality, quarantine
│   ├── gold/                   # Warehouse, reconciliation
│   ├── copilot/                # Catalog, SQL generator, validator, executor
│   └── common/                 # Logging, hashing, exceptions
├── warehouse/dbt_healthguard/  # dbt models (staging, intermediate, marts)
├── orchestration/dags/         # Airflow DAG: healthguard_fhir_pipeline
├── data/
│   ├── raw/synthea/fhir/       # Source NDJSON (gitignored)
│   ├── lakehouse/bronze/       # Bronze Parquet (gitignored)
│   ├── lakehouse/silver/       # Silver Parquet (gitignored)
│   ├── lakehouse/quarantine/   # Quarantined records (gitignored)
│   └── manifests/              # Ingestion manifests (gitignored)
├── scripts/                    # inventory_resources.py, benchmark_pipeline.py
├── tests/                      # Unit, integration, reconciliation, e2e
├── docs/                       # ARCHITECTURE, DATA_PROVENANCE, RUNBOOK, AI_SAFETY
├── app/dashboard/              # Streamlit pages
├── docker-compose.yml
├── Dockerfile
├── requirements-*.txt
└── README.md
```

---

## AI Data Copilot

The copilot answers analytical questions using **governed NL→SQL**:

1. **Metric Catalog** — 15 approved metrics mapped to Gold marts
2. **SQL Generation** — Template-based (not free-form LLM)
3. **SQLGlot Validation** — AST parsing, table/column allowlists, read-only enforcement
4. **Read-Only Execution** — DuckDB `read_only=True`, row limits, timeouts
5. **Security Tests** — 10 adversarial attempts (DELETE, ATTACH, etc.) all rejected

**Example Questions:**
- "How many patients per gender?"
- "Top 10 conditions by patient count"
- "Encounter volume by class per month"

---

## Documentation

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Full system architecture & data flows |
| [DATA_PROVENANCE.md](docs/DATA_PROVENANCE.md) | Synthea generation config, inventory, checksums |
| [DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md) | Resource fields, Silver schemas, Gold models |
| [DATA_QUALITY.md](docs/DATA_QUALITY.md) | Validation rules, quarantine reasons, reconciliation |
| [AI_SAFETY.md](docs/AI_SAFETY.md) | Copilot architecture, allowlists, security tests |
| [RUNBOOK.md](docs/RUNBOOK.md) | Setup, run, retry, rerun, recovery procedures |
| [BENCHMARK_REPORT.md](docs/BENCHMARK_REPORT.md) | 1K/10K/50K benchmarks, throughput, memory |

---

## CI/CD

**GitHub Actions** enforces:
- `ruff` linting (no `--exit-zero`)
- `black` formatting check
- Resource contract validation
- Full pytest suite (must pass)
- Docker Compose config validation

---

## Deployment

### Local (Full Stack)
```bash
docker compose up -d --build
```

### Public Demo (Streamlit Community Cloud)
- **Read-only** dashboard backed by precomputed Gold data
- AI Copilot with LLM API key in Streamlit secrets
- No Airflow, no ingestion, no raw data

> The public demo is **read-only** and uses a small precomputed Gold extract. The full engineering stack runs locally via Docker Compose.

---

## License

MIT License — see [LICENSE](LICENSE)

---

## Acknowledgments

- **MITRE Synthea** — Synthetic patient data generation
- **Apache Airflow** — Orchestration
- **DuckDB** — Analytical engine
- **dbt** — Transformation framework
- **SQLGlot** — SQL parsing & validation
- **Streamlit** — Dashboard framework

---

**Built with engineering rigor, not technology name-dropping.**  
One reliable batch pipeline > ten simulated components.