# Milestone 1 handover

This records the original foundation delivery. The subsequent requested frontend
organization moved `styles.css` to `index.css` and added component/page scaffolds;
see [frontend structure](frontend-structure.md) for the current inventory. The
exam engine remains unimplemented. The test counts below record the original run.

Implementation and automated verification are finished. The exit criterion of a
real registered candidate signing in through Google still needs your OAuth client
configuration and browser acceptance check. At the original foundation handover,
no later milestone had been started. The subsequently authorized exam-domain
implementation is recorded in [Milestone 2 handover](milestone-2.md).

The new repository is `/home/mr_laptop/cck-digital-test`, on branch `main`.
The unrelated existing `ai-assistant` project was untouched. Git is initialized;
the foundation files remain uncommitted, and no remote or deployment was configured.

## Architecture delivered

- FastAPI with validated environment configuration, liveness/readiness endpoints,
  safe errors, restricted origins/hosts, and explicit public response schemas.
- SQLAlchemy 2.0 with PostgreSQL/psycopg and controlled Alembic migrations.
- Preapproved users and candidates; explicit CANDIDATE, ADMIN, PROCTOR, EXAMINER
  roles; backend authentication and role dependencies.
- Google Identity Services popup with server-side signature/audience/issuer/time
  verification, verified-email checks, stable subject binding, and eligibility checks.
- Database-backed sessions, hashed credentials, HttpOnly cookies, expiry, session
  rotation, revocation, and Origin/CSRF protection for mutations.
- Trusted local candidate/staff provisioning CLI with atomic registration and
  duplicate rejection. No public self-registration or role elevation endpoint.
- React/TypeScript login and protected dashboard, session restoration on refresh,
  safe network failure handling, logout, keyboard focus, and local Urdu direction.
- PostgreSQL Compose service, development Dockerfiles, dependency version locks,
  and a GitHub Actions workflow for future backend/frontend checks.

Candidate approval currently grants dashboard access. Exam assignments and
exam-specific authorization belong to the next domain/attempt milestones.

## Database migration

`backend/alembic/versions/0001_auth_foundation.py` creates `users`, `candidates`,
and `auth_sessions`, including unique identity/email/roll/session mappings,
foreign keys, role/status checks, normalized-email validation, and expiry indexing.
The migration supports downgrade; startup never creates tables automatically.

## Checks executed and results

Final checks used the project's isolated `.venv`, Python 3.14.4, Node 24.21.0,
and npm 11.19.0. Docker/CI declare Python 3.12; all Python sources parsed for that
syntax baseline and all 53 pinned distributions' Python version requirements
allow 3.12. A Python 3.12 runtime was unavailable locally. Docker was unavailable
in WSL, so database checks used PostgreSQL 16.2
binaries in `/tmp` with a private Unix socket. Compose/CI target PostgreSQL 17.

| Check | Result |
| --- | --- |
| `pytest -q` | 53 passed, 1 expected PostgreSQL-only skip |
| Same suite with `TEST_DATABASE_URL` | 54 passed |
| Alembic upgrade/downgrade/re-upgrade + model comparison | Passed against PostgreSQL |
| `ruff check .` | Passed |
| `ruff format --check .` | Passed |
| `mypy app` | Passed, 24 source files |
| `python -m pip check` | No broken requirements |
| `npm test` | 9 passed |
| `npm run build` (includes TypeScript check) | Passed |
| `npm audit --audit-level=moderate` | 0 reported vulnerabilities |
| Live frontend + API proxy smoke check | Passed |
| Candidate CLI + duplicate rejection | Passed |
| Git ignore verification | Environment/dependency/build files excluded |

Backend tests cover approved/unregistered identities, credential rejection,
real token cryptography with substituted public certificates, Google provider
failure, candidate/user disablement, role enforcement, stable identity linking,
third-party email restrictions, session restoration/expiry/rotation/revocation,
Origin/CSRF checks, safe validation/configuration errors, and database constraints.

Frontend tests cover approved/denied credential exchange, session restoration,
anonymous redirect, network retry, logout, failed logout, and a delayed profile
response arriving after logout. Test mocks exist only in test code; the live
application has no fake sign-in route or authentication bypass.

The live smoke check confirmed the portal loads, `/api/health` and readiness
return 200 through Vite, anonymous profiles return 401, missing Google setup
fails safely with 503, and foreign-origin login is rejected with 403. Vite
answers preflights with 204 while FastAPI denies the foreign preflight with 400;
neither grants the foreign origin access. An initial smoke assertion expected
FastAPI's status through Vite and was corrected after inspecting both responses.

## Resolved setup issues and remaining limitations

- Missing `ensurepip` was handled through pip's supported `--python` bootstrap;
  the project venv now contains pip and the installed dependencies.
- Package-host DNS interruptions were investigated and downloads completed.
- Sandbox socket restrictions required running database/service checks outside
  the sandbox. These were environment restrictions, not application failures.
