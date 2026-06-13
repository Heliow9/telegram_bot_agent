from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_current_user
from app.services.scheduler_service import (
    job_check_results,
    job_check_games,
    job_send_daily_top_summary,
    job_send_basketball_daily_summary,
    job_send_morning_summary,
    job_send_afternoon_summary,
    job_send_night_summary,
    run_today_audit,
)
from app.services.post_deploy_sync_service import PostDeploySyncService
from app.workers.tasks import send_basketball_ranking_task, send_daily_ranking_task


router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/run-results-check")
def run_results_check(current_user=Depends(get_current_user)):
    job_check_results()
    return {
        "success": True,
        "message": "Verificação de resultados executada com sucesso.",
    }


@router.post("/run-pre-game-check")
def run_pre_game_check(current_user=Depends(get_current_user)):
    job_check_games()
    return {
        "success": True,
        "message": "Verificação pré-jogo executada com sucesso.",
    }


@router.post("/send-daily-ranking")
def send_daily_ranking(current_user=Depends(get_current_user)):
    """Dispara ranking diário em background para não travar a dashboard/API."""
    try:
        task = send_daily_ranking_task.delay()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Fila indisponível para processar ranking diário: {exc}")

    return {
        "success": True,
        "queued": True,
        "task_id": task.id,
        "message": "Ranking diário enfileirado. Acompanhe os logs do worker-analysis.",
    }




@router.post("/send-basketball-ranking")
def send_basketball_ranking(current_user=Depends(get_current_user)):
    """Dispara ranking de basquete em background para não travar a dashboard/API."""
    try:
        task = send_basketball_ranking_task.delay()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Fila indisponível para processar ranking de basquete: {exc}")

    return {
        "success": True,
        "queued": True,
        "task_id": task.id,
        "message": "Ranking de basquete enfileirado. Acompanhe os logs do worker-analysis.",
    }


@router.post("/send-morning-summary")
def send_morning_summary(current_user=Depends(get_current_user)):
    job_send_morning_summary()
    return {"success": True, "message": "Resumo da manhã processado."}


@router.post("/send-afternoon-summary")
def send_afternoon_summary(current_user=Depends(get_current_user)):
    job_send_afternoon_summary()
    return {"success": True, "message": "Resumo da tarde processado."}


@router.post("/send-night-summary")
def send_night_summary(current_user=Depends(get_current_user)):
    job_send_night_summary()
    return {"success": True, "message": "Resumo da noite processado."}


@router.post("/run-today-audit")
def run_today_audit_route(current_user=Depends(get_current_user)):
    return run_today_audit()


@router.post("/run-post-deploy-sync")
def run_post_deploy_sync(current_user=Depends(get_current_user)):
    service = PostDeploySyncService()
    result = service.run_once()
    return {
        "success": True,
        "message": "Sincronização pós-deploy executada com sucesso.",
        "result": result,
    }

# Aliases compatíveis com diferentes versões da dashboard.
@router.post("/run-prelive")
def run_prelive_alias(current_user=Depends(get_current_user)):
    return run_pre_game_check(current_user=current_user)


@router.post("/run-pre-analysis")
def run_pre_analysis_alias(current_user=Depends(get_current_user)):
    return run_pre_game_check(current_user=current_user)


@router.post("/check-results")
def check_results_alias(current_user=Depends(get_current_user)):
    return run_results_check(current_user=current_user)


@router.post("/audit-today")
def audit_today_alias(current_user=Depends(get_current_user)):
    return run_today_audit_route(current_user=current_user)


@router.post("/post-deploy-sync")
def post_deploy_sync_alias(current_user=Depends(get_current_user)):
    return run_post_deploy_sync(current_user=current_user)


@router.post("/daily-ranking")
def daily_ranking_alias(current_user=Depends(get_current_user)):
    return send_daily_ranking(current_user=current_user)


@router.post("/basketball-ranking")
def basketball_ranking_alias(current_user=Depends(get_current_user)):
    return send_basketball_ranking(current_user=current_user)
