# --- shared python image -----------------------------------------------------
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# FFmpeg + ffprobe for the media engine, fonts for burned-in subtitles
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core fonts-liberation curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY apps/api/pyproject.toml ./pyproject.toml
COPY apps/api/app ./app
RUN pip install ".[temporal]" \
    && useradd --create-home --uid 10001 factory \
    && mkdir -p /app/storage && chown -R factory:factory /app/storage
COPY apps/api/alembic ./alembic
COPY apps/api/alembic.ini ./alembic.ini
USER factory

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD curl -fsS http://127.0.0.1:8000/api/v1/healthz || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
