-- ============================================================
--  schema.sql — HealthGuard AI analytics schema
--
--  The original file contained a single audit_logs stub. This
--  version keeps that table (it is still useful) and adds the
--  analytical schema the project was missing.
--
--  Design: one fact table (patient_encounters) plus two
--  dimension views. The dataset is a single flat file, so the
--  dimensions are views over the fact rather than separate
--  tables — that keeps the loader simple and avoids inventing
--  data that does not exist.
--
--  Conventions (must match data/metrics.json and the pandas path
--  in scripts/sql_analytics.py):
--    readmission_flag   1 when Readmission = 'Yes', else 0
--    readmitted_cost    Cost attributed to readmitted patients
--    cost_per_day       Cost / Length_of_Stay
--    age_band           18-30 / 31-45 / 46-60 / 61-75 / 76+
-- ============================================================

CREATE TABLE IF NOT EXISTS audit_logs (
    id         INTEGER PRIMARY KEY,
    user_id    TEXT,
    action     TEXT,
    patient_id TEXT,
    created_at TEXT
);

-- ── FACT: one row per patient encounter ────────────────────
CREATE TABLE IF NOT EXISTS patient_encounters (
    patient_id      INTEGER PRIMARY KEY,
    age             INTEGER NOT NULL,
    age_band        TEXT    NOT NULL,
    gender          TEXT    NOT NULL,
    condition       TEXT    NOT NULL,
    procedure_name  TEXT    NOT NULL,
    cost            REAL    NOT NULL CHECK (cost >= 0),
    length_of_stay  INTEGER NOT NULL CHECK (length_of_stay >= 0),
    readmitted      TEXT    NOT NULL CHECK (readmitted IN ('Yes', 'No')),
    readmission_flag INTEGER NOT NULL CHECK (readmission_flag IN (0, 1)),
    outcome         TEXT    NOT NULL,
    satisfaction    INTEGER,
    cost_per_day    REAL
);

CREATE INDEX IF NOT EXISTS idx_enc_condition   ON patient_encounters(condition);
CREATE INDEX IF NOT EXISTS idx_enc_age_band    ON patient_encounters(age_band);
CREATE INDEX IF NOT EXISTS idx_enc_readmitted  ON patient_encounters(readmission_flag);
CREATE INDEX IF NOT EXISTS idx_enc_gender      ON patient_encounters(gender);

-- ── DIMENSION VIEWS ────────────────────────────────────────
-- Condition-level rollup: where risk and cost concentrate.
CREATE VIEW IF NOT EXISTS dim_condition AS
SELECT
    condition,
    COUNT(*)                                    AS patients,
    SUM(readmission_flag)                       AS readmitted,
    ROUND(AVG(readmission_flag) * 100, 2)       AS readmission_rate_pct,
    ROUND(SUM(cost), 2)                         AS total_cost,
    ROUND(AVG(cost), 2)                         AS avg_cost,
    ROUND(AVG(length_of_stay), 2)               AS avg_los,
    ROUND(AVG(satisfaction), 2)                 AS avg_satisfaction
FROM patient_encounters
GROUP BY condition;

-- Age-band rollup: the demographic risk curve.
CREATE VIEW IF NOT EXISTS dim_age_band AS
SELECT
    age_band,
    COUNT(*)                                    AS patients,
    SUM(readmission_flag)                       AS readmitted,
    ROUND(AVG(readmission_flag) * 100, 2)       AS readmission_rate_pct,
    ROUND(AVG(cost), 2)                         AS avg_cost,
    ROUND(AVG(length_of_stay), 2)               AS avg_los
FROM patient_encounters
GROUP BY age_band;

-- Outcome mix: recovery / stability distribution.
CREATE VIEW IF NOT EXISTS dim_outcome AS
SELECT
    outcome,
    COUNT(*)                                    AS patients,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM patient_encounters), 2)
                                                AS share_pct,
    ROUND(AVG(cost), 2)                         AS avg_cost,
    ROUND(AVG(readmission_flag) * 100, 2)       AS readmission_rate_pct
FROM patient_encounters
GROUP BY outcome;
