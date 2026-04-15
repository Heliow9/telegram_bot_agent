from contextlib import asynccontextmanager
import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app.config import settings
from app.db import Base, engine
from app.routers.predictions import router as predictions_router
from app.routers.auth import router as auth_router
from app.routers.dashboard import router as dashboard_router
from app.routers.settings import router as settings_router
from app.services.scheduler_service import start_scheduler
from app.services.post_deploy_sync_service import PostDeploySyncService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

_scheduler_started = False
_post_deploy_sync_ran = False


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

    if _post_deploy_sync_ran:
        logger.info("⏭️ Pós-deploy sync já executado nesta instância. Ignorando.")
        return

    try:
        logger.info("🔄 Executando sincronização pós-deploy...")
        service = PostDeploySyncService()
        service.run_once()
        _post_deploy_sync_ran = True
        logger.info("✅ Sincronização pós-deploy concluída")
    except Exception as e:
        logger.exception("❌ Erro na sincronização pós-deploy: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Iniciando aplicação...")
    logger.info("📊 Ambiente: %s", settings.app_env)

    Base.metadata.create_all(bind=engine)

    safe_run_post_deploy_sync()
    safe_start_scheduler()

    yield

    logger.info("🛑 Encerrando aplicação...")


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://telegram-bot-agent-6gik.onrender.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(predictions_router)
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(settings_router)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    try:
        response = await call_next(request)
        logger.info(
            "%s %s -> %s",
            request.method,
            request.url.path,
            response.status_code,
        )
        return response
    except Exception as e:
        logger.exception(
            "Erro durante request %s %s: %s",
            request.method,
            request.url.path,
            e,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )


@app.get("/")
def root():
    return {
        "name": settings.app_name,
        "env": settings.app_env,
        "status": "running",
        "scheduler_started": _scheduler_started,
        "post_deploy_sync_ran": _post_deploy_sync_ran,
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": settings.app_name,
        "env": settings.app_env,
        "scheduler_started": _scheduler_started,
        "post_deploy_sync_ran": _post_deploy_sync_ran,
    }


@app.head("/")
def root_head():
    return Response(status_code=200)


@app.head("/health")
def health_head():
    return Response(status_code=200)


@app.get("/ping")
def ping():
    return {
        "pong": True,
        "message": "service awake",
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)