{{ config(materialized='view') }}

with source as (
    select * from {{ source('raw_hospital', 'bronze_encounters') }}
),
renamed as (
    select
        cast(Patient_ID as integer) as patient_id,
        cast(Age as integer) as age,
        trim(Gender) as gender,
        trim(Condition) as condition,
        trim(Procedure) as procedure_name,
        cast(Cost as double) as cost,
        cast(Length_of_Stay as integer) as length_of_stay,
        case when trim(Readmission) = 'Yes' then 1 else 0 end as readmission_flag,
        trim(Outcome) as outcome,
        cast(Satisfaction as integer) as satisfaction,
        _ingested_at as ingested_at
    from source
)
select * from renamed
