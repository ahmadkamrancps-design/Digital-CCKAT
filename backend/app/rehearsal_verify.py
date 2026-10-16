"""Read-only verification for isolated synthetic rehearsals, never public endpoints."""

import argparse
import json
import time
from pathlib import Path
from uuid import UUID

from sqlalchemy import Engine, create_engine, text

from app.config import load_settings
from app.db.session import create_db_engine


def require_rehearsal(engine: Engine) -> None:
    with engine.connect() as connection:
        name = connection.scalar(text("SELECT current_database()"))
        if not isinstance(name, str) or not name.endswith("_rehearsal"):
            raise ValueError("A dedicated rehearsal database is required.")


def verify_expiry(engine: Engine, manifest: Path) -> None:
    require_rehearsal(engine)
    data = json.loads(manifest.read_text())
    if data.get("kind") != "CCK_REHEARSAL_ONLY":
        raise ValueError("A synthetic manifest is required.")
    subject_id = UUID(data["expiry_subject_id"])
    until = time.monotonic() + 75
    while True:
        # No attempt service/API call: only the supervised worker can close this.
        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT status, submitted_at, expires_at FROM subject_attempts WHERE id=:id"),
                {"id": subject_id},
            ).one()
        if row.status == "EXPIRED":
            if row.submitted_at != row.expires_at:
                raise ValueError("Expiry must preserve the authoritative deadline.")
            return
        if row.status != "ACTIVE" or time.monotonic() > until:
            raise ValueError("Unattended subject was not expired by the worker.")
        time.sleep(0.5)


def verify_runtime(engine: Engine) -> None:
    require_rehearsal(engine)
    with engine.connect() as connection:
        forbidden = connection.scalar(
            text("""
            SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls
              OR has_schema_privilege(current_user, current_schema(), 'CREATE')
              OR has_table_privilege(current_user, 'audit_events', 'UPDATE,DELETE,TRUNCATE')
              OR has_table_privilege(current_user, 'grading_records', 'UPDATE,DELETE,TRUNCATE')
              OR has_table_privilege(current_user, 'alembic_version', 'INSERT,UPDATE,DELETE')
            FROM pg_roles WHERE rolname=current_user
        """)
        )
        if forbidden is not False:
            raise ValueError("Runtime privileges exceed the reviewed grants.")


def verify_restore(engine: Engine) -> dict[str, int]:
    require_rehearsal(engine)
    assert engine.url.database is not None
    target = create_engine(
        engine.url.set(database=engine.url.database + "_restore"), hide_parameters=True
    )
    counts = {}
    try:
        with engine.connect() as before, target.connect() as after:
            for table in [
                "users",
                "answers",
                "grading_records",
                "audit_events",
                "security_events",
                "session_events",
                "subject_attempts",
            ]:
                count = before.scalar(text(f"SELECT count(*) FROM {table}"))
                if count != after.scalar(text(f"SELECT count(*) FROM {table}")):
                    raise ValueError("Restored record count differs from source.")
                counts[table] = int(count or 0)
    finally:
        target.dispose()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify synthetic CCK rehearsal evidence")
    parser.add_argument("kind", choices=["expiry", "runtime", "restore"])
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    engine = create_db_engine(load_settings())
    try:
        if args.kind == "expiry":
            if args.manifest is None:
                parser.error("Expiry verification requires --manifest.")
            verify_expiry(engine, args.manifest)
        elif args.kind == "runtime":
            verify_runtime(engine)
        else:
            print(json.dumps({"restored_counts": verify_restore(engine)}))
        print(f"PASS: rehearsal {args.kind}")
    except Exception as error:
        parser.exit(1, f"Rehearsal verification failed: {type(error).__name__}.\n")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
