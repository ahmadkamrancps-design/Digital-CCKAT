"""Exercise real Google verifier cryptography, substituting only certificate retrieval."""

import json
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from google.auth import jwt
from google.auth.crypt import RSASigner

from app.core.security import utc_now
from app.services.google_identity import GoogleIdentityVerifier, InvalidGoogleCredential

CLIENT_ID = "test-client.apps.googleusercontent.com"


@pytest.fixture(scope="module")
def signing_material() -> tuple[RSASigner, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "CCK test certificate")])
    now = utc_now()
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    pem_key = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return RSASigner.from_string(pem_key, key_id="cck-test-key"), certificate.public_bytes(
        serialization.Encoding.PEM
    ).decode()


@pytest.mark.parametrize("invalid", [None, "audience", "issuer", "expiry", "signature"])
def test_real_signature_audience_issuer_and_expiry(
    signing_material: tuple[RSASigner, str],
    invalid: str | None,
) -> None:
    signer, certificate = signing_material
    now = int(utc_now().timestamp())
    claims = {
        "sub": "stable-sub",
        "email": "candidate@gmail.com",
        "email_verified": True,
        "aud": CLIENT_ID,
        "iss": "https://accounts.google.com",
        "iat": now - 10,
        "exp": now + 300,
    }
    if invalid == "audience":
        claims["aud"] = "other-client.apps.googleusercontent.com"
    elif invalid == "issuer":
        claims["iss"] = "https://evil.example"
    elif invalid == "expiry":
        claims["iat"], claims["exp"] = now - 1000, now - 100
    credential = jwt.encode(signer, claims).decode()
    if invalid == "signature":
        parts = credential.split(".")
        parts[2] = ("A" if parts[2][0] != "A" else "B") + parts[2][1:]
        credential = ".".join(parts)

    def certificates(url: str, **kwargs: object) -> SimpleNamespace:
        assert url.startswith("https://www.googleapis.com/")
        assert kwargs["timeout"] == 5
        return SimpleNamespace(status=200, data=json.dumps({"cck-test-key": certificate}).encode())

    with patch("app.services.google_identity.GoogleRequest", return_value=certificates):
        if invalid:
            with pytest.raises(InvalidGoogleCredential):
                GoogleIdentityVerifier(CLIENT_ID).verify(credential)
        else:
            assert GoogleIdentityVerifier(CLIENT_ID).verify(credential).subject == "stable-sub"


def test_public_certificates_are_cached_but_credentials_are_verified_each_time(
    signing_material: tuple[RSASigner, str],
) -> None:
    signer, certificate = signing_material
    requests = 0

    class Certificates(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            nonlocal requests
            requests += 1
            body = json.dumps({"cck-test-key": certificate}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "public, max-age=3600")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Certificates)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    verifier = GoogleIdentityVerifier(CLIENT_ID)
    now = int(utc_now().timestamp())
    try:
        with patch(
            "google.oauth2.id_token._GOOGLE_OAUTH2_CERTS_URL",
            f"http://127.0.0.1:{server.server_port}/certs",
        ):
            for subject in ["first-identity", "second-identity"]:
                claims = {
                    "sub": subject,
                    "email": "test@gmail.com",
                    "email_verified": True,
                    "aud": CLIENT_ID,
                    "iss": "https://accounts.google.com",
                    "iat": now - 10,
                    "exp": now + 300,
                }
                assert verifier.verify(jwt.encode(signer, claims).decode()).subject == subject
            claims["exp"] = now - 1
            with pytest.raises(InvalidGoogleCredential):
                verifier.verify(jwt.encode(signer, claims).decode())
            assert requests == 1
    finally:
        verifier.close()
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
