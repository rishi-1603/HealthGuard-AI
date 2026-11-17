{{ config(materialized='incremental', unique_key='patient_id') }}

with clinical_history as (
    select * from {{ ref('int_patient_clinical_history') }}
)
select
    patient_id,
    age,
    age_band,
    gender,
    condition,
    procedure_name,
    cost,
    length_of_stay,
    cost_per_day,
    readmission_flag,
    outcome,
    satisfaction,
    current_timestamp as mart_updated_at
from clinical_history
{% if is_incremental() %}
    -- Idempotent incremental filtering
    where current_timestamp >= (select coalesce(max(mart_updated_at), cast('1970-01-01 00:00:00' as timestamp)) from {{ this }})
{% endif %}
