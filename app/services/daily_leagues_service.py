from datetime import datetime
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

    def _today(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def _events_for_league_today(self, league_meta: Dict) -> List[Dict]:
        return self.api.get_events_by_day_list(
            self._today(),
            league_meta["name"],
        )

    def get_morning_payloads(self) -> List[Dict]:
        payloads = []

        for league_meta in sorted(LEAGUES, key=lambda x: x["priority"]):
            try:
                events = self._events_for_league_today(league_meta)
                selected = filter_morning_events(events)
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
                payloads.extend(
                    self.analysis_service.build_many_analyses(selected, league_meta)
                )
            except Exception as e:
                print(f"[DAILY] Erro janela 30min em {league_meta['display_name']}: {e}")
                continue

        return self.analysis_service.sort_by_best_picks(payloads)