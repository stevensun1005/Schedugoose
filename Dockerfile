# Schedugoose API — GenAI course planner (FastAPI + LangGraph + OR-Tools).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps first for better layer caching.
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install ".[llm,rag]" || true

# App source.
COPY . .
RUN pip install -e ".[llm,rag]"

EXPOSE 8000

# Container healthcheck hits the API's own /health probe.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=4).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
