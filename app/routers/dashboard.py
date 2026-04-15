from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, case, desc

from app.config import settings
from app.db import get_db
from app.models import Prediction, PredictionOdds
from app.schemas import DashboardSummaryResponse, PredictionListResponse
from app.deps import get_current_user


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _utc_naive_day_bounds():
    """
    Como o sistema salva checked_at/created_at usando datetime.utcnow() (naive UTC),
    calculamos o início e fim do dia na timezone local e convertemos para UTC naive.
    """
    tz = ZoneInfo(settings.timezone)
    now_local = datetime.now(tz)

    start_local = datetime.combine(now_local.date(), time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)

    start_utc_naive = start_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    end_utc_naive = end_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    return start_utc_naive, end_utc_naive


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

    # ===== RESUMO DO DIA BASEADO EM checked_at =====
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
    resolved_query = db.query(Prediction).filter(Prediction.status.in_(["hit", "miss"]))

    resolved_total = resolved_query.count()
    hits = resolved_query.filter(Prediction.status == "hit").count()
    misses = resolved_query.filter(Prediction.status == "miss").count()
    accuracy = round(hits / resolved_total, 4) if resolved_total else 0.0

    by_confidence = []
    for confidence in ["alta", "média", "baixa"]:
        total = resolved_query.filter(Prediction.confidence == confidence).count()
        conf_hits = (
            resolved_query.filter(
                Prediction.confidence == confidence,
                Prediction.status == "hit",
            ).count()
        )
        conf_accuracy = round(conf_hits / total, 4) if total else 0.0

        by_confidence.append(
            {
                "confidence": confidence,
                "total": total,
                "hits": conf_hits,
                "misses": total - conf_hits,
                "accuracy": conf_accuracy,
            }
        )

    league_rows = (
        db.query(
            Prediction.league_name.label("league_name"),
            func.count(Prediction.id).label("total"),
            func.sum(case((Prediction.status == "hit", 1), else_=0)).label("hits"),
            func.sum(case((Prediction.status == "miss", 1), else_=0)).label("misses"),
        )
        .filter(Prediction.status.in_(["hit", "miss"]))
        .group_by(Prediction.league_name)
        .order_by(desc("total"))
        .all()
    )

    by_league = []
    for row in league_rows:
        total = int(row.total or 0)
        league_hits = int(row.hits or 0)
        league_misses = int(row.misses or 0)
        league_accuracy = round(league_hits / total, 4) if total else 0.0

        by_league.append(
            {
                "league_name": row.league_name or "Sem liga",
                "total": total,
                "hits": league_hits,
                "misses": league_misses,
                "accuracy": league_accuracy,
            }
        )

    return {
        "summary": {
            "resolved_total": resolved_total,
            "hits": hits,
            "misses": misses,
            "accuracy": accuracy,
        },
        "by_confidence": by_confidence,
        "by_league": by_league,
    }