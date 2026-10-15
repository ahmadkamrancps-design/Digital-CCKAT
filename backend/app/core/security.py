import hashlib
import secrets
from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    # SQLite unit tests lose timezone metadata; PostgreSQL uses TIMESTAMPTZ.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)
