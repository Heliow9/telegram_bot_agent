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


def _safe_float(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_json_loads(raw_value):
    if raw_value is None:
        return None

    if isinstance(raw_value, dict):
        return raw_value

    if isinstance(raw_value, str):
        raw_value = raw_value.strip()
        if not raw_value:
            return None

        try:
            return json.loads(raw_value)
        except json.JSONDecodeError:
            return None

    return None


def _build_odds_snapshot(odds: Optional[PredictionOdds]) -> Optional[Dict]:
    if not odds:
        return None

    return {
        "bookmaker": odds.bookmaker,
        "home_odds": _safe_float(odds.home_odds),
        "draw_odds": _safe_float(odds.draw_odds),
        "away_odds": _safe_float(odds.away_odds),
        "odds_1x": _safe_float(odds.odds_1x),
        "odds_x2": _safe_float(odds.odds_x2),
        "odds_12": _safe_float(odds.odds_12),
    }


def _build_fair_odds_snapshot(odds: Optional[PredictionOdds]) -> Optional[Dict]:
    if not odds:
        return None

    return {
        "1": _safe_float(odds.fair_home_odds),
        "X": _safe_float(odds.fair_draw_odds),
        "2": _safe_float(odds.fair_away_odds),
        "1X": _safe_float(odds.fair_odds_1x),
        "X2": _safe_float(odds.fair_odds_x2),
        "12": _safe_float(odds.fair_odds_12),
    }


def _build_clv_snapshot(odds: Optional[PredictionOdds]) -> Optional[Dict]:
    if not odds:
        return None

    opening = _safe_float(odds.opening_market_odds)
    latest = _safe_float(odds.latest_market_odds)

    if opening is None or latest is None:
        return None

    return {
        "opening_odds": round(opening, 2),
        "closing_odds": round(latest, 2),
        "movement": round(latest - opening, 2),
    }


def _serialize_prediction_row(
    prediction: Prediction,
    odds: Optional[PredictionOdds] = None,
) -> Dict:
    return {
        "saved_at": prediction.created_at.isoformat() if prediction.created_at else None,
        "league": prediction.league_name,
        "fixture_id": prediction.fixture_id,
        "home_team": prediction.home_team,
        "away_team": prediction.away_team,
        "date": prediction.match_date,
        "time": prediction.match_time,
        "pick": prediction.pick,
        "market_type": prediction.market_type,
        "main_market_pick": prediction.main_market_pick,
        "double_chance_pick": prediction.double_chance_pick,
        "prob_home": round(float(prediction.prob_home or 0.0), 4),
        "prob_draw": round(float(prediction.prob_draw or 0.0), 4),
        "prob_away": round(float(prediction.prob_away or 0.0), 4),
        "prob_1x": _safe_float(prediction.prob_1x),
        "prob_x2": _safe_float(prediction.prob_x2),
        "prob_12": _safe_float(prediction.prob_12),
        "main_market_probability": _safe_float(prediction.main_market_probability),
        "double_chance_probability": _safe_float(prediction.double_chance_probability),
        "best_probability": _safe_float(prediction.best_probability),
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
        "features": _safe_json_loads(prediction.features_json),
        "model_source": prediction.model_source,
        "odds_snapshot": _build_odds_snapshot(odds),
        "fair_odds_snapshot": _build_fair_odds_snapshot(odds),
        "opening_market_odds": _safe_float(odds.opening_market_odds) if odds else None,
        "latest_market_odds": _safe_float(odds.latest_market_odds) if odds else None,
        "clv": _build_clv_snapshot(odds),
    }


def _sync_db_to_json():
    db = SessionLocal()
    try:
        rows = (
            db.query(Prediction, PredictionOdds)
            .outerjoin(PredictionOdds, PredictionOdds.prediction_id == Prediction.id)
            .order_by(Prediction.created_at.desc())
            .all()
        )

        data: List[Dict] = [
            _serialize_prediction_row(prediction, odds)
            for prediction, odds in rows
        ]

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
            print(
                f"[PREDICTION_STORE][JSON] "
                f"Erro ao sincronizar após save_prediction: {sync_error}"
            )


def get_prediction_by_fixture_id(fixture_id: str) -> Optional[Dict]:
    db = SessionLocal()
    try:
        normalized_fixture_id = _normalize_fixture_id(fixture_id)

        row = (
            db.query(Prediction, PredictionOdds)
            .outerjoin(PredictionOdds, PredictionOdds.prediction_id == Prediction.id)
            .filter(Prediction.fixture_id == normalized_fixture_id)
            .first()
        )

        if not row:
            return None

        prediction, odds = row
        return _serialize_prediction_row(prediction, odds)

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
            print(
                f"[PREDICTION_STORE][JSON] "
                f"Erro ao sincronizar após update_prediction_result: {sync_error}"
            )


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
            print(
                f"[PREDICTION_STORE][JSON] "
                f"Erro ao sincronizar após update_prediction_market_odds: {sync_error}"
            )


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
            print(
                f"[PREDICTION_STORE][JSON] "
                f"Erro ao sincronizar após update_prediction_live_state: {sync_error}"
            )


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
                    "market_type": item.market_type,  # ✅ ESSENCIAL
                    "confidence": item.confidence,
                    "status": item.status,
                    "model_source": item.model_source,
                    "is_live": item.is_live,
                    "last_status_text": item.last_status_text,
                    "last_checked_at": (
                        item.last_checked_at.isoformat()
                        if item.last_checked_at else None
                    ),
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
                    "market_type": item.market_type,  # ✅ NOVO
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
                    "market_type": item.market_type,
                    "main_market_pick": item.main_market_pick,
                    "double_chance_pick": item.double_chance_pick,
                    "prob_home": item.prob_home,
                    "prob_draw": item.prob_draw,
                    "prob_away": item.prob_away,
                    "prob_1x": item.prob_1x,
                    "prob_x2": item.prob_x2,
                    "prob_12": item.prob_12,
                    "main_market_probability": item.main_market_probability,
                    "double_chance_probability": item.double_chance_probability,
                    "best_probability": item.best_probability,
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