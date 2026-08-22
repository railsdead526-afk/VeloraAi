# syntax=docker/dockerfile:1

# --- build stage: compile wheels so the runtime image carries no toolchain ---
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# `upgrade` matters: the base image lags security updates between releases,
# and Trivy gates the build on fixable HIGH/CRITICAL findings.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN pip wheel --wheel-dir=/wheels -r requirements.txt


# --- runtime stage ---
FROM python:3.11-slim AS runtime

ARG APP_VERSION=0.0.0
ARG GIT_SHA=unknown

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA}

LABEL org.opencontainers.image.title="VeloraAi" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.licenses="Proprietary"

RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/* \
    && find /usr/local/lib/python3.11 -name '__pycache__' -type d -prune -exec rm -rf {} + \
    && rm -rf /root/.cache

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY app ./app
COPY alembic ./alembic
COPY scripts ./scripts
COPY alembic.ini pyproject.toml docker-entrypoint.sh ./

# A runtime image does not install packages, so pip, setuptools, and wheel are
# pure attack surface. They also drag in vendored dependencies that are
# routinely flagged (setuptools CVE-2025-47273, pip's bundled msgpack) even
# though nothing here imports them. Remove them outright rather than chasing
# their advisories forever.
RUN python -m pip uninstall -y pip setuptools wheel 2>/dev/null || true; \
    rm -rf /usr/local/lib/python3.11/site-packages/pip \
           /usr/local/lib/python3.11/site-packages/pip-*.dist-info \
           /usr/local/lib/python3.11/site-packages/setuptools \
           /usr/local/lib/python3.11/site-packages/setuptools-*.dist-info \
           /usr/local/lib/python3.11/site-packages/pkg_resources \
           /usr/local/lib/python3.11/site-packages/wheel \
           /usr/local/lib/python3.11/site-packages/wheel-*.dist-info \
           /usr/local/lib/python3.11/ensurepip

# Fail the build here, not in production, if that removal broke an import.
RUN python -c "import app.main; import scripts.run_maintenance; print('import smoke test ok')" \
    && python -c "import alembic.config; print('alembic ok')" \
    && find /app -name '__pycache__' -type d -prune -exec rm -rf {} +

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chmod +x /app/docker-entrypoint.sh \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Liveness only; orchestrators should probe /api/v1/ready for traffic gating.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/v1/health || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers"]
