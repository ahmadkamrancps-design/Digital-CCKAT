import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.dependencies import Db
from app.api.routes import (
    admin_domain,
    admin_management,
    attempts,
    auth,
    grading,
    proctor,
    profiles,
)
from app.config import Settings, load_settings
from app.core.clock import DatabaseClock
from app.core.http_security import (
    RequestLimitsMiddleware,
    SafeErrorsMiddleware,
    SecurityHeadersMiddleware,
    security_headers,
)
from app.db.session import create_db_engine, create_session_factory
from app.services.google_identity import GoogleIdentityVerifier
from app.services.operations_service import check_readiness, migration_head

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or load_settings()
    logging.basicConfig(level=config.log_level, format="%(levelname)s %(name)s %(message)s")
    engine = create_db_engine(config)
    identity_verifier = GoogleIdentityVerifier(config.google_client_id)
    expected_head = migration_head()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        # Migrations run explicitly, never via metadata.create_all at startup.
        try:
            yield
        finally:
            identity_verifier.close()
            engine.dispose()

    app = FastAPI(
        title="CCK Digital Entry Test",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if config.environment != "production" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if config.environment != "production" else None,
    )
    app.state.settings = config
    app.state.session_factory = create_session_factory(engine)
    app.state.identity_verifier = identity_verifier
    app.state.clock = DatabaseClock()
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.allowed_hosts)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[config.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )
    app.add_middleware(RequestLimitsMiddleware, max_bytes=config.max_request_bytes)
    app.add_middleware(SafeErrorsMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, production=config.environment == "production")

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI's default error can echo rejected inputs, including credentials.
        return JSONResponse(status_code=422, content={"detail": "Please check the request data."})

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.error("Database request failed error_type=%s", type(exc).__name__)
        return JSONResponse(status_code=503, content={"detail": "Service temporarily unavailable."})

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Request failed error_type=%s", type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={"detail": "Unable to complete this request."},
            headers=security_headers(config.environment == "production"),
        )

    @app.get("/api/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/health/ready", tags=["health"])
    def readiness(db: Db) -> dict[str, str]:
        check_readiness(db, config, expected_head)
        return {"status": "ready"}

    app.include_router(auth.router, prefix="/api")
    app.include_router(profiles.router, prefix="/api")
    app.include_router(admin_domain.router, prefix="/api")
    app.include_router(admin_management.router, prefix="/api")
    app.include_router(attempts.router, prefix="/api")
    app.include_router(attempts.admin_router, prefix="/api")
    app.include_router(proctor.router, prefix="/api")
    app.include_router(grading.router, prefix="/api")
    return app


app = create_app()
