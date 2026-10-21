"""Read-only verification for isolated synthetic rehearsals, never public endpoints."""

import argparse
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from sqlalchemy import Engine, create_engine, inspect, text

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


@dataclass(frozen=True)
class _TableSnapshot:
    columns: tuple[tuple[str, str, bool], ...]
    primary_key: tuple[str, ...]
    count: int
    content_digest: bytes = field(repr=False)


def _restore_snapshot(engine: Engine) -> dict[str, _TableSnapshot]:
    tables = {}
    with (
        engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection,
        connection.begin(),
    ):
        connection.execute(text("SET TRANSACTION READ ONLY"))
        connection.execute(text("SET LOCAL TIME ZONE 'UTC'"))
        connection.execute(text("SET LOCAL DateStyle = 'ISO, YMD'"))
        reflection = inspect(connection)
        quote = engine.dialect.identifier_preparer.quote_identifier
        for name in sorted(reflection.get_table_names(schema="public")):
            columns = tuple(
                (column["name"], str(column["type"]), bool(column["nullable"]))
                for column in reflection.get_columns(name, schema="public")
            )
            primary_key = tuple(
                reflection.get_pk_constraint(name, schema="public")["constrained_columns"]
            )
            if not primary_key:
                raise ValueError("Rehearsal restore verification requires primary keys.")
            ordering = ", ".join(f"row_value.{quote(column)}" for column in primary_key)
            null_checks = ", ".join(f"row_value.{quote(column[0])} IS NULL" for column in columns)
            query = text(
                f"SELECT to_jsonb(row_value)::text, ARRAY[{null_checks}] "
                f"FROM {quote('public')}.{quote(name)} "
                f"AS row_value ORDER BY {ordering}"
            )
            digest = hashlib.sha256()
            count = 0
            # Bound client memory even for full-size rehearsal answer/audit tables.
            with connection.execute(query, execution_options={"yield_per": 500}) as rows:
                for row in rows:
                    value = row[0].encode("utf-8")
                    digest.update(len(value).to_bytes(8, "big"))
                    digest.update(value)
                    # JSON conversion alone conflates SQL NULL and JSON null.
                    nulls = bytes(row[1])
                    digest.update(len(nulls).to_bytes(4, "big"))
                    digest.update(nulls)
                    count += 1
            tables[name] = _TableSnapshot(columns, primary_key, count, digest.digest())
    return tables


def verify_restored_content(source: Engine, target: Engine) -> dict[str, int]:
    """Compare quiesced synthetic databases; never log or return content/digests."""
    if source.dialect.name != "postgresql" or target.dialect.name != "postgresql":
        raise ValueError("PostgreSQL is required for rehearsal restore verification.")
    require_rehearsal(source)
    with target.connect() as connection:
        name = connection.scalar(text("SELECT current_database()"))
        if not isinstance(name, str) or not name.endswith("_restore"):
            raise ValueError("A dedicated restore database is required.")
    before, after = _restore_snapshot(source), _restore_snapshot(target)
    if "alembic_version" not in before or before.keys() != after.keys():
        raise ValueError("Restored table set differs from the migrated source.")
    for name, expected in before.items():
        if expected != after[name]:
            raise ValueError(f"Restored content or columns differ in table {name}.")
    return {name: table.count for name, table in before.items()}


def verify_restore(engine: Engine) -> dict[str, int]:
    require_rehearsal(engine)
    assert engine.url.database is not None
    target = create_engine(
        engine.url.set(database=engine.url.database + "_restore"), hide_parameters=True
    )
    try:
        return verify_restored_content(engine, target)
    finally:
        target.dispose()


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
            print(
                json.dumps(
                    {"restored_counts": verify_restore(engine), "restored_content": "verified"}
                )
            )
        print(f"PASS: rehearsal {args.kind}")
    except Exception as error:
        parser.exit(1, f"Rehearsal verification failed: {type(error).__name__}.\n")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
