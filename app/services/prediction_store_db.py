import json
from datetime import datetime
from typing import Optional, Dict

from app.db import SessionLocal
from app.models import Prediction, PredictionOdds


def _safe_float(value) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_pick(value: Optional[str]) -> str:
    return str(value or "").strip().upper()


def _normalize_result(value: Optional[str]) -> str:
    return str(value or "").strip().upper()


def _pick_market_odds(analysis: dict) -> Optional[float]:
    odds = analysis.get("odds") or {}
    pick = _normalize_pick(analysis.get("suggested_pick"))

    if pick == "1":
        return _safe_float(odds.get("home_odds"))

    if pick == "X":
        return _safe_float(odds.get("draw_odds"))

    if pick == "2":
        return _safe_float(odds.get("away_odds"))

    if pick == "1X":
        return _safe_float(odds.get("odds_1x"))

    if pick == "X2":
        return _safe_float(odds.get("odds_x2"))

    if pick == "12":
        return _safe_float(odds.get("odds_12"))

    return None


def _pick_is_winner(pick: str, result: str) -> bool:
    pick = _normalize_pick(pick)
    result = _normalize_result(result)

    if not pick or not result:
        return False

    if pick in {"1", "X", "2"}:
        return pick == result

    if pick == "1X":
        return result in {"1", "X"}

    if pick == "X2":
        return result in {"X", "2"}

    if pick == "12":
        return result in {"1", "2"}

    return False


