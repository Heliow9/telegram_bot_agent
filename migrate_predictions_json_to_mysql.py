import json
from pathlib import Path
from datetime import datetime

from app.db import SessionLocal
from app.models import Prediction, PredictionOdds

STORE_PATH = Path("data/predictions_log.json")


def main():
    if not STORE_PATH.exists():
        print("Arquivo data/predictions_log.json não encontrado.")
        return

    data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    db = SessionLocal()

    inserted = 0
    skipped = 0

    try:
        for item in data:
            fixture_id = str(item.get("fixture_id", ""))
            if not fixture_id:
                skipped += 1
                continue

            exists = db.query(Prediction).filter(Prediction.fixture_id == fixture_id).first()
            if exists:
                skipped += 1
                continue

            prediction = Prediction(
                fixture_id=fixture_id,
                league_key=None,
                league_name=item.get("league", "Sem liga"),
                home_team=item.get("home_team", ""),
                away_team=item.get("away_team", ""),
                match_date=item.get("date", ""),
                match_time=item.get("time", ""),
                pick=item.get("pick", ""),
                prob_home=float(item.get("prob_home", 0.0)),
                prob_draw=float(item.get("prob_draw", 0.0)),
                prob_away=float(item.get("prob_away", 0.0)),
                confidence=item.get("confidence", "baixa"),
                model_source=item.get("model_source"),
                status=item.get("status", "pending"),
                result=item.get("result"),
                home_score=item.get("home_score"),
                away_score=item.get("away_score"),
                features_json=json.dumps(item.get("features"), ensure_ascii=False)
                if item.get("features") is not None
                else None,
                created_at=datetime.utcnow(),
                checked_at=datetime.fromisoformat(item["checked_at"])
                if item.get("checked_at")
                else None,
            )

            db.add(prediction)
            db.flush()

            odds_snapshot = item.get("odds_snapshot") or {}
            fair_snapshot = item.get("fair_odds_snapshot") or {}

            if odds_snapshot or fair_snapshot:
                prediction_odds = PredictionOdds(
                    prediction_id=prediction.id,
                    bookmaker=odds_snapshot.get("bookmaker"),
                    home_odds=odds_snapshot.get("home_odds"),
                    draw_odds=odds_snapshot.get("draw_odds"),
                    away_odds=odds_snapshot.get("away_odds"),
                    fair_home_odds=fair_snapshot.get("1"),
                    fair_draw_odds=fair_snapshot.get("X"),
                    fair_away_odds=fair_snapshot.get("2"),
                    opening_market_odds=item.get("opening_market_odds"),
                    latest_market_odds=item.get("latest_market_odds"),
                    edge=(item.get("clv") or {}).get("movement"),
                    has_value_bet=False,
                )
                db.add(prediction_odds)

            inserted += 1

        db.commit()
        print(f"Migração concluída. Inseridos: {inserted} | Ignorados: {skipped}")

    except Exception as e:
        db.rollback()
        print(f"Erro na migração: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()