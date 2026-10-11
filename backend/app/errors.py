import logging
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

logger = logging.getLogger(__name__)


class ApiError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str, headers=None):
        super().__init__(status_code, message, headers=headers)
        self.code = code


def install_error_handlers(app: FastAPI):
    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse(status_code=exc.status_code, headers=exc.headers,
            content={"error": {"code": getattr(exc, "code", f"http_{exc.status_code}"),
                               "message": str(exc.detail)}})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Never include input values, bodies or validator context: these can contain passwords.
        details = [{"location": list(e["loc"]), "type": e["type"],
                    "message": "Invalid value"} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"error": {
            "code": "validation_error", "message": "Request validation failed", "details": details}})

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        # SQL exception strings can contain password hashes and other private parameters.
        logger.error("Database operation failed (%s)", type(exc).__name__)
        return JSONResponse(status_code=503, content={"error": {
            "code": "database_unavailable", "message": "Database operation unavailable"}})
