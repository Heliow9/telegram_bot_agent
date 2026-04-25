from contextlib import asynccontextmanager
import logging
import threading
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app.config import settings
from app.db import Base, engine
from app.routers.predictions import router as predictions_router
from app.routers.auth import router as auth_router
from app.routers.dashboard import router as dashboard_router
from app.routers.settings import router as settings_router
from app.routers.admin import router as admin_router
from app.services.scheduler_service import (
    start_scheduler,
    run_missed_summaries_on_startup,
    execute_training_job,
)
from app.services.post_deploy_sync_service import PostDeploySyncService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

_scheduler_started = False
_post_deploy_sync_ran = False
_startup_summary_recovery_ran = False


def reset_training_artifacts() -> None:
    logger.info("🧹 Resetando artefatos de treino (dataset/modelo)...")
    paths = [
        Path("data/historical_training_matches.csv"),
        Path("models/1x2_model.joblib"),
        Path("models/1x2_model_metadata.json"),
    ]

    for path in paths:
        try:
            if path.exists():
                path.unlink()
                logger.info("🗑️ Removido: %s", path)
        except Exception as e:
            logger.warning("⚠️ Erro ao remover %s: %s", path, e)


def safe_start_scheduler() -> None:
    global _scheduler_started
    if _scheduler_started:
        logger.info("⏭️ Scheduler já havia sido iniciado. Ignorando nova inicialização.")
        return

    try:
        start_scheduler()
        _scheduler_started = True
        logger.info("⏰ Scheduler iniciado com sucesso")
    except Exception as e:
        logger.exception("❌ Erro ao iniciar scheduler: %s", e)


def safe_run_post_deploy_sync() -> None:
    global _post_deploy_sync_ran
    if _post_deploy_sync_ran or not settings.run_post_deploy_sync_on_startup:
        return

    try:
        logger.info("🔄 Executando sincronização pós-deploy...")
        service = PostDeploySyncService()
        service.run_once()
        _post_deploy_sync_ran = True
        logger.info("✅ Sincronização pós-deploy concluída")
    except Exception as e:
        logger.exception("❌ Erro na sincronização pós-deploy: %s", e)


def safe_run_startup_summary_recovery() -> None:
    global _startup_summary_recovery_ran
    if _startup_summary_recovery_ran or not settings.run_missed_summary_recovery_on_startup:
        return

    try:
        logger.info("📨 Verificando resumos perdidos por horário de deploy...")
        run_missed_summaries_on_startup()
        _startup_summary_recovery_ran = True
        logger.info("✅ Recuperação de resumos concluída")
    except Exception as e:
        logger.exception("❌ Erro na recuperação de resumos: %s", e)


def should_run_background_jobs() -> bool:
    if settings.app_role == "scheduler":
        return True
    return settings.enable_background_jobs


def start_background_jobs() -> None:
    if not should_run_background_jobs():
        logger.info("⏭️ Background jobs desativados nesta instância | role=%s", settings.app_role)
        return

    def run():
        execute_training_job(trigger="startup")
        safe_start_scheduler()
        safe_run_post_deploy_sync()
        safe_run_startup_summary_recovery()

    thread = threading.Thread(target=run, name="botbet-background-jobs", daemon=True)
    thread.start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Iniciando aplicação...")
    logger.info("📊 Ambiente: %s | role=%s", settings.app_env, settings.app_role)

    if settings.create_tables_on_startup:
        Base.metadata.create_all(bind=engine)

    start_background_jobs()
    yield
    logger.info("🛑 Encerrando aplicação...")


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(predictions_router)
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(settings_router)
app.include_router(admin_router)


def _apply_cors_headers(request: Request, response: JSONResponse) -> JSONResponse:
    origin = request.headers.get("origin")
    allowed = settings.cors_origins or []
    if origin and ("*" in allowed or origin in allowed):
        response.headers["Access-Control-Allow-Origin"] = origin if "*" not in allowed else "*"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Vary"] = "Origin"
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next):
    try:
        response = await call_next(request)
        if settings.request_log_enabled:
            logger.info("%s %s -> %s", request.method, request.url.path, response.status_code)
        return response
    except Exception as e:
        logger.exception("Erro durante request %s %s: %s", request.method, request.url.path, e)
        return _apply_cors_headers(request, JSONResponse(status_code=500, content={"detail": str(e) if settings.app_env != "prod" else "Internal server error"}))


@app.get("/")
def root():
    return {
        "name": settings.app_name,
        "env": settings.app_env,
        "role": settings.app_role,
        "status": "running",
        "background_jobs_enabled": should_run_background_jobs(),
        "scheduler_started": _scheduler_started,
        "post_deploy_sync_ran": _post_deploy_sync_ran,
        "startup_summary_recovery_ran": _startup_summary_recovery_ran,
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": settings.app_name,
        "env": settings.app_env,
        "role": settings.app_role,
        "background_jobs_enabled": should_run_background_jobs(),
        "scheduler_started": _scheduler_started,
        "post_deploy_sync_ran": _post_deploy_sync_ran,
        "startup_summary_recovery_ran": _startup_summary_recovery_ran,
    }


@app.head("/")
def root_head():
    return Response(status_code=200)


@app.head("/health")
def health_head():
    return Response(status_code=200)


@app.get("/ping")
def ping():
    return {"pong": True, "role": settings.app_role}
