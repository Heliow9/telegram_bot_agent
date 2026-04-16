from apscheduler.schedulers.background import BackgroundScheduler
from pathlib import Path
from datetime import datetime
import json
import time

from app.config import settings
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
    get_pending_predictions,
    update_prediction_market_odds,
)
from app.services.runtime_config_service import load_runtime_config


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

ALERT_STORE_PATH = Path("data/sent_alerts.json")
RESULT_STORE_PATH = Path("data/sent_results.json")
SUMMARY_STORE_PATH = Path("data/sent_summaries.json")


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


def _persist_payloads(payloads: list[dict], source_label: str):
    saved = 0

    for payload in payloads:
        try:
            save_prediction(payload)
            saved += 1
        except Exception as e:
            fixture = payload.get("fixture", {})
            fixture_id = fixture.get("id", "sem_id")
            print(
                f"[SCHEDULER] Erro ao persistir previsão "
                f"({source_label}) fixture={fixture_id}: {e}"
            )

    print(
        f"[SCHEDULER] Persistência concluída ({source_label}). "
        f"Payloads processados: {saved}"
    )


def _send_ranked_summary(payloads: list[dict], period_label: str):
    _persist_payloads(payloads, period_label)

    best_result = telegram.send_message(format_best_pick(payloads[0]))
    print(f"[SCHEDULER] Melhor aposta enviada ({period_label}): {best_result}")

    ranking_result = telegram.send_message(format_top_ranking(payloads, top_n=5))
    print(f"[SCHEDULER] Top ranking enviado ({period_label}): {ranking_result}")

    grouped = group_payloads_by_league(payloads)

    desired_order = [
        "Brasileirão Série A",
        "Brasileirão Série B",
        "Premier League",
        "Championship",
        "Liga dos Campeões",
        "Argentina Liga Profesional",
        "Itália Série A",
        "Turquia Super Lig",
        "Libertadores",
        "Copa Sul-Americana",
    ]

    for league_name in desired_order:
        league_payloads = grouped.get(league_name, [])
        if not league_payloads:
            continue

        result = telegram.send_message(
            format_league_summary(league_name, league_payloads)
        )
        print(f"[SCHEDULER] Resumo enviado para liga {league_name}: {result}")


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
        result = telegram.send_message(
            "📭 *Nenhum jogo encontrado pela manhã hoje.*\n\n"
            "Ligas monitoradas: Brasileirão A, Brasileirão B, Premier League, Championship, "
            "Liga dos Campeões, Argentina Liga Profesional, Itália Série A, "
            "Turquia Super Lig, Libertadores e Copa Sul-Americana."
        )
        print(f"[SCHEDULER] Aviso de manhã sem jogos enviado: {result}")
        _save_sent_summary(summary_key)
        _job_log_end("job_send_morning_summary", started, success=True, payloads=0)
        return

    try:
        _send_ranked_summary(payloads, "manhã")
        _save_sent_summary(summary_key)
        _job_log_end("job_send_morning_summary", started, success=True, payloads=total_payloads)
    except Exception as e:
        print(f"[SCHEDULER] Erro ao enviar resumo da manhã: {e}")
        _job_log_end("job_send_morning_summary", started, success=False, payloads=total_payloads)