def save_prediction_db(payload: dict):
    db = SessionLocal()
    try:
        fixture = payload.get("fixture") or {}
        analysis = payload.get("analysis") or {}
        league = payload.get("league") or {}

        fixture_id = str(fixture.get("id", "")).strip()
        if not fixture_id:
            raise ValueError(f"Payload sem fixture.id válido: {payload}")

        existing = db.query(Prediction).filter(Prediction.fixture_id == fixture_id).first()
        if existing:
            print(f"[DB] Prediction já existe para fixture_id={fixture_id}")

            odds = analysis.get("odds") or {}
            fair_odds = analysis.get("fair_odds") or {}
            value_bet = analysis.get("value_bet") or {}

            if odds or fair_odds or value_bet:
                picked_market_odds = _pick_market_odds(analysis)

                if existing.odds is None:
                    prediction_odds = PredictionOdds(
                        prediction_id=existing.id,
                        bookmaker=odds.get("bookmaker"),
                        home_odds=_safe_float(odds.get("home_odds")),
                        draw_odds=_safe_float(odds.get("draw_odds")),
                        away_odds=_safe_float(odds.get("away_odds")),
                        fair_home_odds=_safe_float(fair_odds.get("1")),
                        fair_draw_odds=_safe_float(fair_odds.get("X")),
                        fair_away_odds=_safe_float(fair_odds.get("2")),
                        opening_market_odds=picked_market_odds,
                        latest_market_odds=picked_market_odds,
                        edge=_safe_float(value_bet.get("edge")),
                        has_value_bet=bool(value_bet.get("has_value")),
                    )
                    db.add(prediction_odds)
                else:
                    existing.odds.bookmaker = odds.get("bookmaker")
                    existing.odds.home_odds = _safe_float(odds.get("home_odds"))
                    existing.odds.draw_odds = _safe_float(odds.get("draw_odds"))
                    existing.odds.away_odds = _safe_float(odds.get("away_odds"))
                    existing.odds.fair_home_odds = _safe_float(fair_odds.get("1"))
                    existing.odds.fair_draw_odds = _safe_float(fair_odds.get("X"))
                    existing.odds.fair_away_odds = _safe_float(fair_odds.get("2"))

                    if existing.odds.opening_market_odds is None:
                        existing.odds.opening_market_odds = picked_market_odds

                    existing.odds.latest_market_odds = picked_market_odds
                    existing.odds.edge = _safe_float(value_bet.get("edge"))
                    existing.odds.has_value_bet = bool(value_bet.get("has_value"))

                existing.pick = _normalize_pick(analysis.get("suggested_pick")) or existing.pick
                existing.prob_home = float(analysis.get("prob_home", existing.prob_home or 0.0))
                existing.prob_draw = float(analysis.get("prob_draw", existing.prob_draw or 0.0))
                existing.prob_away = float(analysis.get("prob_away", existing.prob_away or 0.0))
                existing.confidence = analysis.get("confidence", existing.confidence or "baixa")
                existing.model_source = analysis.get("model_source", existing.model_source)

                if analysis.get("features") is not None:
                    existing.features_json = json.dumps(
                        analysis.get("features"),
                        ensure_ascii=False,
                    )

                db.commit()
                print(f"[DB] Prediction existente atualizada | fixture_id={fixture_id}")

            return

        pick = _normalize_pick(analysis.get("suggested_pick"))

        print(
            f"[DB] Salvando prediction | fixture_id={fixture_id} | "
            f"{fixture.get('home_team')} x {fixture.get('away_team')} | "
            f"pick={pick}"
        )

        prediction = Prediction(
            fixture_id=fixture_id,
            league_key=league.get("key"),
            league_name=league.get("display_name"),
            home_team=fixture.get("home_team"),
            away_team=fixture.get("away_team"),
            match_date=fixture.get("date"),
            match_time=fixture.get("time"),
            pick=pick,
            prob_home=float(analysis.get("prob_home", 0.0)),
            prob_draw=float(analysis.get("prob_draw", 0.0)),
            prob_away=float(analysis.get("prob_away", 0.0)),
            confidence=analysis.get("confidence", "baixa"),
            model_source=analysis.get("model_source"),
            status="pending",
            result=None,
            home_score=None,
            away_score=None,
            features_json=json.dumps(
                analysis.get("features"),
                ensure_ascii=False,
            ) if analysis.get("features") is not None else None,
            created_at=datetime.utcnow(),
            checked_at=None,
            started_at=None,
            finished_at=None,
            last_checked_at=None,
            result_source=None,
            last_status_text=None,
            is_live=False,
        )

        db.add(prediction)
        db.flush()

        odds = analysis.get("odds") or {}
        fair_odds = analysis.get("fair_odds") or {}
        value_bet = analysis.get("value_bet") or {}

        if odds or fair_odds or value_bet:
            prediction_odds = PredictionOdds(
                prediction_id=prediction.id,
                bookmaker=odds.get("bookmaker"),
                home_odds=_safe_float(odds.get("home_odds")),
                draw_odds=_safe_float(odds.get("draw_odds")),
                away_odds=_safe_float(odds.get("away_odds")),
                fair_home_odds=_safe_float(fair_odds.get("1")),
                fair_draw_odds=_safe_float(fair_odds.get("X")),
                fair_away_odds=_safe_float(fair_odds.get("2")),
                opening_market_odds=_pick_market_odds(analysis),
                latest_market_odds=_pick_market_odds(analysis),
                edge=_safe_float(value_bet.get("edge")),
                has_value_bet=bool(value_bet.get("has_value")),
            )
            db.add(prediction_odds)

        db.commit()
        print(f"[DB] Prediction salva com sucesso | fixture_id={fixture_id}")

    except Exception as e:
        db.rollback()
        print(f"[DB] Erro ao salvar prediction: {e}")
        raise
    finally:
        db.close()


def update_prediction_result_db(
    fixture_id: str,
    result: str,
    home_score: int,
    away_score: int,
    status_text: Optional[str] = None,
    result_source: Optional[str] = None,
    is_live: bool = False,
    finished: bool = True,
):
    db = SessionLocal()
    try:
        fixture_id = str(fixture_id).strip()
        result = _normalize_result(result)
        now = datetime.utcnow()

        item = db.query(Prediction).filter(Prediction.fixture_id == fixture_id).first()
        if not item:
            print(f"[DB] Prediction não encontrada para fixture_id={fixture_id}")
            return

        previous_status = item.status

        item.result = result
        item.home_score = home_score
        item.away_score = away_score
        item.checked_at = now
        item.last_checked_at = now
        item.last_status_text = status_text
        item.result_source = result_source or "sportsdb"

        if item.started_at is None:
            item.started_at = now

        if finished:
            item.finished_at = now
            item.is_live = False
        else:
            item.is_live = bool(is_live)

        item.status = "hit" if _pick_is_winner(item.pick, result) else "miss"

        db.commit()

        print(
            f"[DB] Resultado atualizado | fixture_id={fixture_id} | "
            f"pick={item.pick} | result={result} | "
            f"placar={home_score}x{away_score} | "
            f"status_anterior={previous_status} | status_novo={item.status}"
        )

    except Exception as e:
        db.rollback()
        print(f"[DB] Erro ao atualizar resultado fixture_id={fixture_id}: {e}")
        raise
    finally:
        db.close()


