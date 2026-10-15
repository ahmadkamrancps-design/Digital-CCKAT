"""Trusted operator command; deletes expired sessions/buckets, never answers or histories."""

import argparse

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import load_settings
from app.core.clock import DatabaseClock
from app.db.session import create_db_engine, create_session_factory
from app.models import AuthSession, LoginThrottle


def prune_expired_auth(db: Session, batch_size: int = 1000) -> tuple[int, int]:
    if not 1 <= batch_size <= 10000:
        raise ValueError("Batch size must be between 1 and 10000")
    now = DatabaseClock().now(db)
    session_ids = list(
        db.scalars(
            select(AuthSession.id)
            .where(AuthSession.expires_at <= now)
            .order_by(AuthSession.id)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
    )
    bucket_keys = list(
        db.scalars(
            select(LoginThrottle.key)
            .where(LoginThrottle.expires_at <= now)
            .order_by(LoginThrottle.key)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
    )
    if session_ids:
        db.execute(delete(AuthSession).where(AuthSession.id.in_(session_ids)))
    if bucket_keys:
        db.execute(delete(LoginThrottle).where(LoginThrottle.key.in_(bucket_keys)))
    db.commit()
    return len(session_ids), len(bucket_keys)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove a bounded batch of expired authentication data"
    )
    parser.add_argument(
        "--batch-size", type=int, default=1000, choices=range(1, 10001), metavar="1..10000"
    )
    args = parser.parse_args()
    engine = create_db_engine(load_settings())
    try:
        with create_session_factory(engine)() as db:
            sessions, buckets = prune_expired_auth(db, args.batch_size)
        print(f"Removed expired sessions: {sessions}; expired login buckets: {buckets}.")
    except SQLAlchemyError:
        parser.exit(
            2, "Authentication cleanup failed. Check database configuration and migrations.\n"
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
