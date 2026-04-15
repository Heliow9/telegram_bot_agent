from pydantic import BaseModel


class RuntimeConfigResponse(BaseModel):
    value_bet_edge: float
    live_monitor_enabled: bool
    live_monitor_interval_seconds: int
    live_minute_checkpoints: str
    live_signal_min_shots_diff: int
    live_signal_min_on_target_diff: int
    live_signal_min_possession_diff: int


class RuntimeConfigUpdate(BaseModel):
    value_bet_edge: float
    live_monitor_enabled: bool
    live_monitor_interval_seconds: int
    live_minute_checkpoints: str
    live_signal_min_shots_diff: int
    live_signal_min_on_target_diff: int
    live_signal_min_possession_diff: int