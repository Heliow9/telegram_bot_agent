import json
from pathlib import Path
from datetime import datetime


STORE_PATH = Path("data/predictions_log.json")


def ensure_store():
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not STORE_PATH.exists():
        STORE_PATH.write_text("[]", encoding="utf-8")


def load_predictions():
    ensure_store()
    try:
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def save_prediction(payload: dict):
    data = load_predictions()

    record = {
        "saved_at": datetime.utcnow().isoformat(),
        "league": payload["league"]["display_name"],
        "fixture_id": payload["fixture"]["id"],
        "home_team": payload["fixture"]["home_team"],
        "away_team": payload["fixture"]["away_team"],
        "date": payload["fixture"]["date"],
        "time": payload["fixture"]["time"],
        "pick": payload["analysis"]["suggested_pick"],
        "prob_home": round(payload["analysis"]["prob_home"], 4),
        "prob_draw": round(payload["analysis"]["prob_draw"], 4),
        "prob_away": round(payload["analysis"]["prob_away"], 4),
        "confidence": payload["analysis"]["confidence"],
    }

    already_exists = any(item.get("fixture_id") == record["fixture_id"] for item in data)
    if not already_exists:
        data.append(record)

    STORE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )