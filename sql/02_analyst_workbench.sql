-- Fixed read-only questions for the current dashboard cohort.
-- Scope: scope_encounters contains ONLY the selected, validated records.
-- There is no generated SQL editor or implicit access to the reference dataset.

-- name: cost_by_condition
WITH condition_totals AS (
    SELECT condition,
           COUNT(*) AS records,
           SUM(cost) AS total_cost,
           AVG(cost) AS avg_cost,
           SUM(CASE WHEN readmission = 'Yes' THEN 1 ELSE 0 END) AS readmitted
    FROM scope_encounters
    GROUP BY condition
)
SELECT condition, records,
       ROUND(total_cost, 2) AS total_cost,
       ROUND(avg_cost, 2) AS avg_cost,
       ROUND(100.0 * total_cost / NULLIF(SUM(total_cost) OVER (), 0), 2) AS cost_share_pct,
       readmitted,
       ROUND(100.0 * readmitted / records, 2) AS readmission_rate_pct
FROM condition_totals
ORDER BY total_cost DESC, condition;

-- name: readmission_by_gender
SELECT gender,
       COUNT(*) AS records,
       SUM(CASE WHEN readmission = 'Yes' THEN 1 ELSE 0 END) AS readmitted,
       ROUND(100.0 * SUM(CASE WHEN readmission = 'Yes' THEN 1 ELSE 0 END) / COUNT(*), 2) AS readmission_rate_pct,
       ROUND(AVG(cost), 2) AS avg_cost,
       ROUND(AVG(length_of_stay), 2) AS avg_stay_days
FROM scope_encounters
GROUP BY gender
ORDER BY gender;

-- name: cost_by_readmission
SELECT readmission,
       COUNT(*) AS records,
       ROUND(SUM(cost), 2) AS total_cost,
       ROUND(AVG(cost), 2) AS avg_cost,
       ROUND(AVG(length_of_stay), 2) AS avg_stay_days,
       ROUND(100.0 * SUM(cost) / NULLIF((SELECT SUM(cost) FROM scope_encounters), 0), 2) AS cost_share_pct
FROM scope_encounters
GROUP BY readmission
ORDER BY readmission;

-- name: outcomes_by_condition
SELECT condition,
       COUNT(*) AS records,
       SUM(CASE WHEN outcome = 'Recovered' THEN 1 ELSE 0 END) AS recovered,
       ROUND(100.0 * SUM(CASE WHEN outcome = 'Recovered' THEN 1 ELSE 0 END) / COUNT(*), 2) AS recovered_rate_pct,
       ROUND(AVG(satisfaction), 2) AS avg_satisfaction
FROM scope_encounters
GROUP BY condition
ORDER BY records DESC, condition;
