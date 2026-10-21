# CCK Digital Entry Test

Foundation, exam domain, attempt engine, candidate interface, recovery, administration,
proctor monitoring, grading/results, security hardening, and Milestone 10 deployment/recovery rehearsals for Cadet College Kohat's entry-test platform. React +
TypeScript, FastAPI, SQLAlchemy 2, PostgreSQL, and Alembic. Candidates sign in with
their admissions roll number, full name, and father's name. Staff use Google Identity Services.
The supplied CCK frontend now supports real assigned exams, server-derived timers,
revisioned autosave, persistent answer recovery, reconnection, navigation/review, and confirmed submission. A separate
development preview remains available without login.
The system is not approved for real examinations.

## Required software

- Python 3.12+ with pip and virtual-environment support (3.12 is the Docker/CI baseline).
- Node.js 22.12+; Node 24 LTS is recommended, with npm.
- Git.
- Docker Engine/Desktop with Compose v2, or an existing PostgreSQL 17 instance.
- A Google Cloud OAuth web client for staff sign-in; candidate sign-in needs no Google setup.

In WSL, open Docker Desktop → Settings → Resources → WSL Integration, enable
this distro, and choose Apply & restart. Verify `docker compose version` afterward.
On Debian/Ubuntu,
install the venv package for your Python version if `python3 -m venv` reports
missing `ensurepip`. If Python's global pip already exists, this supported fallback
can bootstrap the partially created venv without installing system packages:
`python3 -m pip --python .venv/bin/python install pip -r requirements-dev.lock`.

## Local setup

From the repository root:

```bash
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
docker compose up -d db
```

Example database credentials are for local development only. If you change them
or the exposed port, update `backend/.env`'s `DATABASE_URL` to match. Existing
PostgreSQL volumes keep their original database/user/password; changing Compose
environment variables does not rotate an initialized database's credentials.

In the backend terminal:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.lock
python -m pip install --no-deps -e .
alembic upgrade head
python -m app.cli register-candidate \
  --name "Test Candidate" \
  --father-name "Test Father" \
  --roll-number "CCK-104"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log --no-proxy-headers --no-server-header
```

Only provision candidates with actual admissions approval. The CLI creates a user
and candidate in one transaction; duplicate emails, roll numbers, and identities
are rejected. It has no public registration endpoint. To provision a staff account:

```bash
python -m app.cli register-staff \
  --email "approved-staff@gmail.com" --name "Staff Member" --role ADMIN
