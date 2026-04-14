from typing import List, Dict
from app.services.time_utils import event_to_local_datetime, now_local


def _extract_hour(event: Dict) -> int | None:
    dt_local = event_to_local_datetime(
        event.get("dateEvent", ""),
        event.get("strTime", ""),
    )
    if dt_local is None:
        return None
    return dt_local.hour


def _is_future_event(event: Dict) -> bool:
    dt_local = event_to_local_datetime(
        event.get("dateEvent", ""),
        event.get("strTime", ""),
    )
    if dt_local is None:
        return False
    return dt_local > now_local()


def filter_morning_events(events: List[Dict]) -> List[Dict]:
    """
    Jogos futuros da manhã.
    Faixa sugerida: 05:00 até 11:59
    """
    selected = []

    for event in events:
        if not _is_future_event(event):
            continue

        hour = _extract_hour(event)
        if hour is None:
            continue

        if 5 <= hour < 12:
            selected.append(event)

    return sorted(
        selected,
        key=lambda e: event_to_local_datetime(
            e.get("dateEvent", ""),
            e.get("strTime", ""),
        ) or now_local()
    )


def filter_afternoon_events(events: List[Dict]) -> List[Dict]:
    """
    Jogos futuros da tarde/noite.
    Faixa sugerida: 12:00 até 23:59
    """
    selected = []

    for event in events:
        if not _is_future_event(event):
            continue

        hour = _extract_hour(event)
        if hour is None:
            continue

        if 12 <= hour <= 23:
            selected.append(event)

    return sorted(
        selected,
        key=lambda e: event_to_local_datetime(
            e.get("dateEvent", ""),
            e.get("strTime", ""),
        ) or now_local()
    )


def filter_events_starting_in_30_minutes(
    events: List[Dict],
    min_minutes: int = 28,
    max_minutes: int = 31,
) -> List[Dict]:
    """
    Seleciona jogos cuja partida começa em uma janela próxima dos 30 minutos.
    Em produção, uma janela de 28 a 31 minutos funciona melhor do que
    tentar ser exato demais, porque tolera:
    - pequenos atrasos de execução
    - tempo de resposta da API
    - latência do servidor
    """
    now = now_local()
    selected = []

    for event in events:
        dt_local = event_to_local_datetime(
            event.get("dateEvent", ""),
            event.get("strTime", ""),
        )

        if dt_local is None:
            continue

        diff_minutes = (dt_local - now).total_seconds() / 60.0

        if min_minutes <= diff_minutes <= max_minutes:
            selected.append(event)

    return sorted(
        selected,
        key=lambda e: event_to_local_datetime(
            e.get("dateEvent", ""),
            e.get("strTime", ""),
        ) or now_local()
    )