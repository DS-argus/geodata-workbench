FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       gdal-bin \
       libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /workspace

COPY pyproject.toml README.md ./
COPY apps/api ./apps/api
COPY resources ./resources

RUN uv pip install --system --no-cache .

EXPOSE 8000

CMD ["sh", "-c", "alembic -c apps/api/alembic.ini upgrade head && uvicorn app.api:app --host 0.0.0.0 --port 8000"]
