#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERRO: .env não encontrado em ${ENV_FILE}" >&2
  exit 1
fi

upsert_env() {
  local key="$1"
  local value="$2"
  if grep -qE "^${key}=" "${ENV_FILE}"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "${ENV_FILE}"
  else
    printf '\n%s=%s\n' "${key}" "${value}" >> "${ENV_FILE}"
  fi
}

upsert_env CACHE_ENABLED true
upsert_env REDIS_URL redis://localhost:6379/0
upsert_env SPORTSDB_PROXY_ENABLED true
upsert_env SPORTSDB_MAX_REQUESTS_PER_MINUTE 15
upsert_env SPORTSDB_MIN_INTERVAL_SECONDS 4.2
upsert_env SPORTSDB_REQUEST_TIMEOUT_SECONDS 8
upsert_env SPORTSDB_RATE_LIMIT_MAX_WAIT_SECONDS 4
upsert_env SPORTSDB_429_COOLDOWN_SECONDS 180
upsert_env SPORTSDB_SINGLEFLIGHT_WAIT_SECONDS 10
upsert_env SPORTSDB_STALE_TTL_SECONDS 604800
upsert_env SPORTSDB_EVENTSDAY_CACHE_TTL_SECONDS 1800
upsert_env SPORTSDB_NEXTLEAGUE_CACHE_TTL_SECONDS 3600
upsert_env SPORTSDB_TEAM_CACHE_TTL_SECONDS 21600
upsert_env SPORTSDB_TABLE_CACHE_TTL_SECONDS 43200
upsert_env SPORTSDB_EVENT_CACHE_TTL_SECONDS 90
upsert_env SPORTSDB_ENABLE_LEAGUE_NAME_FALLBACK false
upsert_env SPORTSDB_ENABLE_NEXTLEAGUE_FALLBACK true
upsert_env SPORTSDB_MAX_FALLBACK_CALLS_PER_10MIN 3
upsert_env BASKETBALL_PREFETCH_DAYS 8
upsert_env ANALYSIS_CONCURRENCY 1

echo "Perfil gratuito aplicado em ${ENV_FILE}."
echo "Agora execute: bash scripts/restart_botbet_services.sh"
