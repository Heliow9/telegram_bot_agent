from app.db import SessionLocal
from app.models import Prediction
from app.services.sportsdb_api import SportsDBAPI


def main():
    db = SessionLocal()
    api = SportsDBAPI()

    try:
        wrongly_closed = (
            db.query(Prediction)
            .filter(Prediction.status.in_(["hit", "miss"]))
            .all()
        )

        repaired = 0

        for item in wrongly_closed:
            details = api.get_event_details(item.fixture_id)
            if not details:
                continue

            status = str(details.get("strStatus") or "").strip().lower()

            if status in {"1h", "2h", "ht", "half time", "live", "in play", "break"}:
                print(
                    f"Reabrindo fixture {item.fixture_id} | "
                    f"{item.home_team} x {item.away_team} | status={status}"
                )
                item.status = "pending"
                item.result = None
                item.home_score = None
                item.away_score = None
                item.checked_at = None
                repaired += 1

        db.commit()
        print(f"✅ Jogos reabertos: {repaired}")

    except Exception as e:
        db.rollback()
        print(f"❌ Erro no reparo: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()