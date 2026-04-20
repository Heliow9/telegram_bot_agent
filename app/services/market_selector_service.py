from typing import Dict, Optional


class MarketSelectorService:
    MIN_EDGE_TO_SEND = 0.02
    MIN_PROBABILITY_1X2 = 0.44
    MIN_PROBABILITY_DC = 0.62

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

    def _build_1x2_candidates(
        self,
        probs: Dict,
        odds: Dict,
    ) -> list[Dict]:
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

    def _build_double_chance_candidates(
        self,
        probs: Dict,
        odds: Dict,
    ) -> list[Dict]:
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

    def _rank_candidate(self, item: Dict) -> float:
        edge = self._safe_float(item.get("edge"))
        probability = self._safe_float(item.get("probability"))
        market_type = item.get("market_type")

        bonus = 0.0
        if market_type == "1x2":
            bonus += 0.02
        elif market_type == "double_chance":
            bonus += 0.01

        return round((edge * 100) + (probability * 10) + bonus, 4)

    def _passes_minimum_rules(self, item: Dict) -> bool:
        edge = self._safe_float(item.get("edge"))
        probability = self._safe_float(item.get("probability"))
        market_type = item.get("market_type")

        if edge < self.MIN_EDGE_TO_SEND:
            return False

        if market_type == "1x2" and probability < self.MIN_PROBABILITY_1X2:
            return False

        if market_type == "double_chance" and probability < self.MIN_PROBABILITY_DC:
            return False

        return True

    def _build_confidence(
        self,
        probability: float,
        edge: float,
        market_type: str,
    ) -> str:
        score = 0

        if market_type == "double_chance":
            if probability >= 0.78:
                score += 2
            elif probability >= 0.70:
                score += 1
        else:
            if probability >= 0.60:
                score += 2
            elif probability >= 0.52:
                score += 1

        if edge >= 0.08:
            score += 2
        elif edge >= 0.04:
            score += 1

        if score >= 4:
            return "alta"
        if score >= 2:
            return "média"
        return "baixa"

    def choose_best_market(
        self,
        probs: Dict,
        odds: Dict,
    ) -> Dict:
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
            if self._passes_minimum_rules(item)
        ]

        target_pool = valid_candidates if valid_candidates else all_candidates

        ranked = sorted(
            target_pool,
            key=lambda item: self._rank_candidate(item),
            reverse=True,
        )

        best = ranked[0]
        probability = self._safe_float(best.get("probability"))
        edge = self._safe_float(best.get("edge"))
        market_type = str(best.get("market_type") or "")

        confidence = self._build_confidence(
            probability=probability,
            edge=edge,
            market_type=market_type,
        )

        return {
            **best,
            "confidence": confidence,
            "all_candidates": sorted(
                [
                    {
                        **item,
                        "ranking_score": self._rank_candidate(item),
                    }
                    for item in all_candidates
                ],
                key=lambda item: item["ranking_score"],
                reverse=True,
            ),
        }

    def build_analysis_payload(
        self,
        probs: Dict,
        odds: Dict,
        features: Optional[Dict] = None,
        model_source: str = "ml",
    ) -> Dict:
        decision = self.choose_best_market(probs=probs, odds=odds)

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