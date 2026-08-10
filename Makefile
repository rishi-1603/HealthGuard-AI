setup:
	pip install -r requirements.txt

ui:
	streamlit run app/dashboard/Home.py

test:
	pytest -q
