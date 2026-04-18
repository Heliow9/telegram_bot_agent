import json
from datetime import datetime
from typing import Optional, Dict

from app.db import SessionLocal
from app.models import Prediction, PredictionOdds


def _pick_market_odds(analysis: dict) -> Optional[float]:
    odds = analysis.get("odds") or {}
    pick = analysis.get("suggested_pick")

    if pick == "1":
        return odds.get("home_odds")
    if pick == "X":
        return odds.get("draw_odds")
    if pick == "2":
        return odds.get("away_odds")
    return None


def _pick_fair_odds(analysis: dict) -> Optional[float]:
    fair_odds = analysis.get("fair_odds") or {}
    pick = analysis.get("suggested_pick")
    if not pick:
        return None
    return fair_odds.get(pick)


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default=None):
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def save_prediction_db(payload: dict):
    db = SessionLocal()
    try:
        fixture = payload.get("fixture") or {}
        analysis = payload.get("analysis") or {}
        league = payload.get("league") or {}

        fixture_id = str(fixture.get("id", "")).strip()
        if not fixture_id:
            raise ValueError(f"Payload sem fixture.id válido: {payload}")

        existing = (
            db.query(Prediction)
            .filter(Prediction.fixture_id == fixture_id)
            .first()
        )

        if existing:
            print(f"[DB] Prediction já existe para fixture_id={fixture_id}")

            odds = analysis.get("odds") or {}
            fair_odds = analysis.get("fair_odds") or {}
            value_bet = analysis.get("value_bet") or {}

            if existing.odds is None and (odds or fair_odds or value_bet):
                prediction_odds = PredictionOdds(
                    prediction_id=existing.id,
                    bookmaker=odds.get("bookmaker"),
                    home_odds=odds.get("home_odds"),
                    draw_odds=odds.get("draw_odds"),
                    away_odds=odds.get("away_odds"),
                    fair_home_odds=fair_odds.get("1"),
                    fair_draw_odds=fair_odds.get("X"),
                    fair_away_odds=fair_odds.get("2"),
                    opening_market_odds=_pick_market_odds(analysis),
                    latest_market_odds=_pick_market_odds(analysis),
                    edge=value_bet.get("edge"),
                    has_value_bet=bool(value_bet.get("has_value")),
                )
                db.add(prediction_odds)
                db.commit()
                print(
                    f"[DB] Odds vinculadas à prediction existente | "
                    f"fixture_id={fixture_id}"
                )

            elif existing.odds is not None and (odds or fair_odds or value_bet):
                # Atualiza odds existentes sem apagar estrutura anterior
                existing.odds.bookmaker = odds.get("bookmaker") or existing.odds.bookmaker
                existing.odds.home_odds = odds.get("home_odds")
                existing.odds.draw_odds = odds.get("draw_odds")
                existing.odds.away_odds = odds.get("away_odds")
                existing.odds.fair_home_odds = fair_odds.get("1")
                existing.odds.fair_draw_odds = fair_odds.get("X")
                existing.odds.fair_away_odds = fair_odds.get("2")

                picked_market_odds = _pick_market_odds(analysis)
                if existing.odds.opening_market_odds is None and picked_market_odds is not None:
                    existing.odds.opening_market_odds = picked_market_odds
                if picked_market_odds is not None:
                    existing.odds.latest_market_odds = picked_market_odds

                existing.odds.edge = value_bet.get("edge")
                existing.odds.has_value_bet = bool(value_bet.get("has_value"))
                db.commit()
                print(
                    f"[DB] Odds da prediction existente atualizadas | "
                    f"fixture_id={fixture_id}"
                )

            return

        print(
            f"[DB] Salvando prediction | fixture_id={fixture_id} | "
            f"{fixture.get('home_team')} x {fixture.get('away_team')} | "
            f"pick={analysis.get('suggested_pick')}"
        )

        prediction = Prediction(
            fixture_id=fixture_id,
            league_key=league.get("key"),
            league_name=league.get("display_name"),
            home_team=fixture.get("home_team"),
            away_team=fixture.get("away_team"),
            match_date=fixture.get("date"),
            match_time=fixture.get("time"),
            pick=analysis.get("suggested_pick"),
            prob_home=_safe_float(analysis.get("prob_home", 0.0)),
            prob_draw=_safe_float(analysis.get("prob_draw", 0.0)),
            prob_away=_safe_float(analysis.get("prob_away", 0.0)),
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
                home_odds=odds.get("home_odds"),
                draw_odds=odds.get("draw_odds"),
                away_odds=odds.get("away_odds"),
                fair_home_odds=fair_odds.get("1"),
                fair_draw_odds=fair_odds.get("X"),
                fair_away_odds=fair_odds.get("2"),
                opening_market_odds=_pick_market_odds(analysis),
                latest_market_odds=_pick_market_odds(analysis),
                edge=value_bet.get("edge"),
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
        result = str(result).strip().upper()
        now = datetime.utcnow()

        item = (
            db.query(Prediction)
            .filter(Prediction.fixture_id == fixture_id)
            .first()
        )
        if not item:
            print(f"[DB] Prediction não encontrada para fixture_id={fixture_id}")
            return

        previous_status = item.status

        item.result = result
        item.home_score = _safe_int(home_score, item.home_score)
        item.away_score = _safe_int(away_score, item.away_score)
        item.checked_at = now
        item.last_checked_at = now
        item.last_status_text = status_text
        item.result_source = result_source or "sportsdb"
        item.is_live = bool(is_live and not finished)

        if item.started_at is None:
            item.started_at = now

        if finished:
            item.finished_at = now

        item.status = "hit" if str(item.pick).strip().upper() == result else "miss"

        db.commit()

        print(
            f"[DB] Resultado atualizado | fixture_id={fixture_id} | "
            f"pick={item.pick} | result={result} | "
            f"placar={item.home_score}x{item.away_score} | "
            f"status_anterior={previous_status} | status_novo={item.status} | "
            f"is_live={item.is_live}"
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
    if latest_market_odds is None:
        return

    db = SessionLocal()
    try:
        item = (
            db.query(Prediction)
            .filter(Prediction.fixture_id == str(fixture_id).strip())
            .first()
        )
        if not item or not item.odds:
            return

        latest_value = _safe_float(latest_market_odds, None)
        if latest_value is None:
            return

        item.odds.latest_market_odds = latest_value
        item.last_checked_at = datetime.utcnow()
        db.commit()

    except Exception as e:
        db.rollback()
        print(f"[DB] Erro ao atualizar odds fixture_id={fixture_id}: {e}")
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

        item = (
            db.query(Prediction)
            .filter(Prediction.fixture_id == fixture_id)
            .first()
        )
        if not item:
            print(f"[DB] Prediction não encontrada para live_state fixture_id={fixture_id}")
            return

        current_status = str(item.status or "").strip().lower()

        # Se já resolveu, não mexe em live
        if current_status in {"hit", "miss"}:
            print(
                f"[DB] Live state ignorado para jogo resolvido | "
                f"fixture_id={fixture_id} | status={current_status}"
            )
            return

        if home_score is not None:
            parsed_home_score = _safe_int(home_score, item.home_score)
            item.home_score = parsed_home_score

        if away_score is not None:
            parsed_away_score = _safe_int(away_score, item.away_score)
            item.away_score = parsed_away_score

        item.last_checked_at = now
        item.last_status_text = status_text
        item.is_live = bool(is_live)

        if bool(is_live) and item.started_at is None:
            item.started_at = now

        # Se chegou aqui como não-live e ainda estava marcado live, derruba a flag
        if not bool(is_live):
            item.is_live = False

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
        item = (
            db.query(Prediction)
            .filter(Prediction.fixture_id == str(fixture_id).strip())
            .first()
        )
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