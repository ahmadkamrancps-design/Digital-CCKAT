from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete

from app.api.dependencies import (
    Config,
    CurrentAuth,
    Db,
    get_identity_verifier,
    require_csrf,
    require_origin,
)
from app.core.security import token_hash
from app.models import AuthSession, SecurityEvent
from app.schemas.auth import (
    CandidateLoginRequest,
    GoogleLoginRequest,
    MeResponse,
    StaffLoginRequest,
)
from app.services.auth_service import login, profile
from app.services.candidate_login_service import candidate_login
from app.services.google_identity import (
    IdentityProviderUnavailable,
    IdentityVerifier,
    InvalidGoogleCredential,
)
from app.services.login_throttle_service import reserve_login
from app.services.staff_login_service import staff_login

router = APIRouter(prefix="/auth", tags=["authentication"])


def set_session_cookie(response: Response, raw_token: str, settings: Config) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/api",
    )


@router.post("/candidate", response_model=MeResponse, dependencies=[Depends(require_origin)])
def admissions_login(
    body: CandidateLoginRequest, request: Request, response: Response, db: Db, settings: Config
) -> MeResponse:
    try:
        context, raw_token = candidate_login(
            db, body, settings, request.client.host if request.client else "unknown"
        )
    except HTTPException as exc:
        if exc.status_code == 401:
            db.rollback()
            db.add(SecurityEvent(event_type="LOGIN_FAILURE", method="ADMISSIONS"))
            db.commit()
        raise
    set_session_cookie(response, raw_token, settings)
    return profile(context)


@router.post("/staff", response_model=MeResponse, dependencies=[Depends(require_origin)])
def password_login(
    body: StaffLoginRequest, request: Request, response: Response, db: Db, settings: Config
) -> MeResponse:
    try:
        context, raw_token = staff_login(
            db, body, settings, request.client.host if request.client else "unknown"
        )
    except HTTPException as exc:
        if exc.status_code == 401:
            db.rollback()
            db.add(SecurityEvent(event_type="LOGIN_FAILURE", method="PASSWORD"))
            db.commit()
        raise
    set_session_cookie(response, raw_token, settings)
    return profile(context)


@router.post("/google", response_model=MeResponse, dependencies=[Depends(require_origin)])
def google_login(
    body: GoogleLoginRequest,
    request: Request,
    response: Response,
    db: Db,
    settings: Config,
    verifier: Annotated[IdentityVerifier, Depends(get_identity_verifier)],
) -> MeResponse:
    if not settings.google_login_enabled:
        raise HTTPException(404, "Not found.")
    reserve_login(
        db,
        [
            (
                token_hash("google-ip:" + (request.client.host if request.client else "unknown")),
                settings.google_login_ip_limit,
            )
        ],
        "GOOGLE",
    )
    try:
        identity = verifier.verify(body.credential)
    except InvalidGoogleCredential as exc:
        db.add(SecurityEvent(event_type="LOGIN_FAILURE", method="GOOGLE"))
        db.commit()
        raise HTTPException(401, "Google sign-in could not be verified. Please try again.") from exc
    except IdentityProviderUnavailable as exc:
        raise HTTPException(
            503, "Sign-in is temporarily unavailable. Please try again later."
        ) from exc
    try:
        context, raw_token = login(db, identity, settings)
    except HTTPException as exc:
        if exc.status_code == 403:
            db.rollback()
            db.add(SecurityEvent(event_type="LOGIN_FAILURE", method="GOOGLE"))
            db.commit()
        raise
    set_session_cookie(response, raw_token, settings)
    return profile(context)


@router.post(
    "/logout",
    status_code=204,
    dependencies=[Depends(require_origin), Depends(require_csrf)],
)
def logout(context: CurrentAuth, db: Db, settings: Config) -> Response:
    db.execute(delete(AuthSession).where(AuthSession.id == context.session.id))
    db.add(SecurityEvent(user_id=context.user.id, event_type="LOGOUT", method="SESSION"))
    db.commit()
    response = Response(status_code=204)
    response.delete_cookie(
        settings.session_cookie_name,
        path="/api",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )
    return response
