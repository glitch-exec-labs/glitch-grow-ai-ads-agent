# syntax=docker/dockerfile:1.7
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps: gcc for asyncpg/orjson wheels that occasionally miss, curl for healthchecks
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential curl \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --upgrade pip && pip install -e .

# Cloud Run injects PORT env; uvicorn must bind to it. Default 8080 for local.
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn ads_agent.server:app --host 0.0.0.0 --port ${PORT}"]