```

Apply migration `0006_candidate_login` with `alembic upgrade head` before using the
new candidate login. Existing candidates need a verified father's name entered by
an administrator. Names and rolls must come from the official admission record;
this app does not issue admission roll numbers or yet synchronize with cck.edu.pk.
For bulk registration, administrators can import CSV using
`roll_number,full_name,father_name` headers; `email,google_subject,status` are optional.
Email is optional for candidates. See [candidate login setup](docs/candidate-login.md).

Staff roles are ADMIN, PROCTOR, EXAMINER. Approved ADMIN users can open `/admin`
or choose **Open administration portal** on their dashboard. Candidate management,
CSV import, subject configuration, question bank, exam builder, scheduling,
publication, and start controls are implemented. PROCTOR users open `/proctor`
to monitor exams explicitly assigned by an administrator. ADMIN users can monitor
all exams. EXAMINER users open `/grading` to review manual responses for assigned
exams. Candidate preview grants no staff access.

After pulling Milestone 6, run `alembic upgrade head` before starting the backend.
Migration `0004_admin_portal` adds publication/result-control fields and staff
action records. See [Milestone 6 handover](docs/milestone-6.md) for the admin workflow,
CSV format, migration compatibility, and current result-release limits.

The administration portal opens on an overview with database totals, recent exams,
staff activity, and shortcuts for common tasks. Its CCK sidebar leads to candidate
registration/import, subjects, the question bank, exam building, and action history.
Exam pages group scheduling, papers, staff assignments, publication, starts, and
results into clearly labeled sections. See the [administration guide](docs/administration-portal.md).

After pulling Milestone 7, run `alembic upgrade head` to apply
`0005_proctor_monitoring`. Provision approved proctor staff once:

```bash
python -m app.cli register-staff --email "approved-proctor@gmail.com" --name "CCK Proctor" --role PROCTOR
```

In `/admin`, open an exam and use **Proctor access** to assign that staff account.
Sign in as the proctor and choose **Open proctor monitoring** on the dashboard.
Status updates poll about every five seconds. Candidate heartbeats normally send
every ten seconds while a subject is active. The portal shows reported question
position, connection freshness, server-derived time, and safe session events;
it exposes no candidate answers. See [Milestone 7 handover](docs/milestone-7.md).

After pulling Milestone 8, run `alembic upgrade head` to apply `0007_grading_results`.
MCQ, EXACT, and NUMERIC responses are automatically graded when subjects close.
Provision approved examiners with `python -m app.cli register-staff --email "approved-examiner@gmail.com" --name "CCK Examiner" --role EXAMINER`,
then assign them through **Examiner access** in the exam's admin page. Use `/grading`
for manual marks and audited corrections. Administrators can backfill automatic grades
for older completed attempts there. Pause starts and finish all grading before
authorizing result release. Candidates see only released totals at `/results`.
The existing free-access preview includes a labeled sample result at the same route.
See [Milestone 8 handover](docs/milestone-8.md) for rules, endpoints, and verification.

After pulling Milestone 9, install `requirements-dev.lock` again (certificate caching
adds CacheControl/msgpack), then run `alembic upgrade head` for
`0008_security_hardening`. It adds authentication security events and PostgreSQL
guards preventing changes to audit/session-event/grade/security history. All
existing answer and exam tables are preserved. New sign-in limits and body caps
have defaults; local preview and candidate login fields remain unchanged.
See [Milestone 9 handover](docs/milestone-9.md) for the security review, test evidence,
maintenance command, runtime-role template, and production limitations.

Run the expiry worker in a separate backend terminal so deadlines are recorded
even when no browser is connected:

```bash
cd backend
source .venv/bin/activate
python -m app.expiry_worker
```

It polls every second by default. `python -m app.expiry_worker --once` processes
one batch for operational checks. API requests also reconcile expiry and reject
late writes even if the worker is stopped. Restarting either process preserves
stored deadlines and answers. Use a supervised worker process in deployment.

In the frontend terminal:

```bash
cd frontend
npm ci
npm run dev
```

From Windows PowerShell, launch the frontend through Ubuntu's interactive shell:

```powershell
wsl -d Ubuntu -- bash -ic 'cd /home/mr_laptop/cck-digital-test/frontend && npm run dev'
```

The interactive shell loads the Linux Node installation managed by nvm. A
noninteractive `bash -lc` shell can skip that setup and pick Windows npm from the
inherited PATH. Windows npm cannot run the Linux-installed Vite executable from
a WSL UNC directory. Keep installation and execution inside Ubuntu.

Open **http://localhost:5173** (use localhost consistently). API docs are at
http://localhost:8000/docs. Vite proxies `/api` to the backend; there is no need to
put a backend URL in browser code. Keep `FRONTEND_ORIGIN` exactly
`http://localhost:5173` for these commands. A different host/port needs matching
backend and Google-origin configuration.

## Candidate login and design preview

To explore the UI before configuring Google or PostgreSQL, set
`VITE_ENABLE_UI_PREVIEW=true` in `frontend/.env` and run `npm run dev`.
Open `http://localhost:5173/dashboard` or choose **Explore without login** on the
login page. Development preview uses sample candidate details and makes no
authentication API calls. **My Exam** opens `http://localhost:5173/exam`, an
interactive layout preview with English, Mathematics, and Urdu sample questions.
Use the subject selector to try MCQs and short answers, question navigation,
review flags, and the local Finish dialog. Finish opens the submission design
with a green check, sample time, subject/question details, and a Continue button
for the next subject. View the design directly at `http://localhost:5173/submission`.
It is explicitly labeled as a preview, not a server receipt. The timer is paused; responses live
only in page memory and reset on refresh. It does not start a real exam, persist
answers, create a server session, or change backend authorization. Instructions,
system check, profile and help include exam guidance, local device checks, sample
registration details and support information; preview makes no backend requests.

