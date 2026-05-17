from __future__ import annotations

from typing import Any, Dict

from app.workers.celery_app import celery_app
from app.services.analysis_service import AnalysisService
from app.services.telegram_service import TelegramService


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
