# Prediction Point & Feature Boundary Methodology
**Use Case:** 30-Day Inpatient All-Cause Readmission Risk Modeling  
**Dataset Grain:** 984 Inpatient Admission Encounters

---

## 1. Defining the Clinical Decision Moment

To avoid catastrophic target leakage in prospective predictive healthcare models, the feature space must strictly respect chronological boundaries:

```
[Timeline Point 1: Admission]        [Timeline Point 2: In-Hospital Stay]        [Timeline Point 3: DISCHARGE]
  * Patient Demographics               * Daily Lab Trends & Panels                  * Final Completed Length of Stay
  * Primary Inpatient Diagnosis        * Procedures Administered                    * Total Inpatient Cost Incurred
  * Baseline Comorbidity Index         * In-Hospital Complications                  * Discharge Disposition / Destination
  * Historical Utilization             * Discharge Medication Count                 * Planned Post-Acute Follow-up
                                                                                    
                                                                                    ▲
                                                                                    │
                                                                 [CANONICAL PREDICTION MOMENT]
                                                                 "Which patients need post-discharge 
                                                                  transitional care management?"
```

---

## 2. Feature Eligibility Matrix

| Variable Name | Availability Point | Prospective Model Status | Leakage Risk Assessment |
|---|---|---|---|
| `admission_age` | At Admission | **Eligible** | Zero leakage |
| `gender` | At Admission | **Eligible** | Zero leakage |
| `primary_condition` | At Admission | **Eligible** | Zero leakage |
| `comorbidity_score` | At Admission | **Eligible** | Zero leakage |
| `procedure_type` | In-Hospital | **Eligible (at discharge)** | Valid only if completed during stay |
| `medication_count` | In-Hospital | **Eligible (at discharge)** | Valid discharge prescription record |
| `length_of_stay` | At Discharge | **Eligible (at discharge)** | Total realized inpatient duration |
| `total_inpatient_cost` | At Discharge | **Eligible (at discharge)** | Final billed cost |
| `readmission_30d` | Post-Discharge (Day 1-30) | **TARGET VARIABLE ONLY** | Target label — strictly forbidden in features |
