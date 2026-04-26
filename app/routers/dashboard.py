from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, case, desc, and_

from app.config import settings
from app.db import get_db
from app.models import Prediction, PredictionOdds
from app.schemas import PredictionListResponse
from app.deps import get_current_user
from app.services.ml_model_service import MLModelService
from app.services.performance_tuning_service import PerformanceTuningService


router = APIRouter(prefix="/dashboard", tags=["dashboard"])

MODEL_PATH = Path("models/1x2_model.joblib")


def _utc_naive_day_bounds():
    tz = ZoneInfo(settings.timezone)
    now_local = datetime.now(tz)

    start_local = datetime.combine(now_local.date(), time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)

    start_utc_naive = start_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    end_utc_naive = end_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    return start_utc_naive, end_utc_naive


def _calculate_profit(status: str, opening_odds):
    if opening_odds is None:
        return None

    try:
        odd = float(opening_odds)
    except (TypeError, ValueError):
        return None

    if odd <= 1:
        return None

    if status == "hit":
        return round(odd - 1.0, 4)

    if status == "miss":
        return -1.0

    return None


def _estimate_effective_ml_weight(metadata: dict) -> float:
    """
    Estima o peso efetivo do ML com base na saúde do treino.
    A ideia é não supervalorizar um modelo com pouca base ou baixa accuracy.
    """
    if not metadata:
        return 0.0

    try:
        rows = int(metadata.get("rows") or 0)
    except (TypeError, ValueError):
        rows = 0

    try:
        accuracy = float(metadata.get("accuracy")) if metadata.get("accuracy") is not None else 0.0
    except (TypeError, ValueError):
        accuracy = 0.0

    try:
        log_loss = (
            float(metadata.get("log_loss"))
            if metadata.get("log_loss") is not None
            else None
        )
    except (TypeError, ValueError):
        log_loss = None

    weight = 0.0

    if rows >= 30:
        weight = 0.10
    if rows >= 60:
        weight = 0.18
    if rows >= 100:
        weight = 0.25
    if rows >= 200:
        weight = 0.35
    if rows >= 400:
        weight = 0.45

    if accuracy >= 0.38:
        weight += 0.05
    if accuracy >= 0.42:
        weight += 0.05
    if accuracy >= 0.48:
        weight += 0.05

    if log_loss is not None:
        if log_loss <= 1.20:
            weight += 0.03
        if log_loss <= 1.05:
            weight += 0.03

    return round(min(max(weight, 0.0), 0.65), 4)


def _fair_odds_for_prediction(prediction: Prediction):
    odds = prediction.odds
    if not odds:
        return None
    pick = str(prediction.pick or "").upper()
    return {
        "1": odds.fair_home_odds,
        "X": odds.fair_draw_odds,
        "2": odds.fair_away_odds,
        "1X": odds.fair_odds_1x,
        "X2": odds.fair_odds_x2,
        "12": odds.fair_odds_12,
    }.get(pick)


def _odds_movement(prediction: Prediction):
    odds = prediction.odds
    if not odds or odds.opening_market_odds is None or odds.latest_market_odds is None:
        return None
    try:
        return round(float(odds.latest_market_odds) - float(odds.opening_market_odds), 2)
    except Exception:
        return None


def _odds_movement_direction(prediction: Prediction):
    movement = _odds_movement(prediction)
    if movement is None or movement == 0:
        return "stable"
    return "up" if movement > 0 else "down"

