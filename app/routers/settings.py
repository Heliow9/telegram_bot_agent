from fastapi import APIRouter, Depends
from app.deps import get_current_user
from app.schemas_settings import RuntimeConfigResponse, RuntimeConfigUpdate
from app.services.runtime_config_service import load_runtime_config, save_runtime_config

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