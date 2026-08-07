#!/bin/sh
# Idempotent startup: migrations and seed data are safe to re-run on every
# container start (Alembic no-ops when already at head; seed data is
# UPSERT-based). The final `exec` replaces this shell with uvicorn as PID 1
# so it receives SIGTERM directly and shuts down gracefully - no shell
# wrapper left in between to swallow the signal.
set -e

echo "[entrypoint] running database migrations..."
alembic upgrade head

echo "[entrypoint] seeding reference data..."
python -m app.infrastructure.database.seed

echo "[entrypoint] starting application..."
exec "$@"
