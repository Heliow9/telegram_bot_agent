from typing import List, Dict
from datetime import datetime

from app.services.time_utils import event_to_local_datetime, now_local, LOCAL_TZ


def _event_local_datetime(event: Dict):
    """
    Prioriza dateEventLocal/strTimeLocal da TheSportsDB quando disponíveis.
    Fallback: converte dateEvent/strTime UTC para America/Recife.
    """
    date_local = str(event.get("dateEventLocal") or "").strip()
    time_local = str(event.get("strTimeLocal") or "").strip()

    if date_local:
        raw_time = (time_local or "00:00:00").replace("Z", "")
        if "+" in raw_time:
            raw_time = raw_time.split("+", 1)[0]
        if raw_time.count(":") == 1:
            raw_time = f"{raw_time}:00"

        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(f"{date_local} {raw_time}", fmt).replace(
                    tzinfo=LOCAL_TZ
                )
            except ValueError:
                continue

    return event_to_local_datetime(
        event.get("dateEvent", ""),
        event.get("strTime", ""),
    )


def _extract_hour(event: Dict) -> int | None:
    dt_local = _event_local_datetime(event)
    if dt_local is None:
        return None
    return dt_local.hour


def _sort_by_time(events: List[Dict]) -> List[Dict]:
    return sorted(events, key=lambda e: _event_local_datetime(e) or now_local())


def filter_morning_events(events: List[Dict]) -> List[Dict]:
    """
    Grade da manhã: 08:00 até 11:59.
    Não exige jogo futuro para permitir catch-up após restart/deploy.
    """
    selected = []
    for event in events:
        hour = _extract_hour(event)
        if hour is not None and 8 <= hour < 12:
            selected.append(event)
    return _sort_by_time(selected)


def filter_afternoon_events(events: List[Dict]) -> List[Dict]:
    """
    Grade da tarde: 12:00 até 17:59.
    Não exige jogo futuro para permitir catch-up após restart/deploy.
    """
    selected = []
    for event in events:
        hour = _extract_hour(event)
        if hour is not None and 12 <= hour < 18:
            selected.append(event)
    return _sort_by_time(selected)


def filter_night_events(events: List[Dict]) -> List[Dict]:
    """
    Grade da noite: 18:00 até 23:59.
    Não exige jogo futuro para permitir catch-up após restart/deploy.
    """
    selected = []
    for event in events:
        hour = _extract_hour(event)
        if hour is not None and 18 <= hour <= 23:
            selected.append(event)
    return _sort_by_time(selected)


def filter_events_starting_in_30_minutes(
    events: List[Dict],
    min_minutes: int = 25,
    max_minutes: int = 35,
) -> List[Dict]:
    """
    Seleciona jogos cuja partida começa na janela pré-jogo.
    Este filtro continua exigindo jogo futuro para evitar reenvio pós-início.
    """
    now = now_local()
    selected = []
    for event in events:
        dt_local = _event_local_datetime(event)
        if dt_local is None:
            continue
        diff_minutes = (dt_local - now).total_seconds() / 60.0
        if min_minutes <= diff_minutes <= max_minutes:
            selected.append(event)
    return _sort_by_time(selected)
