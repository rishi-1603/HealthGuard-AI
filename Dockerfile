FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python scripts/generate_data.py && python scripts/train_models.py
EXPOSE 8000
CMD ["uvicorn","app.api.main:app","--host","0.0.0.0","--port","8000"]
