from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional


UTC_TZ = ZoneInfo("UTC")
LOCAL_TZ = ZoneInfo("America/Recife")


def parse_event_utc(date_event: str, str_time: str) -> Optional[datetime]:
    if not date_event or not str_time:
        return None

    try:
        return datetime.strptime(
            f"{date_event} {str_time}",
            "%Y-%m-%d %H:%M:%S"
        ).replace(tzinfo=UTC_TZ)
    except ValueError:
        return None


def event_to_local_datetime(date_event: str, str_time: str) -> Optional[datetime]:
    dt_utc = parse_event_utc(date_event, str_time)
    if dt_utc is None:
        return None
    return dt_utc.astimezone(LOCAL_TZ)


def format_local_datetime(date_event: str, str_time: str) -> tuple[str, str]:
    dt_local = event_to_local_datetime(date_event, str_time)
    if dt_local is None:
        return date_event or "", str_time or ""
    return dt_local.strftime("%Y-%m-%d"), dt_local.strftime("%H:%M:%S")


def now_local() -> datetime:
    return datetime.now(LOCAL_TZ)


def now_utc() -> datetime:
    return datetime.now(UTC_TZ)