"""Operator-only encrypted PostgreSQL backups; standard-library/OpenSSL CLI tools.

This module also runs standalone in the PostgreSQL tooling container. No web route
invokes it. Restoration is restricted to a fresh database ending in _restore.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit


class BackupError(Exception):
    pass


def pg_tool(name: str) -> str:
    directory = os.environ.get("PG_CLIENT_BIN")
    executable = str(Path(directory) / name) if directory else shutil.which(name)
    if not executable:
        raise BackupError("PostgreSQL client tools are unavailable.")
    return executable


@contextmanager
def database_environment(secret: Path) -> Iterator[dict[str, str]]:
    try:
        if secret.stat().st_size > 8192:
            raise ValueError
        value = secret.read_text().strip().replace("postgresql+psycopg://", "postgresql://", 1)
        url = urlsplit(value)
        username, password, database = (
            unquote(url.username or ""),
            unquote(url.password or ""),
            unquote(url.path.removeprefix("/")),
        )
        if (
            url.scheme != "postgresql"
            or not url.hostname
            or not username
            or not password
            or not re.fullmatch(r"[A-Za-z0-9_]+", database)
        ):
            raise ValueError
        values = [url.hostname, str(url.port or 5432), database, username, password]
        if any("\n" in field or "\r" in field for field in values):
            raise ValueError
    except (OSError, ValueError):
        raise BackupError("Invalid database secret file.") from None
    with tempfile.TemporaryDirectory(prefix="cck-pgpass-") as directory:
        pgpass = Path(directory) / "pgpass"
        pgpass.write_text(
            ":".join(field.replace("\\", "\\\\").replace(":", "\\:") for field in values) + "\n"
        )
        pgpass.chmod(0o600)
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("PG"):
                del env[key]
        env.update(
            PGHOST=values[0],
            PGPORT=values[1],
            PGDATABASE=database,
            PGUSER=username,
            PGPASSFILE=str(pgpass),
            PGCONNECT_TIMEOUT="5",
            PGAPPNAME="cck-backup",
        )
        for query, variable in {
            "sslmode": "PGSSLMODE",
            "sslrootcert": "PGSSLROOTCERT",
            "sslcert": "PGSSLCERT",
            "sslkey": "PGSSLKEY",
        }.items():
            if query in parse_qs(url.query):
                env[variable] = parse_qs(url.query)[query][-1]
        yield env


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def backup(secret: Path, certificate: Path, directory: Path) -> Path:
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = directory / f"cck-{stamp}-{uuid.uuid4().hex[:8]}.dump.cms"
    partial = target.with_suffix(".partial")
    try:
        with database_environment(secret) as env, tempfile.TemporaryFile() as errors:
            with partial.open("xb") as encrypted:
                partial.chmod(0o600)
                dump = subprocess.Popen(
                    [pg_tool("pg_dump"), "--format=custom", "--no-owner", "--no-privileges"],
                    stdout=subprocess.PIPE,
                    stderr=errors,
                    env=env,
                )
                try:
                    encrypted_result = subprocess.run(
                        [
                            "openssl",
                            "cms",
                            "-encrypt",
                            "-aes-256-gcm",
                            "-binary",
                            "-stream",
                            "-outform",
                            "PEM",
                            "--",
                            str(certificate),
                        ],
                        stdin=dump.stdout,
                        stdout=encrypted,
                        stderr=errors,
                        timeout=3600,
                    )
                finally:
                    if dump.stdout:
                        dump.stdout.close()
                    try:
                        dump.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        dump.kill()
                        dump.wait()
                if encrypted_result.returncode or dump.returncode:
                    raise BackupError("Database backup or authenticated encryption failed.")
                encrypted.flush()
                os.fsync(encrypted.fileno())
        partial.replace(target)
        metadata = {
            "format": "CCK-PGDUMP-CMS-AES256GCM-v1",
            "created_at": datetime.now(UTC).isoformat(),
            "sha256": digest(target),
            "bytes": target.stat().st_size,
        }
        sidecar = target.with_suffix(target.suffix + ".json")
        sidecar.write_text(json.dumps(metadata, indent=2) + "\n")
        sidecar.chmod(0o600)
        return target
    finally:
        partial.unlink(missing_ok=True)


def restore(secret: Path, certificate: Path, key: Path, archive: Path) -> None:
    metadata = json.loads(archive.with_suffix(archive.suffix + ".json").read_text())
    if metadata.get("format") != "CCK-PGDUMP-CMS-AES256GCM-v1" or metadata.get("sha256") != digest(
        archive
    ):
        raise BackupError("Backup checksum or format is invalid.")
    with (
        database_environment(secret) as env,
        tempfile.TemporaryDirectory(prefix="cck-restore-") as directory,
    ):
        if not env["PGDATABASE"].endswith("_restore"):
            raise BackupError("Restore target must be a fresh database ending in _restore.")
        plain = Path(directory) / "restore.dump"
        # Authenticate the entire ciphertext BEFORE allowing pg_restore any writes.
        with plain.open("xb") as output:
            plain.chmod(0o600)
            result = subprocess.run(
                [
                    "openssl",
                    "cms",
                    "-decrypt",
                    "-binary",
                    "-inform",
                    "PEM",
                    "-in",
                    str(archive),
                    "-recip",
                    str(certificate),
                    "-inkey",
                    str(key),
                ],
                stdout=output,
                stderr=subprocess.PIPE,
                timeout=3600,
            )
        if result.returncode:
            raise BackupError("Backup authentication/decryption failed; nothing was restored.")
        query = (
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname NOT IN ('pg_catalog','information_schema') "
            "AND n.nspname NOT LIKE 'pg_toast%' AND c.relkind IN ('r','p','v','m','S')"
        )
        check = subprocess.run(
            [pg_tool("psql"), "-X", "-A", "-t", "--set=ON_ERROR_STOP=1", "-c", query],
            env=env,
            capture_output=True,
            timeout=15,
        )
        if check.returncode or check.stdout.strip() != b"0":
            raise BackupError("Restore target is unavailable or not empty.")
        result = subprocess.run(
            [
                pg_tool("pg_restore"),
                "--exit-on-error",
                "--single-transaction",
                "--no-owner",
                "--no-privileges",
                "--dbname",
                env["PGDATABASE"],
                str(plain),
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=3600,
        )
        if result.returncode:
            raise BackupError("Database restore failed; the restore transaction was rolled back.")


def latest_backup_age(directory: Path) -> float:
    ages = []
    for sidecar in directory.glob("*.dump.cms.json"):
        metadata = json.loads(sidecar.read_text())
        archive = sidecar.with_suffix("")
        if archive.is_file() and metadata.get("format") == "CCK-PGDUMP-CMS-AES256GCM-v1":
            ages.append(
                (datetime.now(UTC) - datetime.fromisoformat(metadata["created_at"])).total_seconds()
            )
    if not ages:
        raise BackupError("No completed backup is available.")
    return min(ages)


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description="CCK encrypted database backup and safe restore")
    parser.add_argument("action", choices=["backup", "loop", "restore", "status"])
    parser.add_argument("--database-secret", type=Path, default=Path("/run/secrets/database_url"))
    parser.add_argument("--certificate", type=Path, default=Path("/run/secrets/backup_certificate"))
    parser.add_argument("--private-key", type=Path, default=Path("/run/secrets/backup_private_key"))
    parser.add_argument("--directory", type=Path, default=Path("/backups"))
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--interval", type=int, default=3600)
    parser.add_argument("--max-age", type=int, default=7200)
    args = parser.parse_args()
    if not 60 <= args.interval <= 86400:
        parser.error("Interval must be between 60 and 86400 seconds.")
    try:
        if args.action == "restore":
            if args.archive is None:
                parser.error("Restore requires --archive.")
            restore(args.database_secret, args.certificate, args.private_key, args.archive)
            print(json.dumps({"event": "RESTORE_COMPLETE"}), flush=True)
        elif args.action == "status":
            age = latest_backup_age(args.directory)
            if age < 0 or age > args.max_age:
                raise BackupError("Database backup is stale.")
            print(json.dumps({"event": "BACKUP_HEALTHY", "age_seconds": round(age)}))
        else:
            while True:
                archive = backup(args.database_secret, args.certificate, args.directory)
                print(
                    json.dumps(
                        {
                            "event": "BACKUP_COMPLETE",
                            "archive": archive.name,
                            "bytes": archive.stat().st_size,
                        }
                    ),
                    flush=True,
                )
                if args.action == "backup":
                    break
                time.sleep(args.interval)
    except (BackupError, OSError, ValueError, subprocess.SubprocessError) as error:
        # No subprocess stderr, DSNs, passwords, or table contents in diagnostics.
        message = str(error) if isinstance(error, BackupError) else type(error).__name__
        parser.exit(1, f"Backup operation failed: {message}\n")


if __name__ == "__main__":
    main()
