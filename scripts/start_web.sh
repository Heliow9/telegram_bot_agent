#!/usr/bin/env bash
set -euo pipefail
export APP_ROLE=${APP_ROLE:-web}
export ENABLE_BACKGROUND_JOBS=${ENABLE_BACKGROUND_JOBS:-false}
exec uvicorn app.main:app --host ${APP_HOST:-0.0.0.0} --port ${APP_PORT:-8000} --workers ${WEB_WORKERS:-2}
