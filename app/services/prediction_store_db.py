import json
from datetime import datetime
from typing import Optional, Dict

from app.db import SessionLocal
from app.models import Prediction, PredictionOdds


def _pick_market_odds(analysis: dict) -> Optional[float]:
    odds = analysis.get("odds") or {}
    pick = analysis.get("suggested_pick")

    if pick == "1":
        return odds.get("home_odds")
    if pick == "X":
        return odds.get("draw_odds")
    if pick == "2":
        return odds.get("away_odds")
    return None


def save_prediction_db(payload: dict):
    db = SessionLocal()
    try:
        fixture_id = str(payload["fixture"]["id"])

        existing = db.query(Prediction).filter(Prediction.fixture_id == fixture_id).first()
        if existing:
            return

        analysis = payload["analysis"]
        fixture = payload["fixture"]
        league = payload["league"]

        prediction = Prediction(
            fixture_id=fixture_id,
            league_key=league.get("key"),
            league_name=league.get("display_name"),
            home_team=fixture.get("home_team"),
            away_team=fixture.get("away_team"),
            match_date=fixture.get("date"),
            match_time=fixture.get("time"),
            pick=analysis.get("suggested_pick"),
            prob_home=float(analysis.get("prob_home", 0.0)),
            prob_draw=float(analysis.get("prob_draw", 0.0)),
            prob_away=float(analysis.get("prob_away", 0.0)),
            confidence=analysis.get("confidence", "baixa"),
            model_source=analysis.get("model_source"),
            status="pending",
            result=None,
            home_score=None,
            away_score=None,
            features_json=json.dumps(analysis.get("features"), ensure_ascii=False)
            if analysis.get("features") is not None
            else None,
            created_at=datetime.utcnow(),
            checked_at=None,
        )

        db.add(prediction)
        db.flush()

        odds = analysis.get("odds") or {}
        fair_odds = analysis.get("fair_odds") or {}
        value_bet = analysis.get("value_bet") or {}

        if odds or fair_odds or value_bet:
            prediction_odds = PredictionOdds(
                prediction_id=prediction.id,
                bookmaker=odds.get("bookmaker"),
                home_odds=odds.get("home_odds"),
                draw_odds=odds.get("draw_odds"),
                away_odds=odds.get("away_odds"),
                fair_home_odds=fair_odds.get("1"),
                fair_draw_odds=fair_odds.get("X"),
                fair_away_odds=fair_odds.get("2"),
                opening_market_odds=_pick_market_odds(analysis),
                latest_market_odds=_pick_market_odds(analysis),
                edge=value_bet.get("edge"),
                has_value_bet=bool(value_bet.get("has_value")),
            )
            db.add(prediction_odds)

        db.commit()

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def update_prediction_result_db(
    fixture_id: str,
    result: str,
    home_score: int,
    away_score: int,
):
    db = SessionLocal()
    try:
        item = db.query(Prediction).filter(Prediction.fixture_id == str(fixture_id)).first()
        if not item:
            return

        item.result = result
        item.home_score = home_score
        item.away_score = away_score
        item.checked_at = datetime.utcnow()
        item.status = "hit" if item.pick == result else "miss"

        db.commit()

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def update_prediction_market_odds_db(
    fixture_id: str,
    latest_market_odds: Optional[float],
):
    if latest_market_odds is None:
        return

    db = SessionLocal()
    try:
        item = db.query(Prediction).filter(Prediction.fixture_id == str(fixture_id)).first()
        if not item or not item.odds:
            return

        item.odds.latest_market_odds = float(latest_market_odds)
        db.commit()

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_prediction_db_by_fixture_id(fixture_id: str) -> Optional[Dict]:
    db = SessionLocal()
    try:
        item = db.query(Prediction).filter(Prediction.fixture_id == str(fixture_id)).first()
        if not item:
            return None

        return {
            "fixture_id": item.fixture_id,
            "status": item.status,
            "result": item.result,
            "home_score": item.home_score,
            "away_score": item.away_score,
        }
    finally:
        db.close()