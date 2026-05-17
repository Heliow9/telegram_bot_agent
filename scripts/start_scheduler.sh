#!/usr/bin/env bash
set -euo pipefail
export APP_ROLE=scheduler
export ENABLE_BACKGROUND_JOBS=true
exec python -m app.worker
