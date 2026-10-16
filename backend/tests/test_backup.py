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
from app.models import User
from app.rehearsal_seed import seed


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
        target = create_engine(restored_url, hide_parameters=True)
        engines += [source, target]
        with Session(source, expire_on_commit=False) as db:
            seed(db, 3, 60, tmp_path / "private-manifest.json")
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
