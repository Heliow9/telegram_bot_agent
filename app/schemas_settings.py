from pydantic import BaseModel
from typing import Optional, List


class RuntimeConfigResponse(BaseModel):
    value_bet_edge: float

    live_monitor_enabled: bool
    live_monitor_interval_seconds: int
    live_minute_checkpoints: str

    live_signal_min_shots_diff: int
    live_signal_min_on_target_diff: int
    live_signal_min_possession_diff: int

    telegram_send_to_main_chat: bool
    telegram_send_to_channel: bool

    odds_api_keys: List[str]


class RuntimeConfigUpdate(BaseModel):
    value_bet_edge: Optional[float] = None

    live_monitor_enabled: Optional[bool] = None
    live_monitor_interval_seconds: Optional[int] = None
    live_minute_checkpoints: Optional[str] = None

    live_signal_min_shots_diff: Optional[int] = None
    live_signal_min_on_target_diff: Optional[int] = None
    live_signal_min_possession_diff: Optional[int] = None

    telegram_send_to_main_chat: Optional[bool] = None
    telegram_send_to_channel: Optional[bool] = None

    odds_api_keys: Optional[List[str]] = None