Production builds ignore this flag and require authentication. Set it to `false`
and restart Vite when testing actual candidate or staff sign-in.

For a **read-only administration design preview**, open
**http://localhost:5173/preview/admin** with that development flag enabled, or choose
**Explore administration design** on the login page. Sample candidates, exams,
subjects, questions and staff actions show the layout without creating a session
or contacting the backend. Search/filter controls work locally; write controls are
disabled. This preview grants no access to `/admin` or its APIs and is absent from
production routing.

With preview disabled and approved candidate records loaded, the dashboard displays assigned
exams and configurable subject cards. Open an exam's instructions, explicitly
open the authorized exam, then choose **Start subject**. Merely viewing instructions
does not start its timer. Refresh restores the existing attempt and server-saved
answers. Finish saves pending answers before requesting submission; the confirmation
page verifies the server receipt. See [Milestone 4 handover](docs/milestone-4.md).
Answers and review flags are preserved in IndexedDB before upload. Temporary network
failures retry automatically; refresh reconciles local drafts against fresh server
answers after authentication. Conflicts require an explicit choice. Expired drafts
cannot be uploaded. The live exam requires IndexedDB and Web Locks on localhost
or HTTPS. Wait for **Saved** before signing out: explicit sign-out clears local
recovery copies. See [Milestone 5 handover](docs/milestone-5.md) for recovery limits.

## Configure staff Google sign-in

Open **Staff sign-in** below the candidate form. Candidates do not need these steps.

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create or
   select a dedicated project.
2. In Google Auth Platform, configure Branding, Audience, and Data Access for
   sign-in profile/email identity. If the project is in testing mode, add the
   candidate/staff Google accounts as test users where required.
3. Create an OAuth client with application type **Web application**.
4. Add Authorized JavaScript origins `http://localhost` and
   `http://localhost:5173`. This implementation uses a popup callback; no redirect
   URI or Google client secret is needed.
5. Put the same public web client ID in `backend/.env` as `GOOGLE_CLIENT_ID` and
   in `frontend/.env` as `VITE_GOOGLE_CLIENT_ID`.
6. Restart both development servers and approve a staff account with the CLI.

Never place a client secret or database credential in a `VITE_` variable. Vite
variables are public browser configuration. Missing Google configuration leaves
the app showing a disabled Continue with Google button and setup message;
sign-in becomes available after you configure the matching client IDs and restart
both servers. The configured button opens Google's account selection popup and
exchanges the returned credential with `/api/auth/google`. Backend approval is
still required. Missing Google configuration does not block candidate sign-in.

Google's [setup instructions](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid)
and [verification guidance](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token)
explain web origins, audience validation, and stable Google `sub` identifiers.
For accounts outside Gmail/Workspace, preapprove the independently verified stable
Google subject using the CLI's `--google-subject` option. Email matching alone is
deliberately insufficient for those accounts. See [security design](docs/security.md).

## Verify candidate sign-in

1. Start PostgreSQL; apply migrations; run both servers.
2. Disable UI preview and sign in with the approved roll number, full name, and father's name.
3. Confirm the dashboard shows the expected candidate name and roll number.
4. Refresh and reopen `/dashboard`; the server session should restore access.
5. Sign out; revisiting `/dashboard` must show sign-in.
6. Try an unknown roll number or incorrect name; access must be denied with no
   new user/candidate/session created.
7. Confirm only assigned exams appear and no result data is exposed.

These manual steps require PostgreSQL and approved admissions records. Staff Google sign-in
additionally requires your actual Google client and accounts. Automated
tests substitute Google's certificate retrieval or verifier at explicit dependency
boundaries; there is no development bypass in the application.

## Checks

From `backend/` with the virtual environment activated:

```bash
pytest -q
ruff check .
ruff format --check .
mypy app
alembic check
```

`alembic check` requires the development PostgreSQL database to be running and
migrated. The quick pytest suite uses SQLite for database unit tests and skips
the PostgreSQL migration roundtrip test. To run the authentication and domain
suites against PostgreSQL plus actual migrations, create a separate test database:

```bash
docker compose exec db createdb -U cck cck_digital_test_test
```

Then, from `backend/`:

```bash
TEST_DATABASE_URL=postgresql+psycopg://cck:cck_local_only@localhost:5432/cck_digital_test_test pytest -q
```

