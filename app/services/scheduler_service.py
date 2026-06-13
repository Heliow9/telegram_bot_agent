from apscheduler.schedulers.background import BackgroundScheduler
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json
import time
from contextlib import contextmanager


from app.config import settings
from app.db import SessionLocal
from app.models import Prediction
from app.services.daily_leagues_service import DailyLeaguesService
from app.services.telegram_service import TelegramService
from app.services.message_formatter import (
    format_prediction_message,
    format_result_message,
    pick_winner_photo_url,
    format_best_pick,
    format_top_ranking,
    format_league_summary,
    group_payloads_by_league,
)
from app.services.time_utils import now_local
from app.services.result_checker_service import ResultCheckerService
from app.services.gemini_summary_service import GeminiSummaryService
from app.services.live_match_monitor_service import LiveMatchMonitorService
from app.services.training_dataset_service import TrainingDatasetService
from app.services.ml_training_service import MLTrainingService
from app.services.odds_service import OddsService
from app.services.prediction_store import (
    save_prediction,
    save_predictions_batch,
    get_pending_predictions,
    update_prediction_market_odds,
)
from app.services.runtime_config_service import load_runtime_config
from app.services.json_lock_store import locked_json


scheduler = BackgroundScheduler(timezone="America/Recife")
daily_service = DailyLeaguesService()
telegram = TelegramService()
result_checker = ResultCheckerService()
gemini_summary = GeminiSummaryService()
live_monitor = LiveMatchMonitorService()
training_dataset_service = TrainingDatasetService()
ml_training_service = MLTrainingService()
odds_service = OddsService()

scheduler_started = False
training_job_running = False

ALERT_STORE_PATH = Path("data/sent_alerts.json")
RESULT_STORE_PATH = Path("data/sent_results.json")
SUMMARY_STORE_PATH = Path("data/sent_summaries.json")
MIN_DAILY_RANKING_ITEMS = 5
DAILY_RANKING_TOP_N = 10
BASKETBALL_RANKING_TOP_N = 8


def _claim_json_key(path: Path, key: str) -> bool:
    """Marca uma chave como em envio de forma atômica entre processos."""
    key = str(key or "").strip()
    if not key:
        return False
    with locked_json(path, list) as items:
        if key in items:
            return False
        items.append(key)
        return True


def _release_json_key(path: Path, key: str) -> None:
    """Remove a chave quando o Telegram falha, permitindo nova tentativa."""
    key = str(key or "").strip()
    if not key:
        return
    with locked_json(path, list) as items:
        while key in items:
            items.remove(key)


def _runtime_config():
    return load_runtime_config()


def _job_log_start(job_name: str):
    started_at = time.perf_counter()
    print(f"[JOB] START {job_name} | at={datetime.utcnow().isoformat()}Z")
    return started_at


def _job_log_end(job_name: str, started_at: float, **kwargs):
    elapsed = round(time.perf_counter() - started_at, 2)
    extra = " | ".join(f"{k}={v}" for k, v in kwargs.items())
    suffix = f" | {extra}" if extra else ""
    print(f"[JOB] END {job_name} | duration={elapsed}s{suffix}")