- Two initial npm moderate advisories were resolved by upgrading to Vitest 4.1.11.
- Python formatting/import/type-check issues and the Alembic path-separator
  warning were resolved.
- One upstream Starlette TestClient deprecation warning remains for its httpx
  compatibility path. All tests pass; review test-client dependency migration
  when updating that upstream stack.
- Docker builds, Compose execution, GitHub CI, PostgreSQL 17, and the Python 3.12
  runtime were not executed locally. CI is configured but has not run remotely.
- Actual Google-issued credentials and popup/browser acceptance remain untested
  until you configure a real client and approved account.
- No exam engine, timer, questions, answer saving, grading, results, admin portal,
  or proctor system exists. Authentication logs are diagnostic logs; the append-oriented
  audit store, distributed rate limits, and production hardening remain future work.

This foundation is not production-ready and must not conduct real examinations.

## Manual configuration and exact run commands

Enable Docker Desktop's WSL integration, or provide a PostgreSQL instance and
matching `DATABASE_URL`. Configure a Google OAuth **Web application** client:
authorized JavaScript origins `http://localhost` and `http://localhost:5173`;
set the same public client ID in `backend/.env` (`GOOGLE_CLIENT_ID`) and
`frontend/.env` (`VITE_GOOGLE_CLIENT_ID`). No Google client secret is needed.
Follow the full Google setup and real-login acceptance checklist in [README](../README.md).

Environment files were already copied from examples without overwriting existing
files and are ignored by Git. Dependencies are installed here. From this workspace,
after Docker and Google setup:

```bash
cd /home/mr_laptop/cck-digital-test
docker compose up -d db
```

Backend terminal:

```bash
cd /home/mr_laptop/cck-digital-test/backend
source .venv/bin/activate
alembic upgrade head
python -m app.cli register-candidate \
  --email "your-approved-account@gmail.com" \
  --name "Test Candidate" --roll-number "CCK-104"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

Frontend terminal:

```bash
cd /home/mr_laptop/cck-digital-test/frontend
npm run dev
```

Open `http://localhost:5173`. Fresh-checkout installation, checks, test database
creation, staff provisioning, and environment instructions are in the README.
Temporary verification services are stopped after checks; the normal development
configuration does not point at the temporary test database.

## Recommendation

Configure Google and complete the real registered/unregistered account browser
check first. Once Milestone 1's exit criteria are demonstrated and you request
Milestone 2, define configurable exams, subjects, MCQ/short-answer questions,
exam question selection, and protected administrative domain APIs. Do not begin
the attempt engine or candidate test shell during the exam-domain milestone.

## Files created

All project files were new; no existing project modules were rewritten. The
following inventory excludes ignored `.env` files, installed dependencies, build
output, and temporary test tooling.

```text
.env.example
.github/workflows/checks.yml
.gitignore
README.md
backend/.dockerignore
backend/.env.example
backend/Dockerfile
backend/alembic.ini
backend/alembic/env.py
backend/alembic/script.py.mako
backend/alembic/versions/0001_auth_foundation.py
backend/app/__init__.py
backend/app/api/__init__.py
backend/app/api/dependencies.py
backend/app/api/routes/__init__.py
backend/app/api/routes/auth.py
backend/app/api/routes/profiles.py
backend/app/cli.py
backend/app/config.py
backend/app/core/__init__.py
backend/app/core/permissions.py
backend/app/core/security.py
backend/app/db/__init__.py
backend/app/db/base.py
backend/app/db/session.py
backend/app/main.py
backend/app/models/__init__.py
backend/app/models/candidate.py
backend/app/models/session.py
backend/app/models/user.py
backend/app/schemas/__init__.py
backend/app/schemas/auth.py
backend/app/services/__init__.py
backend/app/services/auth_service.py
backend/app/services/google_identity.py
backend/pyproject.toml
backend/requirements-dev.lock
backend/requirements.lock
backend/tests/__init__.py
backend/tests/conftest.py
backend/tests/test_auth.py
backend/tests/test_foundation.py
backend/tests/test_google_crypto.py
backend/tests/test_google_identity.py
docker-compose.yml
docs/architecture.md
docs/database.md
docs/exam-lifecycle.md
docs/milestone-1.md
docs/security.md
frontend/.dockerignore
frontend/.env.example
frontend/Dockerfile
frontend/index.html
frontend/package-lock.json
frontend/package.json
frontend/src/App.tsx
frontend/src/components/Layout.tsx
frontend/src/features/auth/AuthProvider.tsx
frontend/src/features/auth/GoogleSignIn.tsx
frontend/src/main.tsx
frontend/src/pages/DashboardPage.tsx
frontend/src/pages/LoginPage.tsx
frontend/src/services/api.ts
frontend/src/styles.css
frontend/src/types/auth.ts
frontend/tests/auth.test.tsx
frontend/tests/setup.ts
frontend/tsconfig.json
frontend/vite.config.ts
```
