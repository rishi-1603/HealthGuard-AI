# HealthGuard 360 — Enterprise Data Dictionary

## 1. Overview of Lakehouse Data Models

HealthGuard 360 models clinical, operational, and financial data across the Medallion architecture (Bronze, Silver, Gold). Below are the column definitions, data types, nullability, constraints, and business logic for all core tables.

---

## 2. Bronze Tier (Raw Landing)

### `bronze_encounters`
Raw immutable clinical encounter records landed from source CSV, API, or Synthea bundles.

| Column | Type | Nullable | Primary Key | Description |
| :--- | :--- | :--- | :--- | :--- |
| `encounter_id` | TEXT | No | Yes | Unique identifier for hospital admission encounter |
| `patient_id` | TEXT | No | No | Unique identifier for patient |
| `encounter_date` | TEXT | No | No | Date of encounter admission (ISO 8601: `YYYY-MM-DD`) |
| `condition` | TEXT | No | No | Primary admitting clinical condition |
| `cost` | REAL | No | No | Total billed encounter treatment cost (USD) |
| `length_of_stay` | INTEGER | No | No | Duration of inpatient stay in days |
| `readmitted` | INTEGER | No | No | Binary flag (1 if readmitted within 30 days, 0 otherwise) |
| `ingested_at` | TIMESTAMP | No | No | UTC timestamp when record landed in Bronze |
| `source_file` | TEXT | Yes | No | Source file name or bundle identifier |

### `bronze_cdc_events`
Write-Ahead Log (WAL) change events streamed from operational EHR database.

| Column | Type | Nullable | Primary Key | Description |
| :--- | :--- | :--- | :--- | :--- |
| `event_id` | TEXT | No | Yes | UUIDv5 deterministic change event identifier |
| `lsn` | INTEGER | No | No | Monotonically increasing Log Sequence Number |
| `op` | TEXT | No | No | Operation type (`c` = create, `u` = update, `d` = delete) |
| `source_table` | TEXT | No | No | Originating operational database table |
| `before` | TEXT | Yes | No | Serialized JSON representation of state before mutation |
| `after` | TEXT | Yes | No | Serialized JSON representation of state after mutation |
| `captured_at` | TIMESTAMP | No | No | UTC timestamp of WAL emission |

---

## 3. Silver Tier (Cleansed & Conformed)

### `silver_encounters`
Cleaned, deduplicated, and schema-validated encounters passing all data quality gates.

| Column | Type | Nullable | Primary Key | Description |
| :--- | :--- | :--- | :--- | :--- |
| `encounter_id` | TEXT | No | Yes | Unique clinical encounter identifier |
| `patient_id` | TEXT | No | No | Foreign key referencing `dim_patient` |
| `encounter_date` | TEXT | No | No | Validated admission date (`YYYY-MM-DD`) |
| `condition` | TEXT | No | No | Standardized condition name |
| `cost` | REAL | No | No | Validated positive cost |
| `length_of_stay` | INTEGER | No | No | Validated positive length of stay |
| `readmitted` | INTEGER | No | No | Validated binary flag (0 or 1) |
| `processed_at` | TIMESTAMP | No | No | UTC timestamp of Silver compaction |

### `quarantine_encounters`
Isolated records that failed schema contracts or clinical domain sanity rules.

| Column | Type | Nullable | Primary Key | Description |
| :--- | :--- | :--- | :--- | :--- |
| `quarantine_id` | TEXT | No | Yes | Unique quarantine incident identifier |
| `encounter_id` | TEXT | Yes | No | Associated encounter identifier (if present) |
| `raw_payload` | TEXT | No | No | Raw serialized payload of failed record |
| `quarantine_reason` | TEXT | No | No | Specific validation failure code (e.g. `INVALID_COST`) |
| `quarantined_at` | TIMESTAMP | No | No | UTC timestamp of quarantine isolation |

---

## 4. Gold Tier Dimensional Models (Star Schema)

### `dim_patient` (SCD Type 2)
Slowly Changing Dimension Type 2 table tracking patient profile histories.

