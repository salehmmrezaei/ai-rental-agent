from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.errors import install_error_handlers
from app.routers import auth, health, users, inventory, operations
from app.upload_limits import UploadRequestLimit
from app.throttle import install_auth_throttle


def create_app() -> FastAPI:
    settings = get_settings()
    settings.signing_key()  # Fail startup rather than issuing tokens with an absent/weak secret.
    app = FastAPI(title="AI Rental Agent", version="0.4.0")
    install_error_handlers(app)
    install_auth_throttle(app, settings.auth_rate_limit)
    app.add_middleware(UploadRequestLimit, max_bytes=settings.max_image_bytes + 65536)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                       allow_credentials=True, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                       allow_headers=["Authorization", "Content-Type"])
    for router in (health.router, auth.router, users.router, inventory.router, operations.router):
        app.include_router(router, prefix="/api/v1")
    return app
