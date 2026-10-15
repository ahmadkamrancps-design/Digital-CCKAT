"""Atomic, persistent sign-in limits; call before starting an authentication transaction."""

import math
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import case, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.clock import DatabaseClock
from app.models import LoginThrottle, SecurityEvent
from app.services.auth_service import as_utc


def reserve_login(db: Session, buckets: list[tuple[str, int]], method: str) -> None:
    now = DatabaseClock().now(db)
    expiry = now + timedelta(minutes=15)
    retry_after = 0
    first_denial = False
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    # Callers supply IP first, then account. Those key namespaces are disjoint:
    # every worker uses the same lock hierarchy. Reject a blocked IP before
    # reserving arbitrary new roll buckets, to bound attack-driven row growth.
    for key, limit in buckets:
        statement = insert(LoginThrottle).values(key=key, attempts=1, expires_at=expiry)
        expired = LoginThrottle.expires_at <= now
        reservation = statement.on_conflict_do_update(
            index_elements=[LoginThrottle.key],
            set_={
                # Saturate rather than allowing unbounded increments/overflow during an attack.
                "attempts": case(
                    (expired, 1),
                    (LoginThrottle.attempts > limit + 1, LoginThrottle.attempts),
                    else_=LoginThrottle.attempts + 1,
                ),
                "expires_at": case((expired, expiry), else_=LoginThrottle.expires_at),
            },
        ).returning(LoginThrottle.attempts, LoginThrottle.expires_at)
        attempts, expires_at = db.execute(reservation).one()
        if attempts > limit:
            retry_after = max(retry_after, math.ceil((as_utc(expires_at) - now).total_seconds()))
            first_denial |= attempts == limit + 1
            break
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
    if first_denial:
        db.add(SecurityEvent(event_type="LOGIN_THROTTLED", method=method))
    # Reservations must survive invalid credentials and HTTP retries.
    db.commit()
    if retry_after:
        raise HTTPException(
            429,
            "Too many sign-in attempts. Please wait before trying again.",
            headers={"Retry-After": str(max(1, retry_after))},
        )
