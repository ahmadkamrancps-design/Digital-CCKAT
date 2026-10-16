"""Container/monitoring command; emits no database configuration or raw errors."""

import argparse
from urllib.error import URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.config import load_settings
from app.db.session import create_db_engine, create_session_factory
from app.services.operations_service import check_worker


def main() -> None:
    parser = argparse.ArgumentParser(description="CCK internal operational probe")
    parser.add_argument("kind", choices=["readiness", "worker"])
    args = parser.parse_args()
    settings = load_settings()
    engine = create_db_engine(settings)
    try:
        if args.kind == "worker":
            with create_session_factory(engine)() as db:
                check_worker(db, settings.expiry_worker_stale_seconds)
        else:
            request = Request(
                "http://127.0.0.1:8000/api/health/ready",
                headers={"Host": settings.allowed_hosts[0]},
            )
            with urlopen(request, timeout=6) as response:
                if response.status != 200:
                    raise RuntimeError("API is not ready")
    except (HTTPException, SQLAlchemyError, URLError, TimeoutError, RuntimeError):
        parser.exit(1, "Service is not ready.\n")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
