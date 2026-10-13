import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.dependencies import Db
from app.api.routes import admin_domain, attempts, auth, profiles
from app.config import Settings, load_settings
from app.core.clock import DatabaseClock
from app.db.session import create_db_engine, create_session_factory
from app.services.google_identity import GoogleIdentityVerifier

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).extend(
                    [
                        (b"cache-control", b"no-store"),
                        (b"x-content-type-options", b"nosniff"),
                        (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    ]
                )
            await send(message)

        await self.app(scope, receive, send_with_headers)


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or load_settings()
    logging.basicConfig(level=config.log_level, format="%(levelname)s %(name)s %(message)s")
    engine = create_db_engine(config)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        # Migrations run explicitly, never via metadata.create_all at startup.
        yield
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
    app.state.identity_verifier = GoogleIdentityVerifier(config.google_client_id)
    app.state.clock = DatabaseClock()
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.allowed_hosts)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[config.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )
    app.add_middleware(SecurityHeadersMiddleware)

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
        return JSONResponse(status_code=500, content={"detail": "Unable to complete this request."})

    @app.get("/api/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/health/ready", tags=["health"])
    def readiness(db: Db) -> dict[str, str]:
        db.execute(text("SELECT 1 FROM users LIMIT 1"))
        return {"status": "ready"}

    app.include_router(auth.router, prefix="/api")
    app.include_router(profiles.router, prefix="/api")
    app.include_router(admin_domain.router, prefix="/api")
    app.include_router(attempts.router, prefix="/api")
    app.include_router(attempts.admin_router, prefix="/api")
    return app


app = create_app()
