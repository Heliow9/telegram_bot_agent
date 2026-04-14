import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List


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


def save_prediction(payload: dict):
    data = load_predictions()

    analysis = payload["analysis"]
    odds = analysis.get("odds")
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
        "league": payload["league"]["display_name"],
        "fixture_id": payload["fixture"]["id"],
        "home_team": payload["fixture"]["home_team"],
        "away_team": payload["fixture"]["away_team"],
        "date": payload["fixture"]["date"],
        "time": payload["fixture"]["time"],
        "pick": analysis["suggested_pick"],
        "prob_home": round(analysis["prob_home"], 4),
        "prob_draw": round(analysis["prob_draw"], 4),
        "prob_away": round(analysis["prob_away"], 4),
        "confidence": analysis["confidence"],
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

    already_exists = any(item.get("fixture_id") == record["fixture_id"] for item in data)
    if not already_exists:
        data.append(record)
        save_all_predictions(data)


def get_prediction_by_fixture_id(fixture_id: str) -> Optional[Dict]:
    data = load_predictions()
    for item in data:
        if str(item.get("fixture_id")) == str(fixture_id):
            return item
    return None


def update_prediction_result(
    fixture_id: str,
    result: str,
    home_score: int,
    away_score: int,
):
    data = load_predictions()

    for item in data:
        if str(item.get("fixture_id")) == str(fixture_id):
            item["result"] = result
            item["home_score"] = home_score
            item["away_score"] = away_score
            item["checked_at"] = datetime.utcnow().isoformat()
            item["status"] = "hit" if item.get("pick") == result else "miss"
            break

    save_all_predictions(data)


def update_prediction_market_odds(
    fixture_id: str,
    latest_market_odds: Optional[float],
):
    if latest_market_odds is None:
        return

    data = load_predictions()

    for item in data:
        if str(item.get("fixture_id")) == str(fixture_id):
            item["latest_market_odds"] = latest_market_odds

            opening = item.get("opening_market_odds")
            if opening is not None:
                item["clv"] = {
                    "opening_odds": round(float(opening), 2),
                    "closing_odds": round(float(latest_market_odds), 2),
                    "movement": round(float(latest_market_odds) - float(opening), 2),
                }
            break

    save_all_predictions(data)


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