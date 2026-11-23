# HealthGuard 360 — Operations & Disaster Recovery Runbook

## 1. Quickstart & Service Startup

### Local Development / Virtualenv
```bash
# 1. Clone repository & enter workspace
git clone https://github.com/rishi-1603/HealthGuard-AI.git
cd HealthGuard-AI

# 2. Activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\Activate.ps1

# 3. Install production dependencies
pip install -r requirements.txt

# 4. Initialize Lakehouse database & run migrations
python -c "from pipeline.warehouse import apply_ddl; from pipeline.config import PipelineConfig; apply_ddl(PipelineConfig())"

# 5. Launch HealthGuard 360 Dashboard
streamlit run app/dashboard/Home.py
```

### Multi-Container Docker Deployment
```bash
# Build and start all services (Postgres, Kafka, Zookeeper, Airflow, Dashboard)
docker compose up -d --build

# Verify container health status
docker compose ps
```

---

## 2. Common Pipeline Operations

### Running Medallion Batch Pipeline
To trigger a manual ingestion and transformation wave:
```bash
python -m orchestration.airflow_dags
```

### Executing CDC Real-Time Synchronization
To process outstanding Write-Ahead Log (WAL) change events into Silver:
```bash
python -c "from pipeline.cdc.lakehouse_sync import LakehouseSyncEngine; from pipeline.config import PipelineConfig; eng = LakehouseSyncEngine(PipelineConfig()); eng.compact_silver_encounters()"
```

### Historical Data Backfill
To backfill historical dates without creating duplicates:
```bash
python -c "from orchestration.airflow_dags import AirflowMedallionRunner; from pipeline.config import PipelineConfig; runner = AirflowMedallionRunner(PipelineConfig()); runner.run_batch_medallion(backfill_days=30)"
```

---

## 3. Incident Response Playbooks

### Playbook 1: Data Trust Score Degradation (< 85%)
- **Symptoms**: Streamlit Data Trust Ops Console displays Grade B or Grade C banner; alert raised on validity or referential integrity.
- **Diagnostic Steps**:
  1. Open Data Trust Console (`http://localhost:8501`) and navigate to the **Data Trust Console** page.
  2. Identify which pillar failed (e.g., Validity dropped due to negative costs).
  3. Query the quarantine table for recent failure reasons:
     ```sql
     SELECT quarantine_reason, COUNT(*) FROM quarantine_encounters GROUP BY quarantine_reason;
     ```
  4. Inspect source feed for upstream EHR schema changes.
- **Remediation**:
  - Update schema validator or notify upstream provider.
  - Re-ingest cleansed records through the quarantine reprocessing workflow.

### Playbook 2: Kafka Consumer Lag & Partition Stalling
- **Symptoms**: Kafka lag metric grows; real-time dashboard encounters delay.
- **Diagnostic Steps**:
  1. Inspect Kafka consumer group status:
     ```bash
     kafka-consumer-groups --bootstrap-server localhost:9092 --describe --group healthguard_streaming_group
     ```
  2. Check for unbalanced partitions or slow consumers.
- **Remediation**:
  - Restart the consumer worker container: `docker compose restart lakehouse-sync`.
  - If partition skew is detected, review patient affinity hashing in `KafkaPartitionRouter`.

### Playbook 3: CDC Synchronization Drift
- **Symptoms**: `silver_operational_encounters` row count lags behind operational PostgreSQL EHR table.
- **Diagnostic Steps**:
  1. Check last applied LSN in `bronze_cdc_events` vs current database LSN:
     ```sql
     SELECT MAX(lsn) FROM bronze_cdc_events;
     ```
  2. Check operational EHR WAL writer status.
- **Remediation**:
  - Run the CDC Catchup Sync task:
    ```bash
    python -c "from pipeline.cdc.lakehouse_sync import LakehouseSyncEngine; LakehouseSyncEngine().sync_bronze_events()"
    ```

---

## 4. Disaster Recovery & Backup / Restore

### Database Snapshot & Backup
```bash
# Backup SQLite Lakehouse Warehouse
sqlite3 warehouse/healthguard.db ".backup 'warehouse/backups/healthguard_backup_$(date +%Y%m%d_%H%M%S).db'"

# Backup PostgreSQL Operational Database
docker compose exec -T postgres pg_dump -U healthguard_admin healthguard_ehr > backups/ehr_backup.sql
```

### Database Restore Procedure
1. Stop all active writing containers:
   ```bash
   docker compose stop dashboard airflow-scheduler
   ```
2. Restore database file from verified snapshot:
   ```bash
   cp warehouse/backups/healthguard_backup_<TIMESTAMP>.db warehouse/healthguard.db
   ```
3. Run verification tests:
   ```bash
   pytest tests/test_schema_contracts.py tests/test_medallion.py
   ```
4. Restart services:
   ```bash
   docker compose start dashboard airflow-scheduler
   ```
