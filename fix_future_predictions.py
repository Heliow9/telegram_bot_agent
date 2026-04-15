from datetime import datetime
from zoneinfo import ZoneInfo

from app.db import SessionLocal
from app.models import Prediction, PredictionOdds


def main():
    tz = ZoneInfo("America/Recife")
    today = datetime.now(tz).date()

    db = SessionLocal()
    try:
        items = (
            db.query(Prediction)
            .filter(Prediction.status == "pending")
            .all()
        )

        to_delete = []

        for item in items:
            match_date_raw = item.match_date
            if not match_date_raw:
                continue

            try:
                match_date = datetime.strptime(str(match_date_raw), "%Y-%m-%d").date()
            except ValueError:
                print(
                    f"[FIX DB] Ignorando fixture_id={item.fixture_id} | "
                    f"match_date inválida={match_date_raw}"
                )
                continue

            if match_date > today:
                to_delete.append(item)

        if not to_delete:
            print("[FIX DB] Nenhuma previsão futura pendente encontrada.")
            return

        print(f"[FIX DB] Previsões futuras pendentes encontradas: {len(to_delete)}")
        print("-" * 80)

        for item in to_delete:
            print(
                f"fixture_id={item.fixture_id} | "
                f"{item.home_team} x {item.away_team} | "
                f"data={item.match_date} | status={item.status}"
            )

        print("-" * 80)

        deleted_odds = 0
        deleted_predictions = 0

        for item in to_delete:
            odds = db.query(PredictionOdds).filter(
                PredictionOdds.prediction_id == item.id
            ).first()

            if odds:
                db.delete(odds)
                deleted_odds += 1

            db.delete(item)
            deleted_predictions += 1

        db.commit()

        print(
            f"[FIX DB] Remoção concluída | "
            f"predictions={deleted_predictions} | odds={deleted_odds}"
        )

    except Exception as e:
        db.rollback()
        print(f"[FIX DB] Erro: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()