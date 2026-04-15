import json
from pathlib import Path
from typing import Optional

from app.db import SessionLocal
from app.models import Prediction
from app.services.sportsdb_api import SportsDBAPI

JSON_PATH = Path("data/predictions_log.json")


FINAL_STATUS_HINTS = {
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


def result_from_scores(home_score: Optional[int], away_score: Optional[int]) -> Optional[str]:
    if home_score is None or away_score is None:
        return None
    if home_score > away_score:
        return "1"
    if away_score > home_score:
        return "2"
    return "X"


def is_finished_event(details: dict) -> bool:
    if not details:
        return False

    locked = str(details.get("strLocked") or "").strip().lower()
    status = str(details.get("strStatus") or "").strip().lower()
    progress = str(details.get("strProgress") or "").strip().lower()

    home_score = safe_int(details.get("intHomeScore"))
    away_score = safe_int(details.get("intAwayScore"))

    # 1) locked é o melhor sinal
    if locked == "locked" and home_score is not None and away_score is not None:
        return True

    # 2) status final explícito
    if status in FINAL_STATUS_HINTS or progress in FINAL_STATUS_HINTS:
        return True

    # 3) fallback pragmático: placar preenchido
    # útil para casos em que a SportsDB deixa status vazio mas o jogo já acabou
    if home_score is not None and away_score is not None:
        return True

    return False


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


def update_json_row(rows, fixture_id: str, home_score: int, away_score: int, result: str, status: str):
    updated = False

    for row in rows:
        if str(row.get("fixture_id")) == str(fixture_id):
            row["home_score"] = home_score
            row["away_score"] = away_score
            row["result"] = result
            row["status"] = status
            updated = True
            break

    return updated


def main():
    db = SessionLocal()
    api = SportsDBAPI()

    json_rows = load_json_rows()

    try:
        rows = (
            db.query(Prediction)
            .filter(Prediction.fixture_id.is_not(None))
            .all()
        )

        checked = 0
        fixed = 0
        fixed_json = 0

        print("🚀 Iniciando auditoria forçada no MySQL + JSON...\n")

        for item in rows:
            fixture_id = str(item.fixture_id).strip()
            if not fixture_id:
                continue

            checked += 1

            try:
                details = api.get_event_details(fixture_id)
            except Exception as e:
                print(f"[REPAIR] Erro ao buscar details fixture={fixture_id}: {e}")
                continue

            if not details:
                print(f"[REPAIR] Sem details para fixture={fixture_id}")
                continue

            home_score = safe_int(details.get("intHomeScore"))
            away_score = safe_int(details.get("intAwayScore"))
            locked = str(details.get("strLocked") or "").strip().lower()
            status_text = str(details.get("strStatus") or "").strip()

            finished = is_finished_event(details)

            if not finished:
                print(
                    f"[REPAIR] Ainda não finalizado | "
                    f"fixture={fixture_id} | "
                    f"{item.home_team} x {item.away_team} | "
                    f"status='{status_text}' | locked='{locked}'"
                )
                continue

            if home_score is None or away_score is None:
                print(
                    f"[REPAIR] Finalizado sem placar válido | "
                    f"fixture={fixture_id} | "
                    f"{item.home_team} x {item.away_team}"
                )
                continue

            real_result = result_from_scores(home_score, away_score)
            if real_result is None:
                continue

            correct_status = "hit" if str(item.pick).strip().upper() == real_result else "miss"

            score_changed = item.home_score != home_score or item.away_score != away_score
            result_changed = str(item.result or "").strip().upper() != real_result
            status_changed = str(item.status or "").strip().lower() != correct_status

            if not (score_changed or result_changed or status_changed):
                continue

            print(
                f"[REPAIR] Corrigindo fixture={fixture_id} | "
                f"{item.home_team} x {item.away_team} | "
                f"salvo={item.home_score}x{item.away_score} ({item.result}/{item.status}) | "
                f"real={home_score}x{away_score} ({real_result}/{correct_status}) | "
                f"locked={locked} | status='{status_text}'"
            )

            item.home_score = home_score
            item.away_score = away_score
            item.result = real_result
            item.status = correct_status

            if update_json_row(
                json_rows,
                fixture_id=fixture_id,
                home_score=home_score,
                away_score=away_score,
                result=real_result,
                status=correct_status,
            ):
                fixed_json += 1

            fixed += 1

        db.commit()
        save_json_rows(json_rows)

        print("\n✅ Auditoria concluída com sucesso")
        print(f"📌 Jogos verificados: {checked}")
        print(f"🛠️ Jogos corrigidos no MySQL: {fixed}")
        print(f"🗂️ Jogos corrigidos no JSON: {fixed_json}")

        # destaque do Bayern
        bayern = (
            db.query(Prediction)
            .filter(Prediction.home_team == "Bayern Munich", Prediction.away_team == "Real Madrid")
            .first()
        )

        if bayern:
            print("\n🎯 Bayern x Real após correção:")
            print(
                f"fixture={bayern.fixture_id} | "
                f"placar={bayern.home_score}x{bayern.away_score} | "
                f"result={bayern.result} | status={bayern.status}"
            )

    except Exception as e:
        db.rollback()
        print(f"\n❌ Erro na auditoria forçada: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()