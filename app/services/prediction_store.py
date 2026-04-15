from typing import Optional, Dict, List

from app.db import SessionLocal
from app.models import Prediction
from app.services.prediction_store_db import (
    save_prediction_db,
    update_prediction_result_db,
    update_prediction_market_odds_db,
)


def save_prediction(payload: dict):
    """
    Fonte principal: MySQL.
    """
    try:
        save_prediction_db(payload)
    except Exception as e:
        print(f"[PREDICTION_STORE][DB] Erro ao salvar previsão no MySQL: {e}")
        raise


def get_prediction_by_fixture_id(fixture_id: str) -> Optional[Dict]:
    db = SessionLocal()
    try:
        item = (
            db.query(Prediction)
            .filter(Prediction.fixture_id == str(fixture_id).strip())
            .first()
        )

        if not item:
            return None

        return {
            "fixture_id": item.fixture_id,
            "league": item.league_name,
            "home_team": item.home_team,
            "away_team": item.away_team,
            "date": item.match_date,
            "time": item.match_time,
            "pick": item.pick,
            "prob_home": item.prob_home,
            "prob_draw": item.prob_draw,
            "prob_away": item.prob_away,
            "confidence": item.confidence,
            "result": item.result,
            "home_score": item.home_score,
            "away_score": item.away_score,
            "status": item.status,
            "checked_at": item.checked_at.isoformat() if item.checked_at else None,
            "model_source": item.model_source,
        }
    finally:
        db.close()


def update_prediction_result(
    fixture_id: str,
    result: str,
    home_score: int,
    away_score: int,
):
    try:
        update_prediction_result_db(
            fixture_id=fixture_id,
            result=result,
            home_score=home_score,
            away_score=away_score,
        )
    except Exception as e:
        print(f"[PREDICTION_STORE][DB] Erro ao atualizar resultado no MySQL: {e}")
        raise


def update_prediction_market_odds(
    fixture_id: str,
    latest_market_odds: Optional[float],
):
    if latest_market_odds is None:
        return

    try:
        update_prediction_market_odds_db(
            fixture_id=fixture_id,
            latest_market_odds=latest_market_odds,
        )
    except Exception as e:
        print(f"[PREDICTION_STORE][DB] Erro ao atualizar odds no MySQL: {e}")
        raise


def get_pending_predictions() -> List[Dict]:
    db = SessionLocal()
    try:
        items = (
            db.query(Prediction)
            .filter(Prediction.status == "pending")
            .order_by(Prediction.created_at.desc())
            .all()
        )

        result = []
        for item in items:
            result.append(
                {
                    "fixture_id": item.fixture_id,
                    "league": item.league_name,
                    "home_team": item.home_team,
                    "away_team": item.away_team,
                    "date": item.match_date,
                    "time": item.match_time,
                    "pick": item.pick,
                    "confidence": item.confidence,
                    "status": item.status,
                    "model_source": item.model_source,
                }
            )

        return result
    finally:
        db.close()


def get_resolved_predictions() -> List[Dict]:
    db = SessionLocal()
    try:
        items = (
            db.query(Prediction)
            .filter(Prediction.status.in_(["hit", "miss"]))
            .order_by(Prediction.checked_at.desc(), Prediction.created_at.desc())
            .all()
        )

        result = []
        for item in items:
            result.append(
                {
                    "fixture_id": item.fixture_id,
                    "league": item.league_name,
                    "home_team": item.home_team,
                    "away_team": item.away_team,
                    "date": item.match_date,
                    "time": item.match_time,
                    "pick": item.pick,
                    "confidence": item.confidence,
                    "status": item.status,
                    "result": item.result,
                    "home_score": item.home_score,
                    "away_score": item.away_score,
                    "checked_at": item.checked_at.isoformat() if item.checked_at else None,
                    "model_source": item.model_source,
                }
            )

        return result
    finally:
        db.close()


def build_stats() -> Dict:
    db = SessionLocal()
    try:
        all_items = db.query(Prediction).all()
        resolved = [item for item in all_items if item.status in ("hit", "miss")]

        total = len(all_items)
        resolved_total = len(resolved)
        hits = sum(1 for item in resolved if item.status == "hit")
        misses = sum(1 for item in resolved if item.status == "miss")
        accuracy = (hits / resolved_total) if resolved_total else 0.0

        by_confidence = {}
        for confidence in ("alta", "média", "baixa"):
            items = [item for item in resolved if item.confidence == confidence]
            conf_total = len(items)
            conf_hits = sum(1 for item in items if item.status == "hit")
            by_confidence[confidence] = {
                "total": conf_total,
                "hits": conf_hits,
                "accuracy": round((conf_hits / conf_total), 4) if conf_total else 0.0,
            }

        by_league = {}
        leagues = sorted(set(item.league_name or "" for item in resolved))
        for league in leagues:
            items = [item for item in resolved if item.league_name == league]
            league_total = len(items)
            league_hits = sum(1 for item in items if item.status == "hit")
            by_league[league] = {
                "total": league_total,
                "hits": league_hits,
                "accuracy": round((league_hits / league_total), 4) if league_total else 0.0,
            }

        return {
            "total_predictions": total,
            "resolved_predictions": resolved_total,
            "hits": hits,
            "misses": misses,
            "accuracy": round(accuracy, 4),
            "by_confidence": by_confidence,
            "by_league": by_league,
        }
    finally:
        db.close()