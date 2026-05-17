#!/usr/bin/env bash
set -euo pipefail
exec celery -A app.workers.celery_app.celery_app worker -Q telegram -n telegram@%h --loglevel=${LOG_LEVEL:-INFO} --concurrency=${TELEGRAM_CONCURRENCY:-1}
