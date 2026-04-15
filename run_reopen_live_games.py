import json
from pathlib import Path
from typing import Optional

from app.db import SessionLocal
from app.models import Prediction
from app.services.sportsdb_api import SportsDBAPI


JSON_PATH = Path("data/predictions_log.json")

LIVE_STATUSES = {
    "1h",
    "2h",
    "ht",
    "half time",
    "live",
    "in play",
    "break",
    "et",
    "extra time",
}

NOT_STARTED_STATUSES = {
    "ns",
    "not started",
    "scheduled",
}

FINAL_STATUSES = {
    "ft",
    "aet",
    "pen",
    "full time",
    "match finished",
    "after extra time",
    "after penalties",
    "finished",
}


def safe_int(value) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_text(value) -> str:
    return str(value or "").strip().lower()


def load_json_rows():
    if not JSON_PATH.exists():
        return []

    try:
        return json.loads(JSON_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def save_json_rows(rows):
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def reopen_json_row(rows, fixture_id: str) -> bool:
    updated = False

    for row in rows:
        if str(row.get("fixture_id")) == str(fixture_id):
            row["status"] = "pending"
            row["result"] = None
            row["home_score"] = None
            row["away_score"] = None
            row["checked_at"] = None
            updated = True
            break

    return updated


def is_live_or_not_finished(details: dict) -> bool:
    """
    Retorna True somente quando houver sinais de que o jogo
    ainda não terminou e precisa ser reaberto.
    """
    if not details:
        return False

    status = normalize_text(details.get("strStatus"))
    progress = normalize_text(details.get("strProgress"))
    locked = normalize_text(details.get("strLocked"))

    home_score = safe_int(details.get("intHomeScore"))
    away_score = safe_int(details.get("intAwayScore"))

    # Se está explicitamente travado/locked, NÃO reabre
    if locked == "locked":
        return False

    # Se está explicitamente final, NÃO reabre
    if status in FINAL_STATUSES or progress in FINAL_STATUSES:
        return False

    # Se está explicitamente ao vivo, reabre
    if status in LIVE_STATUSES or progress in LIVE_STATUSES:
        return True

    # Se está explícito que ainda não começou, também faz sentido reabrir
    # caso tenha sido fechado errado
    if status in NOT_STARTED_STATUSES or progress in NOT_STARTED_STATUSES:
        return True

    # status vazio + sem locked:
    # se tiver placar mas não locked, pode ser jogo em andamento com API ruim
    if home_score is not None and away_score is not None and locked != "locked":
        return True

    # status vazio e sem placar: não começou ou está inconclusivo
    if not status and not progress and locked != "locked":
        return True

    return False


def main():
    db = SessionLocal()
    api = SportsDBAPI()
    json_rows = load_json_rows()

    try:
        rows = (
            db.query(Prediction)
            .filter(Prediction.status.in_(["hit", "miss"]))
            .all()
        )

        checked = 0
        reopened_mysql = 0
        reopened_json = 0

        print("🚀 Iniciando reabertura de jogos em andamento...\n")

        for item in rows:
            fixture_id = str(item.fixture_id).strip()
            if not fixture_id:
                continue

            checked += 1

            try:
                details = api.get_event_details(fixture_id)
            except Exception as e:
                print(f"[REOPEN] Erro ao buscar details fixture={fixture_id}: {e}")
                continue

            if not details:
                print(f"[REOPEN] Sem details para fixture={fixture_id}")
                continue

            status = normalize_text(details.get("strStatus"))
            progress = normalize_text(details.get("strProgress"))
            locked = normalize_text(details.get("strLocked"))
            home_score = safe_int(details.get("intHomeScore"))
            away_score = safe_int(details.get("intAwayScore"))

            must_reopen = is_live_or_not_finished(details)

            if not must_reopen:
                continue

            print(
                f"[REOPEN] Reabrindo fixture={fixture_id} | "
                f"{item.home_team} x {item.away_team} | "
                f"salvo={item.home_score}x{item.away_score} ({item.result}/{item.status}) | "
                f"api_status='{status}' | progress='{progress}' | locked='{locked}' | "
                f"placar_api={home_score}x{away_score}"
            )

            item.status = "pending"
            item.result = None
            item.home_score = None
            item.away_score = None
            item.checked_at = None
            reopened_mysql += 1

            if reopen_json_row(json_rows, fixture_id):
                reopened_json += 1

        db.commit()
        save_json_rows(json_rows)

        print("\n✅ Reabertura concluída com sucesso")
        print(f"📌 Jogos verificados: {checked}")
        print(f"🛠️ Jogos reabertos no MySQL: {reopened_mysql}")
        print(f"🗂️ Jogos reabertos no JSON: {reopened_json}")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Erro na reabertura: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()