"""
Data access layer for the hospital outcomes dataset (984 patients).
Pure stats/outcomes dashboard -- no risk model, per user's request.
"""
from pathlib import Path

import pandas as pd
import streamlit as st

DATA_PATH = Path("data/hospital/hospital_data.csv")


@st.cache_data(ttl=600)
def load_patients() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH)
    return df


def get_kpis(df: pd.DataFrame) -> dict:
    total = len(df)
    readmit_rate = (df.Readmission == "Yes").mean() * 100 if total else 0
    recovered_rate = (df.Outcome == "Recovered").mean() * 100 if total else 0
    return {
        "total_patients": total,
        "avg_age": round(df.Age.mean(), 1) if total else 0,
        "avg_cost": round(df.Cost.mean(), 0) if total else 0,
        "total_cost": round(df.Cost.sum(), 0) if total else 0,
        "avg_los": round(df.Length_of_Stay.mean(), 1) if total else 0,
        "readmission_rate": round(readmit_rate, 1),
        "recovered_rate": round(recovered_rate, 1),
        "avg_satisfaction": round(df.Satisfaction.mean(), 2) if total else 0,
    }


def condition_summary(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("Condition").agg(
        patients=("Patient_ID", "count"),
        avg_cost=("Cost", "mean"),
        avg_los=("Length_of_Stay", "mean"),
        readmission_rate=("Readmission", lambda x: (x == "Yes").mean() * 100),
        avg_satisfaction=("Satisfaction", "mean"),
    ).reset_index().sort_values("patients", ascending=False)
    return g


def apply_filters(df: pd.DataFrame, conditions, genders, outcomes, age_range) -> pd.DataFrame:
    out = df.copy()
    if conditions:
        out = out[out.Condition.isin(conditions)]
    if genders:
        out = out[out.Gender.isin(genders)]
    if outcomes:
        out = out[out.Outcome.isin(outcomes)]
    out = out[(out.Age >= age_range[0]) & (out.Age <= age_range[1])]
    return out


def patient_profile(df: pd.DataFrame, patient_id: int) -> dict:
    row = df[df.Patient_ID == patient_id]
    if row.empty:
        return {}
    r = row.iloc[0]
    cost_percentile = float((df.Cost < r.Cost).mean() * 100)
    return {
        "patient_id": int(r.Patient_ID),
        "age": int(r.Age),
        "gender": r.Gender,
        "condition": r.Condition,
        "procedure": r.Procedure,
        "cost": int(r.Cost),
        "los": int(r.Length_of_Stay),
        "readmission": r.Readmission,
        "outcome": r.Outcome,
        "satisfaction": int(r.Satisfaction),
        "cost_percentile": round(cost_percentile, 1),
    }
