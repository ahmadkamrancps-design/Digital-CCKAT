# Milestone 6 — Admin portal handover

Completed on 13 October 2026. The supplied CCK login, candidate dashboard,
exam, and submission templates remain in place. A separate administration portal
now manages candidates, configurable subjects, questions, exam papers, scheduling,
publication, and start authorization. No proctor dashboard or grading engine was
implemented in this milestone.

## Architecture and behavior

- `/admin` requires an authenticated, active ADMIN account. The backend enforces
  the same role for every administrative endpoint; mutations also require the
  configured origin and session CSRF token. Candidate preview grants no admin
  access. Candidate, proctor, and examiner roles cannot read question-bank keys.
- Candidate management supports create/edit, search by name/email/roll number,
  status and assigned-exam filters, disabling, and exam assignment/revocation.
  Email, Google subject, or eligibility changes revoke existing login sessions.
  Candidate updates cannot change roles or reset attempts.
- UTF-8 CSV imports are reviewed before submission and contain 1–500 new records.
  Backend validation and database constraints apply to every row. The import and
  its staff action records commit in one transaction; a late duplicate rejects
  the whole batch. Failed imports preserve the supplied text for correction.
- Subjects are configurable. Exams select subjects, independent durations, and
  order. Reordering is atomic and rejects a changed subject list. No English,
  Mathematics, or Urdu identifiers are built into the administration architecture.
- The question bank supports MCQ and SHORT_ANSWER, marks, archive/reactivation,
  subject/type/status/search filters, direction, and language. EXACT, NUMERIC,
  and MANUAL settings are stored for later backend grading. Prompts are rendered
  as text; arbitrary HTML is never executed. Urdu text uses Unicode and local RTL.
- The paper builder selects and orders up to 200 questions, with optional marks
  overrides. Server responses supply totals. Failed saves retain the draft.
  Existing backend rules prevent changes to linked questions, authorized papers,
  and exams with attempts; the interface also explains these locks.
- Schedule inputs use the administrator device's displayed time zone and send
  timezone-aware UTC timestamps. Scheduled end remains a server-enforced cutoff.
  New portal exams start unpublished. Publishing validates the papers; enabling
  starts is a separate action and validates them again.
- Unpublishing pauses new exam/subject starts. It does not reset an existing
  attempt, extend a deadline, or discard active answers. Unstarted unpublished
  and archived assignments are hidden; existing attempts remain resumable.
- Result controls record a planned release time and keep results withheld.
  Release requests are rejected by the backend until Milestone 8 implements
  grading and verifies release eligibility. The planned date does not release
  results automatically.
- Successful administrative mutations append a safe staff action record in the
  same transaction. The history lists actor/record identifiers, action, and
  server timestamp, without credentials or candidate answers.

## Files created or changed

| Area | Files |
| --- | --- |
| Backend management | New `app/api/routes/admin_management.py`, `app/services/admin_management_service.py`, `app/schemas/admin_management.py` |
| Staff action records | New `app/models/audit.py`, `app/api/admin_audit.py`; updated domain/attempt admin routes and domain commit helper |
| Exam controls | Updated `app/models/exam.py`, `app/schemas/exam_domain.py`, `app/services/exam_domain_service.py`, `app/services/attempt_service.py` |
| Registration | Updated `app/main.py`, `app/models/__init__.py` |
| Migration | New `alembic/versions/0004_admin_portal.py` |
| Backend tests | New `tests/test_admin_management.py`; updated `tests/test_attempts.py`, `tests/test_foundation.py` |
| Admin interface | New `frontend/src/features/admin/`: `AdminLayout.tsx`, `CandidatesPage.tsx`, `SubjectsPage.tsx`, `QuestionsPage.tsx`, `ExamsPage.tsx`, `PaperBuilder.tsx`, `StaffActionsPage.tsx`, `candidateCsv.ts`, `shared.tsx`, `admin.css` |
| API and routes | New `frontend/src/services/admin.ts`, `frontend/src/types/admin.ts`; updated `App.tsx`, `pages/DashboardPage.tsx` |
| Frontend tests | New `frontend/tests/admin.test.tsx`, `frontend/e2e/admin.spec.ts`, `frontend/e2e/fixtures.ts`; updated resilience suite to use the shared browser fixture |
| Recovery regression found during CI | Updated `frontend/src/features/exam/AnswerQueue.ts`, `frontend/tests/exam-state.test.ts`, `frontend/tests/live-exam.test.tsx` |
| Documentation | Updated README, architecture, database, lifecycle, security, and frontend structure; this handover |

Backend paths in this table are relative to `backend/`. No runtime dependency
was added and the candidate stylesheet was preserved.

## Database migration

Run `alembic upgrade head` to apply `0004_admin_portal`, following
`0003_attempt_engine`. It adds:

- `exams.is_published`: non-null boolean. Legacy exams retain published visibility
  to preserve the established API workflow; newly created portal exams explicitly
  set this false. Start authorization remains independent.
- `exams.results_released`: non-null boolean, initially false.
- `exams.result_release_at`: nullable timezone-aware planned timestamp.
- `audit_events`: UUID id, restrictive actor foreign key, action, target UUID,
  and server timestamp.

The upgrade, downgrade to 0003, re-upgrade, preserved exam data, and Alembic
schema comparison were tested on PostgreSQL. Downgrading removes the new staff
history and result/publication settings; back up before using a downgrade.

## Administration workflow

1. Configure PostgreSQL and Google as described in the root README, apply the
   migration, and provision an approved ADMIN using the CLI below.
2. Set `VITE_ENABLE_UI_PREVIEW=false`, restart Vite, and sign in with that approved
   Google account. Open **Open administration portal** or `/admin`.
