"""Run as a separate supervised process; multiple workers safely skip locked attempts."""

import argparse
import logging
import time

from sqlalchemy.exc import SQLAlchemyError

from app.config import load_settings
from app.core.clock import DatabaseClock
from app.db.session import create_db_engine, create_session_factory
from app.services.attempt_service import expire_due
from app.services.operations_service import record_worker_success


def main() -> None:
    parser = argparse.ArgumentParser(description="Expire CCK subject/exam attempts")
    parser.add_argument("--once", action="store_true", help="Process one batch and exit")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()
    if not 0.1 <= args.interval <= 60:
        parser.error("Interval must be between 0.1 and 60 seconds.")
    if not 1 <= args.batch_size <= 1000:
        parser.error("Batch size must be between 1 and 1000.")
    settings = load_settings()
    logging.basicConfig(level=settings.log_level, format="%(levelname)s %(name)s %(message)s")
    logger = logging.getLogger(__name__)
    engine = create_db_engine(settings)
    factory = create_session_factory(engine)
    try:
        while True:
            processed = 0
            try:
                with factory() as db:
                    processed = expire_due(db, DatabaseClock(), args.batch_size)
                    record_worker_success(db, processed)
                if processed:
                    logger.info("Expired due attempts count=%s", processed)
            except SQLAlchemyError as exc:
                logger.error("Expiry database operation failed error_type=%s", type(exc).__name__)
                if args.once:
                    raise SystemExit(1) from None
            if args.once:
                break
            # Drain a full backlog without an extra pause between every 100 exams.
            # Small/empty batches keep the normal polling cadence.
            if processed < args.batch_size:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
