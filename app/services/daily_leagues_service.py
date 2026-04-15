from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Dict

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

    def _is_event_for_today_local(self, event: Dict) -> bool:
        today = self._today()

        date_event_local = str(event.get("dateEventLocal") or "").strip()
        date_event = str(event.get("dateEvent") or "").strip()

        # Prioriza a data local do evento
        if date_event_local:
            return date_event_local == today

        return date_event == today

    def _events_for_league_today(self, league_meta: Dict) -> List[Dict]:
        raw_events = self.api.get_events_by_day_list(
            self._today(),
            league_meta["name"],
        )

        filtered_events = [
            event for event in raw_events
            if self._is_event_for_today_local(event)
        ]

        print(
            f"[DAILY] {league_meta['display_name']} | "
            f"retornados={len(raw_events)} | "
            f"filtrados_dia_local={len(filtered_events)}"
        )

        return filtered_events

    def get_morning_payloads(self) -> List[Dict]:
        payloads = []

        for league_meta in sorted(LEAGUES, key=lambda x: x["priority"]):
            try:
                events = self._events_for_league_today(league_meta)
                selected = filter_morning_events(events)

                if selected:
                    print(
                        f"[DAILY] Manhã | {league_meta['display_name']} | "
                        f"eventos encontrados: {len(selected)}"
                    )

                payloads.extend(
                    self.analysis_service.build_many_analyses(selected, league_meta)
                )
            except Exception as e:
                print(f"[DAILY] Erro manhã em {league_meta['display_name']}: {e}")
                continue

        return self.analysis_service.sort_by_best_picks(payloads)

    def get_afternoon_payloads(self) -> List[Dict]:
        payloads = []

        for league_meta in sorted(LEAGUES, key=lambda x: x["priority"]):
            try:
                events = self._events_for_league_today(league_meta)
                selected = filter_afternoon_events(events)

                if selected:
                    print(
                        f"[DAILY] Tarde/Noite | {league_meta['display_name']} | "
                        f"eventos encontrados: {len(selected)}"
                    )

                payloads.extend(
                    self.analysis_service.build_many_analyses(selected, league_meta)
                )
            except Exception as e:
                print(f"[DAILY] Erro tarde/noite em {league_meta['display_name']}: {e}")
                continue

        return self.analysis_service.sort_by_best_picks(payloads)

    def get_30min_payloads(self) -> List[Dict]:
        payloads = []

        for league_meta in sorted(LEAGUES, key=lambda x: x["priority"]):
            try:
                events = self._events_for_league_today(league_meta)
                selected = filter_events_starting_in_30_minutes(
                    events,
                    min_minutes=28,
                    max_minutes=31,
                )

                if selected:
                    print(
                        f"[DAILY] Janela 30min | {league_meta['display_name']} | "
                        f"eventos encontrados: {len(selected)}"
                    )

                payloads.extend(
                    self.analysis_service.build_many_analyses(selected, league_meta)
                )
            except Exception as e:
                print(f"[DAILY] Erro janela 30min em {league_meta['display_name']}: {e}")
                continue

        return self.analysis_service.sort_by_best_picks(payloads)