def job_send_afternoon_summary():
    started = _job_log_start("job_send_afternoon_summary")
    total_payloads = 0

    print(f"[SCHEDULER] Rodando resumo da tarde/noite: {now_local()}")

    summary_key = f"{now_local().strftime('%Y-%m-%d')}_afternoon"
    if _already_sent_summary(summary_key):
        print("[SCHEDULER] Resumo da tarde/noite já enviado hoje.")
        _job_log_end("job_send_afternoon_summary", started, sent=False, reason="already_sent")
        return

    try:
        payloads = daily_service.get_afternoon_payloads()
        total_payloads = len(payloads)
        print(f"[SCHEDULER] Jogos encontrados para tarde/noite: {total_payloads}")
    except Exception as e:
        print(f"[SCHEDULER] Erro ao buscar jogos da tarde/noite: {e}")
        _job_log_end("job_send_afternoon_summary", started, success=False, error="fetch_payloads")
        return

    if not payloads:
        result = telegram.send_message(
            "📭 *Nenhum jogo encontrado para a tarde/noite hoje.*\n\n"
            "Ligas monitoradas: Brasileirão A, Brasileirão B, Premier League, Championship, "
            "Liga dos Campeões, Argentina Liga Profesional, Itália Série A, "
            "Turquia Super Lig, Libertadores e Copa Sul-Americana."
        )
        print(f"[SCHEDULER] Aviso de tarde/noite sem jogos enviado: {result}")
        _save_sent_summary(summary_key)
        _job_log_end("job_send_afternoon_summary", started, success=True, payloads=0)
        return

    try:
        _send_ranked_summary(payloads, "tarde/noite")
        _save_sent_summary(summary_key)
        _job_log_end("job_send_afternoon_summary", started, success=True, payloads=total_payloads)
    except Exception as e:
        print(f"[SCHEDULER] Erro ao enviar resumo da tarde/noite: {e}")
        _job_log_end("job_send_afternoon_summary", started, success=False, payloads=total_payloads)


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
            fixture_id = str(item.get("fixture_id", ""))
            league_name = item.get("league")
            home_team = item.get("home_team")
            away_team = item.get("away_team")
            match_date = item.get("date", "")
            pick = item.get("pick")

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

            latest_market_odds = None
            if pick == "1":
                latest_market_odds = odds.get("home_odds")
            elif pick == "X":
                latest_market_odds = odds.get("draw_odds")
            elif pick == "2":
                latest_market_odds = odds.get("away_odds")

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
        payloads = daily_service.get_30min_payloads()
        total_payloads = len(payloads)
        print(f"[SCHEDULER] Jogos encontrados na janela dos 30 min: {total_payloads}")
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
            fixture_id = str(fixture.get("id", ""))
            home_team = fixture.get("home_team", "Casa")
            away_team = fixture.get("away_team", "Fora")

            if not fixture_id:
                print(f"[SCHEDULER] Jogo sem fixture_id: {home_team} x {away_team}")
                continue

            try:
                save_prediction(payload)
            except Exception as e:
                print(f"[SCHEDULER] Erro ao persistir pré-jogo {fixture_id}: {e}")

            alert_key = f"{fixture_id}_30min"

            if _already_sent_alert(alert_key):
                print(f"[SCHEDULER] Alerta já enviado: {home_team} x {away_team}")
                continue

            message = format_prediction_message(payload)
            result = telegram.send_message(message)

            if result.get("ok"):
                _save_sent_alert(alert_key)
                sent_alerts += 1
                print(
                    f"[SCHEDULER] Pré-jogo enviado com sucesso: "
                    f"{home_team} x {away_team}"
                )
            else:
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
            fixture_id = str(item.get("fixture_id", ""))
            result_key = f"{fixture_id}_result"

            if _already_sent_result(result_key):
                print(f"[SCHEDULER] Resultado já enviado anteriormente: {fixture_id}")
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
                _save_sent_result(result_key)
                sent_count += 1
                print(
                    f"[SCHEDULER] Resultado enviado com sucesso: "
                    f"{item['home_team']} x {item['away_team']} | {item['status']}"
                )
            else:
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


def job_daily_training():
    started = _job_log_start("job_daily_training")

    print(f"[TRAINING] Rodando treino diário: {now_local()}")

    try:
        training_dataset_service.append_resolved_predictions_to_dataset()
        ml_training_service.train()
        print("[TRAINING] Treino diário concluído com sucesso.")
        _job_log_end("job_daily_training", started, success=True)
    except Exception as e:
        print(f"[TRAINING] Erro no treino diário: {e}")
        _job_log_end("job_daily_training", started, success=False)


def run_today_audit():
    """
    Auditoria simples do dia:
    reexecuta checker de resultados para pegar inconsistências do dia atual.
    """
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
        job_send_morning_summary,
        "cron",
        hour=8,
        minute=0,
        id="job_send_morning_summary",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
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
        misfire_grace_time=120,
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