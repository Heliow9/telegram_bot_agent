from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, case, desc

from app.config import settings
from app.db import get_db
from app.models import Prediction, PredictionOdds
from app.schemas import PredictionListResponse
from app.deps import get_current_user


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


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

    # ===== RESOLVIDOS DO DIA =====
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

    # ===== FINANCEIRO =====
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
        "high_confidence_predictions": high_confidence_predictions,
        "value_bets": value_bets,
        "today_resolved_predictions": today_resolved_predictions,
        "today_hits": today_hits,
        "today_misses": today_misses,
        "today_accuracy": today_accuracy,
        "profit": round(total_profit, 2),
        "stake": round(total_stake, 2),
        "roi": roi,
        "roi_items": roi_count,
        "today_profit": round(today_profit, 2),
        "today_stake": round(today_stake, 2),
        "today_roi": today_roi,
        "today_roi_items": today_roi_count,
    }


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

    items = (
        query.order_by(Prediction.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return PredictionListResponse(items=items, total=total)


@router.get("/predictions/pending", response_model=PredictionListResponse)
def list_pending_predictions(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    query = db.query(Prediction).filter(Prediction.status == "pending")
    total = query.count()

    items = (
        query.order_by(Prediction.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return PredictionListResponse(items=items, total=total)


@router.get("/predictions/resolved", response_model=PredictionListResponse)
def list_resolved_predictions(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    query = db.query(Prediction).filter(Prediction.status.in_(["hit", "miss"]))
    total = query.count()

    items = (
        query.order_by(
            case((Prediction.checked_at.is_(None), 1), else_=0).asc(),
            desc(Prediction.checked_at),
            desc(Prediction.created_at),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    return PredictionListResponse(items=items, total=total)


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

        if opening is not None and latest is not None:
            movement = round(float(latest) - float(opening), 2)
            if movement < 0:
                movement_direction = "down"
            elif movement > 0:
                movement_direction = "up"

        items.append(
            {
                "prediction_id": prediction.id,
                "fixture_id": prediction.fixture_id,
                "league_name": prediction.league_name,
                "home_team": prediction.home_team,
                "away_team": prediction.away_team,
                "pick": prediction.pick,
                "status": prediction.status,
                "bookmaker": odds.bookmaker,
                "opening_market_odds": odds.opening_market_odds,
                "latest_market_odds": odds.latest_market_odds,
                "fair_home_odds": odds.fair_home_odds,
                "fair_draw_odds": odds.fair_draw_odds,
                "fair_away_odds": odds.fair_away_odds,
                "edge": odds.edge,
                "has_value_bet": odds.has_value_bet,
                "movement": movement,
                "movement_direction": movement_direction,
                "created_at": prediction.created_at.isoformat()
                if prediction.created_at
                else None,
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
    }