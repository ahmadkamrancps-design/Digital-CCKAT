from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.passwords import hash_password, verify_password
from app.core.security import token_hash
from app.models import AuditEvent, AuthSession, Role, User
from app.schemas.auth import StaffLoginRequest
from app.services.auth_service import AuthContext, issue_session
from app.services.login_throttle_service import reserve_login

STAFF_ROLES = {Role.ADMIN, Role.PROCTOR, Role.EXAMINER}


def staff_login(
    db: Session, body: StaffLoginRequest, settings: Settings, client_ip: str
) -> tuple[AuthContext, str]:
    reserve_login(
        db,
        [
            (token_hash("staff-ip:" + client_ip), settings.staff_login_ip_limit),
            (token_hash("staff-email:" + str(body.email)), settings.staff_login_email_limit),
        ],
        "PASSWORD",
    )
    user = db.scalar(select(User).where(User.email == str(body.email)).with_for_update())
    eligible = user is not None and user.is_active and user.role in STAFF_ROLES
    if not verify_password(body.password, user.password_hash if eligible and user else None):
        raise HTTPException(401, "Unable to sign in. Check your email and password.")
    assert user is not None and eligible
    return issue_session(db, user, None, settings, method="PASSWORD")


def set_staff_password(db: Session, email: str, password: str) -> None:
    """Trusted operator only: never creates an account or changes its privileges."""
    user = db.scalar(select(User).where(User.email == email.strip().lower()).with_for_update())
    if user is None or not user.is_active or user.role not in STAFF_ROLES:
        raise ValueError("An active, approved staff account with this email is required.")
    user.password_hash = hash_password(password)
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.add(AuditEvent(user_id=user.id, entity_id=user.id, event_type="STAFF_PASSWORD_SET"))
    db.commit()
