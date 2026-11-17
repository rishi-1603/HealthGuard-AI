{{ config(materialized='view') }}

with source as (
    select * from {{ source('raw_fhir', 'bronze_patients') }}
),
renamed as (
    select
        patient_id,
        native_id,
        trim(gender) as gender,
        birth_date,
        region,
        insurance,
        source_system
    from source
)
select * from renamed
