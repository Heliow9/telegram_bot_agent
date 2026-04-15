import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List

from app.services.prediction_store_db import (
    save_prediction_db,
    update_prediction_result_db,
    update_prediction_market_odds_db,
)


STORE_PATH = Path("data/predictions_log.json")


def ensure_store():
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not STORE_PATH.exists():
        STORE_PATH.write_text("[]", encoding="utf-8")


def load_predictions() -> List[Dict]:
    ensure_store()
    try:
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def save_all_predictions(data: List[Dict]):
    ensure_store()
    STORE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _normalize_fixture_id(value) -> str:
    return str(value or "").strip()


def save_prediction(payload: dict):
    data = load_predictions()

    fixture = payload.get("fixture") or {}
    analysis = payload.get("analysis") or {}
    league = payload.get("league") or {}

    fixture_id = _normalize_fixture_id(fixture.get("id"))
    if not fixture_id:
        raise ValueError(f"Payload sem fixture.id válido: {payload}")

    odds = analysis.get("odds") or {}
    suggested_pick = analysis.get("suggested_pick")

    opening_market_odds = None
    if odds:
        if suggested_pick == "1":
            opening_market_odds = odds.get("home_odds")
        elif suggested_pick == "X":
            opening_market_odds = odds.get("draw_odds")
        elif suggested_pick == "2":
            opening_market_odds = odds.get("away_odds")

    record = {
        "saved_at": datetime.utcnow().isoformat(),
        "league": league.get("display_name"),
        "fixture_id": fixture_id,
        "home_team": fixture.get("home_team"),
        "away_team": fixture.get("away_team"),
        "date": fixture.get("date"),
        "time": fixture.get("time"),
        "pick": suggested_pick,
        "prob_home": round(float(analysis.get("prob_home", 0.0)), 4),
        "prob_draw": round(float(analysis.get("prob_draw", 0.0)), 4),
        "prob_away": round(float(analysis.get("prob_away", 0.0)), 4),
        "confidence": analysis.get("confidence"),
        "result": None,
        "home_score": None,
        "away_score": None,
        "status": "pending",
        "checked_at": None,
        "features": analysis.get("features"),
        "model_source": analysis.get("model_source"),
        "odds_snapshot": odds,
        "fair_odds_snapshot": analysis.get("fair_odds"),
        "opening_market_odds": opening_market_odds,
        "latest_market_odds": opening_market_odds,
        "clv": None,
    }

    already_exists = any(
        _normalize_fixture_id(item.get("fixture_id")) == fixture_id
        for item in data
    )

    if not already_exists:
        data.append(record)
        save_all_predictions(data)
        print(f"[PREDICTION_STORE] JSON salvo | fixture_id={fixture_id}")
    else:
        print(f"[PREDICTION_STORE] JSON já existe | fixture_id={fixture_id}")

    try:
        save_prediction_db(payload)
    except Exception as e:
        print(f"[PREDICTION_STORE][DB] Erro ao salvar previsão no MySQL: {e}")


def get_prediction_by_fixture_id(fixture_id: str) -> Optional[Dict]:
    fixture_id = _normalize_fixture_id(fixture_id)
    data = load_predictions()
    for item in data:
        if _normalize_fixture_id(item.get("fixture_id")) == fixture_id:
            return item
    return None


def update_prediction_result(
    fixture_id: str,
    result: str,
    home_score: int,
    away_score: int,
):
    fixture_id = _normalize_fixture_id(fixture_id)
    data = load_predictions()
    updated = False

    for item in data:
        if _normalize_fixture_id(item.get("fixture_id")) == fixture_id:
            item["result"] = result
            item["home_score"] = home_score
            item["away_score"] = away_score
            item["checked_at"] = datetime.utcnow().isoformat()
            item["status"] = "hit" if str(item.get("pick")) == str(result) else "miss"
            updated = True
            break

    if updated:
        save_all_predictions(data)
    else:
        print(f"[PREDICTION_STORE] Resultado sem item no JSON | fixture_id={fixture_id}")

    try:
        update_prediction_result_db(
            fixture_id=fixture_id,
            result=result,
            home_score=home_score,
            away_score=away_score,
        )
    except Exception as e:
        print(f"[PREDICTION_STORE][DB] Erro ao atualizar resultado no MySQL: {e}")


def update_prediction_market_odds(
    fixture_id: str,
    latest_market_odds: Optional[float],
):
    if latest_market_odds is None:
        return

    fixture_id = _normalize_fixture_id(fixture_id)
    data = load_predictions()
    updated = False

    for item in data:
        if _normalize_fixture_id(item.get("fixture_id")) == fixture_id:
            item["latest_market_odds"] = latest_market_odds

            opening = item.get("opening_market_odds")
            if opening is not None:
                item["clv"] = {
                    "opening_odds": round(float(opening), 2),
                    "closing_odds": round(float(latest_market_odds), 2),
                    "movement": round(float(latest_market_odds) - float(opening), 2),
                }
            updated = True
            break

    if updated:
        save_all_predictions(data)

    try:
        update_prediction_market_odds_db(
            fixture_id=fixture_id,
            latest_market_odds=latest_market_odds,
        )
    except Exception as e:
        print(f"[PREDICTION_STORE][DB] Erro ao atualizar odds no MySQL: {e}")


def get_pending_predictions():
    data = load_predictions()
    return [
        item for item in data
        if item.get("status") in (None, "pending")
    ]


def get_resolved_predictions() -> List[Dict]:
    return [item for item in load_predictions() if item.get("status") in ("hit", "miss")]


def build_stats() -> Dict:
    data = load_predictions()
    resolved = [item for item in data if item.get("status") in ("hit", "miss")]

    total = len(data)
    resolved_total = len(resolved)
    hits = sum(1 for item in resolved if item.get("status") == "hit")
    misses = sum(1 for item in resolved if item.get("status") == "miss")
    accuracy = (hits / resolved_total) if resolved_total else 0.0

    by_confidence = {}
    for confidence in ("alta", "média", "baixa"):
        items = [item for item in resolved if item.get("confidence") == confidence]
        conf_total = len(items)
        conf_hits = sum(1 for item in items if item.get("status") == "hit")
        by_confidence[confidence] = {
            "total": conf_total,
            "hits": conf_hits,
            "accuracy": round((conf_hits / conf_total), 4) if conf_total else 0.0,
        }

    by_league = {}
    leagues = sorted(set(item.get("league", "") for item in resolved))
    for league in leagues:
        items = [item for item in resolved if item.get("league") == league]
        league_total = len(items)
        league_hits = sum(1 for item in items if item.get("status") == "hit")
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