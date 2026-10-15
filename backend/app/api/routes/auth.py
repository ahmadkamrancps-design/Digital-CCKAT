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
from app.models import AuthSession
from app.schemas.auth import CandidateLoginRequest, GoogleLoginRequest, MeResponse
from app.services.auth_service import login, profile
from app.services.candidate_login_service import candidate_login
from app.services.google_identity import (
    IdentityProviderUnavailable,
    IdentityVerifier,
    InvalidGoogleCredential,
)

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
    context, raw_token = candidate_login(
        db, body, settings, request.client.host if request.client else "unknown"
    )
    set_session_cookie(response, raw_token, settings)
    return profile(context)


@router.post("/google", response_model=MeResponse, dependencies=[Depends(require_origin)])
def google_login(
    body: GoogleLoginRequest,
    response: Response,
    db: Db,
    settings: Config,
    verifier: Annotated[IdentityVerifier, Depends(get_identity_verifier)],
) -> MeResponse:
    try:
        identity = verifier.verify(body.credential)
    except InvalidGoogleCredential as exc:
        raise HTTPException(401, "Google sign-in could not be verified. Please try again.") from exc
    except IdentityProviderUnavailable as exc:
        raise HTTPException(
            503, "Sign-in is temporarily unavailable. Please try again later."
        ) from exc
    context, raw_token = login(db, identity, settings)
    set_session_cookie(response, raw_token, settings)
    return profile(context)


@router.post(
    "/logout",
    status_code=204,
    dependencies=[Depends(require_origin), Depends(require_csrf)],
)
def logout(context: CurrentAuth, db: Db, settings: Config) -> Response:
    db.execute(delete(AuthSession).where(AuthSession.id == context.session.id))
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