| Column | Type | Nullable | Primary Key | Description |
| :--- | :--- | :--- | :--- | :--- |
| `patient_key` | TEXT | No | Yes | Surrogate key combining patient ID and version |
| `patient_id` | TEXT | No | No | Natural patient business key |
| `age` | INTEGER | No | No | Patient age in years |
| `gender` | TEXT | No | No | Patient gender (`M`, `F`, `Other`) |
| `risk_band` | TEXT | Yes | No | Computed clinical risk tier (`LOW`, `MEDIUM`, `HIGH`) |
| `valid_from` | TIMESTAMP | No | No | UTC start timestamp of record version validity |
| `valid_to` | TIMESTAMP | Yes | No | UTC expiration timestamp (`NULL` if current) |
| `is_current` | INTEGER | No | No | Flag indicating current version (1 = current, 0 = expired) |

### `dim_date`
Standard date dimension for temporal analytics.

| Column | Type | Nullable | Primary Key | Description |
| :--- | :--- | :--- | :--- | :--- |
| `date_id` | INTEGER | No | Yes | Surrogate key in format `YYYYMMDD` |
| `full_date` | TEXT | No | No | Date string (`YYYY-MM-DD`) |
| `year` | INTEGER | No | No | Calendar year |
| `quarter` | INTEGER | No | No | Calendar quarter (1 to 4) |
| `month` | INTEGER | No | No | Calendar month (1 to 12) |
| `month_name` | TEXT | No | No | Full month name (e.g. `January`) |
| `day_of_month` | INTEGER | No | No | Day of month (1 to 31) |
| `day_name` | TEXT | No | No | Full day of week (e.g. `Monday`) |
| `is_weekend` | INTEGER | No | No | Flag indicating weekend (1 = Saturday/Sunday, 0 = Weekday) |

### `fact_encounter`
Central fact table at the grain of one row per completed inpatient encounter.

| Column | Type | Nullable | Primary Key | Description |
| :--- | :--- | :--- | :--- | :--- |
| `fact_id` | TEXT | No | Yes | Unique fact row surrogate key |
| `encounter_id` | TEXT | No | No | Degenerate dimension identifier |
| `patient_key` | TEXT | No | No | FK referencing `dim_patient.patient_key` (point-in-time) |
| `date_id` | INTEGER | No | No | FK referencing `dim_date.date_id` |
| `condition` | TEXT | No | No | Primary admitted diagnosis |
| `cost` | REAL | No | No | Total treatment cost in USD |
| `length_of_stay` | INTEGER | No | No | Length of stay in days |
| `readmitted` | INTEGER | No | No | 30-day readmission outcome (0 or 1) |
| `satisfaction` | REAL | Yes | No | Patient satisfaction survey rating (1.0 to 5.0) |

---

## 5. Gold Analytical Marts

### `gold_condition_mart`
Aggregated clinical and operational metrics by medical condition.
- `condition` (TEXT): Clinical diagnosis.
- `total_patients` (INTEGER): Total encounter volume.
- `readmitted_count` (INTEGER): Count of 30-day readmissions.
- `readmission_rate_pct` (REAL): Percentage of readmitted encounters (`0.0` – `100.0%`).
- `total_cost` (REAL): Aggregate financial expenditure.
- `avg_cost` (REAL): Average treatment cost per encounter.
- `avg_length_of_stay` (REAL): Mean inpatient duration in days.
- `avg_satisfaction` (REAL): Mean patient experience rating.

### `gold_daily_summary`
Daily hospital operational census and throughput tracker.
- `summary_date` (TEXT): Observation date (`YYYY-MM-DD`).
- `total_patients` (INTEGER): Active daily inpatient encounters.
- `total_cost` (REAL): Daily hospital expenditure.
- `readmitted_count` (INTEGER): Readmission count on date.
- `readmission_rate_pct` (REAL): Daily readmission percentage.
- `avg_cost` (REAL): Average daily encounter cost.
- `avg_length_of_stay` (REAL): Average stay duration.
- `avg_satisfaction` (REAL): Average patient rating.

### `gold_outcome_mart`
Discharge outcome analysis mart (`Discharged`, `Transferred`, `Expired`, `AMA`).
- `outcome` (TEXT): Discharge status description.
- `total_patients` (INTEGER): Number of patients in outcome category.
- `share_pct` (REAL): Share of total hospital discharges.
- `avg_cost` (REAL): Average treatment cost.
- `readmission_rate_pct` (REAL): Readmission rate for outcome category.
