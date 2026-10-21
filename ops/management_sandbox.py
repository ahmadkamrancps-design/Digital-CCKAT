"""Explicit localhost-only management playground. Never imported by production app/images.

Run with PYTHONPATH=backend and the backend venv. Test data persists in its own
cck_management_*_rehearsal database; no public authentication method is added.
"""

import argparse
import json
import os
import re
import secrets
import signal
import socket
import subprocess
from pathlib import Path
from types import FrameType
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import uvicorn
from app.api.dependencies import Db
from app.api.routes.auth import set_session_cookie
from app.config import Settings, load_settings
from app.models import AuditEvent, Candidate, Exam, Role, User
from app.schemas.exam_domain import QuestionWrite, SubjectWrite
from app.services.auth_service import issue_session
from app.services.exam_domain_service import write_question, write_subject
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import TypeAdapter
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

COOKIE_NAME = "cck_management_sandbox"
ENTRY_PATH = "/api/local-management"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
DATABASE_PATTERN = r"cck_management_[a-f0-9]{12}_rehearsal"


def validate_sandbox(settings: Settings) -> None:
    url = make_url(settings.database_url)
    origin = urlsplit(settings.frontend_origin)
    if (
        settings.environment != "development"
        or url.host not in LOCAL_HOSTS
        or not re.fullmatch(DATABASE_PATTERN, url.database or "")
        or origin.scheme != "http"
        or origin.hostname != "localhost"
        or origin.port is None
        or settings.session_cookie_name != COOKIE_NAME
        or settings.session_cookie_secure
    ):
        raise ValueError(
            "Management sandbox requires its isolated localhost development configuration."
        )


def sandbox_database_name(db: Session) -> str | None:
    return db.scalar(text("SELECT current_database()"))


def create_sandbox_app(settings: Settings, administrator_id: UUID) -> FastAPI:
    validate_sandbox(settings)
    from app.main import create_app

    app = create_app(settings)
    nonce = secrets.token_urlsafe(32)

    def require_loopback(request: Request) -> None:
        if not request.client or request.client.host not in {"127.0.0.1", "::1"}:
            raise HTTPException(403, "Local management testing is available on this computer only.")

    @app.get(ENTRY_PATH, include_in_schema=False, response_class=HTMLResponse)
    def entry(request: Request) -> HTMLResponse:
        require_loopback(request)
        return HTMLResponse(
            '<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            "<title>CCK local management testing</title>"
            '<body style="font-family:system-ui;background:#f6f8fb;color:#10213d;'
            'max-width:600px;margin:12vh auto;padding:24px">'
            "<h1>CCK management sandbox</h1>"
            "<p>Local test database · Real management tools</p>"
            "<p>Create candidates, configure exams, edit questions and try marking rules. "
            "Changes are saved in a separate test database and remain after refresh or restart.</p>"
            "<p>Use sample information only. This sandbox does not update admissions records.</p>"
            f'<form method="post" action="{ENTRY_PATH}">'
            f'<input type="hidden" name="nonce" value="{nonce}">'
            '<button style="background:#002b5c;color:white;border:0;border-radius:7px;'
            'padding:14px 22px;font:inherit;cursor:pointer">Open test administration</button>'
            '</form><p role="alert" id="entry-error"></p>'
            "<p>No Google setup is needed for this local sandbox.</p>"
            '<script>document.querySelector("form").addEventListener("submit",async(event)=>{'
            'event.preventDefault();const button=document.querySelector("button");'
            "button.disabled=true;"
            'try{const response=await fetch(location.pathname,{method:"POST",'
            'headers:{"Content-Type":"application/json"},body:JSON.stringify({nonce:'
            'document.querySelector("input").value})});if(!response.ok)throw new Error();'
            'location.replace("/admin");}catch{document.getElementById("entry-error").textContent='
            '"Could not open management. Refresh this page and try again.";button.disabled=false;}'
            "});</script></body></html>",
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
        )

    @app.post(ENTRY_PATH, include_in_schema=False)
    async def enter(request: Request, db: Db) -> Response:
        require_loopback(request)
        if request.headers.get("origin") != settings.frontend_origin:
            raise HTTPException(403, "Open the local management entry page first.")
        body = await request.body()
        try:
            data = json.loads(body) if len(body) <= 1024 else None
            supplied = data.get("nonce") if isinstance(data, dict) and len(data) == 1 else None
            valid = (
                isinstance(supplied, str)
                and supplied.isascii()
                and secrets.compare_digest(supplied, nonce)
            )
        except (UnicodeError, ValueError, TypeError):
            valid = False
        if not valid:
            raise HTTPException(403, "Open the local management entry page first.")
        # Check the actual database too; never issue staff access in a different database.
        name = sandbox_database_name(db)
        if not isinstance(name, str) or not re.fullmatch(DATABASE_PATTERN, name):
            raise HTTPException(403, "This database is not a management sandbox.")
        user = db.scalar(
            select(User)
            .where(User.id == administrator_id, User.role == Role.ADMIN, User.is_active.is_(True))
            .with_for_update()
        )
        if user is None:
            raise HTTPException(403, "The local test administrator is unavailable.")
        db.add(AuditEvent(user_id=user.id, entity_id=user.id, event_type="LOCAL_SANDBOX_SESSION"))
        _, token = issue_session(db, user, None, settings, method="SESSION")
        response = Response(status_code=204, headers={"Cache-Control": "no-store"})
        set_session_cookie(response, token, settings)
        return response

    return app


