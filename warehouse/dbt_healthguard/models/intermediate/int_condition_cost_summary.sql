{{ config(materialized='table') }}

with history as (
    select * from {{ ref('int_patient_clinical_history') }}
),
aggregated as (
    select
        condition,
        count(*) as total_patients,
        sum(readmission_flag) as readmitted_count,
        round(100.0 * sum(readmission_flag) / count(*), 2) as readmission_rate_pct,
        round(sum(cost), 2) as total_cost,
        round(avg(cost), 2) as avg_cost,
        round(avg(length_of_stay), 2) as avg_los,
        round(avg(satisfaction), 2) as avg_satisfaction
    from history
    group by condition
)
select * from aggregated
