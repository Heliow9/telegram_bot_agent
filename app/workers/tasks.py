from __future__ import annotations

from typing import Any, Dict

from app.workers.celery_app import celery_app
from app.services.analysis_service import AnalysisService
from app.services.telegram_service import TelegramService
from app.services.scheduler_service import job_send_basketball_daily_summary, job_send_daily_top_summary


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def analyze_match_task(self, match: Dict[str, Any], league_meta: Dict[str, Any]) -> Dict[str, Any] | None:
    return AnalysisService().build_match_analysis(match, league_meta)


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def send_telegram_task(self, text: str, photo_url: str | None = None) -> bool:
    telegram = TelegramService()
    if photo_url:
        telegram.send_photo(caption=text, photo_url=photo_url)
    else:
        telegram.send_message(text=text)
    return True


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def run_scheduler_tick_task(self, job_name: str) -> str:
    # reservado para evoluções: permite disparar jobs pesados pela fila
    return f"queued:{job_name}"



@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 1}, soft_time_limit=540, time_limit=600, rate_limit="1/m")
def send_basketball_ranking_task(self) -> dict:
    """Executa envio do ranking de basquete fora do request HTTP."""
    return job_send_basketball_daily_summary()


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 1}, soft_time_limit=240, time_limit=300)
def send_daily_ranking_task(self) -> dict:
    """Executa envio do ranking diário de futebol fora do request HTTP."""
    return job_send_daily_top_summary()
