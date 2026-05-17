from fastapi import APIRouter, Depends

from app.deps import get_current_user
from app.services.scheduler_service import (
    job_check_results,
    job_check_games,
    run_today_audit,
)
from app.services.post_deploy_sync_service import PostDeploySyncService


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