def _ensure_json_store(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("[]", encoding="utf-8")


def _load_json_list(path: Path):
    _ensure_json_store(path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def _save_json_list(path: Path, data):
    _ensure_json_store(path)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_sent_alerts():
    return _load_json_list(ALERT_STORE_PATH)


def _save_sent_alert(alert_key: str):
    alerts = _load_sent_alerts()
    if alert_key not in alerts:
        alerts.append(alert_key)
        _save_json_list(ALERT_STORE_PATH, alerts)


def _already_sent_alert(alert_key: str) -> bool:
    return alert_key in _load_sent_alerts()


def _cleanup_old_alert_keys():
    alerts = _load_sent_alerts()
    if not alerts:
        return 0

    today_prefix = now_local().strftime("%Y-%m-%d")
    filtered = []

    for key in alerts:
        text = str(key or "").strip()

        if not text:
            continue

        if today_prefix in text:
            filtered.append(text)
            continue

        if "_" in text and today_prefix not in text:
            continue

        filtered.append(text)

    removed = max(0, len(alerts) - len(filtered))

    if removed > 0:
        _save_json_list(ALERT_STORE_PATH, filtered)
        print(f"[SCHEDULER] Limpeza de sent_alerts concluída | removidos={removed}")

    return removed


def _load_sent_results():
    return _load_json_list(RESULT_STORE_PATH)


def _save_sent_result(result_key: str):
    sent = _load_sent_results()
    if result_key not in sent:
        sent.append(result_key)
        _save_json_list(RESULT_STORE_PATH, sent)


def _already_sent_result(result_key: str) -> bool:
    return result_key in _load_sent_results()


def _load_sent_summaries():
    return _load_json_list(SUMMARY_STORE_PATH)


def _save_sent_summary(summary_key: str):
    sent = _load_sent_summaries()
    if summary_key not in sent:
        sent.append(summary_key)
        _save_json_list(SUMMARY_STORE_PATH, sent)


def _already_sent_summary(summary_key: str) -> bool:
    return summary_key in _load_sent_summaries()


def _current_summary_turn(dt=None) -> str | None:
    """Retorna somente o turno atual para catch-up seguro no startup.

    Regra importante: após um deploy/restart, o bot não deve mandar grades antigas
    de turnos já encerrados. Ele só pode recuperar a grade do turno atual, e os
    filtros do event_selector já removem jogos iniciados/finalizados.
    """
    dt = dt or now_local()
    hour = dt.hour
    if 8 <= hour <= 11:
        return "morning"
    if 12 <= hour <= 17:
        return "afternoon"
    if 18 <= hour <= 23:
        return "night"
    return None


def _send_summary_for_turn(turn: str):
    if turn == "morning":
        return job_send_morning_summary()
    if turn == "afternoon":
        return job_send_afternoon_summary()
    if turn == "night":
        return job_send_night_summary()
    raise ValueError(f"Turno inválido: {turn}")


def _turn_summary_key(turn: str, date_str: str | None = None) -> str:
    date_str = date_str or now_local().strftime("%Y-%m-%d")
    return f"{date_str}_{turn}"


def _turn_bounds(turn: str):
    if turn == "morning":
        return 8, 11, "manhã"
    if turn == "afternoon":
        return 12, 17, "tarde"
    if turn == "night":
        return 18, 23, "noite"
    raise ValueError(f"Turno inválido: {turn}")




def _partial_target_time(turn: str):
    if turn == "morning":
        return 12, 29, "manhã"
    if turn == "afternoon":
        return 17, 59, "tarde"
    if turn == "night":
        return 23, 59, "noite"
    raise ValueError(f"Turno inválido: {turn}")


def _is_inside_partial_catchup_window(turn: str, dt=None, grace_minutes: int = 20) -> bool:
    """Evita envio tardio de parcial após deploy/restart.

    A parcial deve sair antes da próxima grade: manhã 12:29, tarde 17:59, noite 23:59.
    Se o servidor voltar muito depois disso, não recupera a parcial antiga para não
    confundir com os palpites do turno atual.
    """
    dt = dt or now_local()
    hour, minute, _ = _partial_target_time(turn)
    target = dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return target <= dt <= target + timedelta(minutes=grace_minutes)


def _partial_summary_key(turn: str) -> str:
    return f"{now_local().strftime('%Y-%m-%d')}_{turn}_partial"


def _prediction_hour(row: Prediction) -> int | None:
    raw = str(row.match_time or "").strip()
    if not raw:
        return None
    try:
        return int(raw.split(":", 1)[0])
    except Exception:
        return None


def job_send_turn_partial_summary(turn: str, allow_late: bool = False):
    started = _job_log_start(f"job_send_turn_partial_summary:{turn}")
    key = _partial_summary_key(turn)

    if not allow_late and not _is_inside_partial_catchup_window(turn, now_local(), grace_minutes=20):
        _job_log_end(
            f"job_send_turn_partial_summary:{turn}",
            started,
            sent=False,
            reason="outside_partial_window",
        )
        return

    if not _claim_json_key(SUMMARY_STORE_PATH, key):
        _job_log_end(f"job_send_turn_partial_summary:{turn}", started, sent=False, reason="already_sent_or_claimed")
        return

    start_hour, end_hour, label = _turn_bounds(turn)
    today = now_local().strftime("%Y-%m-%d")

    try:
        try:
            result_checker.check_pending_predictions()
        except Exception as e:
            print(f"[PARTIAL] Falha na atualização prévia dos resultados ({label}): {e}")

        db = SessionLocal()
        try:
            rows = (
                db.query(Prediction)
                .filter(Prediction.match_date == today)
                .order_by(Prediction.match_time.asc())
                .all()
            )
            rows = [row for row in rows if (h := _prediction_hour(row)) is not None and start_hour <= h <= end_hour]
        finally:
            db.close()

        total = len(rows)
        hits = sum(1 for row in rows if row.status == "hit")
        misses = sum(1 for row in rows if row.status == "miss")
        pending = sum(1 for row in rows if row.status == "pending")
        resolved = hits + misses
        accuracy = (hits / resolved) if resolved else 0

        lines = [
            f"📌 *Parcial da grade da {label}*",
            "",
            f"Jogos monitorados: *{total}*",
            f"✅ Acertos: *{hits}*",
            f"❌ Erros: *{misses}*",
            f"⏳ Pendentes/em andamento: *{pending}*",
            f"🎯 Aproveitamento parcial: *{accuracy:.1%}*" if resolved else "🎯 Aproveitamento parcial: ainda sem jogos resolvidos",
        ]

        if rows:
            lines.append("")
            lines.append("*Detalhes:*")
            for row in rows[:12]:
                score = ""
                if row.home_score is not None and row.away_score is not None:
                    score = f" | {row.home_score}x{row.away_score}"
                status_icon = "✅" if row.status == "hit" else "❌" if row.status == "miss" else "⏳"
                lines.append(
                    f"{status_icon} {row.match_time[:5]} • {row.home_team} x {row.away_team} • pick {row.pick}{score}"
                )

        result = telegram.send_message("\n".join(lines))
        if not result.get("ok"):
            _release_json_key(SUMMARY_STORE_PATH, key)

        _job_log_end(f"job_send_turn_partial_summary:{turn}", started, success=bool(result.get("ok")), rows=total)
    except Exception as e:
        print(f"[PARTIAL] Erro ao enviar parcial da {label}: {e}")
        _job_log_end(f"job_send_turn_partial_summary:{turn}", started, success=False)


def job_send_morning_partial_summary():
    job_send_turn_partial_summary("morning")


def job_send_afternoon_partial_summary():
    job_send_turn_partial_summary("afternoon")


def job_send_night_partial_summary():
    job_send_turn_partial_summary("night")


def build_alert_key(fixture_id: str, date_str: str | None = None) -> str:
    # Inclui data para evitar colisão/reuso de id da API e facilitar limpeza diária.
    date_str = date_str or now_local().strftime("%Y-%m-%d")
    return f"{date_str}_{fixture_id}_30min"


def build_result_key(fixture_id: str) -> str:
    return f"{fixture_id}_result"


def _normalize_market_type(value) -> str:
    return str(value or "1x2").strip().lower()


def _normalize_pick(value) -> str:
    return str(value or "").strip().upper()


LOCAL_TZ = ZoneInfo("America/Recife")


def _parse_payload_kickoff_local(payload: dict) -> datetime | None:
    fixture = (payload or {}).get("fixture") or {}
    raw = str(fixture.get("kickoff_local") or "").strip()

    if raw:
        try:
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=LOCAL_TZ)
            return dt.astimezone(LOCAL_TZ)
        except Exception:
            pass

    local_date = str(fixture.get("local_date") or "").strip()
    local_time = str(fixture.get("local_time") or "").strip()
    if local_date:
        try:
            time_part = local_time or "00:00:00"
            if time_part.count(":") == 1:
                time_part = f"{time_part}:00"
            return datetime.strptime(f"{local_date} {time_part}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=LOCAL_TZ)
        except Exception:
            pass

    # Fallback: date/time originais da API normalmente são UTC.
    raw_date = str(fixture.get("date") or "").strip()
    raw_time = str(fixture.get("time") or "").strip()
    if raw_date:
        try:
            from app.services.time_utils import event_to_local_datetime
            return event_to_local_datetime(raw_date, raw_time)
        except Exception:
            return None

    return None


def _payload_label(payload: dict) -> str:
    fixture = (payload or {}).get("fixture") or {}
    return f"{fixture.get('home_team', 'Casa')} x {fixture.get('away_team', 'Fora')}"


def _payload_minutes_to_start(payload: dict) -> float | None:
    kickoff = _parse_payload_kickoff_local(payload)
    if kickoff is None:
        return None
    return (kickoff - now_local()).total_seconds() / 60.0


def _is_payload_strictly_future(payload: dict, min_lead_minutes: int = 1) -> bool:
    minutes = _payload_minutes_to_start(payload)
    if minutes is None:
        print(f"[GUARD][DROP] sem kickoff válido | jogo={_payload_label(payload)}")
        return False
    if minutes < min_lead_minutes:
        print(
            f"[GUARD][DROP] jogo já começou ou está muito perto | "
            f"jogo={_payload_label(payload)} | min_para_inicio={minutes:.1f}"
        )
        return False
    return True


def _is_payload_in_prelive_window(payload: dict, min_minutes: int = 0, max_minutes: int = 30) -> bool:
    minutes = _payload_minutes_to_start(payload)
    if minutes is None:
        print(f"[PRELIVE][DROP] sem kickoff válido | jogo={_payload_label(payload)}")
        return False
    if not (min_minutes <= minutes <= max_minutes):
        print(
            f"[PRELIVE][DROP] fora da janela | jogo={_payload_label(payload)} | "
            f"min_para_inicio={minutes:.1f} | janela={min_minutes}-{max_minutes}"
        )
        return False
    return True


def _filter_payloads_future(payloads: list[dict], source_label: str, min_lead_minutes: int = 1) -> list[dict]:
    valid = []
    for payload in payloads or []:
        if _is_payload_strictly_future(payload, min_lead_minutes=min_lead_minutes):
            valid.append(payload)
    dropped = len(payloads or []) - len(valid)
    if dropped:
        print(f"[GUARD] Payloads descartados em {source_label}: {dropped}")
    return valid


def _filter_payloads_prelive(payloads: list[dict]) -> list[dict]:
    valid = []
    for payload in payloads or []:
        if _is_payload_in_prelive_window(payload, 0, 30):
            valid.append(payload)
    dropped = len(payloads or []) - len(valid)
    if dropped:
        print(f"[PRELIVE] Payloads descartados na validação final: {dropped}")
    return valid

def _pick_latest_market_odds_by_market(
    market_type: str,
    pick: str,
    odds: dict,
):
    market_type = _normalize_market_type(market_type)
    pick = _normalize_pick(pick)
    odds = odds or {}

    if market_type == "double_chance":
        if pick == "1X":
            return odds.get("odds_1x")
        if pick == "X2":
            return odds.get("odds_x2")
        if pick == "12":
            return odds.get("odds_12")
        return None

    if pick == "1":
        return odds.get("home_odds")
    if pick == "X":
        return odds.get("draw_odds")
    if pick == "2":
        return odds.get("away_odds")
    return None


def _persist_payloads(payloads: list[dict], source_label: str):
    result = save_predictions_batch(payloads)
    print(
        f"[SCHEDULER] Persistência em lote concluída ({source_label}) | "
        f"salvos={result.get('saved', 0)} | falhas={result.get('failed', 0)}"
    )
    return result


def _send_ranked_summary(payloads: list[dict], period_label: str):
    payloads = _filter_payloads_future(payloads, f"summary:{period_label}", min_lead_minutes=1)

    if not payloads:
        print(f"[SCHEDULER] Nenhum payload futuro válido para enviar no resumo de {period_label}.")
        return {"ok": False, "sent": 0, "reason": "no_future_payloads"}

    _persist_payloads(payloads, period_label)

    best_result = telegram.send_message(format_best_pick(payloads[0]))
    print(f"[SCHEDULER] Melhor aposta enviada ({period_label}): {best_result}")

    ranking_result = telegram.send_message(format_top_ranking(payloads, top_n=10))
    print(f"[SCHEDULER] Top ranking enviado ({period_label}): {ranking_result}")

    grouped = group_payloads_by_league(payloads)

    desired_order = [
        "Brasileirão Série A",
        "Brasileirão Série B",
        "Copa do Brasil",
        "Premier League",
        "LaLiga",
        "Championship",
        "Liga dos Campeões",
        "Liga Europa",
        "Bundesliga",
        "Argentina Liga Profesional",
        "Itália Série A",
        "Turquia Super Lig",
        "Libertadores",
        "Copa Sul-Americana",
        "Copa do Mundo",
        "Amistosos Internacionais",
    ]

    for league_name in desired_order:
        league_payloads = grouped.get(league_name, [])
        if not league_payloads:
            continue

        result = telegram.send_message(
            format_league_summary(league_name, league_payloads)
        )
        print(f"[SCHEDULER] Resumo enviado para liga {league_name}: {result}")

    return {"ok": True, "sent": len(payloads)}




def _payload_unique_key(payload: dict) -> str:
    fixture = (payload or {}).get("fixture") or {}
    return str(fixture.get("id") or f"{fixture.get('home_team')}|{fixture.get('away_team')}|{fixture.get('local_date')}|{fixture.get('local_time')}").strip()


def _merge_unique_payloads(*groups: list[dict]) -> list[dict]:
    merged = []
    seen = set()
    for group in groups:
        for payload in group or []:
            key = _payload_unique_key(payload)
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(payload)
    return merged


def job_send_daily_top_summary():
    """Envia ranking consolidado do dia para evitar dias com só 1 ou 2 palpites."""
    started = _job_log_start("job_send_daily_top_summary")
    today = now_local().strftime("%Y-%m-%d")
    summary_key = f"{today}_daily_top"

    if _already_sent_summary(summary_key):
        _job_log_end("job_send_daily_top_summary", started, sent=False, reason="already_sent")
        return {"ok": False, "sent": 0, "reason": "already_sent"}

    try:
        payloads = daily_service.get_all_day_payloads(today)
        payloads = _filter_payloads_future(payloads, "daily_top", min_lead_minutes=1)

        if len(payloads) < MIN_DAILY_RANKING_ITEMS:
            upcoming = daily_service.get_upcoming_payloads(hours=36)
            upcoming = _filter_payloads_future(upcoming, "daily_top_backfill", min_lead_minutes=1)
            payloads = daily_service.analysis_service.sort_by_best_picks(
                _merge_unique_payloads(payloads, upcoming)
            )

        if not payloads:
            _job_log_end("job_send_daily_top_summary", started, success=True, payloads=0, sent=False, retryable=True)
            return {"ok": False, "sent": 0, "reason": "no_future_payloads"}

        if not _claim_json_key(SUMMARY_STORE_PATH, summary_key):
            _job_log_end("job_send_daily_top_summary", started, sent=False, reason="already_sent_or_claimed")
            return {"ok": False, "sent": 0, "reason": "already_sent_or_claimed"}

        _persist_payloads(payloads, "ranking_diario")

        best_result = telegram.send_message(format_best_pick(payloads[0]))
        ranking_result = telegram.send_message(format_top_ranking(payloads, top_n=DAILY_RANKING_TOP_N))

        ok = bool(best_result.get("ok") and ranking_result.get("ok"))
        if not ok:
            _release_json_key(SUMMARY_STORE_PATH, summary_key)

        _job_log_end(
            "job_send_daily_top_summary",
            started,
            success=ok,
            payloads=len(payloads),
            sent=min(len(payloads), DAILY_RANKING_TOP_N),
        )
        return {"ok": ok, "sent": min(len(payloads), DAILY_RANKING_TOP_N), "payloads": len(payloads)}
    except Exception as e:
        _release_json_key(SUMMARY_STORE_PATH, summary_key)
        print(f"[SCHEDULER] Erro ao enviar ranking diário: {e}")
        _job_log_end("job_send_daily_top_summary", started, success=False)
        return {"ok": False, "sent": 0, "error": str(e)}



def job_refresh_basketball_calendar():
    """Pré-carrega próximos dias no MySQL sem enviar Telegram."""
    started = _job_log_start("job_refresh_basketball_calendar")
    try:
        payloads = daily_service.get_basketball_range_payloads(
            days=settings.basketball_prefetch_days
        )
        if payloads:
            _persist_payloads(payloads, "calendario_basquete_refresh")
        status = daily_service.api.status()
        _job_log_end(
            "job_refresh_basketball_calendar",
            started,
            success=True,
            persisted=len(payloads),
            cooldown=status.get("cooldown_remaining_seconds"),
        )
        return {"ok": True, "persisted": len(payloads), "sportsdb": status}
    except Exception as exc:
        _job_log_end("job_refresh_basketball_calendar", started, success=False)
        return {"ok": False, "persisted": 0, "error": str(exc), "sportsdb": daily_service.api.status()}


def job_send_basketball_daily_summary():
    """Atualiza calendário de basquete e envia ranking do dia.

    A coleta usa o gateway local Redis e pré-carrega os próximos dias para que
    a dashboard mostre partidas futuras sem consultar a TheSportsDB ao abrir.
    """
    started = _job_log_start("job_send_basketball_daily_summary")
    today = now_local().strftime("%Y-%m-%d")
    summary_key = f"{today}_basketball_daily"

    try:
        calendar_payloads = daily_service.get_basketball_range_payloads(
            days=settings.basketball_prefetch_days
        )
        if calendar_payloads:
            _persist_payloads(calendar_payloads, "calendario_basquete")

        payloads = [
            payload for payload in calendar_payloads
            if str((payload.get("fixture") or {}).get("local_date")
                   or (payload.get("fixture") or {}).get("date") or "") == today
        ]
        payloads = _filter_payloads_future(payloads, "basketball_daily", min_lead_minutes=1)

        if not payloads:
            # Usa o próprio calendário pré-carregado como backfill, sem nova
            # rodada de consultas externas.
            payloads = _filter_payloads_future(
                calendar_payloads,
                "basketball_daily_backfill",
                min_lead_minutes=1,
            )

        if not payloads:
            _job_log_end(
                "job_send_basketball_daily_summary",
                started,
                success=True,
                payloads=0,
                sent=False,
                retryable=True,
                sportsdb=daily_service.api.status(),
            )
            return {
                "ok": False,
                "sent": 0,
                "reason": "no_future_payloads",
                "sportsdb": daily_service.api.status(),
            }

        # Atualizar calendário deve funcionar mesmo se o resumo já foi enviado.
        if _already_sent_summary(summary_key):
            _job_log_end(
                "job_send_basketball_daily_summary",
                started,
                sent=False,
                reason="already_sent",
                persisted=len(calendar_payloads),
            )
            return {
                "ok": True,
                "sent": 0,
                "reason": "already_sent",
                "persisted": len(calendar_payloads),
            }

        if not _claim_json_key(SUMMARY_STORE_PATH, summary_key):
            _job_log_end(
                "job_send_basketball_daily_summary",
                started,
                sent=False,
                reason="already_sent_or_claimed",
            )
            return {"ok": False, "sent": 0, "reason": "already_sent_or_claimed"}

        ranking_result = telegram.send_message(
            format_top_ranking(payloads, top_n=BASKETBALL_RANKING_TOP_N)
        )
        ok = bool(ranking_result.get("ok"))
        if not ok:
            _release_json_key(SUMMARY_STORE_PATH, summary_key)

        _job_log_end(
            "job_send_basketball_daily_summary",
            started,
            success=ok,
            payloads=len(payloads),
            persisted=len(calendar_payloads),
            sent=min(len(payloads), BASKETBALL_RANKING_TOP_N),
        )
        return {
            "ok": ok,
            "sent": min(len(payloads), BASKETBALL_RANKING_TOP_N),
            "payloads": len(payloads),
            "persisted": len(calendar_payloads),
            "sportsdb": daily_service.api.status(),
        }
    except Exception as e:
        _release_json_key(SUMMARY_STORE_PATH, summary_key)
        print(f"[SCHEDULER] Erro ao enviar ranking de basquete: {e}")
        _job_log_end("job_send_basketball_daily_summary", started, success=False)
        return {"ok": False, "sent": 0, "error": str(e), "sportsdb": daily_service.api.status()}


def _preload_turn_payloads(payloads: list[dict], period_label: str):
    """Persiste palpites do turno para dashboard e envia a grade consolidada no Telegram."""
    result = _send_ranked_summary(payloads, period_label)
    print(
        f"[SCHEDULER] Grade do turno processada | "
        f"periodo={period_label} | payloads_entrada={len(payloads)} | result={result}"
    )
    return result


def job_send_morning_summary():
    started = _job_log_start("job_send_morning_summary")
    total_payloads = 0

    print(f"[SCHEDULER] Rodando resumo da manhã: {now_local()}")

    summary_key = f"{now_local().strftime('%Y-%m-%d')}_morning"
    if _already_sent_summary(summary_key):
        print("[SCHEDULER] Resumo da manhã já enviado hoje.")
        _job_log_end("job_send_morning_summary", started, sent=False, reason="already_sent")
        return

    try:
        payloads = daily_service.get_morning_payloads()
        total_payloads = len(payloads)
        print(f"[SCHEDULER] Jogos encontrados para manhã: {total_payloads}")
    except Exception as e:
        print(f"[SCHEDULER] Erro ao buscar jogos da manhã: {e}")
        _job_log_end("job_send_morning_summary", started, success=False, error="fetch_payloads")
        return

    if not payloads:
        print("[SCHEDULER] Nenhum jogo encontrado para manhã para preload. Vai tentar novamente no próximo ciclo/startup.")
        _job_log_end("job_send_morning_summary", started, success=True, payloads=0, sent=False, retryable=True)
        return

    try:
        if not _claim_json_key(SUMMARY_STORE_PATH, summary_key):
            print("[SCHEDULER] Resumo da manhã já enviado/em envio hoje.")
            _job_log_end("job_send_morning_summary", started, sent=False, reason="already_sent_or_claimed")
            return

        send_result = _preload_turn_payloads(payloads, "manhã")
        if not send_result.get("ok"):
            _release_json_key(SUMMARY_STORE_PATH, summary_key)
        _job_log_end("job_send_morning_summary", started, success=bool(send_result.get("ok")), payloads=total_payloads, sent=send_result.get("sent", 0))
    except Exception as e:
        _release_json_key(SUMMARY_STORE_PATH, summary_key)
        print(f"[SCHEDULER] Erro ao enviar resumo da manhã: {e}")
        _job_log_end("job_send_morning_summary", started, success=False, payloads=total_payloads)


def job_send_afternoon_summary():
    started = _job_log_start("job_send_afternoon_summary")
    total_payloads = 0

    print(f"[SCHEDULER] Rodando resumo da tarde: {now_local()}")

    summary_key = f"{now_local().strftime('%Y-%m-%d')}_afternoon"
    if _already_sent_summary(summary_key):
        print("[SCHEDULER] Resumo da tarde já enviado hoje.")
        _job_log_end("job_send_afternoon_summary", started, sent=False, reason="already_sent")
        return

    try:
        payloads = daily_service.get_afternoon_payloads()
        total_payloads = len(payloads)
        print(f"[SCHEDULER] Jogos encontrados para tarde: {total_payloads}")
    except Exception as e:
        print(f"[SCHEDULER] Erro ao buscar jogos da tarde: {e}")
        _job_log_end("job_send_afternoon_summary", started, success=False, error="fetch_payloads")
        return

    if not payloads:
        print("[SCHEDULER] Nenhum jogo encontrado para tarde para preload. Vai tentar novamente no próximo ciclo/startup.")
        _job_log_end("job_send_afternoon_summary", started, success=True, payloads=0, sent=False, retryable=True)
        return

    try:
        if not _claim_json_key(SUMMARY_STORE_PATH, summary_key):
            print("[SCHEDULER] Resumo da tarde já enviado/em envio hoje.")
            _job_log_end("job_send_afternoon_summary", started, sent=False, reason="already_sent_or_claimed")
            return

        send_result = _preload_turn_payloads(payloads, "tarde")
        if not send_result.get("ok"):
            _release_json_key(SUMMARY_STORE_PATH, summary_key)
        _job_log_end("job_send_afternoon_summary", started, success=bool(send_result.get("ok")), payloads=total_payloads, sent=send_result.get("sent", 0))
    except Exception as e:
        _release_json_key(SUMMARY_STORE_PATH, summary_key)
        print(f"[SCHEDULER] Erro ao enviar resumo da tarde: {e}")
        _job_log_end("job_send_afternoon_summary", started, success=False, payloads=total_payloads)




def job_send_night_summary():
    started = _job_log_start("job_send_night_summary")
    total_payloads = 0

    print(f"[SCHEDULER] Rodando resumo da noite: {now_local()}")

    summary_key = f"{now_local().strftime('%Y-%m-%d')}_night"
    if _already_sent_summary(summary_key):
        print("[SCHEDULER] Resumo da noite já enviado hoje.")
        _job_log_end("job_send_night_summary", started, sent=False, reason="already_sent")
        return

    try:
        payloads = daily_service.get_night_payloads()
        total_payloads = len(payloads)
        print(f"[SCHEDULER] Jogos encontrados para noite: {total_payloads}")
    except Exception as e:
        print(f"[SCHEDULER] Erro ao buscar jogos da noite: {e}")
        _job_log_end("job_send_night_summary", started, success=False, error="fetch_payloads")
        return

    if not payloads:
        print("[SCHEDULER] Nenhum jogo encontrado para noite para preload. Vai tentar novamente no próximo ciclo/startup.")
        _job_log_end("job_send_night_summary", started, success=True, payloads=0, sent=False, retryable=True)
        return

    try:
        if not _claim_json_key(SUMMARY_STORE_PATH, summary_key):
            print("[SCHEDULER] Resumo da noite já enviado/em envio hoje.")
            _job_log_end("job_send_night_summary", started, sent=False, reason="already_sent_or_claimed")
            return

        send_result = _preload_turn_payloads(payloads, "noite")
        if not send_result.get("ok"):
            _release_json_key(SUMMARY_STORE_PATH, summary_key)
        _job_log_end("job_send_night_summary", started, success=bool(send_result.get("ok")), payloads=total_payloads, sent=send_result.get("sent", 0))
    except Exception as e:
        _release_json_key(SUMMARY_STORE_PATH, summary_key)
        print(f"[SCHEDULER] Erro ao enviar resumo da noite: {e}")
        _job_log_end("job_send_night_summary", started, success=False, payloads=total_payloads)


def job_preload_upcoming_predictions():
    started = _job_log_start("job_preload_upcoming_predictions")
    try:
        # Janela móvel future-only: melhora o radar e evita depender de uma
        # data exata quando a fonte externa usa UTC/local de formas diferentes.
        hours = 48
        combined = daily_service.get_upcoming_payloads(hours=hours)

        if not combined:
            _job_log_end(
                "job_preload_upcoming_predictions",
                started,
                success=True,
                payloads=0,
                window_hours=hours,
            )
            return

        _persist_payloads(combined, f"preload_upcoming:{hours}h")
        _job_log_end(
            "job_preload_upcoming_predictions",
            started,
            success=True,
            payloads=len(combined),
            window_hours=hours,
        )
    except Exception as e:
        print(f"[SCHEDULER] Erro no preload de previsões futuras: {e}")
        _job_log_end("job_preload_upcoming_predictions", started, success=False)


def run_missed_summaries_on_startup():
    """
    Catch-up seguro após deploy/restart.

    Antes, se o worker reiniciasse depois das 18:00, ele disparava manhã, tarde
    e noite se as flags do dia não existissem. Isso enviava palpites de jogos já
    concluídos. Agora só recupera a grade do turno atual e, mesmo assim, os
    filtros dos turnos só aceitam jogos futuros.
    """
    started = _job_log_start("run_missed_summaries_on_startup")

    try:
        now = now_local()
        today_str = now.strftime("%Y-%m-%d")
        current_turn = _current_summary_turn(now)
        ran_turn = None

        if current_turn:
            key = _turn_summary_key(current_turn, today_str)
            if not _already_sent_summary(key):
                print(
                    f"[SCHEDULER] Catch-up seguro do turno atual acionado no startup | "
                    f"turn={current_turn} | now={now}"
                )
                _send_summary_for_turn(current_turn)
                ran_turn = current_turn
            else:
                print(
                    f"[SCHEDULER] Catch-up ignorado: grade do turno atual já enviada | "
                    f"turn={current_turn} | key={key}"
                )
        else:
            print(f"[SCHEDULER] Catch-up de grades ignorado fora dos turnos | now={now}")

        # Parciais só podem ser recuperadas dentro de uma janela curta após o horário oficial.
        # Isso evita receber parcial da manhã/tarde à noite depois de deploy/restart.
        for partial_turn in ("morning", "afternoon", "night"):
            partial_key = _partial_summary_key(partial_turn)
            if (
                not _already_sent_summary(partial_key)
                and _is_inside_partial_catchup_window(partial_turn, now, grace_minutes=20)
            ):
                print(
                    f"[SCHEDULER] Catch-up pontual da parcial acionado no startup | "
                    f"turn={partial_turn} | now={now}"
                )
                job_send_turn_partial_summary(partial_turn)

        job_preload_upcoming_predictions()

        # Recupera apenas jogos que estejam dentro dos 30 minutos antes do kickoff.
        # Não dispara palpites futuros do dia inteiro após deploy/restart.
        job_check_games()

        _job_log_end(
            "run_missed_summaries_on_startup",
            started,
            success=True,
            current_turn=current_turn,
            ran_turn=ran_turn,
        )
    except Exception as e:
        print(f"[SCHEDULER] Erro no catch-up seguro de resumos no startup: {e}")
        _job_log_end("run_missed_summaries_on_startup", started, success=False)

def _refresh_clv_for_pending_predictions():
    if not odds_service.is_available():
        print("[CLV] OddsService indisponível. Pulando refresh de linha.")
        return 0

    pending = get_pending_predictions()
    if not pending:
        print("[CLV] Nenhuma previsão pendente para atualizar odds.")
        return 0

    updated = 0

    for item in pending:
        try:
            fixture_id = str(item.get("fixture_id", "")).strip()
            league_name = item.get("league")
            home_team = item.get("home_team")
            away_team = item.get("away_team")
            match_date = item.get("date", "")
            pick = _normalize_pick(item.get("pick"))
            market_type = _normalize_market_type(item.get("market_type"))

            if not fixture_id or not league_name or not home_team or not away_team or not pick:
                continue

            odds = odds_service.get_match_odds(
                home_team=home_team,
                away_team=away_team,
                league_name=league_name,
                match_date=match_date,
            )

            if not odds:
                continue

            latest_market_odds = _pick_latest_market_odds_by_market(
                market_type=market_type,
                pick=pick,
                odds=odds,
            )

            if latest_market_odds is not None:
                update_prediction_market_odds(fixture_id, latest_market_odds)
                updated += 1

        except Exception as e:
            print(f"[CLV] Erro atualizando linha de {item.get('fixture_id')}: {e}")

    print(f"[CLV] Odds atualizadas em previsões pendentes: {updated}")
    return updated


def job_check_games():
    started = _job_log_start("job_check_games")
    total_payloads = 0
    sent_alerts = 0

    print(f"[SCHEDULER] Rodando verificação pré-jogo: {now_local()}")

    try:
        football_payloads = daily_service.get_30min_payloads()
        basketball_payloads = daily_service.get_basketball_30min_payloads()
        payloads = _merge_unique_payloads(football_payloads, basketball_payloads)
        raw_payloads = len(payloads)
        payloads = _filter_payloads_prelive(payloads)
        total_payloads = len(payloads)
        print(f"[SCHEDULER] Jogos encontrados na janela dos 30 min: {total_payloads} | raw={raw_payloads}")
    except Exception as e:
        print(f"[SCHEDULER] Erro ao buscar payloads: {e}")
        _job_log_end("job_check_games", started, success=False, error="fetch_payloads")
        return

    if not payloads:
        print("[SCHEDULER] Nenhum jogo elegível no momento.")
        clv_updated = _refresh_clv_for_pending_predictions()
        _job_log_end("job_check_games", started, success=True, payloads=0, clv_updated=clv_updated)
        return

    for payload in payloads:
        try:
            fixture = payload["fixture"]
            fixture_id = str(fixture.get("id", "")).strip()
            home_team = fixture.get("home_team", "Casa")
            away_team = fixture.get("away_team", "Fora")

            if not fixture_id:
                print(f"[SCHEDULER] Jogo sem fixture_id: {home_team} x {away_team}")
                continue

            try:
                save_prediction(payload)
            except Exception as e:
                print(f"[SCHEDULER] Erro ao persistir pré-jogo {fixture_id}: {e}")

            fixture_date = str(fixture.get("local_date") or fixture.get("date") or now_local().strftime("%Y-%m-%d"))
            alert_key = build_alert_key(fixture_id, fixture_date)

            if not _claim_json_key(ALERT_STORE_PATH, alert_key):
                print(f"[SCHEDULER] Alerta já enviado/em envio: {home_team} x {away_team}")
                continue

            message = format_prediction_message(payload)
            result = telegram.send_message(message)

            if result.get("ok"):
                sent_alerts += 1
                print(
                    f"[SCHEDULER] Pré-jogo enviado com sucesso: "
                    f"{home_team} x {away_team}"
                )
            else:
                _release_json_key(ALERT_STORE_PATH, alert_key)
                print(f"[SCHEDULER] Falha no envio Telegram: {result}")

        except Exception as e:
            print(f"[SCHEDULER] Erro no envio pré-jogo: {e}")

    clv_updated = _refresh_clv_for_pending_predictions()
    _job_log_end(
        "job_check_games",
        started,
        success=True,
        payloads=total_payloads,
        sent_alerts=sent_alerts,
        clv_updated=clv_updated,
    )


def job_check_results():
    started = _job_log_start("job_check_results")
    updated_count = 0
    sent_count = 0

    print(f"[SCHEDULER] Rodando verificação de resultados: {now_local()}")

    try:
        updates = result_checker.check_pending_predictions()
        updated_count = len(updates)
        print(f"[SCHEDULER] Resultados finalizados encontrados: {updated_count}")
    except Exception as e:
        print(f"[SCHEDULER] Erro ao checar resultados: {e}")
        _job_log_end("job_check_results", started, success=False, error="result_checker")
        return

    if not updates:
        print("[SCHEDULER] Nenhum resultado novo para enviar.")
        _job_log_end("job_check_results", started, success=True, updated=0, sent=0)
        return

    for item in updates:
        try:
            fixture_id = str(item.get("fixture_id", "")).strip()
            result_key = build_result_key(fixture_id)

            if not _claim_json_key(RESULT_STORE_PATH, result_key):
                print(f"[SCHEDULER] Resultado já enviado/em envio anteriormente: {fixture_id}")
                continue

            ai_summary = gemini_summary.build_result_summary(item)
            caption = format_result_message(item, ai_summary=ai_summary)
            photo_url = pick_winner_photo_url(item)

            if photo_url:
                result = telegram.send_photo(photo_url, caption=caption)
            else:
                result = telegram.send_message(caption)

            print(f"[SCHEDULER] Retorno Telegram: {result}")

            if result.get("ok"):
                sent_count += 1
                print(
                    f"[SCHEDULER] Resultado enviado com sucesso: "
                    f"{item['home_team']} x {item['away_team']} | {item['status']}"
                )
            else:
                _release_json_key(RESULT_STORE_PATH, result_key)
                print(f"[SCHEDULER] Falha ao enviar resultado: {result}")

        except Exception as e:
            print(f"[SCHEDULER] Erro no envio de resultado: {e}")

    _job_log_end(
        "job_check_results",
        started,
        success=True,
        updated=updated_count,
        sent=sent_count,
    )


def job_monitor_live_matches():
    started = _job_log_start("job_monitor_live_matches")

    runtime = _runtime_config()
    live_enabled = bool(
        runtime.get("live_monitor_enabled", settings.live_monitor_enabled)
    )

    if not live_enabled:
        print("[LIVE] Monitor live desativado por configuração.")
        _job_log_end("job_monitor_live_matches", started, success=True, skipped=True)
        return

    print(f"[LIVE] Rodando monitor live: {now_local()}")
    try:
        live_monitor.monitor_live_matches()
        _job_log_end("job_monitor_live_matches", started, success=True)
    except Exception as e:
        print(f"[LIVE] Erro geral no monitor live: {e}")
        _job_log_end("job_monitor_live_matches", started, success=False)


def execute_training_job(trigger: str = "manual"):
    global training_job_running

    started = _job_log_start(f"training_job:{trigger}")

    if training_job_running:
        message = "Já existe um treino em andamento."
        print(f"[TRAINING] {message}")
        _job_log_end(
            f"training_job:{trigger}",
            started,
            success=False,
            skipped=True,
            reason="already_running",
        )
        return {
            "success": False,
            "skipped": True,
            "message": message,
            "trigger": trigger,
        }

    training_job_running = True

    try:
        print(f"[TRAINING] Rodando treino ({trigger}): {now_local()}")

        added_db = training_dataset_service.append_resolved_predictions_to_dataset()
        added_json = training_dataset_service.append_legacy_json_predictions_to_dataset()
        added = int(added_db or 0) + int(added_json or 0)
        print(
            f"[TRAINING] Dataset atualizado | novas linhas líquidas={added} "
            f"(db={added_db}, json={added_json})"
        )

        train_result = ml_training_service.train()

        result = {
            "success": True,
            "skipped": False,
            "trigger": trigger,
            "added": added,
            "train_result": train_result,
            "message": "Treino executado com sucesso.",
            "executed_at": now_local().isoformat(),
        }

        print(f"[TRAINING] Treino ({trigger}) concluído com sucesso.")
        _job_log_end(
            f"training_job:{trigger}",
            started,
            success=True,
            added=added,
        )
        return result

    except Exception as e:
        print(f"[TRAINING] Erro no treino ({trigger}): {e}")
        _job_log_end(
            f"training_job:{trigger}",
            started,
            success=False,
            error=str(e),
        )
        return {
            "success": False,
            "skipped": False,
            "trigger": trigger,
            "message": f"Erro ao executar treino: {e}",
            "error": str(e),
            "executed_at": now_local().isoformat(),
        }

    finally:
        training_job_running = False


def run_manual_training_job():
    return execute_training_job(trigger="manual")


def job_daily_training():
    result = execute_training_job(trigger="scheduled")

    if result.get("success"):
        print("[TRAINING] Treino diário concluído com sucesso.")
    elif result.get("skipped"):
        print(f"[TRAINING] Treino diário ignorado: {result.get('message')}")
    else:
        print(f"[TRAINING] Erro no treino diário: {result.get('message')}")


def run_today_audit():
    started = _job_log_start("run_today_audit")
    try:
        updates = result_checker.check_pending_predictions()
        _job_log_end("run_today_audit", started, success=True, updated=len(updates))
        return {
            "success": True,
            "updated": len(updates),
        }
    except Exception as e:
        print(f"[AUDIT] Erro na auditoria do dia: {e}")
        _job_log_end("run_today_audit", started, success=False)
        return {
            "success": False,
            "updated": 0,
            "error": str(e),
        }


def start_scheduler():
    global scheduler_started

    if scheduler_started:
        print("[SCHEDULER] Já iniciado, ignorando nova inicialização.")
        return

    removed_alerts = _cleanup_old_alert_keys()
    if removed_alerts:
        print(f"[SCHEDULER] Chaves antigas de alerta removidas no startup: {removed_alerts}")

    runtime = _runtime_config()
    live_enabled = bool(
        runtime.get("live_monitor_enabled", settings.live_monitor_enabled)
    )
    live_interval_seconds = int(
        runtime.get(
            "live_monitor_interval_seconds",
            settings.live_monitor_interval_seconds,
        )
    )


    scheduler.add_job(
        job_refresh_basketball_calendar,
        "cron",
        hour=6,
        minute=20,
        id="job_refresh_basketball_calendar",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=900,
    )

    scheduler.add_job(
        job_send_daily_top_summary,
        "cron",
        hour=7,
        minute=30,
        id="job_send_daily_top_summary",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=1800,
    )



    scheduler.add_job(
        job_send_basketball_daily_summary,
        "cron",
        hour=10,
        minute=30,
        id="job_send_basketball_daily_summary",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=1800,
    )

    scheduler.add_job(
        job_send_morning_summary,
        "cron",
        hour=8,
        minute=0,
        id="job_send_morning_summary",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=2400,
    )

    scheduler.add_job(
        job_send_afternoon_summary,
        "cron",
        hour=12,
        minute=30,
        id="job_send_afternoon_summary",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=2400,
    )

    scheduler.add_job(
        job_send_night_summary,
        "cron",
        hour=18,
        minute=0,
        id="job_send_night_summary",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=2400,
    )

    scheduler.add_job(
        job_send_morning_partial_summary,
        "cron",
        hour=12,
        minute=29,
        id="job_send_morning_partial_summary",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=1200,
    )

    scheduler.add_job(
        job_send_afternoon_partial_summary,
        "cron",
        hour=17,
        minute=59,
        id="job_send_afternoon_partial_summary",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=1200,
    )

    scheduler.add_job(
        job_send_night_partial_summary,
        "cron",
        hour=23,
        minute=59,
        id="job_send_night_partial_summary",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=1800,
    )

    scheduler.add_job(
        job_preload_upcoming_predictions,
        "interval",
        hours=6,
        id="job_preload_upcoming_predictions",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=600,
    )

    scheduler.add_job(
        job_daily_training,
        "cron",
        hour=0,
        minute=0,
        id="job_daily_training",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=600,
    )

    scheduler.add_job(
        job_check_games,
        "interval",
        minutes=1,
        id="job_check_games",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
    )

    scheduler.add_job(
        job_check_results,
        "interval",
        minutes=15,
        id="job_check_results",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
    )

    scheduler.add_job(
        run_today_audit,
        "cron",
        hour=23,
        minute=55,
        id="run_today_audit",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )

    if live_enabled:
        scheduler.add_job(
            job_monitor_live_matches,
            "interval",
            seconds=live_interval_seconds,
            id="job_monitor_live_matches",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=30,
        )

    scheduler.start()
    scheduler_started = True


    print("[SCHEDULER] Iniciado com sucesso.")
    print("[SCHEDULER] Aguardando primeiro ciclo automático dos jobs...")

    if live_enabled:
        print("[SCHEDULER] Monitor live habilitado e aguardando próximo ciclo normal.")
