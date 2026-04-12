from typing import List, Dict
from app.constants import LEAGUES
from app.services.sportsdb_api import SportsDBAPI
from app.services.analysis_service import AnalysisService
from app.services.event_selector import (
    get_upcoming_events,
    filter_morning_events,
    filter_afternoon_events,
    filter_events_starting_in_30_minutes,
)
from app.services.time_utils import now_local


class DailyLeaguesService:
    def __init__(self):
        self.api = SportsDBAPI()
        self.analysis_service = AnalysisService()

    def _today(self) -> str:
        # usa o mesmo fuso do projeto
        return now_local().strftime("%Y-%m-%d")

    def _sorted_leagues(self) -> List[Dict]:
        return sorted(LEAGUES, key=lambda x: x["priority"])

    def _events_for_league_today(self, league_meta: Dict) -> List[Dict]:
        try:
            return self.api.get_events_by_day_list(
                self._today(),
                league_meta["name"],
            )
        except Exception as e:
            print(f"[DAILY] Erro ao buscar jogos da liga {league_meta['display_name']}: {e}")
            return []

    def _build_payloads_for_filtered_events(self, filter_func) -> List[Dict]:
        payloads = []

        for league_meta in self._sorted_leagues():
            try:
                events = self._events_for_league_today(league_meta)
                selected = filter_func(events)

                analyses = self.analysis_service.build_many_analyses(
                    selected,
                    league_meta
                )
                payloads.extend(analyses)

            except Exception as e:
                print(f"[DAILY] Erro processando liga {league_meta['display_name']}: {e}")
                continue

        return self.analysis_service.sort_by_best_picks(payloads)

    def get_all_today_payloads(self) -> List[Dict]:
        """
        Todos os jogos futuros do dia.
        """
        return self._build_payloads_for_filtered_events(get_upcoming_events)

    def get_morning_payloads(self) -> List[Dict]:
        """
        Jogos futuros da manhã.
        """
        return self._build_payloads_for_filtered_events(filter_morning_events)

    def get_afternoon_payloads(self) -> List[Dict]:
        """
        Jogos futuros da tarde/noite.
        """
        return self._build_payloads_for_filtered_events(filter_afternoon_events)

    def get_30min_payloads(self) -> List[Dict]:
        """
        Jogos que ainda não começaram e faltam até 30 minutos.
        Isso permite recuperar alertas mesmo se o servidor subir atrasado.
        """
        def _filter(events):
            return filter_events_starting_in_30_minutes(
                events,
                max_minutes=30,
            )

        return self._build_payloads_for_filtered_events(_filter)