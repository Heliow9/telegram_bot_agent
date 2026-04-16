import json
from pathlib import Path
from typing import Any, Dict

from app.config import settings


CONFIG_PATH = Path("data/runtime_config.json")


DEFAULT_CONFIG = {
    "value_bet_edge": settings.value_bet_edge,
    "live_monitor_enabled": settings.live_monitor_enabled,
    "live_monitor_interval_seconds": settings.live_monitor_interval_seconds,
    "live_minute_checkpoints": settings.live_minute_checkpoints,
    "live_signal_min_shots_diff": settings.live_signal_min_shots_diff,
    "live_signal_min_on_target_diff": settings.live_signal_min_on_target_diff,
    "live_signal_min_possession_diff": settings.live_signal_min_possession_diff,
    "telegram_send_to_main_chat": True,
    "telegram_send_to_channel": False,
}


def ensure_runtime_config() -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(
            json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def load_runtime_config() -> Dict[str, Any]:
    ensure_runtime_config()

    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

        if not isinstance(raw, dict):
            return DEFAULT_CONFIG.copy()

        merged = DEFAULT_CONFIG.copy()
        merged.update(raw)
        return merged

    except json.JSONDecodeError:
        return DEFAULT_CONFIG.copy()
    except Exception as e:
        print(f"[RUNTIME_CONFIG] Erro ao carregar config: {e}")
        return DEFAULT_CONFIG.copy()


def save_runtime_config(data: Dict[str, Any]) -> Dict[str, Any]:
    ensure_runtime_config()

    current = load_runtime_config()
    current.update(data)

    CONFIG_PATH.write_text(
        json.dumps(current, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return current