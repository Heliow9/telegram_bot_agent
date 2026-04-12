from apscheduler.schedulers.background import BackgroundScheduler
from pathlib import Path
from datetime import datetime
import json

from app.services.daily_leagues_service import DailyLeaguesService
from app.services.telegram_service import TelegramService
from app.services.message_formatter import format_prediction_message
from app.services.time_utils import now_local


scheduler = BackgroundScheduler(timezone="America/Recife")
daily_service = DailyLeaguesService()
telegram = TelegramService()

scheduler_started = False

ALERT_STORE_PATH = Path("data/sent_alerts.json")


def _ensure_alert_store():
    ALERT_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not ALERT_STORE_PATH.exists():
        ALERT_STORE_PATH.write_text("[]", encoding="utf-8")


def _load_sent_alerts():
    _ensure_alert_store()
    try:
        return json.loads(ALERT_STORE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def _save_sent_alert(alert_key: str):
    alerts = _load_sent_alerts()
    if alert_key not in alerts:
        alerts.append(alert_key)
        ALERT_STORE_PATH.write_text(
            json.dumps(alerts, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _already_sent(alert_key: str) -> bool:
    alerts = _load_sent_alerts()
    return alert_key in alerts


def job_check_games():
    print(f"[SCHEDULER] Rodando verificação: {now_local()}")

    try:
        # agora usa o método certo: só jogos na faixa dos 30 min
        payloads = daily_service.get_30min_payloads()
        print(f"[SCHEDULER] Jogos encontrados na janela dos 30 min: {len(payloads)}")
    except Exception as e:
        print(f"[SCHEDULER] Erro ao buscar payloads: {e}")
        return

    if not payloads:
        print("[SCHEDULER] Nenhum jogo elegível no momento.")
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

            alert_key = f"{fixture_id}_30min"

            if _already_sent(alert_key):
                print(f"[SCHEDULER] Já enviado antes: {home_team} x {away_team}")
                continue

            message = format_prediction_message(payload)
            result = telegram.send_message(message)

            if result.get("ok"):
                _save_sent_alert(alert_key)
                print(f"[SCHEDULER] Enviado com sucesso: {home_team} x {away_team}")
            else:
                print(f"[SCHEDULER] Falha no envio Telegram: {result}")

        except Exception as e:
            print(f"[SCHEDULER] Erro no jogo: {e}")


def start_scheduler():
    global scheduler_started

    if scheduler_started:
        print("[SCHEDULER] Já iniciado, ignorando nova inicialização.")
        return

    # job recorrente
    scheduler.add_job(
        job_check_games,
        "interval",
        minutes=7,
        id="job_check_games",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()
    scheduler_started = True
    print("[SCHEDULER] Iniciado com sucesso.")

    # executa imediatamente ao subir a aplicação
    print("[SCHEDULER] Executando primeira verificação imediata...")
    job_check_games()