import json
from pathlib import Path
from typing import Any, Dict

from sqlalchemy import inspect

from app.config import settings
from app.db import SessionLocal, engine
from app.models import RuntimeConfigState


CONFIG_PATH = Path("data/runtime_config.json")
CONFIG_DB_KEY = "default"


DEFAULT_CONFIG = {
    "value_bet_edge": settings.value_bet_edge,
    "live_monitor_enabled": settings.live_monitor_enabled,
    "live_monitor_interval_seconds": settings.live_monitor_interval_seconds,
    "live_minute_checkpoints": settings.live_minute_checkpoints,
    "live_signal_min_shots_diff": settings.live_signal_min_shots_diff,
    "live_signal_min_on_target_diff": settings.live_signal_min_on_target_diff,
    "live_signal_min_possession_diff": settings.live_signal_min_possession_diff,
    "telegram_send_to_main_chat": True,
    "telegram_send_to_channel": True,
    "odds_api_keys": [settings.odds_api_key] if settings.odds_api_key else [],
}


def ensure_runtime_config() -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(
            json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _db_runtime_table_available() -> bool:
    try:
        inspector = inspect(engine)
        return inspector.has_table(RuntimeConfigState.__tablename__)
    except Exception:
        return False


def _load_runtime_config_from_db() -> Dict[str, Any] | None:
    if not _db_runtime_table_available():
        return None

    db = SessionLocal()
    try:
        row = (
            db.query(RuntimeConfigState)
            .filter(RuntimeConfigState.config_key == CONFIG_DB_KEY)
            .first()
        )
        if not row or not row.config_json:
            return None

        raw = json.loads(row.config_json)
        return raw if isinstance(raw, dict) else None
    except Exception as e:
        print(f"[RUNTIME_CONFIG] Erro ao carregar config do banco: {e}")
        return None
    finally:
        db.close()


def _save_runtime_config_to_db(data: Dict[str, Any]) -> None:
    if not _db_runtime_table_available():
        return

    db = SessionLocal()
    try:
        row = (
            db.query(RuntimeConfigState)
            .filter(RuntimeConfigState.config_key == CONFIG_DB_KEY)
            .first()
        )

        payload = json.dumps(data, ensure_ascii=False, indent=2)

        if row is None:
            row = RuntimeConfigState(
                config_key=CONFIG_DB_KEY,
                config_json=payload,
            )
            db.add(row)
        else:
            row.config_json = payload

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[RUNTIME_CONFIG] Erro ao salvar config no banco: {e}")
    finally:
        db.close()


def _sanitize_runtime_config(data: Dict[str, Any]) -> Dict[str, Any]:
    sanitized = DEFAULT_CONFIG.copy()
    sanitized.update(data or {})

    raw_keys = sanitized.get("odds_api_keys", [])

    if isinstance(raw_keys, str):
        raw_keys = [line.strip() for line in raw_keys.splitlines() if line.strip()]
    elif not isinstance(raw_keys, list):
        raw_keys = []

    cleaned_keys = []
    seen = set()

    for item in raw_keys:
        key = str(item or "").strip()
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        cleaned_keys.append(key)

    if not cleaned_keys and settings.odds_api_key:
        cleaned_keys = [settings.odds_api_key]

    sanitized["odds_api_keys"] = cleaned_keys
    sanitized["telegram_send_to_main_chat"] = bool(
        sanitized.get("telegram_send_to_main_chat", True)
    )
    sanitized["telegram_send_to_channel"] = bool(
        sanitized.get("telegram_send_to_channel", True)
    )

    return sanitized


def load_runtime_config() -> Dict[str, Any]:
    ensure_runtime_config()

    try:
        db_raw = _load_runtime_config_from_db()
        if isinstance(db_raw, dict):
            sanitized = _sanitize_runtime_config(db_raw)
            try:
                CONFIG_PATH.write_text(
                    json.dumps(sanitized, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception:
                pass
            return sanitized

        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

        if not isinstance(raw, dict):
            return DEFAULT_CONFIG.copy()

        sanitized = _sanitize_runtime_config(raw)
        _save_runtime_config_to_db(sanitized)
        return sanitized

    except json.JSONDecodeError:
        sanitized = DEFAULT_CONFIG.copy()
        _save_runtime_config_to_db(sanitized)
        return sanitized
    except Exception as e:
        print(f"[RUNTIME_CONFIG] Erro ao carregar config: {e}")
        return DEFAULT_CONFIG.copy()


def save_runtime_config(data: Dict[str, Any]) -> Dict[str, Any]:
    ensure_runtime_config()

    current = load_runtime_config()
    current.update(data)

    sanitized = _sanitize_runtime_config(current)

    CONFIG_PATH.write_text(
        json.dumps(sanitized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _save_runtime_config_to_db(sanitized)

    return sanitized
