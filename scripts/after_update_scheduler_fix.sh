#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
source venv/bin/activate
pip install -r requirements.txt
rm -f data/sent_summaries.json data/sent_alerts.json || true
pm2 restart api scheduler worker-analysis celery-beat || pm2 restart all
pm2 status
