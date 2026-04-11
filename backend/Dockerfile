# backend/Dockerfile
# Multi-stage build for Know Your SAP Masters — Celery Worker Fleet
# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: Builder — install all dependencies
FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libhdb-client-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (all in one layer — better cache)
COPY requirements.txt requirements-memgraph.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt -r requirements-memgraph.txt

# Stage 2: Runtime
FROM python:3.11-slim-bookworm

WORKDIR /app

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libhdb-client3 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Non-root user for security
RUN useradd -m -u 1000 celeryuser && chown -R celeryuser:celeryuser /app
USER celeryuser

# Environment defaults (can be overridden at runtime via docker-compose)
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV CELERY_BROKER_URL=amqp://sapmasters:sapmasters123@rabbitmq:5672//
ENV CELERY_RESULT_BACKEND=redis://redis:6379/0
ENV REDIS_URL=redis://redis:6379/0
ENV QDRANT_URL=http://qdrant:6333
ENV MEMGRAPH_URI=bolt://memgraph:7687

# Default command: start Celery worker
# Override in docker-compose for specific roles (beat, flower, API, etc.)
CMD ["celery", "-A", "app.workers.celery_app", "worker", "--loglevel=info", "--concurrency=8"]
