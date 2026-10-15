# Milestone 9 — security review and hardening

The existing CCK candidate/admin/proctor/examiner templates, admissions login,
development preview, exam engine, offline recovery, and scoring remain in place.
This milestone hardens their boundaries and records remaining production risks.
Milestone 10 deployment and operational acceptance have not started.

## Review and implemented changes

| Area | Finding and resulting behavior |
| --- | --- |
| Authentication | Existing approved-record and staff Google checks retained. Google requests now share a PostgreSQL IP limit before verification. Concurrent successful sign-ins leave one valid logical session. |
| HTTP inputs | Nonempty API bodies require JSON. Authentication bodies are capped at 16 KiB; other bodies default to 2 MiB. Streaming or incorrect Content-Length cannot bypass the cap. Compressed input is rejected. |
| Throttling | Candidate limits retain their existing policy. IP buckets are checked before account buckets; blocked IPs cannot keep creating arbitrary roll buckets. Saturated counters avoid overflow, and first denials create bounded per-window events. |
| CSRF/CORS | Exact allowed origin, credentials-aware CORS, and synchronizer token checks retained. Non-ASCII CSRF input now returns 403 instead of causing an exception. Regression tests inspect the entire privileged route surface for wrong-role denial and mutation Origin/CSRF requirements. |
| Sessions | Opaque hashed credentials, HttpOnly/SameSite cookies, single-session rotation and revocation retained. Session expiry now uses database time. A bounded operator cleanup command removes expired sessions/buckets. |
| Google transport | CacheControl honors public certificate HTTP cache lifetimes. The worker shares a serialized transport with five-second network timeout; tokens/claims are never cached. A real RSA/certificate test verifies separate credentials and rejects an expired credential after a cache hit. |
| Audit and grades | New minimal authentication events; PostgreSQL statement triggers reject UPDATE/DELETE/TRUNCATE on audit, exam-event, grading, and authentication histories. Grade corrections still append revisions. |
| Database access | A tested runtime-role grant template permits normal application operations and history appends, while denying DDL, history rewrites, and Alembic changes. Development credentials are preserved; deployment must configure separate roles. |
| Candidate data | Existing explicit DTOs, assignment/ownership checks, private answer keys, unpublished-result suppression, immutable raw answers after closure, and plain React rendering reviewed. Existing functional/security tests retained. |
| Proxy and headers | Development proxy strips supplied forwarding headers. Backend container disables proxy-header trust, access logs, and the server header. API and development HTML gain framing defenses; production API gains HSTS. Full production HTML CSP belongs at the ingress. |
| Configuration | Invalid origin ports/whitespace and wildcard/URL-shaped hosts fail startup validation. Database credentials are excluded from settings repr. Safe startup/API error messages remain. |
| Dependencies/secrets | Python and npm audits report no known vulnerabilities at review time. CI adds audits, read-only repository permissions, credential-free checkout, and verified full-commit action pins. Real .env/build artifacts remain ignored; tracked credential-pattern review found no matches. |

Only public certificate caching adds application dependencies: CacheControl 0.14.4
and msgpack 1.2.3, pinned in `requirements.lock`. The frontend dependency lock is
unchanged. CI audit tooling runs separately from application dependencies.

## Files created

- `backend/alembic/versions/0008_security_hardening.py`
- `backend/app/core/http_security.py`
- `backend/app/models/security_event.py`
- `backend/app/services/login_throttle_service.py`
- `backend/app/auth_maintenance.py`
- `backend/ops/grant-runtime.psql`
- `backend/tests/test_security.py`
- `frontend/e2e/security.spec.ts`
- `docs/milestone-9.md`

## Files changed

- HTTP/configuration: `backend/app/main.py`, `backend/app/config.py`,
  `backend/app/api/dependencies.py`, `backend/app/api/routes/auth.py`,
  `backend/app/core/security.py`, `backend/app/core/clock.py`.
- Authentication/history: `backend/app/services/auth_service.py`,
  `backend/app/services/candidate_login_service.py`,
  `backend/app/services/google_identity.py`, `backend/app/models/__init__.py`,
  `backend/app/models/audit.py`, `backend/app/models/grading.py`.
- Setup/proxy: `backend/.env.example`, `backend/Dockerfile`,
  `backend/pyproject.toml`, `backend/requirements.lock`, `frontend/vite.config.ts`.
- Tests/CI: `backend/tests/test_auth.py`, `backend/tests/test_candidate_login.py`,
  `backend/tests/test_google_crypto.py`, `.github/workflows/checks.yml`.
- Documentation: `README.md`, `docs/architecture.md`, `docs/database.md`,
  `docs/security.md`.

## Migration and database operation

