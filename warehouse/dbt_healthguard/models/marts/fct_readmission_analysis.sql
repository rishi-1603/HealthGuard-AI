{{ config(materialized='table') }}

with summary as (
    select * from {{ ref('int_condition_cost_summary') }}
)
select
    condition,
    total_patients,
    readmitted_count,
    readmission_rate_pct,
    total_cost,
    avg_cost,
    avg_los,
    avg_satisfaction,
    case
        when readmission_rate_pct >= 30.0 then 'HIGH_RISK'
        when readmission_rate_pct >= 20.0 then 'MODERATE_RISK'
        else 'LOW_RISK'
    end as risk_tier
from summary
