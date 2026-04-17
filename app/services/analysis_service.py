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

    def _get_dynamic_ml_weight(self) -> float:
        metadata = self.ml_model.get_metadata() if self.ml_model else {}
        rows = int(metadata.get("rows", 0) or 0)
        accuracy = float(metadata.get("accuracy", 0.0) or 0.0)

        if rows < 80:
            return 0.20
        if rows < 150:
            return 0.30
        if rows < 300:
            return 0.40

        if accuracy >= 0.56:
            return 0.65
        if accuracy >= 0.50:
            return 0.50
        if accuracy >= 0.45:
            return 0.35

        return 0.25

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

        ml_weight = self._get_dynamic_ml_weight()
        heuristic_weight = 1.0 - ml_weight

        blended = {
            "1": ml_probs["1"] * ml_weight + heuristic_probs["1"] * heuristic_weight,
            "X": ml_probs["X"] * ml_weight + heuristic_probs["X"] * heuristic_weight,
            "2": ml_probs["2"] * ml_weight + heuristic_probs["2"] * heuristic_weight,
        }

        source = "ml_blend" if ml_weight > 0 else "heuristic"
        return self._normalize_probs(blended), source

    def _confidence_from_probability(
        self,
        best_probability: float,
        raw_ml_probs: Optional[Dict[str, float]],
        features: Dict,
    ) -> str:
        confidence_score = 0

        if best_probability >= 0.60:
            confidence_score += 2
        elif best_probability >= 0.54:
            confidence_score += 1

        min_sample = min(
            int(features.get("sample_home", 0) or 0),
            int(features.get("sample_away", 0) or 0),
        )

        if min_sample >= 7:
            confidence_score += 2
        elif min_sample >= 5:
            confidence_score += 1

        form_gap = abs(float(features.get("form_diff", 0.0) or 0.0))
        rank_gap = abs(float(features.get("rank_diff", 0.0) or 0.0))

        if form_gap >= 0.18:
            confidence_score += 1
        if rank_gap >= 0.25:
            confidence_score += 1

        if raw_ml_probs:
            ordered = sorted(raw_ml_probs.values(), reverse=True)
            if len(ordered) >= 2 and (ordered[0] - ordered[1]) >= 0.12:
                confidence_score += 1

        if confidence_score >= 5:
            return "alta"
        if confidence_score >= 3:
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

        confidence = self._confidence_from_probability(
            best_probability=best_probability,
            raw_ml_probs=raw_ml_probs,
            features=features,
        )

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