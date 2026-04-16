from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Dict, Optional

from app.constants import LEAGUES
from app.services.sportsdb_api import SportsDBAPI
from app.services.analysis_service import AnalysisService
from app.services.event_selector import (
    filter_morning_events,
    filter_afternoon_events,
    filter_events_starting_in_30_minutes,
)


class DailyLeaguesService:
    def __init__(self):
        self.api = SportsDBAPI()
        self.analysis_service = AnalysisService()
        self.tz = ZoneInfo("America/Recife")

    def _now_local(self) -> datetime:
        return datetime.now(self.tz)

    def _today(self) -> str:
        return self._now_local().strftime("%Y-%m-%d")

    def _parse_local_datetime_from_event(self, event: Dict) -> Optional[datetime]:
        date_event_local = str(event.get("dateEventLocal") or "").strip()
        time_event_local = str(event.get("strTimeLocal") or "").strip()

        if date_event_local:
            if not time_event_local:
                time_event_local = "00:00:00"

            normalized_time = time_event_local.replace("Z", "")
            if "+" in normalized_time:
                normalized_time = normalized_time.split("+", 1)[0]
            if normalized_time.count(":") == 1:
                normalized_time = f"{normalized_time}:00"

            raw_value = f"{date_event_local} {normalized_time}"

            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    return datetime.strptime(raw_value, fmt).replace(tzinfo=self.tz)
                except ValueError:
                    continue

        return None

    def _is_event_for_target_local_date(self, event: Dict, target_date: str) -> bool:
        date_event_local = str(event.get("dateEventLocal") or "").strip()
        date_event = str(event.get("dateEvent") or "").strip()

        if date_event_local and date_event_local == target_date:
            return True

        local_dt = self._parse_local_datetime_from_event(event)
        if local_dt and local_dt.strftime("%Y-%m-%d") == target_date:
            return True

        return date_event == target_date

    def _events_for_league_on_date(self, league_meta: Dict, date_str: str) -> List[Dict]:
        raw_events = self.api.get_events_by_day_list(
            date_str,
            league_meta["name"],
        )

        filtered_events = []

        for event in raw_events:
            if self._is_event_for_target_local_date(event, date_str):
                filtered_events.append(event)
            else:
                print(
                    f"[DAILY][DROP] {league_meta['display_name']} | "
                    f"evento={event.get('strEvent')} | "
                    f"dateEvent={event.get('dateEvent')} {event.get('strTime')} | "
                    f"dateEventLocal={event.get('dateEventLocal')} {event.get('strTimeLocal')}"
                )

        print(
            f"[DAILY] {league_meta['display_name']} | "
            f"data={date_str} | "
            f"retornados={len(raw_events)} | "
            f"filtrados_dia_local={len(filtered_events)}"
        )

        return filtered_events

    def _select_events(self, events: List[Dict], selector_name: str) -> tuple[List[Dict], str]:
        if selector_name == "morning":
            return filter_morning_events(events), "Manhã"

        if selector_name == "afternoon":
            return filter_afternoon_events(events), "Tarde/Noite"

        if selector_name == "30min":
            return (
                filter_events_starting_in_30_minutes(
                    events,
                    min_minutes=28,
                    max_minutes=31,
                ),
                "Janela 30min",
            )

        if selector_name == "all_day":
            return events, "Dia inteiro"

        return [], selector_name

    def _build_payloads_for_date(
        self,
        date_str: str,
        selector_name: str,
    ) -> List[Dict]:
        payloads = []

        for league_meta in sorted(LEAGUES, key=lambda x: x["priority"]):
            try:
                events = self._events_for_league_on_date(league_meta, date_str)
                selected, label = self._select_events(events, selector_name)

                if selected:
                    print(
                        f"[DAILY] {label} | {league_meta['display_name']} | "
                        f"data={date_str} | eventos encontrados: {len(selected)}"
                    )

                built_payloads = self.analysis_service.build_many_analyses(
                    selected,
                    league_meta,
                )

                if built_payloads:
                    print(
                        f"[DAILY] {label} | {league_meta['display_name']} | "
                        f"payloads gerados: {len(built_payloads)}"
                    )

                payloads.extend(built_payloads)

            except Exception as e:
                print(
                    f"[DAILY] Erro {selector_name} em "
                    f"{league_meta['display_name']} | data={date_str}: {e}"
                )
                continue

        return self.analysis_service.sort_by_best_picks(payloads)

    def get_all_day_payloads(self, date_str: Optional[str] = None) -> List[Dict]:
        target_date = date_str or self._today()
        return self._build_payloads_for_date(target_date, "all_day")

    def get_morning_payloads(self, date_str: Optional[str] = None) -> List[Dict]:
        target_date = date_str or self._today()
        return self._build_payloads_for_date(target_date, "morning")

    def get_afternoon_payloads(self, date_str: Optional[str] = None) -> List[Dict]:
        target_date = date_str or self._today()
        return self._build_payloads_for_date(target_date, "afternoon")

    def get_30min_payloads(self, date_str: Optional[str] = None) -> List[Dict]:
        target_date = date_str or self._today()
        return self._build_payloads_for_date(target_date, "30min")