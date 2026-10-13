from unittest.mock import patch

import pytest
from google.auth.exceptions import TransportError

from app.services.google_identity import (
    GoogleIdentityVerifier,
    IdentityProviderUnavailable,
    InvalidGoogleCredential,
)

CLIENT_ID = "test-client.apps.googleusercontent.com"


@pytest.mark.parametrize(
    "email,hd,authoritative",
    [
        ("Test@gmail.com", None, True),
        ("Test@college.example", "college.example", True),
        ("Test@thirdparty.example", None, False),
    ],
)
def test_google_claim_validation_and_audience(
    email: str, hd: str | None, authoritative: bool
) -> None:
    claims = {"sub": "stable-sub", "email": email, "email_verified": True, "hd": hd}
    with patch(
        "app.services.google_identity.id_token.verify_oauth2_token", return_value=claims
    ) as verify:
        identity = GoogleIdentityVerifier(CLIENT_ID).verify("credential")
    assert identity.subject == "stable-sub"
    assert identity.email == email.lower()
    assert identity.email_authoritative == authoritative
    assert verify.call_args.kwargs["audience"] == CLIENT_ID


@pytest.mark.parametrize(
    "claims",
    [
        {"sub": "stable-sub", "email": "test@gmail.com", "email_verified": False},
        {"sub": "stable-sub", "email": "test@gmail.com", "email_verified": "true"},
        {"sub": "", "email": "test@gmail.com", "email_verified": True},
        {"sub": "stable-sub", "email_verified": True},
    ],
)
def test_incomplete_or_unverified_claims_denied(claims: dict[str, object]) -> None:
    with patch("app.services.google_identity.id_token.verify_oauth2_token", return_value=claims):
        with pytest.raises(InvalidGoogleCredential):
            GoogleIdentityVerifier(CLIENT_ID).verify("credential")


def test_google_library_verification_failure_denied() -> None:
    with patch("app.services.google_identity.id_token.verify_oauth2_token", side_effect=ValueError):
        with pytest.raises(InvalidGoogleCredential):
            GoogleIdentityVerifier(CLIENT_ID).verify("forged-or-expired")


def test_google_network_failure_reported_as_unavailable() -> None:
    with patch(
        "app.services.google_identity.id_token.verify_oauth2_token", side_effect=TransportError
    ):
        with pytest.raises(IdentityProviderUnavailable):
            GoogleIdentityVerifier(CLIENT_ID).verify("credential")


def test_google_configuration_required() -> None:
    with pytest.raises(IdentityProviderUnavailable):
        GoogleIdentityVerifier("").verify("credential")
