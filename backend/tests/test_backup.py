import hashlib
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from alembic import command
from app.backup import BackupError, backup, database_environment, latest_backup_age, restore
from app.core.clock import DatabaseClock
from app.models import AuditEvent, Candidate, User
from app.rehearsal_seed import seed
from app.rehearsal_verify import verify_restored_content
from app.schemas.attempt import AnswerWrite
from app.services import attempt_service


def test_database_credentials_stay_in_private_pgpass_and_restore_names_are_bounded(
    tmp_path: Path,
) -> None:
    secret = tmp_path / "url"
    secret.write_text(
        "postgresql+psycopg://owner:PRIVATE%3Apass%5Cword@localhost:5432/cck_restore?sslmode=require"
    )
    with database_environment(secret) as env:
        assert "PGPASSWORD" not in env
        assert env["PGSSLMODE"] == "require"
        path = Path(env["PGPASSFILE"])
        assert path.stat().st_mode & 0o777 == 0o600
        assert "PRIVATE\\:pass\\\\word" in path.read_text()
    assert not path.exists()
    secret.write_text("invalid PRIVATE secret")
    with pytest.raises(BackupError) as failure:
        with database_environment(secret):
            pass
    assert "PRIVATE" not in str(failure.value)


def test_no_backup_is_not_reported_healthy(tmp_path: Path) -> None:
    with pytest.raises(BackupError, match="No completed backup"):
        latest_backup_age(tmp_path)


