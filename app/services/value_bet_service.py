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

    def evaluate(
        self,
        probs: Dict[str, float],
        odds: Optional[Dict],
        preferred_pick: Optional[str] = None,
        preferred_market_type: Optional[str] = None,
    ) -> Dict:
        result = {
            "has_value": False,
            "best_market": None,
            "edge": 0.0,
            "details": None,
            "market_type": preferred_market_type,
            "pick": preferred_pick,
            "market_odds": None,
            "fair_odds": None,
            "label": None,
        }
        if not odds:
            return result

        threshold = self._edge_threshold()
        markets = {
            "1": {"label": "Casa", "market_type": "1x2", "model_prob": probs.get("1", 0.0), "odds": odds.get("home_odds")},
            "X": {"label": "Empate", "market_type": "1x2", "model_prob": probs.get("X", 0.0), "odds": odds.get("draw_odds")},
            "2": {"label": "Fora", "market_type": "1x2", "model_prob": probs.get("2", 0.0), "odds": odds.get("away_odds")},
            "1X": {"label": "Casa ou Empate", "market_type": "double_chance", "model_prob": probs.get("1X", 0.0), "odds": odds.get("odds_1x")},
            "X2": {"label": "Empate ou Fora", "market_type": "double_chance", "model_prob": probs.get("X2", 0.0), "odds": odds.get("odds_x2")},
            "12": {"label": "Casa ou Fora", "market_type": "double_chance", "model_prob": probs.get("12", 0.0), "odds": odds.get("odds_12")},
        }

        def build_details(market: str, data: Dict, edge: float):
            market_odds = float(data["odds"])
            implied = self.decimal_to_implied_prob(market_odds)
            fair_odds = self.prob_to_fair_odds(data["model_prob"])
            return {
                "market": market,
                "label": data["label"],
                "market_type": data["market_type"],
                "model_prob": round(float(data["model_prob"] or 0.0), 4),
                "implied_prob": round(implied, 4),
                "odds": round(market_odds, 2),
                "fair_odds": fair_odds,
                "edge": round(edge, 4),
                "required_edge": round(threshold, 4),
            }

        best_market = None
        best_edge = float('-inf')
        best_details = None

        for market, data in markets.items():
            market_odds = data["odds"]
            model_prob = float(data["model_prob"] or 0.0)
            if not market_odds or model_prob <= 0:
                continue
            implied = self.decimal_to_implied_prob(float(market_odds))
            edge = model_prob - implied
            if edge > best_edge:
                best_edge = edge
                best_market = market
                best_details = build_details(market, data, edge)

        chosen_market = preferred_pick if preferred_pick in markets else best_market
        chosen_details = None
        chosen_edge = 0.0
        if chosen_market:
            chosen = markets[chosen_market]
            chosen_odds = chosen.get("odds")
            if chosen_odds and float(chosen_odds) > 0 and float(chosen.get("model_prob") or 0.0) > 0:
                chosen_edge = float(chosen.get("model_prob") or 0.0) - self.decimal_to_implied_prob(float(chosen_odds))
                chosen_details = build_details(chosen_market, chosen, chosen_edge)

        final_details = chosen_details or best_details
        final_edge = chosen_edge if chosen_details else (best_edge if best_edge != float('-inf') else 0.0)
        final_market = chosen_market or best_market

        if final_details:
            result.update({
                "details": final_details,
                "best_market": final_market,
                "edge": round(final_edge, 4),
                "market_type": final_details.get("market_type"),
                "pick": final_market,
                "market_odds": final_details.get("odds"),
                "fair_odds": final_details.get("fair_odds"),
                "label": final_details.get("label"),
            })
            result["has_value"] = final_edge >= threshold

        return result
