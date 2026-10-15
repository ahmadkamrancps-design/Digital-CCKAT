"""Match trusted admissions records. This endpoint never registers a candidate."""

import logging
import math
import secrets
import unicodedata
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import case, delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.clock import DatabaseClock
from app.core.security import token_hash
from app.models import Candidate, CandidateStatus, LoginThrottle, Role, User
from app.schemas.auth import CandidateLoginRequest
from app.services.auth_service import AuthContext, as_utc, issue_session

logger = logging.getLogger(__name__)
INVALID_DETAILS = "Unable to sign in. Check your admissions details or contact admissions."


def normalize_name(value: str) -> str:
    # No fuzzy matching, transliteration, punctuation removal, or ignored name parts.
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def throttle(db: Session, roll_number: str, client_ip: str, settings: Settings) -> None:
    now = DatabaseClock().now(db)
    expiry = now + timedelta(minutes=15)
    # Atomic upserts share limits between workers and survive application restarts.
    # Raw rolls, IP addresses, names, and answers are never stored in these buckets.
    buckets = [
        (token_hash("ip:" + client_ip), settings.candidate_login_ip_limit),
        (token_hash("roll:" + roll_number), settings.candidate_login_roll_limit),
    ]
    retry_after = 0
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    for key, limit in sorted(buckets):
        statement = insert(LoginThrottle).values(key=key, attempts=1, expires_at=expiry)
        expired = LoginThrottle.expires_at <= now
        reservation = statement.on_conflict_do_update(
            index_elements=[LoginThrottle.key],
            set_={
                "attempts": case((expired, 1), else_=LoginThrottle.attempts + 1),
                "expires_at": case((expired, expiry), else_=LoginThrottle.expires_at),
            },
        ).returning(LoginThrottle.attempts, LoginThrottle.expires_at)
        attempts, expires_at = db.execute(reservation).one()
        if attempts > limit:
            retry_after = max(retry_after, math.ceil((as_utc(expires_at) - now).total_seconds()))
    # Clean a bounded batch only after reserving both keys. Skip other workers'
    # locks so expiry cleanup cannot deadlock against an in-flight reservation.
    expired_keys = list(
        db.scalars(
            select(LoginThrottle.key)
            .where(LoginThrottle.expires_at <= now)
            .limit(100)
            .with_for_update(skip_locked=True)
        )
    )
    if expired_keys:
        db.execute(delete(LoginThrottle).where(LoginThrottle.key.in_(expired_keys)))
    # Keep the reservation even when credential checks below reject the request.
    db.commit()
    if retry_after:
        raise HTTPException(
            429,
            "Too many sign-in attempts. Please wait before trying again.",
            headers={"Retry-After": str(max(1, retry_after))},
        )


def candidate_login(
    db: Session, body: CandidateLoginRequest, settings: Settings, client_ip: str
) -> tuple[AuthContext, str]:
    roll = body.roll_number.strip().lower()
    throttle(db, roll, client_ip, settings)
    initial = db.scalar(
        select(Candidate).where(func.lower(func.btrim(Candidate.roll_number)) == roll)
    )
    # Lock user then candidate, matching admin edits and session rotation order.
    user = (
        db.scalar(select(User).where(User.id == initial.user_id).with_for_update())
        if initial
        else None
    )
    candidate = (
        db.scalar(
            select(Candidate)
            .where(Candidate.id == initial.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if initial
        else None
    )
    # Always compare both names, including for unknown/ineligible records.
    name_matches = secrets.compare_digest(
        normalize_name(body.full_name).encode(),
        normalize_name(candidate.full_name if candidate else "").encode(),
    )
    father_matches = secrets.compare_digest(
        normalize_name(body.father_name).encode(),
        normalize_name((candidate.father_name or "") if candidate else "").encode(),
    )
    if (
        user is None
        or candidate is None
        or not user.is_active
        or user.role != Role.CANDIDATE
        or candidate.status != CandidateStatus.APPROVED
        or candidate.roll_number.strip().lower() != roll
        or not candidate.father_name
        or not name_matches
        or not father_matches
    ):
        logger.info("LOGIN_FAILURE method=admissions reason=invalid_or_ineligible")
        raise HTTPException(401, INVALID_DETAILS)
    return issue_session(db, user, candidate, settings)
