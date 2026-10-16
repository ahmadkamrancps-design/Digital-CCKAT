"""Local HTTPS rehearsal against disposable PostgreSQL databases; Docker CI is authoritative.

Run with the backend venv and PYTHONPATH=backend. Never edits the development DB.
"""

import argparse
import json
import os
import signal
import ssl
import subprocess
import time
import uuid
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from alembic import command
from alembic.config import Config
from app.backup import backup, restore
from app.config import load_settings
from app.rehearsal_seed import seed
from app.rehearsal_verify import verify_expiry
from prepare_staging import prepare
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


def main() -> None:
    parser = argparse.ArgumentParser(description="Isolated local CCK HTTPS production rehearsal")
    parser.add_argument("--nginx-bin", type=Path, required=True)
    parser.add_argument("--mime-types", type=Path, required=True)
    parser.add_argument("--k6-bin", type=Path)
    parser.add_argument("--candidates", type=int, default=22)
    parser.add_argument("--keep-running", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.chdir(root / "backend")
    prefix = "cck_native_" + uuid.uuid4().hex[:10]
    directory = root / "test-results" / prefix
    prepare(directory, 9443, 9080)
    secrets = directory / "secrets"
    password = (secrets / "owner_password").read_text().strip()
    role = prefix + "_owner"
    source_name, target_name = prefix + "_rehearsal", prefix + "_restore"
    admin = create_engine(
        load_settings().database_url, isolation_level="AUTOCOMMIT", hide_parameters=True
    )
    source_url = admin.url.set(username=role, password=password, database=source_name)
    target_url = source_url.set(database=target_name)
    processes = []
    logs = []
    engine = None
    created = False
    env = os.environ.copy()
    env.update(
        ENVIRONMENT="production",
        DATABASE_URL=source_url.render_as_string(hide_password=False),
        SESSION_COOKIE_SECURE="true",
        FRONTEND_ORIGIN="https://localhost:9443",
        ALLOWED_HOSTS='["localhost"]',
        GOOGLE_CLIENT_ID="",
        REQUIRE_EXPIRY_WORKER="true",
        CANDIDATE_LOGIN_IP_LIMIT="20000",
        VITE_ENABLE_UI_PREVIEW="false",
        VITE_GOOGLE_CLIENT_ID="",
    )
    env.pop("DATABASE_URL_FILE", None)
    try:
        with admin.connect() as connection:
            connection.connection.driver_connection.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD {}"
                ).format(sql.Identifier(role), sql.Literal(password))
            )
            created = True
            connection.execute(text(f'CREATE DATABASE "{source_name}" OWNER "{role}"'))
            connection.execute(text(f'CREATE DATABASE "{target_name}" OWNER "{role}"'))
        os.environ.update(
            {
                key: value
                for key, value in env.items()
                if key
                in {
                    "ENVIRONMENT",
                    "DATABASE_URL",
                    "SESSION_COOKIE_SECURE",
                    "FRONTEND_ORIGIN",
                    "ALLOWED_HOSTS",
                    "REQUIRE_EXPIRY_WORKER",
                    "CANDIDATE_LOGIN_IP_LIMIT",
                    "GOOGLE_CLIENT_ID",
                }
            }
        )
        command.upgrade(Config("alembic.ini"), "head")
        engine = create_engine(source_url, hide_parameters=True)
        with Session(engine, expire_on_commit=False) as db:
            seed(db, args.candidates, 60, directory / "manifest.json")
        source_secret = secrets / "owner_database_url"
        source_secret.write_text(source_url.render_as_string(hide_password=False))
        target_secret = secrets / "restore_database_url"
        target_secret.write_text(target_url.render_as_string(hide_password=False))
        if not args.skip_build:
            build = subprocess.run(
                ["npm", "run", "build"],
                cwd=root / "frontend",
                env=env,
                capture_output=True,
                check=False,
            )
            if build.returncode:
                raise RuntimeError("Production frontend build failed")
        native_bin = directory / "bin"
        native_bin.mkdir()
        (native_bin / "nginx").symlink_to(args.nginx_bin.resolve())
        env.update(
            PATH=str(native_bin) + os.pathsep + env["PATH"],
            CCK_SERVER_NAME="localhost",
            CCK_PUBLIC_ORIGIN=env["FRONTEND_ORIGIN"],
            CCK_API_UPSTREAM="127.0.0.1:8002",
            CCK_RESOLVER="127.0.0.53",
            CCK_TLS_CERTIFICATE=str(secrets / "tls_certificate.pem"),
            CCK_TLS_KEY=str(secrets / "tls_private_key.pem"),
            CCK_STATIC_ROOT=str(root / "frontend/dist"),
            CCK_HEADERS_FILE=str(root / "frontend/ops/security-headers.conf"),
            CCK_MIME_TYPES_FILE=str(args.mime_types.resolve()),
            CCK_TEMPLATE=str(root / "frontend/ops/nginx.conf.template"),
            CCK_HTTP_LISTEN="9080",
            CCK_HTTPS_LISTEN="9443",
            CCK_REHEARSAL_MANIFEST=str(directory / "manifest.json"),
            CCK_BASE_URL=env["FRONTEND_ORIGIN"],
            CCK_LOCAL_SELF_SIGNED="true",
        )
        commands = [
            [
                str(root / "backend/.venv/bin/uvicorn"),
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8002",
                "--workers",
                "2",
                "--proxy-headers",
                "--forwarded-allow-ips",
                "127.0.0.1",
                "--no-access-log",
                "--no-server-header",
            ],
            [
                str(root / "backend/.venv/bin/python"),
                "-m",
                "app.expiry_worker",
                "--interval",
                "0.2",
            ],
            ["sh", str(root / "frontend/ops/start-gateway.sh")],
        ]
        for index, cmd in enumerate(commands):
            log = (directory / f"service-{index}.log").open("w")
            logs.append(log)
            processes.append(
                subprocess.Popen(
                    cmd,
                    cwd=root / "backend",
                    env=env,
                    stdout=log,
                    stderr=log,
                    start_new_session=True,
                )
            )
        context = ssl.create_default_context(cafile=str(secrets / "tls_certificate.pem"))
        until = time.monotonic() + 40
        while True:
            try:
                with urlopen(
                    env["FRONTEND_ORIGIN"] + "/api/health/ready",
                    context=context,
                    timeout=3,
                ) as response:
                    if response.status == 200:
                        break
            except (URLError, OSError):
                pass
            if time.monotonic() > until:
                raise RuntimeError(
                    "Native HTTPS services did not become ready; inspect private service logs"
                )
            time.sleep(0.2)
        print(
            "PASS: production frontend, HTTPS gateway, API and expiry worker are ready",
            flush=True,
        )
        if args.k6_bin:
            k6 = subprocess.run(
                [
                    str(args.k6_bin.resolve()),
                    "run",
                    "--summary-export",
                    str(directory / "load-summary.json"),
                    str(root / "ops/load/exam.js"),
                ],
                env=env,
                cwd=root,
                capture_output=True,
            )
            (directory / "load.log").write_bytes(k6.stdout + k6.stderr)
            if k6.returncode:
                raise RuntimeError("Load rehearsal failed; inspect aggregate load report")
            print(
                "PASS: candidate load rehearsal completed with zero integrity failures",
                flush=True,
            )
        env["LD_LIBRARY_PATH"] = "/tmp/cck-browser-libs/root/usr/lib/x86_64-linux-gnu"
        browser = subprocess.run(
            ["node", "e2e/production-rehearsal.mjs"],
            cwd=root / "frontend",
            env=env,
            capture_output=True,
        )
        (directory / "browser.log").write_bytes(browser.stdout + browser.stderr)
        if browser.returncode:
            raise RuntimeError("Real-browser rehearsal failed; inspect private browser report")
        print(
            "PASS: real Chromium candidate workflow, recovery, submission and results",
            flush=True,
        )
        verify_expiry(engine, directory / "manifest.json")
        print("PASS: worker expired an unattended subject without API contact", flush=True)
        archive = backup(source_secret, secrets / "backup_certificate.pem", directory / "backups")
        restore(
            target_secret,
            secrets / "backup_certificate.pem",
            secrets / "backup_private_key.pem",
            archive,
        )
        restored = create_engine(target_url, hide_parameters=True)
        try:
            with engine.connect() as before, restored.connect() as after:
                for table in [
                    "users",
                    "answers",
                    "grading_records",
                    "audit_events",
                    "security_events",
                    "session_events",
                ]:
                    assert before.scalar(text(f"SELECT count(*) FROM {table}")) == after.scalar(
                        text(f"SELECT count(*) FROM {table}")
                    )
        finally:
            restored.dispose()
        print("PASS: encrypted backup restored all critical row counts", flush=True)
        (directory / "report.json").write_text(
            json.dumps(
                {
                    "kind": "LOCAL_REHEARSAL",
                    "candidates_seeded": args.candidates,
                    "browser": "passed",
                    "load": "passed" if args.k6_bin else "not_run",
                    "encrypted_restore": "passed",
                    "unattended_expiry": "passed",
                    "production_capacity_certified": False,
                },
                indent=2,
            )
        )
        print(f"Aggregate evidence: {directory / 'report.json'}", flush=True)
        if args.keep_running:
            print(
                "Rehearsal only; Ctrl+C cleans up isolated services and databases.",
                flush=True,
            )
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    except Exception as error:
        parser.exit(1, f"Rehearsal failed: {type(error).__name__}. Inspect {directory} logs.\n")
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
        for log in logs:
            log.close()
        if engine:
            engine.dispose()
        if created:
            with admin.connect() as connection:
                for name in [target_name, source_name]:
                    connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
                connection.execute(text(f'DROP ROLE "{role}"'))
        admin.dispose()


if __name__ == "__main__":
    main()
