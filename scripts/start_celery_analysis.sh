#!/usr/bin/env bash
set -euo pipefail
exec celery -A app.workers.celery_app.celery_app worker -Q analysis -n analysis@%h --loglevel=${LOG_LEVEL:-INFO} --concurrency=${ANALYSIS_CONCURRENCY:-2}
