-- ============================================================
--  01_readmission_cost_burden.sql
--  The question the hospital CFO actually asks:
--  what do readmissions cost us, and where do they concentrate?
--
--  Verified pattern (scripts/sql_analytics.py reproduces these
--  numbers in pandas — parity is test-enforced):
--    264 of 984 patients readmitted (26.8%) hold 43.8% of cost
--    ₹13,650 per readmitted patient vs ₹6,431 for the rest (+112.3%)
-- ============================================================

-- ── 1. The headline cost burden ────────────────────────────
-- Business Question: How much of our cost sits with readmitted patients?
-- Why It Matters:   If a minority of patients holds a large share of cost,
--                   the intervention target is decided, not debated.
SELECT
    readmitted,
    COUNT(*)                                              AS patients,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM patient_encounters), 2)
                                                          AS patient_share_pct,
    ROUND(SUM(cost), 0)                                   AS total_cost,
    ROUND(SUM(cost) * 100.0 / (SELECT SUM(cost) FROM patient_encounters), 2)
                                                          AS cost_share_pct,
    ROUND(AVG(cost), 0)                                   AS avg_cost_per_patient,
    ROUND(AVG(length_of_stay), 1)                         AS avg_los_days
FROM patient_encounters
GROUP BY readmitted
ORDER BY readmitted DESC;


-- ── 2. Cost premium of readmission ────────────────────────
-- Business Question: What does one readmission cost on average?
-- Why It Matters:   This is the V in any expected-value calculation.
SELECT
    ROUND(AVG(CASE WHEN readmission_flag = 1 THEN cost END), 0)  AS avg_cost_readmitted,
    ROUND(AVG(CASE WHEN readmission_flag = 0 THEN cost END), 0)  AS avg_cost_not_readmitted,
    ROUND(
        (AVG(CASE WHEN readmission_flag = 1 THEN cost END)
         - AVG(CASE WHEN readmission_flag = 0 THEN cost END))
        / AVG(CASE WHEN readmission_flag = 0 THEN cost END) * 100, 1
    )                                                            AS cost_premium_pct,
    ROUND(SUM(CASE WHEN readmission_flag = 1 THEN cost
                   - (SELECT AVG(cost) FROM patient_encounters) END), 0)
                                                                 AS excess_cost_above_average
FROM patient_encounters;


-- ── 3. Where readmission concentrates by condition ────────
-- Business Question: Which conditions drive the readmission cost?
-- Why It Matters:   Targeting starts where the excess cost is largest,
--                   not where the rate is highest.
SELECT
    condition,
    COUNT(*)                                              AS patients,
    SUM(readmission_flag)                                 AS readmitted,
    ROUND(AVG(readmission_flag) * 100, 1)                 AS readmission_rate_pct,
    ROUND(SUM(CASE WHEN readmission_flag = 1 THEN cost END), 0)
                                                          AS readmission_cost,
    ROUND(AVG(cost), 0)                                   AS avg_cost,
    ROUND(AVG(length_of_stay), 1)                         AS avg_los
FROM patient_encounters
GROUP BY condition
HAVING SUM(readmission_flag) > 0
ORDER BY readmission_cost DESC;


-- ── 4. Age-band risk curve ────────────────────────────────
-- Business Question: At what age does readmission risk rise?
-- Why It Matters:   Defines the cohort for a follow-up programme.
-- Caveat:           small bands are reported with their n, and the
--                   Python layer refuses to compute confidence
--                   intervals where n is too small (see model docs).
SELECT
    age_band,
    COUNT(*)                                              AS patients,
    SUM(readmission_flag)                                 AS readmitted,
    ROUND(AVG(readmission_flag) * 100, 1)                 AS readmission_rate_pct,
    ROUND(AVG(cost), 0)                                   AS avg_cost
FROM patient_encounters
GROUP BY age_band
ORDER BY
    CASE age_band
        WHEN '18-30' THEN 1 WHEN '31-45' THEN 2 WHEN '46-60' THEN 3
        WHEN '61-75' THEN 4 ELSE 5
    END;


-- ── 5. Cost per day of stay — efficiency, not just volume ─
-- Business Question: Which conditions consume the most resource per day?
-- Why It Matters:   A long cheap stay and a short expensive one are
--                   different operational problems.
SELECT
    condition,
    ROUND(AVG(cost_per_day), 0)                           AS avg_cost_per_day,
    ROUND(AVG(length_of_stay), 1)                         AS avg_los,
    ROUND(AVG(cost), 0)                                   AS avg_cost,
    COUNT(*)                                              AS patients
FROM patient_encounters
GROUP BY condition
ORDER BY avg_cost_per_day DESC
LIMIT 10;


-- ── 6. Outcome mix and its cost ───────────────────────────
-- Business Question: Does a good outcome cost less?
-- Why It Matters:   Tests the assumption behind "quality saves money".
SELECT
    outcome,
    COUNT(*)                                              AS patients,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM patient_encounters), 1)
                                                          AS share_pct,
    ROUND(AVG(cost), 0)                                   AS avg_cost,
    ROUND(AVG(readmission_flag) * 100, 1)                 AS readmission_rate_pct,
    ROUND(AVG(satisfaction), 2)                           AS avg_satisfaction
FROM patient_encounters
GROUP BY outcome
ORDER BY patients DESC;


-- ── 7. Gender split — the fairness lens ───────────────────
-- Business Question: Are outcomes and costs equal across genders?
-- Why It Matters:   The model reports an AUC gap of 0.006 but a large
--                   base-rate disparity (F 43.9% vs M 7.4%). This query
--                   is the SQL side of that disclosure.
SELECT
    gender,
    COUNT(*)                                              AS patients,
    SUM(readmission_flag)                                 AS readmitted,
    ROUND(AVG(readmission_flag) * 100, 1)                 AS readmission_rate_pct,
    ROUND(AVG(cost), 0)                                   AS avg_cost,
    ROUND(AVG(length_of_stay), 1)                         AS avg_los,
    ROUND(AVG(satisfaction), 2)                           AS avg_satisfaction
FROM patient_encounters
GROUP BY gender;
