"""Railway entry point: existing API plus the built React app on one HTTPS origin.

Railway terminates TLS. Credentials remain environment secrets; no local sandbox
routes, sample admissions records or question keys are part of the static build.
"""

import argparse
import os
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import Settings

ROOT = Path(__file__).resolve().parents[1]
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self' https://accounts.google.com/gsi/client; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com "
    "https://accounts.google.com/gsi/style; font-src 'self' https://fonts.gstatic.com; "
    "connect-src 'self' https://accounts.google.com/gsi/; "
    "frame-src https://accounts.google.com/gsi/; "
    "img-src 'self' data: https://lh3.googleusercontent.com; "
    "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
)
SPA_ROUTES = {
    "",
    "login",
    "dashboard",
    "exam",
    "submission",
    "instructions",
    "system-check",
    "profile",
    "help",
    "proctor",
    "grading",
    "results",
    "admin",
    "admin/candidates",
    "admin/subjects",
    "admin/questions",
    "admin/exams",
    "admin/exams/new",
    "admin/actions",
}


class WebSecurityHeaders:
    """Apply the full browser policy normally supplied by the Docker Nginx gateway."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                values = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != b"content-security-policy"
                ]
                values.extend(
                    [
                        (b"content-security-policy", CONTENT_SECURITY_POLICY.encode()),
                        (b"cross-origin-opener-policy", b"same-origin-allow-popups"),
                        (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                    ]
                )
                message["headers"] = values
            await send(message)

        await self.app(scope, receive, headers)


def normalize_database_url(value: str) -> str:
    """Preserve escaped passwords/options while selecting our installed SQLAlchemy driver."""
    try:
        url = make_url(value)
        if url.drivername not in {"postgres", "postgresql", "postgresql+psycopg"}:
            raise ValueError
        return url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)
    except (ArgumentError, ValueError):
        raise ValueError("Invalid PostgreSQL configuration.") from None


def configure_environment(migration: bool = False) -> None:
    key = "CCK_MIGRATION_DATABASE_URL" if migration else "DATABASE_URL"
    value = os.environ.get(key)
    if not value or os.environ.get("DATABASE_URL_FILE"):
        raise ValueError("Supply the required Railway database variable; omit DATABASE_URL_FILE.")
    os.environ["DATABASE_URL"] = normalize_database_url(value)
    # Fail closed: never silently run a public deployment in development mode.
    if os.environ.get("ENVIRONMENT") != "production":
        raise ValueError("Railway entry point requires ENVIRONMENT=production.")
    Settings(_env_file=None)
    # app.migrate/app.cli/worker only need their own database URL after this selection.
    os.environ.pop("CCK_MIGRATION_DATABASE_URL", None)


def create_web_app(settings: Settings | None = None, directory: Path | None = None) -> FastAPI:
    from app.main import create_app

    root = (directory or ROOT / "static").resolve()
    if not (root / "index.html").is_file() or not (root / "assets").is_dir():
        raise RuntimeError("Built frontend is missing. Use Dockerfile.railway.")
    app = create_app(settings)
    app.add_middleware(WebSecurityHeaders)
    # Only this directory is public. Do not mount the repository or backend source.
    app.mount("/assets", StaticFiles(directory=root / "assets"), name="frontend-assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> FileResponse:
        parts = path.rstrip("/").split("/")
        exam_detail = len(parts) == 3 and parts[:2] == ["admin", "exams"]
        if path.rstrip("/") not in SPA_ROUTES and not exam_detail:
            # Unknown APIs, dotfiles, docs and development previews never become SPA responses.
            raise HTTPException(404, "Not found.")
        return FileResponse(root / "index.html")

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the CCK Railway services")
    parser.add_argument("service", choices=["web", "worker", "migrate", "cli", "maintenance"])
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        configure_environment(migration=args.service == "migrate")
    except (ValueError, RuntimeError):
        parser.exit(1, "Invalid Railway configuration. Check the service's private variables.\n")
    if args.service == "web":
        if args.arguments:
            parser.error("Web service takes no extra arguments.")
        import uvicorn

        try:
            port = int(os.environ.get("PORT", "8000"))
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            parser.exit(1, "PORT must be between 1 and 65535.\n")
        # Forwarded identity headers remain untrusted. See the deployment guide's
        # shared-ingress throttling limitation; never use forwarded-allow-ips=*.
        uvicorn.run(
            create_web_app(),
            host="0.0.0.0",
            port=port,
            proxy_headers=False,
            access_log=False,
            server_header=False,
        )
    else:
        modules = {
            "worker": "app.expiry_worker",
            "migrate": "app.migrate",
            "cli": "app.cli",
            "maintenance": "app.auth_maintenance",
        }
        os.execv(sys.executable, [sys.executable, "-m", modules[args.service], *args.arguments])


if __name__ == "__main__":
    main()
