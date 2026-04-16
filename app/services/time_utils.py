from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional


UTC_TZ = ZoneInfo("UTC")
LOCAL_TZ = ZoneInfo("America/Recife")


def parse_event_utc(date_event: str, str_time: str) -> Optional[datetime]:
    if not date_event:
        return None

    raw_time = (str_time or "").strip()

    if not raw_time:
        raw_time = "00:00:00"

    raw_time = raw_time.replace("Z", "")
    if "+" in raw_time:
        raw_time = raw_time.split("+", 1)[0]
    if raw_time.count(":") == 1:
        raw_time = f"{raw_time}:00"

    raw_value = f"{date_event} {raw_time}"

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(raw_value, fmt).replace(tzinfo=UTC_TZ)
        except ValueError:
            continue

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