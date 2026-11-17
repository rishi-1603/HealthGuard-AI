{{ config(materialized='table') }}

with encounters as (
    select * from {{ ref('int_patient_clinical_history') }}
)
select distinct
    patient_id,
    age,
    age_band,
    gender
from encounters
