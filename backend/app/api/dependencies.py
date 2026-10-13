import secrets
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import Settings
from app.services.auth_service import AuthContext, authenticate
from app.services.google_identity import IdentityVerifier


def get_settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as db:
        yield db


Db = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]


def get_identity_verifier(request: Request) -> IdentityVerifier:
    return request.app.state.identity_verifier  # type: ignore[no-any-return]


def require_origin(request: Request, settings: Config) -> None:
    if request.headers.get("origin") != settings.frontend_origin:
        raise HTTPException(403, "This request is not allowed.")


def get_auth(request: Request, db: Db, settings: Config) -> AuthContext:
    return authenticate(db, request.cookies.get(settings.session_cookie_name))


CurrentAuth = Annotated[AuthContext, Depends(get_auth)]


def require_csrf(request: Request, context: CurrentAuth) -> None:
    submitted = request.headers.get("x-csrf-token", "")
    if not secrets.compare_digest(submitted, context.session.csrf_token):
        raise HTTPException(403, "This request is not allowed. Refresh and try again.")