Tests use isolated random schemas and clean them up. CI runs the quick and
PostgreSQL suites, Python checks, frontend tests/build, and Chromium recovery tests.

From `frontend/`:

```bash
npm test
npm run typecheck
npm run build
npx playwright install --with-deps chromium
npm run test:e2e
```

Browser tests start a separate frontend on port 5174 with synthetic API responses,
real IndexedDB, and real Web Locks. They do not require Google credentials or a
running backend. The normal development server on port 5173 can remain running.

## Implemented endpoints

| Endpoint | Access | Purpose |
| --- | --- | --- |
| GET /api/health | Public | Process liveness |
| GET /api/health/ready | Public | Database and initial schema availability |
| POST /api/auth/google | Exact allowed origin + Google credential | Verify identity, approval, issue session |
| POST /api/auth/candidate | Exact allowed origin + three admissions fields; persistent rate limits | Match approved candidate and issue session |
| POST /api/auth/logout | Session + exact origin + CSRF header | Revoke session |
| GET /api/me | Approved user session | Restore public account/profile state |
| GET /api/candidate/me | Approved CANDIDATE role | Protected candidate profile |
| GET /api/admin/subjects, /exams, /questions | Approved ADMIN session | Paginated domain lists |
| GET/POST /api/admin/candidates | ADMIN; mutations require origin + CSRF | Search/filter or create approved candidate records |
| PUT /api/admin/candidates/{id} | ADMIN + origin + CSRF | Edit/disable candidate and revoke changed-access sessions |
| POST /api/admin/candidates/import | ADMIN + origin + CSRF | Atomic import of up to 500 validated candidate rows |
| GET /api/admin/candidates/{id}/assignments | ADMIN | Inspect that candidate's assignments |
| PUT /api/admin/exams/{id}/subject-order | ADMIN + origin + CSRF | Atomically reorder all exam subjects |
| POST /api/admin/exams/{id}/publication | ADMIN + origin + CSRF | Publish/unpublish; unpublishing pauses new starts |
| POST /api/admin/exams/{id}/result-release | ADMIN + origin + CSRF | Authorize/schedule completed results or withhold them |
| GET /api/admin/examiners | ADMIN | List approved examiner accounts |
| GET/PUT /api/admin/exams/{id}/examiners[/{user_id}] | ADMIN; writes require origin + CSRF | Inspect, assign, or revoke examiner scope |
| GET /api/grading/exams, /exams/{id}/attempts, /exams/{id}/queue | ADMIN or exam-assigned EXAMINER | Grading progress and manual responses |
| GET /api/grading/answers/{id}/history | ADMIN or exam-assigned EXAMINER | Preserve and inspect grade revisions |
| POST /api/grading/answers/{id}/grade | Scoped grading role + origin + CSRF | Record manual marks with stale-write protection |
| POST /api/admin/attempts/{id}/grade | ADMIN + origin + CSRF | Backfill automatic grades for completed attempts |
| GET /api/candidate/results | Owning, approved CANDIDATE | Released subject totals and percentage; withheld marks are absent |
| GET /api/admin/actions | ADMIN | Paginated staff action history |
| GET /api/admin/proctors | ADMIN | List active proctor accounts without identity secrets |
| GET /api/admin/exams/{id}/proctors | ADMIN | Inspect assigned proctors |
| PUT /api/admin/exams/{id}/proctors/{user_id} | ADMIN + origin + CSRF | Assign/revoke exam-specific monitoring access |
| GET /api/proctor/exams | Assigned PROCTOR or ADMIN | List permitted monitoring exams |
| GET /api/proctor/exams/{id}/sessions | Assigned PROCTOR or ADMIN | Safe candidate status, expiry, position, and contact freshness |
| GET /api/proctor/attempts/{id}/events | Assigned PROCTOR or ADMIN | Allowlisted session event history without answers |
| POST /api/candidate/attempts/{id}/presence | Owning CANDIDATE + origin + CSRF | Rate-limited position/heartbeat and browser reports |
| POST /api/admin/subjects, /exams, /questions | ADMIN + origin + CSRF | Create domain records |
| PUT /api/admin/subjects/{id}, /exams/{id}, /questions/{id} | ADMIN + origin + CSRF | Replace editable records |
| GET/POST /api/admin/exams/{id}/subjects | ADMIN; mutations also require origin + CSRF | Configure durations and subject order |
| PUT/DELETE /api/admin/exams/{id}/subjects/{id} | ADMIN + origin + CSRF | Edit/remove an exam subject |
| POST /api/admin/questions/{id}/archive | ADMIN + origin + CSRF | Archive an unassigned question |
| GET/PUT /api/admin/exam-subjects/{id}/questions | ADMIN; mutations also require origin + CSRF | Read/replace an ordered paper |
| PUT /api/admin/exams/{id}/candidates/{candidate_id} | ADMIN + origin + CSRF | Assign/revoke candidate eligibility |
| POST /api/admin/exams/{id}/start-authorization | ADMIN + origin + CSRF | Allow/pause new starts |
| GET /api/candidate/exams | Approved CANDIDATE | List own active assignments and attempt IDs |
| POST /api/candidate/exams/{id}/attempt | CANDIDATE + origin + CSRF | Start/resume one logical exam attempt |
| GET /api/candidate/attempts/{id} | Owning assigned CANDIDATE | Resume state and server timestamps |
| POST /api/candidate/attempts/{id}/subjects/{sid}/start | Owning CANDIDATE + origin + CSRF | Start the next ordered subject |
| GET /api/candidate/attempts/{id}/subjects/{sid}/questions | Owning CANDIDATE | Safe paper and saved answers for a started subject |
| PUT /api/candidate/attempts/{id}/subjects/{sid}/answers/{exam_question_id} | Owning CANDIDATE + origin + CSRF | Revision-protected answer/review save |
| POST /api/candidate/attempts/{id}/subjects/{sid}/submit | Owning CANDIDATE + origin + CSRF | Lock subject and return authoritative state |
| POST /api/candidate/attempts/{id}/submit | Owning CANDIDATE + origin + CSRF | Return final receipt after all subjects close |

