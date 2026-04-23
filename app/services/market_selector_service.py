from typing import Dict, Optional

from app.services.performance_tuning_service import PerformanceTuningService


class MarketSelectorService:
    MIN_EDGE_TO_SEND = 0.02
    MIN_PROBABILITY_1X2 = 0.45
    MIN_PROBABILITY_DC = 0.64

    def __init__(self):
        self.performance_tuning = PerformanceTuningService()

    def _safe_float(self, value, default=0.0) -> float:
        try:
            if value is None or value == "":
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def _implied_probability(self, odds: Optional[float]) -> Optional[float]:
        odds = self._safe_float(odds, default=0.0)
        if odds <= 1:
            return None
        return 1.0 / odds

    def _fair_odds(self, probability: Optional[float]) -> Optional[float]:
        probability = self._safe_float(probability, default=0.0)
        if probability <= 0:
            return None
        return round(1.0 / probability, 4)

    def _edge(self, probability: Optional[float], market_odds: Optional[float]) -> Optional[float]:
        probability = self._safe_float(probability, default=0.0)
        market_odds = self._safe_float(market_odds, default=0.0)

        if probability <= 0 or market_odds <= 1:
            return None

        return round((probability * market_odds) - 1.0, 4)

    def _build_1x2_candidates(self, probs: Dict, odds: Dict) -> list[Dict]:
        candidates = []
        mapping = [
            ("1", "prob_home", "home_odds"),
            ("X", "prob_draw", "draw_odds"),
            ("2", "prob_away", "away_odds"),
        ]

        for pick, prob_key, odds_key in mapping:
            probability = self._safe_float(probs.get(prob_key))
            market_odds = self._safe_float(odds.get(odds_key), default=0.0)
            if probability <= 0 or market_odds <= 1:
                continue
            fair_odds = self._fair_odds(probability)
            edge = self._edge(probability, market_odds)
            candidates.append(
                {
                    "market_type": "1x2",
                    "suggested_pick": pick,
                    "label": pick,
                    "probability": round(probability, 4),
                    "market_odds": round(market_odds, 4),
                    "fair_odds": fair_odds,
                    "edge": edge,
                    "has_value": bool(edge is not None and edge >= self.MIN_EDGE_TO_SEND),
                }
            )
        return candidates

    def _build_double_chance_candidates(self, probs: Dict, odds: Dict) -> list[Dict]:
        prob_home = self._safe_float(probs.get("prob_home"))
        prob_draw = self._safe_float(probs.get("prob_draw"))
        prob_away = self._safe_float(probs.get("prob_away"))

        dc_candidates = [
            {
                "market_type": "double_chance",
                "suggested_pick": "1X",
                "label": "Casa ou Empate",
                "probability": round(prob_home + prob_draw, 4),
                "market_odds": self._safe_float(odds.get("odds_1x"), default=0.0),
            },
            {
                "market_type": "double_chance",
                "suggested_pick": "X2",
                "label": "Empate ou Fora",
                "probability": round(prob_draw + prob_away, 4),
                "market_odds": self._safe_float(odds.get("odds_x2"), default=0.0),
            },
            {
                "market_type": "double_chance",
                "suggested_pick": "12",
                "label": "Casa ou Fora",
                "probability": round(prob_home + prob_away, 4),
                "market_odds": self._safe_float(odds.get("odds_12"), default=0.0),
            },
        ]

        candidates = []
        for item in dc_candidates:
            if item["probability"] <= 0 or item["market_odds"] <= 1:
                continue
            fair_odds = self._fair_odds(item["probability"])
            edge = self._edge(item["probability"], item["market_odds"])
            candidates.append(
                {
                    **item,
                    "market_odds": round(item["market_odds"], 4),
                    "fair_odds": fair_odds,
                    "edge": edge,
                    "has_value": bool(edge is not None and edge >= self.MIN_EDGE_TO_SEND),
                }
            )
        return candidates

    def _historical_adjustment(self, item: Dict, historical_context: Optional[Dict] = None) -> float:
        pick = item.get("suggested_pick")
        market_type = item.get("market_type")
        confidence = item.get("confidence")
        league_name = (historical_context or {}).get("league_name")

        adjustment = 0.0
        adjustment += self.performance_tuning.market_adjustment(market_type)
        adjustment += self.performance_tuning.pick_adjustment(pick)
        adjustment += self.performance_tuning.confidence_adjustment(confidence)
        adjustment += self.performance_tuning.league_adjustment(league_name)
        return round(adjustment, 4)

    def _feature_adjustment(self, item: Dict, features: Optional[Dict] = None, probs: Optional[Dict] = None) -> float:
        features = features or {}
        probs = probs or {}
        pick = str(item.get("suggested_pick") or "").upper()
        market_type = str(item.get("market_type") or "").lower()
        score = 0.0

        balanced = self._safe_float(features.get("balanced_match_indicator"))
        high_draw = self._safe_float(features.get("high_draw_profile_indicator"))
        low_scoring = self._safe_float(features.get("low_scoring_indicator"))
        abs_rank_gap = self._safe_float(features.get("absolute_rank_gap"))
        form_gap = self._safe_float(features.get("form_gap_abs"))
        sample_home = self._safe_float(features.get("sample_home"))
        sample_away = self._safe_float(features.get("sample_away"))
        min_sample = min(sample_home, sample_away)
        draw_prob = self._safe_float(probs.get("prob_draw"))

        if market_type == "1x2":
            if pick == "X" and (balanced >= 1 or high_draw >= 1 or low_scoring >= 1):
                score += 0.035
            if pick in {"1", "2"} and balanced >= 1 and abs_rank_gap < 4 and form_gap < 0.14:
                score -= 0.05
            if pick in {"1", "2"} and min_sample < 4:
                score -= 0.03
        else:
            if pick in {"1X", "X2"} and (balanced >= 1 or draw_prob >= 0.29):
                score += 0.02
            if pick == "12" and draw_prob >= 0.28:
                score -= 0.05
            if pick == "12" and low_scoring >= 1:
                score -= 0.04

        return round(score, 4)

    def _rank_candidate(self, item: Dict, features: Optional[Dict] = None, probs: Optional[Dict] = None, historical_context: Optional[Dict] = None) -> float:
        edge = self._safe_float(item.get("edge"))
        probability = self._safe_float(item.get("probability"))
        market_type = item.get("market_type")

        bonus = 0.0
        if market_type == "1x2":
            bonus += 0.02
        elif market_type == "double_chance":
            bonus += 0.01

        bonus += self._feature_adjustment(item=item, features=features, probs=probs)
        bonus += self._historical_adjustment(item=item, historical_context=historical_context)
        return round((edge * 100) + (probability * 10) + bonus, 4)

    def _passes_minimum_rules(self, item: Dict, features: Optional[Dict] = None, probs: Optional[Dict] = None) -> bool:
        edge = self._safe_float(item.get("edge"))
        probability = self._safe_float(item.get("probability"))
        market_type = item.get("market_type")
        pick = str(item.get("suggested_pick") or "").upper()
        probs = probs or {}
        features = features or {}
        draw_prob = self._safe_float(probs.get("prob_draw"))
        balanced = self._safe_float(features.get("balanced_match_indicator"))
        min_sample = min(
            self._safe_float(features.get("sample_home")),
            self._safe_float(features.get("sample_away")),
        )

        if edge < self.MIN_EDGE_TO_SEND:
            return False

        if market_type == "1x2" and probability < self.MIN_PROBABILITY_1X2:
            return False
        if market_type == "double_chance" and probability < self.MIN_PROBABILITY_DC:
            return False

        if pick == "X" and draw_prob < 0.29:
            return False
        if pick in {"1", "2"} and balanced >= 1 and probability < 0.5:
            return False
        if pick in {"1", "2"} and min_sample < 4 and probability < 0.54:
            return False
        if pick == "12" and draw_prob >= 0.27:
            return False

        return True

    def _build_confidence(self, probability: float, edge: float, market_type: str, features: Optional[Dict] = None) -> str:
        score = 0
        features = features or {}
        min_sample = min(
            int(self._safe_float(features.get("sample_home"))),
            int(self._safe_float(features.get("sample_away"))),
        )

        if market_type == "double_chance":
            if probability >= 0.80:
                score += 2
            elif probability >= 0.72:
                score += 1
        else:
            if probability >= 0.61:
                score += 2
            elif probability >= 0.54:
                score += 1

        if edge >= 0.08:
            score += 2
        elif edge >= 0.04:
            score += 1

        if min_sample >= 7:
            score += 1

        if score >= 4:
            return "alta"
        if score >= 2:
            return "média"
        return "baixa"

    def choose_best_market(self, probs: Dict, odds: Dict, features: Optional[Dict] = None, historical_context: Optional[Dict] = None) -> Dict:
        candidates_1x2 = self._build_1x2_candidates(probs=probs, odds=odds)
        candidates_dc = self._build_double_chance_candidates(probs=probs, odds=odds)
        all_candidates = candidates_1x2 + candidates_dc

        if not all_candidates:
            return {
                "market_type": None,
                "suggested_pick": None,
                "label": None,
                "probability": 0.0,
                "market_odds": None,
                "fair_odds": None,
                "edge": None,
                "has_value": False,
                "confidence": "baixa",
                "all_candidates": [],
            }

        valid_candidates = [
            item for item in all_candidates
            if self._passes_minimum_rules(item, features=features, probs=probs)
        ]
        target_pool = valid_candidates if valid_candidates else all_candidates

        ranked = sorted(
            target_pool,
            key=lambda item: self._rank_candidate(item, features=features, probs=probs, historical_context=historical_context),
            reverse=True,
        )

        best = ranked[0]
        probability = self._safe_float(best.get("probability"))
        edge = self._safe_float(best.get("edge"))
        market_type = str(best.get("market_type") or "")
        confidence = self._build_confidence(probability=probability, edge=edge, market_type=market_type, features=features)

        return {
            **best,
            "confidence": confidence,
            "all_candidates": sorted(
                [
                    {
                        **item,
                        "ranking_score": self._rank_candidate(item, features=features, probs=probs, historical_context=historical_context),
                    }
                    for item in all_candidates
                ],
                key=lambda item: item["ranking_score"],
                reverse=True,
            ),
        }

    def build_analysis_payload(self, probs: Dict, odds: Dict, features: Optional[Dict] = None, model_source: str = "ml", historical_context: Optional[Dict] = None) -> Dict:
        decision = self.choose_best_market(
            probs=probs,
            odds=odds,
            features=features,
            historical_context=historical_context,
        )

        prob_home = self._safe_float(probs.get("prob_home"))
        prob_draw = self._safe_float(probs.get("prob_draw"))
        prob_away = self._safe_float(probs.get("prob_away"))

        fair_odds = {
            "1": self._fair_odds(prob_home),
            "X": self._fair_odds(prob_draw),
            "2": self._fair_odds(prob_away),
            "1X": self._fair_odds(prob_home + prob_draw),
            "X2": self._fair_odds(prob_draw + prob_away),
            "12": self._fair_odds(prob_home + prob_away),
        }

        return {
            "prob_home": round(prob_home, 4),
            "prob_draw": round(prob_draw, 4),
            "prob_away": round(prob_away, 4),
            "suggested_pick": decision.get("suggested_pick"),
            "market_type": decision.get("market_type"),
            "market_label": decision.get("label"),
            "confidence": decision.get("confidence", "baixa"),
            "best_probability": decision.get("probability", 0.0),
            "model_source": model_source,
            "features": features or {},
            "historical_context": historical_context or {},
            "odds": {
                "bookmaker": odds.get("bookmaker"),
                "home_odds": odds.get("home_odds"),
                "draw_odds": odds.get("draw_odds"),
                "away_odds": odds.get("away_odds"),
                "odds_1x": odds.get("odds_1x"),
                "odds_x2": odds.get("odds_x2"),
                "odds_12": odds.get("odds_12"),
            },
            "fair_odds": fair_odds,
            "value_bet": {
                "has_value": bool(decision.get("has_value")),
                "edge": decision.get("edge"),
                "market_odds": decision.get("market_odds"),
                "fair_odds": decision.get("fair_odds"),
                "market_type": decision.get("market_type"),
                "pick": decision.get("suggested_pick"),
                "label": decision.get("label"),
            },
            "market_candidates": decision.get("all_candidates", []),
        }
