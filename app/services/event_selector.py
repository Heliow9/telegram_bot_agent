from datetime import datetime, timedelta
from typing import List, Dict, Optional
from app.services.time_utils import event_to_local_datetime, now_local


def get_upcoming_events(events: List[Dict]) -> List[Dict]:
    now = now_local()
    upcoming = []

    for event in events:
        dt_local = event_to_local_datetime(
            event.get("dateEvent", ""),
            event.get("strTime", ""),
        )

        if dt_local is None:
            continue

        if dt_local > now:
            upcoming.append(event)

    upcoming.sort(
        key=lambda e: event_to_local_datetime(
            e.get("dateEvent", ""),
            e.get("strTime", "")
        ) or now
    )
    return upcoming


def get_next_valid_event(events: List[Dict]) -> Optional[Dict]:
    upcoming = get_upcoming_events(events)
    return upcoming[0] if upcoming else None


def filter_morning_events(events: List[Dict]) -> List[Dict]:
    filtered = []

    for event in get_upcoming_events(events):
        dt_local = event_to_local_datetime(
            event.get("dateEvent", ""),
            event.get("strTime", ""),
        )
        if dt_local is None:
            continue

        if 6 <= dt_local.hour < 12:
            filtered.append(event)

    return filtered


def filter_afternoon_events(events: List[Dict]) -> List[Dict]:
    filtered = []

    for event in get_upcoming_events(events):
        dt_local = event_to_local_datetime(
            event.get("dateEvent", ""),
            event.get("strTime", ""),
        )
        if dt_local is None:
            continue

        if dt_local.hour >= 12:
            filtered.append(event)

    return filtered


def filter_events_starting_in_30_minutes(events: List[Dict], tolerance_minutes: int = 5) -> List[Dict]:
    now = now_local()
    filtered = []

    for event in get_upcoming_events(events):
        dt_local = event_to_local_datetime(
            event.get("dateEvent", ""),
            event.get("strTime", ""),
        )
        if dt_local is None:
            continue

        diff = dt_local - now
        diff_minutes = diff.total_seconds() / 60

        if 30 - tolerance_minutes <= diff_minutes <= 30 + tolerance_minutes:
            filtered.append(event)

    return filtered