def update_prediction_market_odds_db(
    fixture_id: str,
    latest_market_odds: Optional[float],
):
    latest_market_odds = _safe_float(latest_market_odds)
    if latest_market_odds is None:
        return

    db = SessionLocal()
    try:
        item = db.query(Prediction).filter(
            Prediction.fixture_id == str(fixture_id).strip()
        ).first()

        if not item or not item.odds:
            return

        item.odds.latest_market_odds = latest_market_odds
        item.last_checked_at = datetime.utcnow()
        db.commit()

    except Exception as e:
        db.rollback()
        print(f"[DB] Erro ao atualizar latest_market_odds fixture_id={fixture_id}: {e}")
        raise
    finally:
        db.close()


def update_prediction_live_state_db(
    fixture_id: str,
    home_score: Optional[int],
    away_score: Optional[int],
    status_text: Optional[str] = None,
    is_live: bool = True,
):
    db = SessionLocal()
    try:
        fixture_id = str(fixture_id).strip()
        now = datetime.utcnow()

        item = db.query(Prediction).filter(Prediction.fixture_id == fixture_id).first()
        if not item:
            print(f"[DB] Prediction não encontrada para live_state fixture_id={fixture_id}")
            return

        current_status = str(item.status or "").strip().lower()
        if current_status in {"hit", "miss"}:
            print(
                f"[DB] Live state ignorado para jogo resolvido | "
                f"fixture_id={fixture_id} | status={current_status}"
            )
            return

        normalized_status = str(status_text or "").strip().upper()

        not_started_statuses = {
            "",
            "NS",
            "NOT STARTED",
            "TIME TO BE DEFINED",
            "TBD",
            "SCHEDULED",
        }

        finished_statuses = {
            "FT",
            "AET",
            "PEN",
            "FINISHED",
            "MATCH FINISHED",
            "ENDED",
        }

        item.home_score = int(home_score) if home_score is not None else item.home_score
        item.away_score = int(away_score) if away_score is not None else item.away_score
        item.last_checked_at = now
        item.last_status_text = status_text

        if normalized_status in finished_statuses:
            item.is_live = False
            if item.started_at is None:
                item.started_at = now
            if item.finished_at is None:
                item.finished_at = now

        elif normalized_status in not_started_statuses:
            item.is_live = False
            item.started_at = None

        else:
            item.is_live = bool(is_live)
            if bool(is_live) and item.started_at is None:
                item.started_at = now

        db.commit()

        print(
            f"[DB] Live state atualizado | fixture_id={fixture_id} | "
            f"placar={item.home_score}x{item.away_score} | "
            f"status_text={status_text} | is_live={item.is_live}"
        )

    except Exception as e:
        db.rollback()
        print(f"[DB] Erro ao atualizar live state fixture_id={fixture_id}: {e}")
        raise
    finally:
        db.close()


def get_prediction_db_by_fixture_id(fixture_id: str) -> Optional[Dict]:
    db = SessionLocal()
    try:
        item = db.query(Prediction).filter(
            Prediction.fixture_id == str(fixture_id).strip()
        ).first()

        if not item:
            return None

        return {
            "fixture_id": item.fixture_id,
            "status": item.status,
            "result": item.result,
            "home_score": item.home_score,
            "away_score": item.away_score,
            "pick": item.pick,
            "started_at": item.started_at.isoformat() if item.started_at else None,
            "finished_at": item.finished_at.isoformat() if item.finished_at else None,
            "last_checked_at": item.last_checked_at.isoformat() if item.last_checked_at else None,
            "result_source": item.result_source,
            "last_status_text": item.last_status_text,
            "is_live": item.is_live,
        }
    finally:
        db.close()