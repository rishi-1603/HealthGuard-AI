import os
import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

@st.cache_data(ttl=300)
def get_json(endpoint: str):
    url = f"{API_BASE_URL}{endpoint}"
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return response.json()

def post_json(endpoint: str, payload: dict):
    url = f"{API_BASE_URL}{endpoint}"
    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()
