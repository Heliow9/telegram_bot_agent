from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, Mapping


UTC_TZ = ZoneInfo("UTC")
LOCAL_TZ = ZoneInfo("America/Recife")


def _normalize_time(raw_time: str) -> str:
    raw_time = (raw_time or "").strip()
    if not raw_time:
        return "00:00:00"
    raw_time = raw_time.replace("Z", "")
    if "+" in raw_time:
        raw_time = raw_time.split("+", 1)[0]
    if "T" in raw_time:
        raw_time = raw_time.split("T", 1)[-1]
    if raw_time.count(":") == 1:
        raw_time = f"{raw_time}:00"
    return raw_time


def _parse_datetime(date_value: str, time_value: str, tz: ZoneInfo) -> Optional[datetime]:
    if not date_value:
        return None
    raw_value = f"{date_value} {_normalize_time(time_value)}"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(raw_value, fmt).replace(tzinfo=tz)
        except ValueError:
            continue
    return None


def parse_event_utc(date_event: str, str_time: str) -> Optional[datetime]:
    return _parse_datetime(date_event, str_time, UTC_TZ)


def event_to_local_datetime(date_event: str, str_time: str) -> Optional[datetime]:
    dt_utc = parse_event_utc(date_event, str_time)
    if dt_utc is None:
        return None
    return dt_utc.astimezone(LOCAL_TZ)


def event_payload_to_local_datetime(event: Mapping) -> Optional[datetime]:
    local_date = str(event.get("dateEventLocal") or "").strip()
    local_time = str(event.get("strTimeLocal") or "").strip()
    if local_date:
        parsed = _parse_datetime(local_date, local_time, LOCAL_TZ)
        if parsed is not None:
            return parsed
    return event_to_local_datetime(
        str(event.get("dateEvent") or "").strip(),
        str(event.get("strTime") or "").strip(),
    )


def format_local_datetime(date_event: str, str_time: str) -> tuple[str, str]:
    dt_local = event_to_local_datetime(date_event, str_time)
    if dt_local is None:
        return date_event or "", str_time or ""
    return dt_local.strftime("%Y-%m-%d"), dt_local.strftime("%H:%M:%S")


def now_local() -> datetime:
    return datetime.now(LOCAL_TZ)


def now_utc() -> datetime:
    return datetime.now(UTC_TZ)
