"""Bounded Argon2id work; passwords are never trimmed, logged, or stored in plaintext."""

import re
import secrets
from threading import BoundedSemaphore

from cryptography.exceptions import InvalidKey
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from fastapi import HTTPException

_workers = BoundedSemaphore(2)
_encoding = re.compile(r"\$argon2id\$v=19\$m=65536,t=3,p=1\$[A-Za-z0-9+/]{22}\$[A-Za-z0-9+/]{43}")


def validate_new_password(password: str) -> None:
    if (
        not 15 <= len(password) <= 128
        or len(password.encode("utf-8")) > 512
        or not password.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in password)
    ):
        raise ValueError("Use 15–128 characters without control characters.")


def hash_password(password: str) -> str:
    validate_new_password(password)
    if not _workers.acquire(blocking=False):
        raise HTTPException(503, "Sign-in is busy. Please try again shortly.")
    try:
        return Argon2id(
            salt=secrets.token_bytes(16), length=32, iterations=3, lanes=1, memory_cost=65536
        ).derive_phc_encoded(password.encode("utf-8"))
    finally:
        _workers.release()


_dummy_hash = hash_password(secrets.token_urlsafe(32))


def verify_password(password: str, stored_hash: str | None) -> bool:
    # Unknown users and absent/malformed hashes incur the same KDF work as a real user.
    valid_encoding = stored_hash is not None and _encoding.fullmatch(stored_hash) is not None
    encoded = stored_hash if valid_encoding else _dummy_hash
    assert encoded is not None
    if not _workers.acquire(blocking=False):
        raise HTTPException(503, "Sign-in is busy. Please try again shortly.")
    try:
        Argon2id.verify_phc_encoded(password.encode("utf-8"), encoded)
        return valid_encoding
    except (InvalidKey, ValueError):
        return False
    finally:
        _workers.release()
