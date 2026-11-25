# Same image runs locally and on Azure Container Apps / App Service.
# Configuration comes from environment variables (Key Vault references in Azure).
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home appuser && mkdir -p /app/var /app/eval/results && chown -R appuser /app/var /app/eval/results
USER appuser

EXPOSE 8501
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"
CMD ["streamlit", "run", "app/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