def seed_management(db: Session) -> UUID:
    administrator = User(display_name="Local Test Administrator", role=Role.ADMIN)
    db.add(administrator)
    for number in range(1, 4):
        user = User(display_name=f"Sample Candidate {number}", role=Role.CANDIDATE)
        db.add(user)
        db.flush()
        db.add(
            Candidate(
                user_id=user.id,
                roll_number=f"TEST-{number:03}",
                full_name=user.display_name,
                father_name=f"Sample Father {number}",
            )
        )
    db.add(Exam(title="Sample entry test — editable draft", is_published=False))
    db.commit()
    subjects = {
        label: write_subject(db, SubjectWrite(name=label, code=f"TEST_{code}")).id
        for label, code in [("English", "ENG"), ("Mathematics", "MATH"), ("Urdu", "UR")]
    }
    examples = [
        {
            "subject_id": subjects["English"],
            "type": "MCQ",
            "prompt": "Select the opposite of creation.",
            "marks": "1",
            "options": [
                {"text": "Destruction", "is_correct": True},
                {"text": "Development", "is_correct": False},
            ],
        },
        {
            "subject_id": subjects["English"],
            "type": "SHORT_ANSWER",
            "prompt": "Complete: From darkness unto _____.",
            "marks": "2",
            "grading": {"mode": "EXACT", "trim_whitespace": True, "case_sensitive": False},
            "accepted_answers": ["light"],
        },
        {
            "subject_id": subjects["Mathematics"],
            "type": "SHORT_ANSWER",
            "prompt": "Find x: 3(x + 5) = 24.",
            "marks": "2",
            "grading": {"mode": "NUMERIC", "absolute_tolerance": "0"},
            "accepted_answers": ["3"],
        },
        {
            "subject_id": subjects["Urdu"],
            "type": "SHORT_ANSWER",
            "prompt": "اپنی پسندیدہ کتاب کا نام لکھیں۔",
            "marks": "2",
            "language": "ur",
            "direction": "rtl",
            "grading": {"mode": "MANUAL"},
            "accepted_answers": [],
        },
    ]
    for example in examples:
        write_question(db, TypeAdapter(QuestionWrite).validate_python(example))
    return administrator.id


def migrate_sandbox(database_url: str, directory: Path) -> None:
    url = make_url(database_url)
    if url.host not in LOCAL_HOSTS or not re.fullmatch(DATABASE_PATTERN, url.database or ""):
        raise ValueError("Only the local management sandbox can be migrated by this tool.")
    environment = {**os.environ, "DATABASE_URL": database_url, "ENVIRONMENT": "development"}
    environment.pop("DATABASE_URL_FILE", None)
    with (directory / "migrations.log").open("a") as log:
        subprocess.run(
            [str(Path(os.sys.executable).parent / "alembic"), "upgrade", "head"],
            env=environment,
            stdout=log,
            stderr=log,
            check=True,
        )