def test_restore_verification_rejects_non_postgresql_databases() -> None:
    engine = create_engine("sqlite://")
    try:
        with pytest.raises(ValueError, match="PostgreSQL is required"):
            verify_restored_content(engine, engine)
    finally:
        engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="Real encrypted PostgreSQL recovery"
)
def test_encrypted_backup_tamper_rejection_and_fresh_database_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not shutil.which("openssl"):
        pytest.skip("OpenSSL is required for the backup roundtrip")
    root_url = make_url(os.environ["TEST_DATABASE_URL"]).difference_update_query(["options"])
    admin = create_engine(root_url, isolation_level="AUTOCOMMIT", hide_parameters=True)
    prefix = "cck_backup_" + uuid.uuid4().hex[:12]
    source_name, restored_name = prefix + "_rehearsal", prefix + "_restore"
    source_url, restored_url = (
        root_url.set(database=source_name),
        root_url.set(database=restored_name),
    )
    engines = []
    try:
        with admin.connect() as connection:
            if not connection.scalar(
                text("SELECT rolsuper OR rolcreatedb FROM pg_roles WHERE rolname=current_user")
            ):
                pytest.skip("Disposable test role cannot create a recovery database")
            connection.execute(text(f'CREATE DATABASE "{source_name}"'))
            connection.execute(text(f'CREATE DATABASE "{restored_name}"'))
        monkeypatch.setenv("DATABASE_URL", source_url.render_as_string(hide_password=False))
        command.upgrade(Config("alembic.ini"), "head")
        source = create_engine(source_url, hide_parameters=True)
        target = create_engine(
            restored_url,
            hide_parameters=True,
            connect_args={"options": "-ctimezone=Asia/Karachi"},
        )
        engines += [source, target]
        with Session(source, expire_on_commit=False) as db:
            seed(db, 3, 60, tmp_path / "private-manifest.json")
            manifest = json.loads((tmp_path / "private-manifest.json").read_text())
            candidate = db.scalar(
                select(Candidate).where(Candidate.roll_number == "REHEARSAL-00000")
            )
            assert candidate is not None
            clock = DatabaseClock()
            attempt = attempt_service.begin_exam(
                db, uuid.UUID(manifest["exam_id"]), candidate.id, clock
            )
            subject_id = attempt.subjects[0].id
            attempt_service.begin_subject(db, attempt.id, subject_id, candidate.id, clock)
            paper = attempt_service.subject_paper(db, attempt.id, subject_id, candidate.id, clock)
            for question, selected, short in [
                (paper.questions[0], paper.questions[0].options[0].id, None),
                (paper.questions[1], None, "light پاکستان"),
            ]:
                attempt_service.save_answer(
                    db,
                    attempt.id,
                    subject_id,
                    question.exam_question_id,
                    candidate.id,
                    AnswerWrite(
                        expected_revision=0,
                        selected_option_id=selected,
                        short_answer_text=short,
                        is_marked_for_review=True,
                    ),
                    clock,
                )
            attempt_service.submit_subject(db, attempt.id, subject_id, candidate.id, clock)
            db.add(
                AuditEvent(
                    user_id=uuid.UUID(manifest["admin"]["profile"]["user"]["id"]),
                    event_type="REHEARSAL_RECOVERY_FIXTURE",
                    entity_id=attempt.id,
                )
            )
            db.commit()
        with source.begin() as connection:
            # Exercise JSON key-order normalization and SQL NULL versus JSON null
            # without introducing any application table or production migration.
            connection.execute(
                text("CREATE TABLE recovery_json_fixture (id integer PRIMARY KEY, payload json)")
            )
            connection.execute(
                text("""INSERT INTO recovery_json_fixture VALUES
                     (1, NULL), (2, '{"b": 2, "a": 1}'::json)""")
            )
        certificate, key = tmp_path / "cert.pem", tmp_path / "key.pem"
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-subj",
                "/CN=CCK backup fixture",
                "-keyout",
                str(key),
                "-out",
                str(certificate),
            ],
            check=True,
            capture_output=True,
        )
        source_secret, target_secret = tmp_path / "source-url", tmp_path / "target-url"
        source_secret.write_text(source_url.render_as_string(hide_password=False))
        target_secret.write_text(restored_url.render_as_string(hide_password=False))
        archive = backup(source_secret, certificate, tmp_path / "archives")
        assert archive.stat().st_mode & 0o777 == 0o600
        assert b"REHEARSAL Candidate" not in archive.read_bytes()
        assert latest_backup_age(archive.parent) < 30
        damaged = archive.with_name("tampered.dump.cms")
        payload = bytearray(archive.read_bytes())
        index = len(payload) // 2
        while (
            payload[index] not in b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
        ):
            index += 1
        payload[index] = ord("A") if payload[index] != ord("A") else ord("B")
        damaged.write_bytes(payload)
        metadata = json.loads(archive.with_suffix(".cms.json").read_text())
        metadata["sha256"] = hashlib.sha256(payload).hexdigest()
        damaged.with_suffix(".cms.json").write_text(json.dumps(metadata))
        with pytest.raises(BackupError, match="authentication/decryption"):
            restore(target_secret, certificate, key, damaged)
        assert inspect(target).get_table_names() == []
        restore(target_secret, certificate, key, archive)
        with Session(target) as db:
            assert db.scalar(select(func.count()).select_from(User)) == 4
        assert set(inspect(source).get_table_names()) == set(inspect(target).get_table_names())
        counts = verify_restored_content(source, target)
        assert counts["answers"] == 31
        assert counts["grading_records"] == 30
        assert all(isinstance(count, int) for count in counts.values())
        with pytest.raises(ValueError, match="dedicated restore database"):
            verify_restored_content(source, source)
        with pytest.raises(ValueError, match="dedicated rehearsal database"):
            verify_restored_content(admin, target)

        def change(
            table: str,
            column: str,
            row_id: uuid.UUID,
            expression: str,
            parameters: dict[str, object],
        ) -> None:
            guarded = table in {"grading_records", "audit_events"}
            with target.begin() as connection:
                # The schema owner can inject a storage-corruption fixture;
                # append-only guards remain enabled outside this transaction.
                if guarded:
                    connection.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER USER"))
                connection.execute(
                    text(f"UPDATE {table} SET {column}={expression} WHERE id=:id"),
                    {"id": row_id, **parameters},
                )
                if guarded:
                    connection.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER USER"))

        # These committed changes keep row counts identical. Simulate corruption
        # only in the disposable restored copy, never through application routes.
        for table, column, replacement in [
            ("answers", "short_answer_text", "'CORRUPTED recovery answer'"),
            ("answers", "revision", "revision + 1"),
            ("answers", "is_marked_for_review", "NOT is_marked_for_review"),
            ("subject_attempts", "expires_at", "expires_at + interval '1 second'"),
            ("question_options", "option_text", "'CORRUPTED option'"),
            ("grading_records", "marks_awarded", "0.25"),
            ("audit_events", "entity_id", f"'{uuid.uuid4()}'::uuid"),
            ("exams", "results_released", "NOT results_released"),
        ]:
            with target.connect() as connection:
                original = connection.execute(
                    text(f"SELECT id, {column} FROM {table} WHERE {column} IS NOT NULL LIMIT 1")
                ).one()
            change(table, column, original.id, replacement, {})
            try:
                with pytest.raises(ValueError, match=f"table {table}") as failure:
                    verify_restored_content(source, target)
                assert "CORRUPTED" not in str(failure.value)
                assert "پاکستان" not in str(failure.value)
            finally:
                change(table, column, original.id, ":original", {"original": original[1]})
        assert verify_restored_content(source, target) == counts
        with target.begin() as connection:
            connection.execute(
                text("""UPDATE recovery_json_fixture SET payload='{"a": 1, "b": 2}'::json
                     WHERE id=2""")
            )
        assert verify_restored_content(source, target) == counts
        with target.begin() as connection:
            connection.execute(
                text("UPDATE recovery_json_fixture SET payload='null'::json WHERE id=1")
            )
        with pytest.raises(ValueError, match="table recovery_json_fixture"):
            verify_restored_content(source, target)
        with target.begin() as connection:
            connection.execute(text("UPDATE recovery_json_fixture SET payload=NULL WHERE id=1"))
        assert verify_restored_content(source, target) == counts
        with target.begin() as connection:
            connection.execute(
                text("""ALTER TABLE proctor_exam_assignments
                     ALTER COLUMN created_at TYPE timestamp without time zone""")
            )
        with pytest.raises(ValueError, match="table proctor_exam_assignments"):
            verify_restored_content(source, target)
        with target.begin() as connection:
            connection.execute(
                text("""ALTER TABLE proctor_exam_assignments
                     ALTER COLUMN created_at TYPE timestamp with time zone""")
            )
        assert verify_restored_content(source, target) == counts
        with target.begin() as connection:
            connection.execute(text("ALTER TABLE proctor_exam_assignments ADD COLUMN extra bool"))
        with pytest.raises(ValueError, match="table proctor_exam_assignments"):
            verify_restored_content(source, target)
        with target.begin() as connection:
            connection.execute(text("DROP TABLE proctor_exam_assignments"))
        with pytest.raises(ValueError, match="table set"):
            verify_restored_content(source, target)
        with target.connect() as connection:
            with pytest.raises(DBAPIError):
                connection.execute(text("DELETE FROM security_events"))
            connection.rollback()
        with pytest.raises(BackupError, match="not empty"):
            restore(target_secret, certificate, key, archive)
        with pytest.raises(BackupError, match="ending in _restore"):
            restore(source_secret, certificate, key, archive)
    finally:
        for engine in engines:
            engine.dispose()
        with admin.connect() as connection:
            for name in [restored_name, source_name]:
                connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()
