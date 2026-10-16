"""Run as the migration owner before starting runtime services."""

from pathlib import Path

from alembic.config import Config
from sqlalchemy.exc import SQLAlchemyError

from alembic import command
from app.config import load_settings
from app.db.session import create_db_engine


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    command.upgrade(Config(str(root / "alembic.ini")), "head")
    engine = create_db_engine(load_settings())
    try:
        with engine.begin() as connection:
            quote = connection.dialect.identifier_preparer.quote
            schema = connection.exec_driver_sql("SELECT current_schema()").scalar_one()
            grants = (root / "ops/grant-runtime.psql").read_text()
            grants = grants.replace(':"schema_name"', quote(schema)).replace(
                ':"runtime_role"', quote("cck_runtime")
            )
            connection.exec_driver_sql(grants)
    except SQLAlchemyError:
        raise SystemExit("Runtime grants failed. Review migration-owner configuration.") from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
