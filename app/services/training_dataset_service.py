from pathlib import Path
from typing import Dict, List, Optional
import json

import pandas as pd

from app.db import SessionLocal
from app.models import Prediction
from app.services.predictor import extract_team_form, get_table_position
from app.services.ml_feature_builder import build_match_features
from app.services.sportsdb_api import SportsDBAPI


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
            "fixture_id": str(event.get("idEvent", "")).strip(),
            "home_team": home_team,
            "away_team": away_team,
            "home_score": home_score,
            "away_score": away_score,
        }

        return row

    def _parse_features_json(self, raw_features) -> Optional[Dict]:
        if raw_features is None:
            return None

        if isinstance(raw_features, dict):
            return raw_features

        if isinstance(raw_features, str):
            raw_features = raw_features.strip()
            if not raw_features:
                return None
            try:
                parsed = json.loads(raw_features)
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None

        return None

    def build_training_row_from_prediction_db(self, item: Prediction) -> Optional[Dict]:
        if item.status not in ("hit", "miss"):
            return None

        features = self._parse_features_json(item.features_json)
        result = str(item.result or "").strip().upper()

        if not features or result not in ("1", "X", "2"):
            return None

        if item.home_score is None or item.away_score is None:
            return None

        fixture_id = str(item.fixture_id or "").strip()
        if not fixture_id:
            return None

        row = {
            **features,
            "target": result,
            "league": item.league_name,
            "fixture_id": fixture_id,
            "home_team": item.home_team,
            "away_team": item.away_team,
            "home_score": int(item.home_score),
            "away_score": int(item.away_score),
        }

        return row

    def save_rows(self, rows: List[Dict]):
        if not rows:
            print("[TRAINING] Nenhuma linha para salvar.")
            return

        TRAINING_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        df_new = pd.DataFrame(rows)

        if TRAINING_DATA_PATH.exists():
            try:
                df_old = pd.read_csv(TRAINING_DATA_PATH)
                df = pd.concat([df_old, df_new], ignore_index=True)
            except Exception as e:
                print(f"[TRAINING] Erro ao ler dataset anterior, recriando arquivo: {e}")
                df = df_new.copy()
        else:
            df = df_new.copy()

        if "fixture_id" in df.columns:
            df["fixture_id"] = df["fixture_id"].astype(str).str.strip()
            df = df.drop_duplicates(subset=["fixture_id"], keep="last")

        df.to_csv(TRAINING_DATA_PATH, index=False)
        print(f"[TRAINING] Dataset salvo em {TRAINING_DATA_PATH} com {len(df)} linhas")

    def append_resolved_predictions_to_dataset(self) -> int:
        db = SessionLocal()
        try:
            items = (
                db.query(Prediction)
                .filter(Prediction.status.in_(["hit", "miss"]))
                .all()
            )

            rows = []
            for item in items:
                row = self.build_training_row_from_prediction_db(item)
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
            print(
                f"[TRAINING] Incremento concluído. "
                f"Linhas válidas processadas: {len(rows)} | novas linhas líquidas: {added}"
            )
            return added
        finally:
            db.close()