"""Run as a separate supervised process; multiple workers safely skip locked attempts."""

import argparse
import logging
import time

from sqlalchemy.exc import SQLAlchemyError

from app.config import load_settings
from app.core.clock import DatabaseClock
from app.db.session import create_db_engine, create_session_factory
from app.services.attempt_service import expire_due


def main() -> None:
    parser = argparse.ArgumentParser(description="Expire CCK subject/exam attempts")
    parser.add_argument("--once", action="store_true", help="Process one batch and exit")
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()
    if not 0.1 <= args.interval <= 60:
        parser.error("Interval must be between 0.1 and 60 seconds.")
    settings = load_settings()
    logging.basicConfig(level=settings.log_level, format="%(levelname)s %(name)s %(message)s")
    logger = logging.getLogger(__name__)
    engine = create_db_engine(settings)
    factory = create_session_factory(engine)
    try:
        while True:
            try:
                with factory() as db:
                    processed = expire_due(db, DatabaseClock())
                if processed:
                    logger.info("Expired due attempts count=%s", processed)
            except SQLAlchemyError as exc:
                logger.error("Expiry database operation failed error_type=%s", type(exc).__name__)
                if args.once:
                    raise SystemExit(1) from None
            if args.once:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
