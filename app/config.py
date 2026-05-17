from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()


def _env_bool(name: str, default: str = "false") -> bool:
    return str(os.getenv(name, default)).strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: str = "") -> list[str]:
    raw = str(os.getenv(name, default)).strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


class Settings(BaseModel):
    app_name: str = os.getenv("APP_NAME", "Bot Bet 1x2")
    app_env: str = os.getenv("APP_ENV", "dev")
    app_host: str = os.getenv("APP_HOST", "127.0.0.1")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    app_role: str = os.getenv("APP_ROLE", "web").strip().lower()
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_dir: str = os.getenv("LOG_DIR", "logs")

    redis_url: str = os.getenv("REDIS_URL", "")
    celery_result_backend: str = os.getenv("CELERY_RESULT_BACKEND", "")
    cache_enabled: bool = _env_bool("CACHE_ENABLED", "true")
    cache_prefix: str = os.getenv("CACHE_PREFIX", "botbet")
    cache_default_ttl_seconds: int = int(os.getenv("CACHE_DEFAULT_TTL_SECONDS", "300"))

    signal_min_score: float = float(os.getenv("SIGNAL_MIN_SCORE", "0.72"))
    signal_min_probability: float = float(os.getenv("SIGNAL_MIN_PROBABILITY", "0.52"))
    signal_max_risk_penalty: float = float(os.getenv("SIGNAL_MAX_RISK_PENALTY", "0.22"))

    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    telegram_channel_chat_id: str = os.getenv("TELEGRAM_CHANNEL_CHAT_ID", "")

    sportsdb_api_key: str = os.getenv("SPORTSDB_API_KEY", "123")
    sportsdb_base_url: str = os.getenv(
        "SPORTSDB_BASE_URL",
        "https://www.thesportsdb.com/api/v1/json",
    )

    football_api_key: str = os.getenv("FOOTBALL_API_KEY", "")
    football_api_base_url: str = os.getenv(
        "FOOTBALL_API_BASE_URL",
        "https://v3.football.api-sports.io",
    )

    timezone: str = os.getenv("TIMEZONE", "America/Recife")

    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    odds_api_key: str = os.getenv("ODDS_API_KEY", "")
    odds_regions: str = os.getenv("ODDS_REGIONS", "eu")
    odds_markets: str = os.getenv("ODDS_MARKETS", "h2h")
    odds_format: str = os.getenv("ODDS_FORMAT", "decimal")
    value_bet_edge: float = float(os.getenv("VALUE_BET_EDGE", "0.05"))

    live_monitor_enabled: bool = _env_bool("LIVE_MONITOR_ENABLED", "true")
    live_monitor_interval_seconds: int = int(os.getenv("LIVE_MONITOR_INTERVAL_SECONDS", "120"))
    live_minute_checkpoints: str = os.getenv("LIVE_MINUTE_CHECKPOINTS", "15,30,45,60,75")
    live_signal_min_shots_diff: int = int(os.getenv("LIVE_SIGNAL_MIN_SHOTS_DIFF", "4"))
    live_signal_min_on_target_diff: int = int(os.getenv("LIVE_SIGNAL_MIN_ON_TARGET_DIFF", "2"))
    live_signal_min_possession_diff: int = int(os.getenv("LIVE_SIGNAL_MIN_POSSESSION_DIFF", "8"))

    enable_background_jobs: bool = _env_bool("ENABLE_BACKGROUND_JOBS", "false")
    run_post_deploy_sync_on_startup: bool = _env_bool("RUN_POST_DEPLOY_SYNC_ON_STARTUP", "false")
    run_missed_summary_recovery_on_startup: bool = _env_bool("RUN_MISSED_SUMMARY_RECOVERY_ON_STARTUP", "false")
    create_tables_on_startup: bool = _env_bool("CREATE_TABLES_ON_STARTUP", "true")
    request_log_enabled: bool = _env_bool("REQUEST_LOG_ENABLED", "true")
    cors_origins: list[str] = _env_list("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,https://bot-bet-front.onrender.com")

    database_url: str = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://root:password@localhost:3306/bot_bet",
    )

    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "change-this-secret")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    jwt_access_token_expire_minutes: int = int(
        os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "1440")
    )


settings = Settings()
