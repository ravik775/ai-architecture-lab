# syntax=docker/dockerfile:1
# Multi-stage build: uv resolves/installs into a venv in `builder`, the
# runtime stage copies only that venv + app source - no uv, no dev tools,
# no build toolchain in the final image.

FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Dependency metadata first - this layer only invalidates when
# pyproject.toml/uv.lock change, not on every source edit.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Now the application source.
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./


FROM python:3.12-slim AS runtime

RUN groupadd --system weather && useradd --system --gid weather --no-create-home weather

WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=builder --chown=weather:weather /app/.venv /app/.venv
COPY --from=builder --chown=weather:weather /app/app /app/app
COPY --from=builder --chown=weather:weather /app/alembic /app/alembic
COPY --from=builder --chown=weather:weather /app/alembic.ini /app/alembic.ini
COPY --chown=weather:weather docker/entrypoint.sh /app/docker/entrypoint.sh
RUN chmod +x /app/docker/entrypoint.sh && \
    mkdir -p /app/data /app/.nicegui && chown weather:weather /app/data /app/.nicegui
# /app/.nicegui: NiceGUI's app.storage.user (session state - see
# app/ui/pages.py) persists to a file here, relative to WORKDIR. Without
# this, the non-root `weather` user gets a PermissionError trying to
# create it at first request - verified live (see the git history for
# this line for the exact traceback).

USER weather
# 8000: public API/UI. 9464: /metrics - deliberately NOT published to the
# host in docker-compose.yml, reachable only over the internal Docker
# network (e.g. by the prometheus service) - see settings.py's
# `metrics_port` docstring for the reasoning. EXPOSE is documentation only;
# it doesn't itself publish or restrict anything.
EXPOSE 8000 9464

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live', timeout=2)" || exit 1

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
