from typing import Dict, List, Optional

from app.services.sportsdb_api import SportsDBAPI
from app.services.predictor import (
    extract_team_form,
    calculate_prediction,
    get_table_position,
)
from app.services.ml_feature_builder import build_match_features
from app.services.ml_model_service import MLModelService
from app.services.odds_service import OddsService
from app.services.value_bet_service import ValueBetService


class AnalysisService:
    ML_BLEND_WEIGHT = 0.65
    HEURISTIC_BLEND_WEIGHT = 0.35

    def __init__(self):
        self.api = SportsDBAPI()
        self.ml_model = MLModelService()
        self.odds_service = OddsService()
        self.value_bet_service = ValueBetService()

    def _get_table_rows(self, league_id: str, season: str) -> List[Dict]:
        data = self.api.lookup_table(league_id, season)
        table = data.get("table")

        if isinstance(table, list):
            return table

        return []

    def _normalize_probs(self, probs: Dict[str, float]) -> Dict[str, float]:
        p1 = float(probs.get("1", 0.0) or 0.0)
        px = float(probs.get("X", 0.0) or 0.0)
        p2 = float(probs.get("2", 0.0) or 0.0)

        total = p1 + px + p2
        if total <= 0:
            return {"1": 0.34, "X": 0.32, "2": 0.34}

        return {
            "1": p1 / total,
            "X": px / total,
            "2": p2 / total,
        }

    def _blend_probabilities(
        self,
        heuristic_analysis: Dict,
        ml_probs: Optional[Dict[str, float]],
    ) -> tuple[Dict[str, float], str]:
        heuristic_probs = self._normalize_probs({
            "1": heuristic_analysis.get("prob_home", 0.0),
            "X": heuristic_analysis.get("prob_draw", 0.0),
            "2": heuristic_analysis.get("prob_away", 0.0),
        })

        if not ml_probs:
            return heuristic_probs, "heuristic"

        ml_probs = self._normalize_probs(ml_probs)

        blended = {
            "1": (
                ml_probs["1"] * self.ML_BLEND_WEIGHT
                + heuristic_probs["1"] * self.HEURISTIC_BLEND_WEIGHT
            ),
            "X": (
                ml_probs["X"] * self.ML_BLEND_WEIGHT
                + heuristic_probs["X"] * self.HEURISTIC_BLEND_WEIGHT
            ),
            "2": (
                ml_probs["2"] * self.ML_BLEND_WEIGHT
                + heuristic_probs["2"] * self.HEURISTIC_BLEND_WEIGHT
            ),
        }

        return self._normalize_probs(blended), "ml_blend"

    def _confidence_from_probability(self, best_probability: float) -> str:
        if best_probability >= 0.56:
            return "alta"
        if best_probability >= 0.45:
            return "média"
        return "baixa"

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

        heuristic_analysis = calculate_prediction(
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

        raw_ml_probs = self.ml_model.predict_proba(features)
        probs, model_source = self._blend_probabilities(
            heuristic_analysis=heuristic_analysis,
            ml_probs=raw_ml_probs,
        )

        options = {"1": probs["1"], "X": probs["X"], "2": probs["2"]}
        suggested_pick = max(options, key=options.get)
        best_probability = options[suggested_pick]
        confidence = self._confidence_from_probability(best_probability)

        analysis = {
            **heuristic_analysis,
            "prob_home": probs["1"],
            "prob_draw": probs["X"],
            "prob_away": probs["2"],
            "suggested_pick": suggested_pick,
            "best_probability": best_probability,
            "confidence": confidence,
            "model_source": model_source,
            "features": features,
            "raw_ml_probs": raw_ml_probs,
        }

        odds = self.odds_service.get_match_odds(
            home_team=home_team,
            away_team=away_team,
            league_name=league_meta["display_name"],
            match_date=match.get("dateEvent", ""),
        )

        value_bet = self.value_bet_service.evaluate(
            probs={
                "1": analysis["prob_home"],
                "X": analysis["prob_draw"],
                "2": analysis["prob_away"],
            },
            odds=odds,
        )

        analysis["odds"] = odds
        analysis["value_bet"] = value_bet

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
                p["analysis"].get("value_bet", {}).get("edge", 0.0),
                p["analysis"]["best_probability"],
                p["analysis"].get("ranking_score", 0),
            ),
            reverse=True,
        )