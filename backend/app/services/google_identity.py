from dataclasses import dataclass
from functools import partial
from threading import Lock
from typing import Protocol

import requests
from cachecontrol import CacheControl
from google.auth.exceptions import GoogleAuthError, TransportError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token


class InvalidGoogleCredential(Exception):
    pass


class IdentityProviderUnavailable(Exception):
    pass


@dataclass(frozen=True)
class GoogleIdentity:
    subject: str
    email: str
    email_authoritative: bool


class IdentityVerifier(Protocol):
    def verify(self, credential: str) -> GoogleIdentity: ...


class GoogleIdentityVerifier:
    def __init__(self, client_id: str) -> None:
        self.client_id = client_id
        # Google's public certificate responses carry cache lifetimes. CacheControl
        # honors them; tokens/claims are never cached. Serialize this shared Session.
        self._transport = CacheControl(requests.Session())
        self._request = GoogleRequest(session=self._transport)
        self._lock = Lock()

    def close(self) -> None:
        self._transport.close()

    def verify(self, credential: str) -> GoogleIdentity:
        if not self.client_id:
            raise IdentityProviderUnavailable
        try:
            # google-auth verifies signature, audience, issuer, and token time validity.
            # google-auth has no type annotations at this external library boundary.
            with self._lock:
                claims: dict[str, object] = id_token.verify_oauth2_token(  # type: ignore[no-untyped-call]
                    credential,
                    partial(self._request, timeout=5),
                    audience=self.client_id,
                )
        except TransportError as exc:
            raise IdentityProviderUnavailable from exc
        except (ValueError, GoogleAuthError) as exc:
            raise InvalidGoogleCredential from exc

        subject = claims.get("sub")
        email = claims.get("email")
        if (
            claims.get("email_verified") is not True
            or not isinstance(subject, str)
            or not subject
            or len(subject) > 255
            or not isinstance(email, str)
            or len(email) > 254
            or "@" not in email
        ):
            raise InvalidGoogleCredential
        email = email.strip().lower()
        # Third-party email ownership is not guaranteed by Google. Require an
        # independently approved sub mapping for those accounts' first login.
        authoritative = email.endswith("@gmail.com") or bool(claims.get("hd"))
        return GoogleIdentity(subject, email, authoritative)
