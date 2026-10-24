"""Application factory and router registration.

Run with:  uvicorn app.main:app --reload --port 8000   (from backend/)
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api.routes import (
    auth,
    dashboard,
    device_api,
    displays,
    legacy,
    media,
    ocr,
    publications,
    users,
    versions,
    ws,
)
from app.core.config import get_settings
from app.core.logging import configure_logging, new_request_id, set_request_id
from app.services.realtime import pump

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings = get_settings()
    configure_logging("DEBUG" if settings.debug else "INFO")
    logger.info(
        "Starting %s v%s (environment=%s)",
        settings.app_name,
        __version__,
        settings.environment,
    )

    await pump.start()
    try:
        yield
    finally:
        await pump.stop()
        logger.info("Shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
    )

    # Specific origins, not "*". Credentials with a wildcard origin is both
    # rejected by browsers and wrong for an internal tool.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-Request-ID", "ETag", "X-Content-Checksum"],
    )

    @application.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or new_request_id()
        set_request_id(request_id)
        try:
            response = await call_next(request)
        finally:
            set_request_id(None)
        response.headers["X-Request-ID"] = request_id
        return response

    @application.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        from app.core.logging import get_request_id

        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "request_id": get_request_id()},
            headers=getattr(exc, "headers", None),
        )

    @application.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        from app.core.logging import get_request_id

        # First message only: enough for the user to fix the field, without
        # echoing internal model structure.
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", []) if p not in ("body",))
        message = first.get("msg", "Data tidak valid.")
        detail = f"{field}: {message}" if field else message

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": detail, "request_id": get_request_id()},
        )

    @application.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        """Never leak a traceback or an internal path to a client."""
        from app.core.logging import get_request_id

        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Terjadi kesalahan di server. Hubungi admin dengan ID ini.",
                "request_id": get_request_id(),
            },
        )

    @application.get("/health", tags=["health"])
    async def health():
        """Cheap liveness check. Deliberately loads no OCR model."""
        return {"status": "ok", "service": settings.app_name, "version": __version__}

    @application.get("/", tags=["health"])
    async def root():
        return {"status": "ok", "service": settings.app_name, "version": __version__}

    api_routers = (
        auth.router,
        users.router,
        versions.router,
        publications.router,
        displays.router,
        dashboard.router,
        media.router,
        ocr.router,
        device_api.router,
        ws.router,
    )
    for router in api_routers:
        application.include_router(router, prefix="/api")

    if settings.enable_legacy_api:
        application.include_router(legacy.router)

    return application


app = create_app()
