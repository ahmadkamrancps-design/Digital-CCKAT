import logging
from dataclasses import dataclass
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.clock import DatabaseClock
from app.core.security import as_utc as as_utc
from app.core.security import new_token, token_hash
from app.models import AuthSession, Candidate, CandidateStatus, Role, SecurityEvent, User
from app.schemas.auth import CandidateProfile, MeResponse, UserProfile
from app.services.google_identity import GoogleIdentity

logger = logging.getLogger(__name__)


@dataclass
class AuthContext:
    user: User
    candidate: Candidate | None
    session: AuthSession


def ensure_eligible(db: Session, user: User) -> Candidate | None:
    if not user.is_active:
        raise HTTPException(403, "This account is not authorized. Contact admissions.")
    if user.role != Role.CANDIDATE:
        return None
    candidate = db.scalar(select(Candidate).where(Candidate.user_id == user.id))
    if candidate is None or candidate.status != CandidateStatus.APPROVED:
        raise HTTPException(403, "This account is not authorized. Contact admissions.")
    return candidate


def login(db: Session, identity: GoogleIdentity, settings: Settings) -> tuple[AuthContext, str]:
    # Lock the user row to serialize initial identity binding and session rotation.
    user = db.scalar(select(User).where(User.google_subject == identity.subject).with_for_update())
    if user is None:
        user = db.scalar(select(User).where(User.email == identity.email).with_for_update())
        if user is None or user.google_subject is not None or not identity.email_authoritative:
            logger.info("LOGIN_FAILURE reason=not_authorized")
            raise HTTPException(403, "This account is not authorized. Contact admissions.")
    candidate = ensure_eligible(db, user)
    user.google_subject = identity.subject
    # The approved email/name remain administration-controlled. Never rebind by email.
    return issue_session(db, user, candidate, settings)


def issue_session(
    db: Session,
    user: User,
    candidate: Candidate | None,
    settings: Settings,
    *,
    method: str = "GOOGLE",
) -> tuple[AuthContext, str]:
    # Callers hold the user lock, serializing login with admissions record edits.
    raw_token = new_token()
    session = AuthSession(
        user_id=user.id,
        token_hash=token_hash(raw_token),
        csrf_token=new_token(),
        expires_at=DatabaseClock().now(db) + timedelta(seconds=settings.session_ttl_seconds),
    )
    try:
        db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
        db.add(session)
        db.add(SecurityEvent(user_id=user.id, event_type="LOGIN_SUCCESS", method=method))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            409, "Sign-in changed in another session. Please sign in again."
        ) from exc
    logger.info("LOGIN_SUCCESS user_id=%s role=%s", user.id, user.role.value)
    return AuthContext(user, candidate, session), raw_token


def authenticate(db: Session, raw_token: str | None) -> AuthContext:
    if not raw_token or len(raw_token) > 128:
        raise HTTPException(401, "Please sign in to continue.")
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash(raw_token)))
    if session is None or as_utc(session.expires_at) <= DatabaseClock().now(db):
        raise HTTPException(401, "Your session has ended. Please sign in again.")
    user = db.get(User, session.user_id)
    if user is None:
        raise HTTPException(401, "Please sign in to continue.")
    candidate = ensure_eligible(db, user)
    return AuthContext(user, candidate, session)


def profile(context: AuthContext) -> MeResponse:
    user, candidate, session = context.user, context.candidate, context.session
    return MeResponse(
        user=UserProfile(
            id=user.id, email=user.email, display_name=user.display_name, role=user.role
        ),
        candidate=CandidateProfile(
            id=candidate.id,
            roll_number=candidate.roll_number,
            full_name=candidate.full_name,
            status=candidate.status,
        )
        if candidate
        else None,
        csrf_token=session.csrf_token,
        session_expires_at=as_utc(session.expires_at),
    )
