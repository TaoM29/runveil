FROM ghcr.io/astral-sh/uv:0.12.19@sha256:04d046b13e60d6bcec73cbc5e1cad25d680dea90c8573340950a0ac2d1aef424 AS uv
FROM python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3 AS build
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY apps/api apps/api
COPY apps/worker apps/worker
COPY packages packages
RUN uv sync --locked --no-dev --no-editable --package runveil-api --package runveil-worker --no-cache

FROM python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY alembic.ini ./
COPY packages/persistence/migrations packages/persistence/migrations
COPY scripts/cloud_entrypoint.py scripts/cloud_entrypoint.py
COPY deploy/certs/rds.pem certs/rds.pem
VOLUME ["/tmp"]
USER 65532:65532
ENTRYPOINT ["python", "scripts/cloud_entrypoint.py"]
