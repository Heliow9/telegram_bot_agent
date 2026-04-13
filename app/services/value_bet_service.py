from typing import Optional, Dict
from app.config import settings


class ValueBetService:
    def __init__(self):
        self.edge = settings.value_bet_edge

    @staticmethod
    def decimal_to_implied_prob(odds: float) -> float:
        if not odds or odds <= 0:
            return 0.0
        return 1.0 / odds

    def evaluate(self, probs: Dict[str, float], odds: Optional[Dict]) -> Dict:
        result = {
            "has_value": False,
            "best_market": None,
            "edge": 0.0,
            "details": None,
        }

        if not odds:
            return result

        markets = {
            "1": {
                "model_prob": probs.get("1", 0.0),
                "odds": odds.get("home_odds"),
            },
            "X": {
                "model_prob": probs.get("X", 0.0),
                "odds": odds.get("draw_odds"),
            },
            "2": {
                "model_prob": probs.get("2", 0.0),
                "odds": odds.get("away_odds"),
            },
        }

        best_market = None
        best_edge = 0.0
        best_details = None

        for market, data in markets.items():
            market_odds = data["odds"]
            if not market_odds:
                continue

            implied = self.decimal_to_implied_prob(market_odds)
            edge = data["model_prob"] - implied

            if edge > best_edge:
                best_edge = edge
                best_market = market
                best_details = {
                    "market": market,
                    "model_prob": round(data["model_prob"], 4),
                    "implied_prob": round(implied, 4),
                    "odds": market_odds,
                    "edge": round(edge, 4),
                }

        if best_market and best_edge >= self.edge:
            result["has_value"] = True
            result["best_market"] = best_market
            result["edge"] = round(best_edge, 4)
            result["details"] = best_details

        return result