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

    def _is_event_for_target_local_date(self, event: Dict, target_date: str) -> bool:
        date_event_local = str(event.get("dateEventLocal") or "").strip()
        date_event = str(event.get("dateEvent") or "").strip()

        if date_event_local:
            return date_event_local == target_date

        return date_event == target_date

    def _events_for_league_on_date(self, league_meta: Dict, date_str: str) -> List[Dict]:
        raw_events = self.api.get_events_by_day_list(
            date_str,
            league_meta["name"],
        )

        filtered_events = [
            event for event in raw_events
            if self._is_event_for_target_local_date(event, date_str)
        ]

        print(
            f"[DAILY] {league_meta['display_name']} | "
            f"data={date_str} | "
            f"retornados={len(raw_events)} | "
            f"filtrados_dia_local={len(filtered_events)}"
        )

        return filtered_events

    def _build_payloads_for_date(
        self,
        date_str: str,
        selector_name: str,
    ) -> List[Dict]:
        payloads = []

        for league_meta in sorted(LEAGUES, key=lambda x: x["priority"]):
            try:
                events = self._events_for_league_on_date(league_meta, date_str)

                if selector_name == "morning":
                    selected = filter_morning_events(events)
                    label = "Manhã"
                elif selector_name == "afternoon":
                    selected = filter_afternoon_events(events)
                    label = "Tarde/Noite"
                elif selector_name == "30min":
                    selected = filter_events_starting_in_30_minutes(
                        events,
                        min_minutes=28,
                        max_minutes=31,
                    )
                    label = "Janela 30min"
                else:
                    selected = []
                    label = selector_name

                if selected:
                    print(
                        f"[DAILY] {label} | {league_meta['display_name']} | "
                        f"data={date_str} | eventos encontrados: {len(selected)}"
                    )

                payloads.extend(
                    self.analysis_service.build_many_analyses(selected, league_meta)
                )

            except Exception as e:
                print(
                    f"[DAILY] Erro {selector_name} em "
                    f"{league_meta['display_name']} | data={date_str}: {e}"
                )
                continue

        return self.analysis_service.sort_by_best_picks(payloads)

    def get_morning_payloads(self, date_str: Optional[str] = None) -> List[Dict]:
        target_date = date_str or self._today()
        return self._build_payloads_for_date(target_date, "morning")

    def get_afternoon_payloads(self, date_str: Optional[str] = None) -> List[Dict]:
        target_date = date_str or self._today()
        return self._build_payloads_for_date(target_date, "afternoon")

    def get_30min_payloads(self, date_str: Optional[str] = None) -> List[Dict]:
        target_date = date_str or self._today()
        return self._build_payloads_for_date(target_date, "30min")