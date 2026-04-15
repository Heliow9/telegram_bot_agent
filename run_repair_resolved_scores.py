from app.db import SessionLocal
from app.models import Prediction
from app.services.sportsdb_api import SportsDBAPI


def normalize_result_from_scores(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "1"
    if away_score > home_score:
        return "2"
    return "X"


def main():
    db = SessionLocal()
    api = SportsDBAPI()

    try:
        rows = (
            db.query(Prediction)
            .filter(Prediction.status.in_(["hit", "miss"]))
            .all()
        )

        fixed = 0
        checked = 0

        for item in rows:
            checked += 1

            details = api.get_event_details(item.fixture_id)
            if not details:
                print(f"[REPAIR] Sem details para fixture_id={item.fixture_id}")
                continue

            result_data = api.get_event_result(item.fixture_id)
            if not result_data:
                print(f"[REPAIR] Sem result_data para fixture_id={item.fixture_id}")
                continue

            finished = bool(result_data.get("finished"))
            if not finished:
                print(
                    f"[REPAIR] Ainda não finalizado, ignorando | "
                    f"fixture_id={item.fixture_id} | "
                    f"{item.home_team} x {item.away_team}"
                )
                continue

            home_score = result_data.get("home_score")
            away_score = result_data.get("away_score")

            if home_score is None or away_score is None:
                print(
                    f"[REPAIR] Finalizado sem placar confiável | "
                    f"fixture_id={item.fixture_id}"
                )
                continue

            real_result = normalize_result_from_scores(home_score, away_score)
            correct_status = "hit" if str(item.pick).strip().upper() == real_result else "miss"

            score_changed = (
                item.home_score != home_score or
                item.away_score != away_score
            )
            result_changed = str(item.result or "").strip().upper() != real_result
            status_changed = str(item.status or "").strip().lower() != correct_status

            if not (score_changed or result_changed or status_changed):
                continue

            print(
                f"[REPAIR] Corrigindo fixture_id={item.fixture_id} | "
                f"{item.home_team} x {item.away_team} | "
                f"salvo={item.home_score}x{item.away_score} ({item.result}/{item.status}) | "
                f"real={home_score}x{away_score} ({real_result}/{correct_status})"
            )

            item.home_score = home_score
            item.away_score = away_score
            item.result = real_result
            item.status = correct_status

            fixed += 1

        db.commit()

        print(f"\n✅ Auditoria concluída")
        print(f"📌 Jogos verificados: {checked}")
        print(f"🛠️ Jogos corrigidos: {fixed}")

    except Exception as e:
        db.rollback()
        print(f"❌ Erro no reparo: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()