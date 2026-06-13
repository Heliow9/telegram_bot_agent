#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

sudo systemctl enable --now redis-server
redis-cli ping

if [[ -x "${ROOT_DIR}/venv/bin/pip" ]]; then
  "${ROOT_DIR}/venv/bin/pip" install -r requirements.txt
fi

pm2 delete celery >/dev/null 2>&1 || true
pm2 delete worker-analysis >/dev/null 2>&1 || true
chmod +x scripts/start_celery_analysis.sh scripts/start_scheduler.sh scripts/start_web.sh
pm2 start scripts/start_celery_analysis.sh --name worker-analysis --interpreter bash --cwd "${ROOT_DIR}"

if pm2 describe api >/dev/null 2>&1; then
  pm2 restart api --update-env
fi
if pm2 describe scheduler >/dev/null 2>&1; then
  pm2 restart scheduler --update-env
fi

pm2 save
pm2 list

echo
printf 'Worker registrado:\n'
"${ROOT_DIR}/venv/bin/celery" -A app.workers.celery_app.celery_app inspect registered 2>/dev/null | grep -i basketball -C 4 || true
