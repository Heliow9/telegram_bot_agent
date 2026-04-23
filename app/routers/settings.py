from fastapi import APIRouter, Depends, HTTPException
from app.deps import get_current_user
from app.schemas_settings import RuntimeConfigResponse, RuntimeConfigUpdate
from app.services.runtime_config_service import load_runtime_config, save_runtime_config
from app.services.scheduler_service import run_manual_training_job


router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/runtime", response_model=RuntimeConfigResponse)
def get_runtime_settings(current_user=Depends(get_current_user)):
    return load_runtime_config()


@router.put("/runtime", response_model=RuntimeConfigResponse)
def update_runtime_settings(
    payload: RuntimeConfigUpdate,
    current_user=Depends(get_current_user),
):
    updated = save_runtime_config(
        payload.model_dump(exclude_unset=True, exclude_none=True)
    )
    return updated


@router.post("/runtime/train")
def run_manual_training(current_user=Depends(get_current_user)):
    try:
        result = run_manual_training_job()
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao executar treino manual: {e}",
        )