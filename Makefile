setup:
	python scripts/generate_data.py && python scripts/train_models.py
api:
	uvicorn app.api.main:app --reload
ui:
	streamlit run app/dashboard/Home.py
 test:
	pytest -q
