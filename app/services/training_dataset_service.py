from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pandas as pd

from app.services.predictor import extract_team_form, get_table_position
from app.services.ml_feature_builder import build_match_features
from app.services.sportsdb_api import SportsDBAPI


TRAINING_DATA_PATH = Path("data/historical_training_matches.csv")


class TrainingDatasetService:
    def __init__(self):
        self.api = SportsDBAPI()
        self._table_cache: Dict[Tuple[str, str], List[Dict]] = {}
        self._team_last_events_cache: Dict[str, List[Dict]] = {}

    def _get_target_from_scores(self, home_score: int, away_score: int) -> str:
        if home_score > away_score:
            return "1"
        if away_score > home_score:
            return "2"
        return "X"

    def _get_table_rows(self, league_id: str, season: str) -> List[Dict]:
        cache_key = (league_id, season)

        if cache_key in self._table_cache:
            return self._table_cache[cache_key]

        data = self.api.lookup_table(league_id, season)
        table = data.get("table")
        rows = table if isinstance(table, list) else []
        self._table_cache[cache_key] = rows
        return rows

    def _get_team_last_events(self, team_id: str, limit: int = 10) -> List[Dict]:
        if team_id in self._team_last_events_cache:
            return self._team_last_events_cache[team_id][:limit]

        events = self.api.get_team_last_events_list(team_id)
        events = events if isinstance(events, list) else []
        self._team_last_events_cache[team_id] = events
        return events[:limit]

    def _filter_home_events(self, events: List[Dict], team_name: str, limit: int = 5) -> List[Dict]:
        return [event for event in events if event.get("strHomeTeam") == team_name][:limit]

    def _filter_away_events(self, events: List[Dict], team_name: str, limit: int = 5) -> List[Dict]:
        return [event for event in events if event.get("strAwayTeam") == team_name][:limit]

    def build_training_row(self, event: Dict, league_meta: Dict) -> Optional[Dict]:
        fixture_id = event.get("idEvent")
        home_team = event.get("strHomeTeam")
        away_team = event.get("strAwayTeam")
        home_team_id = event.get("idHomeTeam")
        away_team_id = event.get("idAwayTeam")

        home_score = event.get("intHomeScore")
        away_score = event.get("intAwayScore")

        if not fixture_id:
            return None

        if not home_team or not away_team or not home_team_id or not away_team_id:
            return None

        try:
            home_score = int(home_score)
            away_score = int(away_score)
        except (TypeError, ValueError):
            return None

        home_all_events = self._get_team_last_events(str(home_team_id), limit=10)
        away_all_events = self._get_team_last_events(str(away_team_id), limit=10)

        home_general = home_all_events[:10]
        away_general = away_all_events[:10]

        home_home = self._filter_home_events(home_all_events, home_team, limit=5)
        away_away = self._filter_away_events(away_all_events, away_team, limit=5)

        home_general_form = extract_team_form(home_general or [], home_team)
        away_general_form = extract_team_form(away_general or [], away_team)
        home_home_form = extract_team_form(home_home or [], home_team)
        away_away_form = extract_team_form(away_away or [], away_team)

        table_rows = self._get_table_rows(
            league_id=str(league_meta["id"]),
            season=str(league_meta["season"]),
        )

        total_teams = len(table_rows) if table_rows else 20
        home_rank = get_table_position(table_rows, home_team)
        away_rank = get_table_position(table_rows, away_team)

        if home_rank is None:
            home_rank = total_teams
        if away_rank is None:
            away_rank = total_teams

        features = build_match_features(
            home_general_form=home_general_form,
            away_general_form=away_general_form,
            home_home_form=home_home_form,
            away_away_form=away_away_form,
            home_rank=home_rank,
            away_rank=away_rank,
            total_teams=total_teams,
            league_priority=league_meta["priority"],
        )

        row = {
            **features,
            "target": self._get_target_from_scores(home_score, away_score),
            "league": league_meta["display_name"],
            "fixture_id": fixture_id,
            "home_team": home_team,
            "away_team": away_team,
            "home_score": home_score,
            "away_score": away_score,
        }

        return row

    def save_rows(self, rows: List[Dict]):
        if not rows:
            print("[TRAINING] Nenhuma linha para salvar.")
            return

        TRAINING_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(rows)

        if TRAINING_DATA_PATH.exists():
            old = pd.read_csv(TRAINING_DATA_PATH)
            df = pd.concat([old, df], ignore_index=True)
            df = df.drop_duplicates(subset=["fixture_id"], keep="last")

        df.to_csv(TRAINING_DATA_PATH, index=False)
        print(f"[TRAINING] Dataset salvo em {TRAINING_DATA_PATH} com {len(df)} linhas")