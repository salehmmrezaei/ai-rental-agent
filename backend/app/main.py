from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.routers.health import router


def create_app() -> FastAPI:
    app = FastAPI(title="AI Rental Agent", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins,
                       allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "DELETE"],
                       allow_headers=["Authorization", "Content-Type"])
    app.include_router(router, prefix="/api/v1")
    return app