def _serialize_prediction(prediction: Prediction):
    return {
        "id": prediction.id,
        "fixture_id": prediction.fixture_id,
        "league_key": prediction.league_key,
        "league_name": prediction.league_name,
        "home_team": prediction.home_team,
        "away_team": prediction.away_team,
        "match_date": prediction.match_date,
        "match_time": prediction.match_time,
        "pick": prediction.pick,
        "market_type": prediction.market_type,
        "main_market_pick": prediction.main_market_pick,
        "double_chance_pick": prediction.double_chance_pick,
        "prob_home": prediction.prob_home,
        "prob_draw": prediction.prob_draw,
        "prob_away": prediction.prob_away,
        "prob_1x": prediction.prob_1x,
        "prob_x2": prediction.prob_x2,
        "prob_12": prediction.prob_12,
        "main_market_probability": prediction.main_market_probability,
        "double_chance_probability": prediction.double_chance_probability,
        "best_probability": prediction.best_probability,
        "confidence": prediction.confidence,
        "model_source": prediction.model_source,
        "status": prediction.status,
        "result": prediction.result,
        "home_score": prediction.home_score,
        "away_score": prediction.away_score,
        "features_json": prediction.features_json,
        "created_at": prediction.created_at.isoformat() if prediction.created_at else None,
        "checked_at": prediction.checked_at.isoformat() if prediction.checked_at else None,
        "started_at": prediction.started_at.isoformat() if prediction.started_at else None,
        "finished_at": prediction.finished_at.isoformat() if prediction.finished_at else None,
        "last_checked_at": prediction.last_checked_at.isoformat() if prediction.last_checked_at else None,
        "result_source": prediction.result_source,
        "last_status_text": prediction.last_status_text,
        "is_live": prediction.is_live,
        "bookmaker": prediction.odds.bookmaker if prediction.odds else None,
        "opening_market_odds": prediction.odds.opening_market_odds if prediction.odds else None,
        "latest_market_odds": prediction.odds.latest_market_odds if prediction.odds else None,
        "edge": prediction.odds.edge if prediction.odds else None,
        "has_value_bet": bool(prediction.odds.has_value_bet) if prediction.odds else False,
        "fair_odds": _fair_odds_for_prediction(prediction),
        "movement": _odds_movement(prediction),
        "movement_direction": _odds_movement_direction(prediction),
    }


def _build_model_status():
    ml_model = MLModelService()
    tuning_service = PerformanceTuningService()
    metadata = ml_model.get_metadata() if hasattr(ml_model, "get_metadata") else {}

    features = getattr(ml_model, "features_", None) or []
    classes = getattr(ml_model, "classes_", None) or []

    model_loaded = False
    try:
        model_loaded = bool(ml_model.is_available())
    except Exception:
        model_loaded = False

    last_training_at = None
    if MODEL_PATH.exists():
        try:
            modified_ts = MODEL_PATH.stat().st_mtime
            last_training_at = datetime.fromtimestamp(
                modified_ts,
                tz=ZoneInfo(settings.timezone),
            ).isoformat()
        except Exception:
            last_training_at = None

    return {
        "model_loaded": model_loaded,
        "model_path": str(MODEL_PATH),
        "last_training_at": metadata.get("trained_at") or last_training_at,
        "rows": metadata.get("rows", 0),
        "train_rows": metadata.get("train_rows", 0),
        "test_rows": metadata.get("test_rows", 0),
        "accuracy": metadata.get("accuracy"),
        "log_loss": metadata.get("log_loss"),
        "classes": classes,
        "class_distribution": metadata.get("class_distribution", {}),
        "features_count": len(features),
        "features": features,
        "effective_ml_weight": _estimate_effective_ml_weight(metadata),
        "historical_reliability": tuning_service.reliability_state(),
    }


