from typing import Dict, List, Optional, Tuple

from app.services.time_utils import event_payload_to_local_datetime
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
from app.services.market_selector_service import MarketSelectorService
from app.services.performance_tuning_service import PerformanceTuningService


class AnalysisService:
    def __init__(self):
        self.api = SportsDBAPI()
        self.ml_model = MLModelService()
        self.odds_service = OddsService()
        self.value_bet_service = ValueBetService()
        self.market_selector = MarketSelectorService()
        self.performance_tuning = PerformanceTuningService()
        self._table_cache: Dict[Tuple[str, str], List[Dict]] = {}
        self._team_events_cache: Dict[Tuple[str, str, int], List[Dict]] = {}

    def _get_table_rows(self, league_id: str, season: str) -> List[Dict]:
        cache_key = (str(league_id), str(season))
        if cache_key in self._table_cache:
            return self._table_cache[cache_key]

        data = self.api.lookup_table(league_id, season)
        table = data.get("table")
        rows = table if isinstance(table, list) else []
        self._table_cache[cache_key] = rows
        return rows

    def _get_team_events(self, mode: str, team_name: str, team_id: str, limit: int) -> List[Dict]:
        cache_key = (mode, str(team_id), int(limit))
        if cache_key in self._team_events_cache:
            return self._team_events_cache[cache_key]

        if mode == "general":
            data = self.api.get_team_last_events_list_limited(str(team_id), limit=limit)
        elif mode == "home":
            data = self.api.get_team_last_home_events(team_name, str(team_id), limit=limit)
        else:
            data = self.api.get_team_last_away_events(team_name, str(team_id), limit=limit)

        rows = data or []
        self._team_events_cache[cache_key] = rows
        return rows

    def _normalize_probs(self, probs: Dict[str, float]) -> Dict[str, float]:
        p1 = float(probs.get("1", 0.0) or 0.0)
        px = float(probs.get("X", 0.0) or 0.0)
        p2 = float(probs.get("2", 0.0) or 0.0)
        total = p1 + px + p2
        if total <= 0:
            return {"1": 0.34, "X": 0.32, "2": 0.34}
        return {"1": p1 / total, "X": px / total, "2": p2 / total}

    def _get_dynamic_ml_weight(self) -> float:
        metadata = self.ml_model.get_metadata() if self.ml_model else {}
        rows = int(metadata.get("rows", 0) or 0)
        accuracy = float(metadata.get("accuracy", 0.0) or 0.0)
        classes = metadata.get("classes") or []

        # Evita que um modelo muito pequeno ou desequilibrado puxe a decisão real.
        if rows < 60 or len(classes) < 3:
            return 0.0
        if accuracy < 0.48:
            return 0.0
        if rows < 120:
            return 0.18
        if rows < 220:
            return 0.28
        if rows < 400:
            return 0.38
        if accuracy >= 0.58:
            return 0.62
        if accuracy >= 0.54:
            return 0.48
        return 0.32

    def _blend_probabilities(self, heuristic_analysis: Dict, ml_probs: Optional[Dict[str, float]], features: Optional[Dict] = None) -> tuple[Dict[str, float], str]:
        heuristic_probs = self._normalize_probs({
            "1": heuristic_analysis.get("prob_home", 0.0),
            "X": heuristic_analysis.get("prob_draw", 0.0),
            "2": heuristic_analysis.get("prob_away", 0.0),
        })
        if not ml_probs:
            return heuristic_probs, "heuristic"

        ml_probs = self._normalize_probs(ml_probs)
        ml_weight = self._get_dynamic_ml_weight()
        if ml_weight <= 0:
            return heuristic_probs, "heuristic"

        heuristic_weight = 1.0 - ml_weight
        blended = {
            "1": ml_probs["1"] * ml_weight + heuristic_probs["1"] * heuristic_weight,
            "X": ml_probs["X"] * ml_weight + heuristic_probs["X"] * heuristic_weight,
            "2": ml_probs["2"] * ml_weight + heuristic_probs["2"] * heuristic_weight,
        }

        # Em jogos equilibrados, protege melhor o empate.
        features = features or {}
        draw_profile = float(features.get("avg_draw_rate", 0.0) or 0.0)
        balanced = float(features.get("balanced_match_indicator", 0.0) or 0.0)
        low_scoring = float(features.get("low_scoring_indicator", 0.0) or 0.0)
        if draw_profile >= 0.28 or balanced >= 1 or low_scoring >= 1:
            blended["X"] += 0.015

        return self._normalize_probs(blended), ("ml_blend" if ml_weight > 0 else "heuristic")

    def _confidence_from_probability(self, best_probability: float, raw_ml_probs: Optional[Dict[str, float]], features: Dict) -> str:
        confidence_score = 0
        if best_probability >= 0.60:
            confidence_score += 2
        elif best_probability >= 0.54:
            confidence_score += 1

        min_sample = min(int(features.get("sample_home", 0) or 0), int(features.get("sample_away", 0) or 0))
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

        home_general = self._get_team_events("general", home_team, str(home_team_id), 10)
        away_general = self._get_team_events("general", away_team, str(away_team_id), 10)
        home_home = self._get_team_events("home", home_team, str(home_team_id), 5)
        away_away = self._get_team_events("away", away_team, str(away_team_id), 5)

        home_general_form = extract_team_form(home_general, home_team)
        away_general_form = extract_team_form(away_general, away_team)
        home_home_form = extract_team_form(home_home, home_team)
        away_away_form = extract_team_form(away_away, away_team)

        table_rows = self._get_table_rows(league_id=league_meta["id"], season=league_meta["season"])
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
        probs, model_source = self._blend_probabilities(heuristic_analysis=heuristic_analysis, ml_probs=raw_ml_probs, features=features)
        odds = self.odds_service.get_match_odds(
            home_team=home_team,
            away_team=away_team,
            league_name=league_meta["display_name"],
            match_date=match.get("dateEvent", ""),
        )

        probs_payload = {
            "prob_home": probs["1"],
            "prob_draw": probs["X"],
            "prob_away": probs["2"],
        }
        historical_context = {
            "league_name": league_meta.get("display_name") or league_meta.get("name"),
            "reliability": self.performance_tuning.reliability_state(),
        }

        decision_payload = self.market_selector.build_analysis_payload(
            probs=probs_payload,
            odds=odds or {},
            features=features,
            model_source=model_source,
            historical_context=historical_context,
        )

        fallback_confidence = self._confidence_from_probability(
            best_probability=float(decision_payload.get("best_probability") or 0.0),
            raw_ml_probs=raw_ml_probs,
            features=features,
        )
        decision_payload["confidence"] = decision_payload.get("confidence") or fallback_confidence
        decision_payload["raw_ml_probs"] = raw_ml_probs
        decision_payload["main_market_pick"] = max({"1": probs["1"], "X": probs["X"], "2": probs["2"]}, key=lambda k: {"1": probs["1"], "X": probs["X"], "2": probs["2"]}[k])
        decision_payload["main_market_probability"] = max(probs.values())
        decision_payload["prob_1x"] = round(probs["1"] + probs["X"], 4)
        decision_payload["prob_x2"] = round(probs["X"] + probs["2"], 4)
        decision_payload["prob_12"] = round(probs["1"] + probs["2"], 4)

        dc_probs = {
            "1X": decision_payload["prob_1x"],
            "X2": decision_payload["prob_x2"],
            "12": decision_payload["prob_12"],
        }
        decision_payload["double_chance_pick"] = max(dc_probs, key=dc_probs.get)
        decision_payload["double_chance_probability"] = dc_probs[decision_payload["double_chance_pick"]]

        aligned_value_bet = self.value_bet_service.evaluate(
            probs={
                "1": decision_payload["prob_home"],
                "X": decision_payload["prob_draw"],
                "2": decision_payload["prob_away"],
                "1X": decision_payload["prob_1x"],
                "X2": decision_payload["prob_x2"],
                "12": decision_payload["prob_12"],
            },
            odds=odds,
            preferred_pick=decision_payload.get("suggested_pick"),
            preferred_market_type=decision_payload.get("market_type"),
        )
        decision_payload["value_bet"] = aligned_value_bet
        decision_payload["historical_tuning"] = historical_context["reliability"]

        if aligned_value_bet.get("market_odds") and not (decision_payload.get("value_bet") or {}).get("market_odds"):
            decision_payload["value_bet"] = aligned_value_bet
        decision_payload["historical_tuning"] = historical_context["reliability"]

        kickoff_local = event_payload_to_local_datetime(match)
        local_date = kickoff_local.strftime("%Y-%m-%d") if kickoff_local else (match.get("dateEventLocal") or match.get("dateEvent", ""))
        local_time = kickoff_local.strftime("%H:%M:%S") if kickoff_local else (match.get("strTimeLocal") or match.get("strTime", ""))

        return {
            "league": league_meta,
            "fixture": {
                "league": match.get("strLeague", league_meta["display_name"]),
                "league_key": league_meta["key"],
                "home_team": home_team,
                "away_team": away_team,
                "date": match.get("dateEvent", ""),
                "time": match.get("strTime", ""),
                "local_date": local_date,
                "local_time": local_time,
                "kickoff_local": kickoff_local.isoformat() if kickoff_local else None,
                "id": match.get("idEvent", ""),
            },
            "analysis": decision_payload,
        }

    def build_many_analyses(self, matches: List[Dict], league_meta: Dict) -> List[Dict]:
        payloads = []
        self._table_cache.clear()
        self._team_events_cache.clear()
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
                p["analysis"].get("best_probability", 0.0),
                max((item.get("ranking_score", 0.0) for item in p["analysis"].get("market_candidates", [])), default=0.0),
            ),
            reverse=True,
        )
