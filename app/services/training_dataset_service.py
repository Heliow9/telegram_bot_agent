from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd

from app.services.predictor import extract_team_form, get_table_position
from app.services.ml_feature_builder import build_match_features
from app.services.sportsdb_api import SportsDBAPI
from app.services.prediction_store import load_predictions


TRAINING_DATA_PATH = Path("data/historical_training_matches.csv")


class TrainingDatasetService:
    def __init__(self):
        self.api = SportsDBAPI()

    def _get_target_from_scores(self, home_score: int, away_score: int) -> str:
        if home_score > away_score:
            return "1"
        if away_score > home_score:
            return "2"
        return "X"

    def _get_table_rows(self, league_id: str, season: str) -> List[Dict]:
        data = self.api.lookup_table(league_id, season)
        table = data.get("table")
        return table if isinstance(table, list) else []

    def build_training_row(self, event: Dict, league_meta: Dict) -> Optional[Dict]:
        home_team = event.get("strHomeTeam")
        away_team = event.get("strAwayTeam")
        home_team_id = event.get("idHomeTeam")
        away_team_id = event.get("idAwayTeam")

        home_score = event.get("intHomeScore")
        away_score = event.get("intAwayScore")

        if not home_team or not away_team or not home_team_id or not away_team_id:
            return None

        try:
            home_score = int(home_score)
            away_score = int(away_score)
        except (TypeError, ValueError):
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
            "fixture_id": event.get("idEvent"),
            "home_team": home_team,
            "away_team": away_team,
            "home_score": home_score,
            "away_score": away_score,
        }

        return row

    def build_training_row_from_prediction_log(self, item: Dict) -> Optional[Dict]:
        if item.get("status") not in ("hit", "miss"):
            return None

        features = item.get("features")
        result = item.get("result")

        if not features or result not in ("1", "X", "2"):
            return None

        try:
            home_score = int(item.get("home_score"))
            away_score = int(item.get("away_score"))
        except (TypeError, ValueError):
            return None

        row = {
            **features,
            "target": result,
            "league": item.get("league"),
            "fixture_id": item.get("fixture_id"),
            "home_team": item.get("home_team"),
            "away_team": item.get("away_team"),
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

    def append_resolved_predictions_to_dataset(self) -> int:
        predictions = load_predictions()
        rows = []

        for item in predictions:
            row = self.build_training_row_from_prediction_log(item)
            if row:
                rows.append(row)

        if not rows:
            print("[TRAINING] Nenhuma previsão resolvida com features para adicionar.")
            return 0

        before_count = 0
        if TRAINING_DATA_PATH.exists():
            try:
                before_count = len(pd.read_csv(TRAINING_DATA_PATH))
            except Exception:
                before_count = 0

        self.save_rows(rows)

        after_count = 0
        if TRAINING_DATA_PATH.exists():
            try:
                after_count = len(pd.read_csv(TRAINING_DATA_PATH))
            except Exception:
                after_count = before_count

        added = max(0, after_count - before_count)
        print(f"[TRAINING] Incremento concluído. Novas linhas líquidas: {added}")
        return added