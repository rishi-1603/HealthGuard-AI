{{ config(materialized='table') }}

with encounters as (
    select * from {{ ref('stg_hospital_encounters') }}
),
enriched as (
    select
        patient_id,
        age,
        case
            when age <= 30 then '18-30'
            when age <= 45 then '31-45'
            when age <= 60 then '46-60'
            when age <= 75 then '61-75'
            else '76+'
        end as age_band,
        gender,
        condition,
        procedure_name,
        cost,
        length_of_stay,
        round(cost / nullif(length_of_stay, 0), 2) as cost_per_day,
        readmission_flag,
        outcome,
        satisfaction
    from encounters
)
select * from enriched
