from contextlib import asynccontextmanager
import logging
import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from app.config import settings
from app.routers.predictions import router as predictions_router
from app.services.scheduler_service import start_scheduler

# -----------------------------------------------------------------------------
# Logging básico
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# Controle simples para evitar múltiplas inicializações do scheduler
_scheduler_started = False


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Iniciando aplicação...")
    logger.info("📊 Ambiente: %s", settings.app_env)

    safe_start_scheduler()

    yield

    logger.info("🛑 Encerrando aplicação...")


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
)

# -----------------------------------------------------------------------------
# Rotas
# -----------------------------------------------------------------------------
app.include_router(predictions_router)


# -----------------------------------------------------------------------------
# Middleware simples para log de requests
# -----------------------------------------------------------------------------
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
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": settings.app_name,
        "env": settings.app_env,
        "scheduler_started": _scheduler_started,
    }


# Responde ao healthcheck HEAD do Render sem retornar 405
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


# Opcional: porta local quando rodar diretamente com python main.py
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)