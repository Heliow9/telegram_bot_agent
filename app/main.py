from fastapi import FastAPI
from app.config import settings
from app.routers.predictions import router as predictions_router

app = FastAPI(title=settings.app_name)

app.include_router(predictions_router)


@app.get("/")
def root():
    return {
        "name": settings.app_name,
        "env": settings.app_env,
        "status": "running",
    }