"""Match trusted admissions records. This endpoint never registers a candidate."""

import logging
import secrets
import unicodedata

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.security import token_hash
from app.models import Candidate, CandidateStatus, Role, User
from app.schemas.auth import CandidateLoginRequest
from app.services.auth_service import AuthContext, issue_session
from app.services.login_throttle_service import reserve_login

logger = logging.getLogger(__name__)
INVALID_DETAILS = "Unable to sign in. Check your admissions details or contact admissions."


def normalize_name(value: str) -> str:
    # No fuzzy matching, transliteration, punctuation removal, or ignored name parts.
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def throttle(db: Session, roll_number: str, client_ip: str, settings: Settings) -> None:
    # Atomic upserts share limits between workers and survive application restarts.
    # Raw rolls, IP addresses, names, and answers are never stored in these buckets.
    buckets = [
        (token_hash("ip:" + client_ip), settings.candidate_login_ip_limit),
        (token_hash("roll:" + roll_number), settings.candidate_login_roll_limit),
    ]
    reserve_login(db, buckets, "ADMISSIONS")


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
    return issue_session(db, user, candidate, settings, method="ADMISSIONS")