@router.get("/summary")
def dashboard_summary(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    total_predictions = db.query(func.count(Prediction.id)).scalar() or 0

    resolved_predictions = (
        db.query(func.count(Prediction.id))
        .filter(Prediction.status.in_(["hit", "miss"]))
        .scalar()
        or 0
    )

    hits = (
        db.query(func.count(Prediction.id))
        .filter(Prediction.status == "hit")
        .scalar()
        or 0
    )

    misses = (
        db.query(func.count(Prediction.id))
        .filter(Prediction.status == "miss")
        .scalar()
        or 0
    )

    pending_predictions = (
        db.query(func.count(Prediction.id))
        .filter(Prediction.status == "pending")
        .scalar()
        or 0
    )

    live_filter = and_(
        Prediction.is_live.is_(True),
        Prediction.status == "pending",
        Prediction.started_at.is_not(None),
        Prediction.finished_at.is_(None),
    )

    live_predictions = (
        db.query(func.count(Prediction.id))
        .filter(live_filter)
        .scalar()
        or 0
    )

    high_confidence_predictions = (
        db.query(func.count(Prediction.id))
        .filter(Prediction.confidence == "alta")
        .scalar()
        or 0
    )

    value_bets = (
        db.query(func.count(PredictionOdds.id))
        .filter(PredictionOdds.has_value_bet.is_(True))
        .scalar()
        or 0
    )

    accuracy = round(hits / resolved_predictions, 4) if resolved_predictions else 0.0

    start_utc, end_utc = _utc_naive_day_bounds()

    today_resolved_predictions = (
        db.query(func.count(Prediction.id))
        .filter(
            Prediction.status.in_(["hit", "miss"]),
            Prediction.checked_at.is_not(None),
            Prediction.checked_at >= start_utc,
            Prediction.checked_at < end_utc,
        )
        .scalar()
        or 0
    )

    today_hits = (
        db.query(func.count(Prediction.id))
        .filter(
            Prediction.status == "hit",
            Prediction.checked_at.is_not(None),
            Prediction.checked_at >= start_utc,
            Prediction.checked_at < end_utc,
        )
        .scalar()
        or 0
    )

    today_misses = (
        db.query(func.count(Prediction.id))
        .filter(
            Prediction.status == "miss",
            Prediction.checked_at.is_not(None),
            Prediction.checked_at >= start_utc,
            Prediction.checked_at < end_utc,
        )
        .scalar()
        or 0
    )

    today_accuracy = (
        round(today_hits / today_resolved_predictions, 4)
        if today_resolved_predictions
        else 0.0
    )

    today_live_predictions = (
        db.query(func.count(Prediction.id))
        .filter(
            live_filter,
            Prediction.started_at.is_not(None),
            Prediction.started_at >= start_utc,
            Prediction.started_at < end_utc,
        )
        .scalar()
        or 0
    )

    resolved_with_odds = (
        db.query(Prediction, PredictionOdds)
        .outerjoin(PredictionOdds, PredictionOdds.prediction_id == Prediction.id)
        .filter(Prediction.status.in_(["hit", "miss"]))
        .all()
    )

    total_profit = 0.0
    total_stake = 0.0
    roi_count = 0

    today_profit = 0.0
    today_stake = 0.0
    today_roi_count = 0

    for prediction, odds in resolved_with_odds:
        opening_odds = odds.opening_market_odds if odds else None
        profit = _calculate_profit(prediction.status, opening_odds)

        if profit is not None:
            total_profit += profit
            total_stake += 1.0
            roi_count += 1

            if (
                prediction.checked_at is not None
                and prediction.checked_at >= start_utc
                and prediction.checked_at < end_utc
            ):
                today_profit += profit
                today_stake += 1.0
                today_roi_count += 1

    roi = round(total_profit / total_stake, 4) if total_stake else 0.0
    today_roi = round(today_profit / today_stake, 4) if today_stake else 0.0

    return {
        "total_predictions": total_predictions,
        "resolved_predictions": resolved_predictions,
        "hits": hits,
        "misses": misses,
        "accuracy": accuracy,
        "pending_predictions": pending_predictions,
        "live_predictions": live_predictions,
        "high_confidence_predictions": high_confidence_predictions,
        "value_bets": value_bets,
        "today_resolved_predictions": today_resolved_predictions,
        "today_hits": today_hits,
        "today_misses": today_misses,
        "today_accuracy": today_accuracy,
        "today_live_predictions": today_live_predictions,
        "profit": round(total_profit, 2),
        "stake": round(total_stake, 2),
        "roi": roi,
        "roi_items": roi_count,
        "today_profit": round(today_profit, 2),
        "today_stake": round(today_stake, 2),
        "today_roi": today_roi,
        "today_roi_items": today_roi_count,
    }


@router.get("/model-status")
def model_status(current_user=Depends(get_current_user)):
    return _build_model_status()


@router.get("/predictions", response_model=PredictionListResponse)
def list_predictions(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    status: str | None = Query(default=None),
    league_name: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    query = db.query(Prediction)

    if status:
        query = query.filter(Prediction.status == status)

    if league_name:
        query = query.filter(Prediction.league_name == league_name)

    total = query.count()

    rows = (
        query.order_by(Prediction.match_date.asc(), Prediction.match_time.asc(), Prediction.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    items = [_serialize_prediction(row) for row in rows]

    return {
        "items": items,
        "total": total,
    }


@router.get("/predictions/pending", response_model=PredictionListResponse)
def list_pending_predictions(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    query = db.query(Prediction).filter(Prediction.status == "pending")
    total = query.count()

    rows = (
        query.order_by(Prediction.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    items = [_serialize_prediction(row) for row in rows]

    return {
        "items": items,
        "total": total,
    }


@router.get("/predictions/resolved", response_model=PredictionListResponse)
def list_resolved_predictions(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    query = db.query(Prediction).filter(Prediction.status.in_(["hit", "miss"]))
    total = query.count()

    rows = (
        query.order_by(
            case((Prediction.checked_at.is_(None), 1), else_=0).asc(),
            desc(Prediction.checked_at),
            desc(Prediction.created_at),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    items = [_serialize_prediction(row) for row in rows]

    return {
        "items": items,
        "total": total,
    }


@router.get("/market")
def market_overview(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    rows = (
        db.query(Prediction, PredictionOdds)
        .join(PredictionOdds, PredictionOdds.prediction_id == Prediction.id)
        .order_by(Prediction.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    items = []

    for prediction, odds in rows:
        opening = odds.opening_market_odds
        latest = odds.latest_market_odds

        movement = None
        movement_direction = "stable"

        try:
            if opening is not None and latest is not None:
                opening = float(opening)
                latest = float(latest)

                movement = round(latest - opening, 2)

                if movement > 0:
                    movement_direction = "up"
                elif movement < 0:
                    movement_direction = "down"
        except Exception:
            movement = None
            movement_direction = "stable"

        fair_odds = None

        try:
            pick = (prediction.pick or "").upper()

            if pick == "1":
                fair_odds = odds.fair_home_odds
            elif pick == "X":
                fair_odds = odds.fair_draw_odds
            elif pick == "2":
                fair_odds = odds.fair_away_odds
            elif pick == "1X":
                fair_odds = odds.fair_odds_1x
            elif pick == "X2":
                fair_odds = odds.fair_odds_x2
            elif pick == "12":
                fair_odds = odds.fair_odds_12
        except Exception:
            fair_odds = None

        market_type = getattr(prediction, "market_type", None) or "1x2"

        status = (prediction.status or "").lower()
        if status not in ["pending", "hit", "miss"]:
            status = "pending"

        items.append(
            {
                "prediction_id": prediction.id,
                "fixture_id": prediction.fixture_id,
                "league_name": prediction.league_name,
                "home_team": prediction.home_team,
                "away_team": prediction.away_team,
                "match_date": prediction.match_date,
                "match_time": prediction.match_time,
                "pick": prediction.pick,
                "market_type": market_type,
                "status": status,
                "result": prediction.result,
                "home_score": prediction.home_score,
                "away_score": prediction.away_score,
                "confidence": prediction.confidence,
                "bookmaker": odds.bookmaker,
                "opening_market_odds": odds.opening_market_odds,
                "latest_market_odds": odds.latest_market_odds,
                "fair_odds": fair_odds,
                "edge": odds.edge,
                "has_value_bet": odds.has_value_bet,
                "home_odds": odds.home_odds,
                "draw_odds": odds.draw_odds,
                "away_odds": odds.away_odds,
                "odds_1x": odds.odds_1x,
                "odds_x2": odds.odds_x2,
                "odds_12": odds.odds_12,
                "fair_home_odds": odds.fair_home_odds,
                "fair_draw_odds": odds.fair_draw_odds,
                "fair_away_odds": odds.fair_away_odds,
                "fair_odds_1x": odds.fair_odds_1x,
                "fair_odds_x2": odds.fair_odds_x2,
                "fair_odds_12": odds.fair_odds_12,
                "movement": movement,
                "movement_direction": movement_direction,
                "is_live": prediction.is_live,
                "created_at": prediction.created_at.isoformat() if prediction.created_at else None,
                "checked_at": prediction.checked_at.isoformat() if prediction.checked_at else None,
                "started_at": prediction.started_at.isoformat() if prediction.started_at else None,
                "finished_at": prediction.finished_at.isoformat() if prediction.finished_at else None,
                "last_checked_at": prediction.last_checked_at.isoformat() if prediction.last_checked_at else None,
                "result_source": prediction.result_source,
                "last_status_text": prediction.last_status_text,
            }
        )

    total = db.query(func.count(PredictionOdds.id)).scalar() or 0

    return {
        "items": items,
        "total": total,
    }


@router.get("/model-performance")
def model_performance(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    resolved_rows = (
        db.query(Prediction, PredictionOdds)
        .outerjoin(PredictionOdds, PredictionOdds.prediction_id == Prediction.id)
        .filter(Prediction.status.in_(["hit", "miss"]))
        .all()
    )

    resolved_total = len(resolved_rows)
    hits = sum(1 for prediction, _ in resolved_rows if prediction.status == "hit")
    misses = sum(1 for prediction, _ in resolved_rows if prediction.status == "miss")
    accuracy = round(hits / resolved_total, 4) if resolved_total else 0.0

    total_profit = 0.0
    total_stake = 0.0

    for prediction, odds in resolved_rows:
        opening_odds = odds.opening_market_odds if odds else None
        profit = _calculate_profit(prediction.status, opening_odds)
        if profit is not None:
            total_profit += profit
            total_stake += 1.0

    roi = round(total_profit / total_stake, 4) if total_stake else 0.0

    by_confidence = []
    for confidence in ["alta", "média", "baixa"]:
        conf_rows = [
            (prediction, odds)
            for prediction, odds in resolved_rows
            if prediction.confidence == confidence
        ]

        total = len(conf_rows)
        conf_hits = sum(1 for prediction, _ in conf_rows if prediction.status == "hit")
        conf_misses = sum(1 for prediction, _ in conf_rows if prediction.status == "miss")
        conf_accuracy = round(conf_hits / total, 4) if total else 0.0

        conf_profit = 0.0
        conf_stake = 0.0

        for prediction, odds in conf_rows:
            opening_odds = odds.opening_market_odds if odds else None
            profit = _calculate_profit(prediction.status, opening_odds)
            if profit is not None:
                conf_profit += profit
                conf_stake += 1.0

        conf_roi = round(conf_profit / conf_stake, 4) if conf_stake else 0.0

        by_confidence.append(
            {
                "confidence": confidence,
                "total": total,
                "hits": conf_hits,
                "misses": conf_misses,
                "accuracy": conf_accuracy,
                "profit": round(conf_profit, 2),
                "stake": round(conf_stake, 2),
                "roi": conf_roi,
            }
        )

    league_map = {}

    for prediction, odds in resolved_rows:
        league_name = prediction.league_name or "Sem liga"

        if league_name not in league_map:
            league_map[league_name] = {
                "league_name": league_name,
                "total": 0,
                "hits": 0,
                "misses": 0,
                "accuracy": 0.0,
                "profit": 0.0,
                "stake": 0.0,
                "roi": 0.0,
            }

        league_map[league_name]["total"] += 1

        if prediction.status == "hit":
            league_map[league_name]["hits"] += 1
        elif prediction.status == "miss":
            league_map[league_name]["misses"] += 1

        opening_odds = odds.opening_market_odds if odds else None
        profit = _calculate_profit(prediction.status, opening_odds)
        if profit is not None:
            league_map[league_name]["profit"] += profit
            league_map[league_name]["stake"] += 1.0

    by_league = []
    for _, item in league_map.items():
        total = item["total"]
        hits_count = item["hits"]
        stake = item["stake"]

        item["accuracy"] = round(hits_count / total, 4) if total else 0.0
        item["profit"] = round(item["profit"], 2)
        item["stake"] = round(stake, 2)
        item["roi"] = round(item["profit"] / stake, 4) if stake else 0.0
        by_league.append(item)

    by_league.sort(key=lambda x: x["total"], reverse=True)

    market_map = {}
    for prediction, odds in resolved_rows:
        market_type = (prediction.market_type or "1x2").strip().lower() or "1x2"
        market_entry = market_map.setdefault(
            market_type,
            {
                "market_type": market_type,
                "total": 0,
                "hits": 0,
                "misses": 0,
                "profit": 0.0,
                "stake": 0.0,
            },
        )
        market_entry["total"] += 1

        if prediction.status == "hit":
            market_entry["hits"] += 1
        elif prediction.status == "miss":
            market_entry["misses"] += 1

        opening_odds = odds.opening_market_odds if odds else None
        profit = _calculate_profit(prediction.status, opening_odds)
        if profit is not None:
            market_entry["profit"] += profit
            market_entry["stake"] += 1.0

    by_market = []
    for _, item in market_map.items():
        total = item["total"]
        stake = item["stake"]
        item["accuracy"] = round(item["hits"] / total, 4) if total else 0.0
        item["profit"] = round(item["profit"], 2)
        item["stake"] = round(stake, 2)
        item["roi"] = round(item["profit"] / stake, 4) if stake else 0.0
        by_market.append(item)

    by_market.sort(key=lambda x: x["total"], reverse=True)

    tuning_service = PerformanceTuningService()

    return {
        "summary": {
            "resolved_total": resolved_total,
            "hits": hits,
            "misses": misses,
            "accuracy": accuracy,
            "profit": round(total_profit, 2),
            "stake": round(total_stake, 2),
            "roi": roi,
        },
        "by_confidence": by_confidence,
        "by_league": by_league,
        "by_market": by_market,
        "historical_reliability": tuning_service.reliability_state(),
    }
