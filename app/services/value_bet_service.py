from typing import Optional, Dict

from app.config import settings
from app.services.runtime_config_service import load_runtime_config


class ValueBetService:
    def __init__(self):
        self.default_edge = settings.value_bet_edge

    def _edge_threshold(self) -> float:
        runtime = load_runtime_config()
        return float(runtime.get("value_bet_edge", self.default_edge))

    @staticmethod
    def decimal_to_implied_prob(odds: Optional[float]) -> float:
        if not odds or odds <= 0:
            return 0.0
        return 1.0 / odds

    @staticmethod
    def prob_to_fair_odds(prob: Optional[float]) -> Optional[float]:
        try:
            prob_value = float(prob or 0.0)
        except (TypeError, ValueError):
            return None

        if prob_value <= 0:
            return None

        return round(1.0 / prob_value, 2)

    def evaluate(self, probs: Dict[str, float], odds: Optional[Dict]) -> Dict:
        result = {
            "has_value": False,
            "best_market": None,
            "edge": 0.0,
            "details": None,
        }

        if not odds:
            return result

        threshold = self._edge_threshold()

        markets = {
            "1": {
                "label": "Casa",
                "model_prob": probs.get("1", 0.0),
                "odds": odds.get("home_odds"),
            },
            "X": {
                "label": "Empate",
                "model_prob": probs.get("X", 0.0),
                "odds": odds.get("draw_odds"),
            },
            "2": {
                "label": "Fora",
                "model_prob": probs.get("2", 0.0),
                "odds": odds.get("away_odds"),
            },
        }

        best_market = None
        best_edge = 0.0
        best_details = None

        for market, data in markets.items():
            market_odds = data["odds"]
            model_prob = data["model_prob"]

            if not market_odds:
                continue

            implied = self.decimal_to_implied_prob(market_odds)
            edge = model_prob - implied
            fair_odds = self.prob_to_fair_odds(model_prob)

            if edge > best_edge:
                best_edge = edge
                best_market = market
                best_details = {
                    "market": market,
                    "label": data["label"],
                    "model_prob": round(model_prob, 4),
                    "implied_prob": round(implied, 4),
                    "odds": round(float(market_odds), 2),
                    "fair_odds": fair_odds,
                    "edge": round(edge, 4),
                    "required_edge": round(threshold, 4),
                }

        if best_market and best_edge >= threshold:
            result["has_value"] = True
            result["best_market"] = best_market
            result["edge"] = round(best_edge, 4)
            result["details"] = best_details
        else:
            result["details"] = best_details

        return result