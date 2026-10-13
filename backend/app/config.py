from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://cck:cck_local_only@localhost:5432/cck_digital_test"
    google_client_id: str = ""
    frontend_origin: str = "http://localhost:5173"
    allowed_hosts: list[str] = ["localhost", "127.0.0.1"]
    session_cookie_name: str = Field(default="cck_session", pattern=r"^[A-Za-z0-9_-]+$")
    session_cookie_secure: bool = False
    session_ttl_seconds: int = Field(default=28800, ge=300, le=86400)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    @model_validator(mode="after")
    def validate_configuration(self) -> "Settings":
        if make_url(self.database_url).drivername != "postgresql+psycopg":
            raise ValueError("DATABASE_URL must use postgresql+psycopg")
        origin = urlsplit(self.frontend_origin)
        if (
            origin.scheme not in {"http", "https"}
            or not origin.hostname
            or origin.path
            or origin.query
            or origin.fragment
            or origin.username
            or origin.password
        ):
            raise ValueError("FRONTEND_ORIGIN must be an exact HTTP(S) origin without a path")
        if not self.allowed_hosts or "*" in self.allowed_hosts:
            raise ValueError("ALLOWED_HOSTS must contain explicit hostnames")
        if self.google_client_id and not self.google_client_id.endswith(
            ".apps.googleusercontent.com"
        ):
            raise ValueError("GOOGLE_CLIENT_ID must be a Google OAuth web client ID")
        if self.environment == "production":
            if not self.google_client_id or not self.session_cookie_secure:
                raise ValueError("Production requires Google configuration and secure cookies")
            if origin.scheme != "https":
                raise ValueError("Production FRONTEND_ORIGIN must use HTTPS")
            if make_url(self.database_url).password in {None, "", "cck_local_only"}:
                raise ValueError("Production requires separate database credentials")
        return self


def load_settings() -> Settings:
    try:
        return Settings()
    except (ValidationError, ValueError, ArgumentError):
        # Startup errors must not echo the settings input, which contains DB credentials.
        raise RuntimeError("Invalid configuration. Check environment variables and .env.") from None
