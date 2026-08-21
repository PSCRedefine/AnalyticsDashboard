# One image, two entry points. The API and the dashboard share every dependency
# except Streamlit's, and building twice to save a few megabytes would mean two
# images that can drift apart. The compose file picks the command.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir --no-deps -e .

COPY app.py ./
COPY .streamlit/ ./.streamlit/
COPY models/ ./models/
COPY data/ ./data/
COPY scripts/ ./scripts/

RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000 8501

CMD ["uvicorn", "analytics_dashboard.api:app", "--host", "0.0.0.0", "--port", "8000"]