`0008_security_hardening` follows `0007_grading_results`. It adds `security_events`
and one schema-local trigger function with four statement triggers. It does not
modify existing exam, identity, answer, grade, or audit rows. Local upgrade preserved
their row counts; `alembic check` reports no schema drift. PostgreSQL roundtrip
tests verify downgrade/re-upgrade and the complete migration chain.

Downgrade removes the new security-event table and all four guards; it loses that
history and weakens protection. Do not use downgrade as an unreviewed live rollback.
Backups, recovery testing, and role separation are required before real examinations.

The operator role template is intentionally not applied to the existing development
account. Before deployment, provision a separate non-owner runtime role without
superuser, owner-role memberships, schema creation, role/database creation,
replication, or RLS bypass. Configure its password through the deployment secret
store, then run this as the migration owner in a dedicated CCK database/schema:

```bash
cd backend
psql --set=ON_ERROR_STOP=1 --single-transaction \
  --set=schema_name=public --set=runtime_role=cck_app \
  --file=ops/grant-runtime.psql
```

Supply connection details through a protected operator connection/service file;
do not paste passwords into shell commands. The template assumes the runtime role
already exists. Reapply reviewed grants after migrations. Owners can disable
triggers; this is not tamper-proof protection against a privileged operator.

## Verification

Local checks include Ruff lint/format, strict mypy, pip dependency consistency,
the complete quick backend suite, targeted PostgreSQL tests, all frontend unit
tests, TypeScript/production build, all existing browser workflows, and four new
browser security checks. PostgreSQL tests cover atomic concurrent throttle limits,
six simultaneous successful sign-ins, migration roundtrips, bulk history tampering,
runtime-role permissions, and bounded cleanup. A separate real Chromium → Vite →
FastAPI → PostgreSQL smoke verifies grading, publication, and result withdrawal
using isolated synthetic accounts/schema; it cleans up afterward.

The quick backend suite passes 263 tests with 10 PostgreSQL cases deliberately
skipped. The 139 frontend unit tests and 19 browser workflows pass. CI also runs the entire suite against
PostgreSQL 17/Python 3.12. Local targeted tests use PostgreSQL 16.2/Python 3.14.
There is a pre-existing Starlette/httpx TestClient deprecation warning, with no
application test failures attributable to it.

Initial checks exposed an obsolete oversized-body assertion and a test helper
depending on FastAPI's internal router layout. The schema validation test now stays
below the outer body cap, and route coverage uses public OpenAPI paths. These test
issues are resolved; the application rejects oversized data before validation.

Both `npm audit` and pip-audit of production/development locks reported no known
vulnerabilities on 14 October 2026. This is not a penetration test, artifact-hash
guarantee, or production security certification. CI runs the audits on every push/PR.

## Run locally

Use the Ubuntu/WSL shell for both frontend and backend. Reuse the existing local
PostgreSQL service; otherwise start Compose from the repository root:

```bash
docker compose up -d db
```

Backend, from the repository root in its own terminal:

```bash
cd backend
source .venv/bin/activate
python -m pip install -r requirements-dev.lock
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 \
  --no-access-log --no-proxy-headers --no-server-header
```

Frontend, in another terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. Development no-login preview remains controlled by
`VITE_ENABLE_UI_PREVIEW=true` in the ignored `frontend/.env`. Production builds
ignore the preview flag; preview grants no backend staff or exam privileges.
Keep real .env files and credentials out of Git. Staff Google setup remains
documented in the README; candidate login needs approved admissions data only.

Optional bounded cleanup, from `backend` with the venv activated:

```bash
python -m app.auth_maintenance --batch-size 1000
```

It is not scheduled automatically and never deletes exam answers or audit histories.

## Remaining risks and next milestone

Candidate roll/name/father-name details are personal information, not a private
authentication factor. Someone who knows them can impersonate a candidate. The
requested login and free testing preview are preserved; stronger or supervised
verification remains a production acceptance decision. Staff Google sign-in also
needs real configured-account acceptance and review of single-use nonce/replay
protection; the current ID token is reusable within Google's validity period.

Milestone 10 must configure and validate HTTPS, production HTML CSP/HSTS, trusted
ingress IP handling, connection/body/header timeouts and perimeter rate policy,
separate runtime/migration credentials, managed-device cleanup, security-event
retention/monitoring, backup restoration, load/concurrency limits, expiry-worker
operations, and a realistic mock examination. Failed malformed requests and broad
permission/CSRF denials are not yet in the persistent security-event trail. No
independent penetration test has been performed. These are explicit acceptance
gaps; this milestone does not make the platform production-ready.

Primary references: [OWASP REST security](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html),
[Google certificate caching](https://googleapis.dev/python/google-auth/latest/reference/google.oauth2.id_token.html),
[PostgreSQL triggers](https://www.postgresql.org/docs/17/sql-createtrigger.html),
[GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use).