def prepare_database(directory: Path, base: Settings) -> tuple[str, UUID]:
    url = make_url(base.database_url)
    if base.environment != "development" or url.host not in LOCAL_HOSTS:
        raise ValueError("Launch from the local development database configuration only.")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.is_symlink() or directory.stat().st_mode & 0o077:
        raise ValueError("Use a private operator-owned sandbox directory.")
    manifest = directory / "sandbox.json"
    if manifest.exists():
        if manifest.is_symlink() or manifest.stat().st_mode & 0o077:
            raise ValueError("Sandbox metadata must be private.")
        data = json.loads(manifest.read_text())
        if data.get("kind") != "LOCAL_CCK_MANAGEMENT_SANDBOX":
            raise ValueError("Invalid sandbox metadata.")
        migrate_sandbox(data["database_url"], directory)
        return data["database_url"], UUID(data["administrator_id"])
    name = f"cck_management_{uuid4().hex[:12]}_rehearsal"
    sandbox_url = url.set(database=name)
    engine = create_engine(url, isolation_level="AUTOCOMMIT", hide_parameters=True)
    try:
        with engine.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        engine.dispose()
    migrate_sandbox(sandbox_url.render_as_string(hide_password=False), directory)
    engine = create_engine(sandbox_url, hide_parameters=True)
    try:
        with Session(engine, expire_on_commit=False) as db:
            administrator_id = seed_management(db)
    finally:
        engine.dispose()
    with manifest.open("x") as stream:
        manifest.chmod(0o600)
        json.dump(
            {
                "kind": "LOCAL_CCK_MANAGEMENT_SANDBOX",
                "database_url": sandbox_url.render_as_string(hide_password=False),
                "administrator_id": str(administrator_id),
            },
            stream,
        )
    return sandbox_url.render_as_string(hide_password=False), administrator_id


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Start a separate localhost CCK management sandbox"
    )
    parser.add_argument("--directory", type=Path, default=Path("test-results/management-sandbox"))
    parser.add_argument("--frontend-port", type=int, default=5175)
    parser.add_argument("--api-port", type=int, default=8003)
    args = parser.parse_args()
    if args.frontend_port == args.api_port or not all(
        1024 <= port <= 65535 for port in (args.frontend_port, args.api_port)
    ):
        parser.error("Choose distinct local ports in 1024..65535.")
    root = Path(__file__).resolve().parents[1]
    directory = args.directory.resolve()
    children: list[subprocess.Popen] = []
    logs = []
    os.umask(0o077)
    try:
        # Refuse occupied ports before provisioning or starting anything.
        for port in (args.frontend_port, args.api_port):
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", port))
        os.chdir(root / "backend")
        base = load_settings()
        database_url, administrator_id = prepare_database(directory, base)
        settings = Settings(
            _env_file=None,
            database_url=database_url,
            environment="development",
            frontend_origin=f"http://localhost:{args.frontend_port}",
            session_cookie_name=COOKIE_NAME,
            session_ttl_seconds=7200,
            allowed_hosts=["localhost", "127.0.0.1"],
        )
        validate_sandbox(settings)
        app = create_sandbox_app(settings, administrator_id)
        environment = {
            **os.environ,
            "DATABASE_URL": database_url,
            "ENVIRONMENT": "development",
            "FRONTEND_ORIGIN": settings.frontend_origin,
            "SESSION_COOKIE_NAME": COOKIE_NAME,
            "SESSION_COOKIE_SECURE": "false",
            "ALLOWED_HOSTS": '["localhost","127.0.0.1"]',
            "VITE_ENABLE_UI_PREVIEW": "false",
            "VITE_MANAGEMENT_SANDBOX": "true",
            "VITE_GOOGLE_CLIENT_ID": "",
            "DEV_API_TARGET": f"http://127.0.0.1:{args.api_port}",
        }
        environment.pop("DATABASE_URL_FILE", None)
        commands = [
            (["npm", "run", "dev", "--", "--port", str(args.frontend_port)], root / "frontend"),
            ([os.sys.executable, "-m", "app.expiry_worker"], root / "backend"),
        ]
        for index, (command, working_directory) in enumerate(commands):
            log = (directory / f"service-{index}.log").open("a")
            logs.append(log)
            children.append(
                subprocess.Popen(
                    command,
                    cwd=working_directory,
                    env=environment,
                    stdout=log,
                    stderr=log,
                    start_new_session=True,
                )
            )
        print(f"Local management testing: {settings.frontend_origin}{ENTRY_PATH}", flush=True)
        print(
            "Separate persistent test database. Ctrl+C stops services and retains test changes.",
            flush=True,
        )

        def stop_requested(signum: int, frame: FrameType | None) -> None:
            raise KeyboardInterrupt

        # Uvicorn re-emits SIGTERM after graceful shutdown; run child cleanup too.
        signal.signal(signal.SIGTERM, stop_requested)
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=args.api_port,
            access_log=False,
            server_header=False,
            proxy_headers=False,
        )
    except KeyboardInterrupt:
        pass
    except Exception as error:
        parser.exit(
            1, f"Management sandbox failed: {type(error).__name__}. Inspect private sandbox logs.\n"
        )
    finally:
        for child in reversed(children):
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
        for log in logs:
            log.close()


if __name__ == "__main__":
    main()
