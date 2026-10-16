from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings


def create_db_engine(settings: Settings) -> Engine:
    url = make_url(settings.database_url)
    # Preserve search_path/SSL options used by isolated tests and managed databases.
    options = str(url.query.get("options", ""))
    options += f" -c statement_timeout={settings.database_statement_timeout_ms}"
    options += f" -c lock_timeout={settings.database_lock_timeout_ms}"
    return create_engine(
        url.update_query_dict({"options": options.strip()}),
        pool_pre_ping=True,
        hide_parameters=True,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout_seconds,
        connect_args={"connect_timeout": 5},
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
