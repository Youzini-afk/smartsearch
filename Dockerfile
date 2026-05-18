FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md README.zh-CN.md ./
COPY src ./src

RUN pip install --upgrade pip \
    && pip install ".[postgres,mcp]"

EXPOSE 8000

CMD ["sh", "-c", "uvicorn smart_search.server.app:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}"]
