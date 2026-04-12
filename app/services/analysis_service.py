from typing import Dict, List, Optional
from app.services.sportsdb_api import SportsDBAPI
from app.services.predictor import (
    extract_team_form,
    calculate_prediction,
    get_table_position,
)


class AnalysisService:
    def __init__(self):
        self.api = SportsDBAPI()

    def _get_table_rows(self, league_id: str, season: str) -> List[Dict]:
        data = self.api.lookup_table(league_id, season)
        table = data.get("table")

        if isinstance(table, list):
            return table

        return []

    def build_match_analysis(self, match: Dict, league_meta: Dict) -> Optional[Dict]:
        home_team = match.get("strHomeTeam")
        away_team = match.get("strAwayTeam")
        home_team_id = match.get("idHomeTeam")
        away_team_id = match.get("idAwayTeam")

        if not home_team or not away_team or not home_team_id or not away_team_id:
            return None

        home_general = self.api.get_team_last_events_list_limited(str(home_team_id), limit=10)
        away_general = self.api.get_team_last_events_list_limited(str(away_team_id), limit=10)

        home_home = self.api.get_team_last_home_events(home_team, str(home_team_id), limit=5)
        away_away = self.api.get_team_last_away_events(away_team, str(away_team_id), limit=5)

        home_general_form = extract_team_form(home_general or [], home_team)
        away_general_form = extract_team_form(away_general or [], away_team)
        home_home_form = extract_team_form(home_home or [], home_team)
        away_away_form = extract_team_form(away_away or [], away_team)

        table_rows = self._get_table_rows(
            league_id=league_meta["id"],
            season=league_meta["season"],
        )

        total_teams = len(table_rows) if table_rows else 20
        home_rank = get_table_position(table_rows, home_team)
        away_rank = get_table_position(table_rows, away_team)

        analysis = calculate_prediction(
            home_team=home_team,
            away_team=away_team,
            home_general_form=home_general_form,
            away_general_form=away_general_form,
            home_home_form=home_home_form,
            away_away_form=away_away_form,
            home_rank=home_rank,
            away_rank=away_rank,
            total_teams=total_teams,
            league_priority=league_meta["priority"],
        )

        return {
            "league": league_meta,
            "fixture": {
                "league": match.get("strLeague", league_meta["display_name"]),
                "league_key": league_meta["key"],
                "home_team": home_team,
                "away_team": away_team,
                "date": match.get("dateEvent", ""),
                "time": match.get("strTime", ""),
                "id": match.get("idEvent", ""),
            },
            "analysis": analysis,
        }

    def build_many_analyses(self, matches: List[Dict], league_meta: Dict) -> List[Dict]:
        payloads = []

        for match in matches:
            try:
                payload = self.build_match_analysis(match, league_meta=league_meta)
                if payload:
                    payloads.append(payload)
            except Exception as exc:
                print(f"Erro analisando jogo {match.get('idEvent')}: {exc}")
                continue

        return payloads

    def sort_by_best_picks(self, payloads: List[Dict]) -> List[Dict]:
        return sorted(
            payloads,
            key=lambda p: (
                p["analysis"]["ranking_score"],
                p["analysis"]["best_probability"],
            ),
            reverse=True,
        )