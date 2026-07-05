# Dockerfile.api
FROM python:3.11-slim

WORKDIR /app

# System deps for psycopg2 and sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl && rm -rf /var/lib/apt/lists/*

COPY ml/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    fastapi uvicorn[standard] prometheus-fastapi-instrumentator

COPY api/     ./api/
COPY ml/      ./ml/
COPY rag/     ./rag/

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
