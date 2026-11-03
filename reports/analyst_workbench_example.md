# Recorded cost review

Report generated (UTC): Reproducible example; dataset version as committed
This is a synthetic-data analysis snapshot, not a care-period or clinical report.

## Population and evidence
- Selected records: 65; full reference: 984.
- The reference includes the selection. It is not an independent control group.
- Each record is one synthetic patient, not a validated admission timeline.
- Selected scope ID: 2c11efed5d06d5c92829
- Reference scope ID: f703d2727895fdc3aa3f
- Both source and selected data-contract checks: PASS.

## Selected cohort versus reference
Differences use unrounded metrics; displayed numbers use two-decimal half-up rounding.
| Metric | Selected | Full reference | Difference | Difference unit |
|---|---:|---:|---:|---|
| Readmission rate | 1.54 % | 26.83 % | -25.29 | percentage points |
| Mean recorded cost | 2,000.00 INR | 8,367.48 INR | -6,367.48 | INR |
| Mean length of stay | 36.09 days | 37.66 days | -1.57 | days |
| Recovered outcome rate | 0.00 % | 60.06 % | -60.06 | percentage points |

## Executed SQL question
Where is recorded cost concentrated?

SQL/pandas reconciliation: PASS (7 result cells checked).
```sql
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
```

## Scoped SQL results
| condition | records | total_cost | avg_cost | cost_share_pct | readmitted | readmission_rate_pct |
| --- | --- | --- | --- | --- | --- | --- |
| Diabetes | 65 | 130000.0 | 2000.0 | 100.0 | 1 | 1.54 |

## Interpretation and next checks
Review which conditions account for recorded cost, then check case mix and data definitions before attributing the difference to a service or intervention. Recorded cost is not an estimate of preventable savings.

## Boundaries
No diagnosis, treatment or care prioritisation is supported. No model or provider generated the report numbers. Aggregate output is not a certification of privacy, clinical validity or causal business impact.
