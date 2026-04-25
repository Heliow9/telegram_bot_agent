from typing import List, Dict
from app.services.time_utils import event_payload_to_local_datetime, now_local


def _event_dt(event: Dict):
    return event_payload_to_local_datetime(event)


def _extract_hour(event: Dict) -> int | None:
    dt_local = _event_dt(event)
    return dt_local.hour if dt_local else None


def _is_future_event(event: Dict) -> bool:
    dt_local = _event_dt(event)
    return bool(dt_local and dt_local > now_local())


def _sort_by_local_time(events: List[Dict]) -> List[Dict]:
    return sorted(events, key=lambda e: _event_dt(e) or now_local())


def _filter_by_turn(events: List[Dict], start_hour: int, end_hour: int, future_only: bool = False) -> List[Dict]:
    selected = []
    for event in events:
        if future_only and not _is_future_event(event):
            continue
        hour = _extract_hour(event)
        if hour is None:
            continue
        if start_hour <= hour <= end_hour:
            selected.append(event)
    return _sort_by_local_time(selected)


def filter_morning_events(events: List[Dict]) -> List[Dict]:
    return _filter_by_turn(events, 8, 11, future_only=False)


def filter_afternoon_events(events: List[Dict]) -> List[Dict]:
    return _filter_by_turn(events, 12, 17, future_only=False)


def filter_night_events(events: List[Dict]) -> List[Dict]:
    return _filter_by_turn(events, 18, 23, future_only=False)


def filter_events_starting_in_30_minutes(
    events: List[Dict],
    min_minutes: int = 29,
    max_minutes: int = 35,
) -> List[Dict]:
    now = now_local()
    selected = []
    for event in events:
        dt_local = _event_dt(event)
        if dt_local is None:
            continue
        diff_minutes = (dt_local - now).total_seconds() / 60.0
        if min_minutes <= diff_minutes <= max_minutes:
            selected.append(event)
    return _sort_by_local_time(selected)
