from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict

from app.config import settings


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except Exception:
        return default


@dataclass
class SignalScore:
    score: float
    approved: bool
    min_score: float
    probability_score: float
    value_score: float
    confidence_score: float
    sample_score: float
    market_score: float
    risk_score: float
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["score"] = round(self.score, 4)
        return data


class SignalScoreService:
    """Pontuação final para decidir se uma entrada é forte o bastante.

    O score usa probabilidade do modelo, edge de value bet, confiança, amostra,
    tipo de mercado e penalizações de risco. Mantém a decisão auditável.
    """

    def __init__(self):
        self.min_score = _float(getattr(settings, "signal_min_score", 0.72), 0.72)
        self.min_probability = _float(getattr(settings, "signal_min_probability", 0.52), 0.52)
        self.max_risk_penalty = _float(getattr(settings, "signal_max_risk_penalty", 0.22), 0.22)

    def evaluate(self, analysis: Dict[str, Any], features: Dict[str, Any] | None = None) -> SignalScore:
        features = features or {}
        best_probability = _float(analysis.get("best_probability"))
        value_bet = analysis.get("value_bet") or {}
        edge = _float(value_bet.get("edge"))
        confidence = str(analysis.get("confidence") or "baixa").lower()
        market_type = str(analysis.get("market_type") or "1x2")

        sample_home = _float(features.get("sample_home"), 0)
        sample_away = _float(features.get("sample_away"), 0)
        min_sample = min(sample_home, sample_away)

        probability_score = _clamp((best_probability - self.min_probability) / 0.22)
        value_score = _clamp((edge + 0.02) / 0.14)
        confidence_score = {"alta": 1.0, "média": 0.66, "media": 0.66, "baixa": 0.28}.get(confidence, 0.35)
        sample_score = _clamp(min_sample / 8.0)
        market_score = 0.92 if market_type == "double_chance" else 0.78

        # Penaliza jogos muito equilibrados quando a sugestão é 1x2 agressivo.
        prob_home = _float(analysis.get("prob_home"))
        prob_away = _float(analysis.get("prob_away"))
        gap = abs(prob_home - prob_away)
        risk_penalty = 0.0
        if market_type == "1x2" and gap < 0.08:
            risk_penalty += 0.12
        if min_sample < 4:
            risk_penalty += 0.08
        if edge < 0:
            risk_penalty += 0.10
        risk_penalty = min(risk_penalty, self.max_risk_penalty)
        risk_score = 1.0 - risk_penalty

        score = (
            probability_score * 0.30
            + value_score * 0.28
            + confidence_score * 0.18
            + sample_score * 0.12
            + market_score * 0.07
            + risk_score * 0.05
        )
        score = _clamp(score - risk_penalty)
        approved = score >= self.min_score and best_probability >= self.min_probability

        reason = (
            f"score={score:.2f}, prob={best_probability:.2%}, edge={edge:.2%}, "
            f"confiança={confidence}, amostra_min={int(min_sample)}, mercado={market_type}"
        )

        return SignalScore(
            score=score,
            approved=approved,
            min_score=self.min_score,
            probability_score=probability_score,
            value_score=value_score,
            confidence_score=confidence_score,
            sample_score=sample_score,
            market_score=market_score,
            risk_score=risk_score,
            reason=reason,
        )
