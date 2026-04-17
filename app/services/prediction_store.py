import json
from pathlib import Path
from typing import Optional, Dict, List

from app.db import SessionLocal
from app.models import Prediction, PredictionOdds
from app.services.prediction_store_db import (
    save_prediction_db,
    update_prediction_result_db,
    update_prediction_market_odds_db,
    update_prediction_live_state_db,
)


STORE_PATH = Path("data/predictions_log.json")


def ensure_store():
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not STORE_PATH.exists():
        STORE_PATH.write_text("[]", encoding="utf-8")


def save_all_predictions(data: List[Dict]):
    ensure_store()
    STORE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _normalize_fixture_id(value) -> str:
    return str(value or "").strip()


def _sync_db_to_json():
    db = SessionLocal()
    try:
        rows = (
            db.query(Prediction, PredictionOdds)
            .outerjoin(PredictionOdds, PredictionOdds.prediction_id == Prediction.id)
            .order_by(Prediction.created_at.desc())
            .all()
        )

        data: List[Dict] = []

        for prediction, odds in rows:
            record = {
                "saved_at": prediction.created_at.isoformat() if prediction.created_at else None,
                "league": prediction.league_name,
                "fixture_id": prediction.fixture_id,
                "home_team": prediction.home_team,
                "away_team": prediction.away_team,
                "date": prediction.match_date,
                "time": prediction.match_time,
                "pick": prediction.pick,
                "prob_home": round(float(prediction.prob_home or 0.0), 4),
                "prob_draw": round(float(prediction.prob_draw or 0.0), 4),
                "prob_away": round(float(prediction.prob_away or 0.0), 4),
                "confidence": prediction.confidence,
                "result": prediction.result,
                "home_score": prediction.home_score,
                "away_score": prediction.away_score,
                "status": prediction.status,
                "checked_at": prediction.checked_at.isoformat() if prediction.checked_at else None,
                "started_at": prediction.started_at.isoformat() if prediction.started_at else None,
                "finished_at": prediction.finished_at.isoformat() if prediction.finished_at else None,
                "last_checked_at": prediction.last_checked_at.isoformat() if prediction.last_checked_at else None,
                "result_source": prediction.result_source,
                "last_status_text": prediction.last_status_text,
                "is_live": prediction.is_live,
                "features": None,
                "model_source": prediction.model_source,
                "odds_snapshot": {
                    "bookmaker": odds.bookmaker if odds else None,
                    "home_odds": odds.home_odds if odds else None,
                    "draw_odds": odds.draw_odds if odds else None,
                    "away_odds": odds.away_odds if odds else None,
                } if odds else None,
                "fair_odds_snapshot": {
                    "1": odds.fair_home_odds if odds else None,
                    "X": odds.fair_draw_odds if odds else None,
                    "2": odds.fair_away_odds if odds else None,
                } if odds else None,
                "opening_market_odds": odds.opening_market_odds if odds else None,
                "latest_market_odds": odds.latest_market_odds if odds else None,
                "clv": (
                    {
                        "opening_odds": round(float(odds.opening_market_odds), 2),
                        "closing_odds": round(float(odds.latest_market_odds), 2),
                        "movement": round(
                            float(odds.latest_market_odds) - float(odds.opening_market_odds),
                            2,
                        ),
                    }
                    if odds
                    and odds.opening_market_odds is not None
                    and odds.latest_market_odds is not None
                    else None
                ),
            }

            data.append(record)

        save_all_predictions(data)
        return data

    finally:
        db.close()


def load_predictions() -> List[Dict]:
    ensure_store()
    return _sync_db_to_json()


def save_prediction(payload: dict):
    try:
        save_prediction_db(payload)
    except Exception as e:
        print(f"[PREDICTION_STORE][DB] Erro ao salvar previsão no MySQL: {e}")
        raise
    finally:
        try:
            _sync_db_to_json()
        except Exception as sync_error:
            print(f"[PREDICTION_STORE][JSON] Erro ao sincronizar após save_prediction: {sync_error}")


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
            "started_at": item.started_at.isoformat() if item.started_at else None,
            "finished_at": item.finished_at.isoformat() if item.finished_at else None,
            "last_checked_at": item.last_checked_at.isoformat() if item.last_checked_at else None,
            "result_source": item.result_source,
            "last_status_text": item.last_status_text,
            "is_live": item.is_live,
            "model_source": item.model_source,
        }
    finally:
        db.close()


def update_prediction_result(
    fixture_id: str,
    result: str,
    home_score: int,
    away_score: int,
    status_text: Optional[str] = None,
    result_source: Optional[str] = None,
    is_live: bool = False,
    finished: bool = True,
):
    try:
        update_prediction_result_db(
            fixture_id=fixture_id,
            result=result,
            home_score=home_score,
            away_score=away_score,
            status_text=status_text,
            result_source=result_source,
            is_live=is_live,
            finished=finished,
        )
    except Exception as e:
        print(f"[PREDICTION_STORE][DB] Erro ao atualizar resultado no MySQL: {e}")
        raise
    finally:
        try:
            _sync_db_to_json()
        except Exception as sync_error:
            print(f"[PREDICTION_STORE][JSON] Erro ao sincronizar após update_prediction_result: {sync_error}")


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
    finally:
        try:
            _sync_db_to_json()
        except Exception as sync_error:
            print(f"[PREDICTION_STORE][JSON] Erro ao sincronizar após update_prediction_market_odds: {sync_error}")


def update_prediction_live_state(
    fixture_id: str,
    home_score: Optional[int],
    away_score: Optional[int],
    status_text: Optional[str] = None,
    is_live: bool = True,
):
    try:
        update_prediction_live_state_db(
            fixture_id=fixture_id,
            home_score=home_score,
            away_score=away_score,
            status_text=status_text,
            is_live=is_live,
        )
    except Exception as e:
        print(f"[PREDICTION_STORE][DB] Erro ao atualizar live state no MySQL: {e}")
        raise
    finally:
        try:
            _sync_db_to_json()
        except Exception as sync_error:
            print(f"[PREDICTION_STORE][JSON] Erro ao sincronizar após update_prediction_live_state: {sync_error}")


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
                    "is_live": item.is_live,
                    "last_status_text": item.last_status_text,
                    "last_checked_at": item.last_checked_at.isoformat() if item.last_checked_at else None,
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
                    "started_at": item.started_at.isoformat() if item.started_at else None,
                    "finished_at": item.finished_at.isoformat() if item.finished_at else None,
                    "last_checked_at": item.last_checked_at.isoformat() if item.last_checked_at else None,
                    "result_source": item.result_source,
                    "last_status_text": item.last_status_text,
                    "is_live": item.is_live,
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