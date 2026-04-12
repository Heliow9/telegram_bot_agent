from fastapi import FastAPI
from app.config import settings
from app.routers.predictions import router as predictions_router

# scheduler
from app.services.scheduler_service import start_scheduler

app = FastAPI(title=settings.app_name)

# rotas
app.include_router(predictions_router)


@app.on_event("startup")
def startup_event():
    print("🚀 Iniciando aplicação...")
    print(f"📊 Ambiente: {settings.app_env}")

    try:
        start_scheduler()
        print("⏰ Scheduler iniciado com sucesso")
    except Exception as e:
        print(f"❌ Erro ao iniciar scheduler: {e}")


@app.get("/")
def root():
    return {
        "name": settings.app_name,
        "env": settings.app_env,
        "status": "running",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
    }