3. Create subjects and questions. Create an unpublished exam, configure its
   subjects/durations, and build each ordered paper.
4. Register/import approved candidates and assign them to the exam.
5. Set the schedule, verify every paper, publish the exam, and enable starts.
   Pause starts before making allowed changes to an exam with no attempts.
6. Review staff action history. Keep results withheld pending the grading milestone.

Example CSV (use actual approved registrations, not these examples):

```csv
email,full_name,roll_number,google_subject,status
candidate@gmail.com,Test Candidate,CCK-104,,APPROVED
other@gmail.com,"Candidate, Example",CCK-105,,DISABLED
```

Only the first three headers are required. Optional blank status defaults to
APPROVED, shown explicitly in the import review. An imported Google subject must
be independently verified. Import does not overwrite existing candidates.

## Running the system

Use Ubuntu/WSL terminals. Preserve existing `.env` files; configure Google client
IDs and enable Docker Desktop's Ubuntu WSL integration if still needed. From the
repository root:

```bash
docker compose up -d db
```

Backend terminal:

```bash
cd /home/mr_laptop/cck-digital-test/backend
source .venv/bin/activate
alembic upgrade head
python -m app.cli register-staff --email "approved-admin@gmail.com" --name "CCK Administrator" --role ADMIN
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

Provision the administrator once. In another backend terminal:

```bash
cd /home/mr_laptop/cck-digital-test/backend
source .venv/bin/activate
python -m app.expiry_worker
```

Frontend terminal:

```bash
cd /home/mr_laptop/cck-digital-test/frontend
npm ci
npm run dev
```

Open `http://localhost:5173`. Reuse an existing server on that port. Windows
PowerShell users can launch Ubuntu's Node environment with:

```powershell
wsl -d Ubuntu -- bash -ic 'cd /home/mr_laptop/cck-digital-test/frontend && npm run dev'
```

## Verification

| Check | Result |
| --- | --- |
| Backend quick suite | 144 passed; 4 PostgreSQL-only checks skipped |
| Full PostgreSQL suite before the additional archived-visibility case | 147 passed, including migrations and concurrency |
| Full PostgreSQL 17 suite in GitHub CI | 148 passed |
| Final PostgreSQL attempt regression | 33 passed; the added unpublished/archived parameter cases both passed separately |
| Frontend unit/component suite | 109 passed across 8 files |
| Real Chromium workflow suite | 8 passed: 3 admin and 5 recovery scenarios |
| TypeScript and Vite production build | Passed |
| Backend Ruff lint/format and strict mypy | Passed |

The browser suite includes 3 administrator scenarios and the existing 5 recovery
scenarios. It exercises candidate creation/disable and rejected imports, MCQ and
numeric question creation, paper selection/order/marks and failed-save retention,
publication and configuration locking, role exclusion, offline reload/reconnection,
lost acknowledgements, tab ownership, expiry, and stale-answer conflicts.

Failures investigated and corrected:

- An admin test's ambiguous label selector timed out at the question type control.
  It now selects the named combobox explicitly; the full admin scenario passes.
- Adding an exam subject retained the previous next-sequence default. The form
  now derives its next value from the saved subject response; the browser test
  verifies it advances to 2 after the first subject.
- One existing frontend unit scenario timed out while a production build and
  suites competed for local resources. The complete unit suite passed when run
  without a simultaneous build; its assertions and timeout were retained.
- Recovery browser traces showed external Google Fonts requests stalling page
  navigation. Both browser suites now share a fixture that blocks those requests
  and uses the system font fallback. Application styling remains unchanged.
- A second CI run found a real recovery race: a reconnect/manual retry during a
  failed save's local checkpoint could clear its error and leave the pending
  answer without another upload. Deterministic regressions failed before the fix.
  Retry and reconnect now await the active drain before clearing errors and
  starting fresh serialized work. Explicit conflict choices use the same path.
  Tests cover both retry actions, deadline expiry during the wait, and conflict
  resolution while persistence is pending. Existing test timeouts were retained.

Local PostgreSQL checks used a temporary PostgreSQL 16.2 instance. GitHub CI
uses PostgreSQL 17 and Python 3.12; local Python was 3.14. The existing local
Starlette/httpx test-client deprecation warning does not affect these results.

Backend checks:

```bash
cd backend
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app
.venv/bin/python -m pytest -q
TEST_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/DISPOSABLE_TEST_DB .venv/bin/python -m pytest -q
```

Frontend checks:

```bash
cd frontend
npm test
npm run build
npx playwright install --with-deps chromium
npm run test:e2e
```

Use a disposable PostgreSQL database for tests. Browser tests use an isolated
Vite server on 5174 and stateful synthetic API responses with real Chromium;
they do not constitute an actual Google-to-production-backend acceptance test.

## Known limits and next milestone

The normal local Google credentials and Docker/PostgreSQL setup still need the
external configuration described in README. Tests used an isolated PostgreSQL
instance and fixture identities; no live administrator was silently provisioned
and existing environment files were retained. Candidate preview remains available.

Staff records are provisioned through the CLI. This milestone records staff
mutations, rather than all candidate/proctor browser events. Audit storage is
append-oriented through the application, not protected against a privileged
database operator changing rows. Imports are create-only and no private CSV
exports were added. Draft metadata does not have conflict revisions for concurrent
administrators; exam locks and constraints protect exam integrity.

Result release, grading, proctor monitoring, security hardening, load qualification,
and production operations remain in their designated milestones. The application
is not production-ready for real examinations.

Next: **Milestone 7 — Proctor System**. Keep the candidate template and reuse
server-authoritative attempt state. Proctor access should expose status/events
without candidate answers.