Individual exam/question GET routes are also available. Question responses contain
answer keys **only within ADMIN-protected routes**. Candidate paper schemas
exclude keys, accepted values, and grading configuration. See
[Milestone 2 handover](docs/milestone-2.md) for domain examples and
[Milestone 3 handover](docs/milestone-3.md) for attempt setup and API contracts.

## Documentation and next step

- [Architecture and repository structure](docs/architecture.md)
- [Frontend source structure and image assets](docs/frontend-structure.md)
- [Database and migration design](docs/database.md)
- [Authentication/security decisions and limitations](docs/security.md)
- [Future exam lifecycle constraints](docs/exam-lifecycle.md)
- [Milestone 1 handover and verification results](docs/milestone-1.md)
- [Milestone 2 handover, admin workflow, and verification results](docs/milestone-2.md)
- [Milestone 3 handover, attempt workflow, and verification results](docs/milestone-3.md)
- [Milestone 4 handover, live candidate interface, and verification results](docs/milestone-4.md)
- [Milestone 5 handover, offline recovery, and verification results](docs/milestone-5.md)
- [Milestone 6 handover, administration workflow, and verification results](docs/milestone-6.md)
- [Milestone 7 handover, proctor workflow, and verification results](docs/milestone-7.md)
- [Milestone 8 handover, grading/results workflow, and verification results](docs/milestone-8.md)
- [Milestone 9 handover, security review, and verification results](docs/milestone-9.md)
- [Milestone 10 handover and remaining acceptance gates](docs/milestone-10.md)
- [Production deployment, monitoring, and recovery](docs/production-operations.md)
- [Capacity profiles and supervised mock examination](docs/capacity-and-rehearsal.md)
- [GitHub setup and progress history](docs/version-control.md)

Milestone 10 preserves the CCK templates, admissions login, and development preview.
The deployment candidate is configured for `digital.cckat.edu.pk`, with a 7,000
simultaneous-candidate planning target. Production DNS/hosting/TLS, full capacity
and supervised acceptance tests, staff Google acceptance, stronger or supervised
candidate verification, and durable off-site/PITR recovery remain required.
See the handover and operational runbooks before any public deployment.
