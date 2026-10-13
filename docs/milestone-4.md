# Milestone 4 — Live candidate test interface

The supplied CCK dashboard, navy exam header, question palette, question card,
and submission confirmation now connect to the Milestone 3 attempt APIs.
The independent development preview still works without login and never calls
the backend. No exam engine rewrite, added npm dependency, or new migration.

## Files and responsibilities

- `frontend/src/types/attempt.ts`: allowlisted candidate API contracts.
- `frontend/src/services/exam.ts`: candidate reads and CSRF-protected mutations.
- `frontend/src/services/api.ts`: retains structured conflict detail for explicit resolution.
- `frontend/src/features/exam/AssignedExams.tsx`: real assignments and configurable subject cards.
- `frontend/src/features/exam/LiveExam.tsx`: instructions, explicit start, current paper,
  navigation, review flags, clearing, option cross-out, save feedback, and Finish dialog.
- `frontend/src/features/exam/AnswerQueue.ts`: debounced serialized revisioned saves,
  acknowledgement tracking, safe retry, conflict choices, deadline/access locking.
- `frontend/src/features/exam/ServerDeadline.ts`: monotonic server-derived countdown.
- `frontend/src/features/exam/ExamSessions.tsx`: per-account in-memory queues retained
  across internal navigation; disposal on logout/account change; unsaved refresh warning.
- `frontend/src/features/exam/LiveSubmission.tsx`: server-verified receipt using the
  supplied CCK confirmation layout, persisted timestamp, question count, next subject.
- `App.tsx`, `AuthProvider.tsx`, dashboard/exam/submission pages, `ExamHeader.tsx`,
  `QuestionRenderer.tsx`, and `index.css`: integrate the live flow and keep the templates.
  The campus crop remains `object-position: 50% 80%`.
- Backend attempt schema/service: assigned summaries add `subjects`, containing only
  `exam_subject_id`, `name`, `duration_minutes`, and `sequence`. No prompts/keys.
- `frontend/tests/auth.test.tsx`: authentication fixtures isolated from exam reads.
- `frontend/tests/exam-state.test.ts`, `live-exam.test.tsx`: synchronization/timer and workflow checks.
- `backend/tests/test_attempts.py`: verifies ordered safe summaries without starting an attempt.
- README, architecture, security, lifecycle, and frontend documentation updated.

Database migrations remain `0001_auth_foundation`, `0002_exam_domain`, and
`0003_attempt_engine`. Use `alembic upgrade head` as usual.

## Behavior

Real mode requires a verified registered Google session and an active exam
assignment. The dashboard lists only assigned exams. Open instructions, open the
authorized exam, then explicitly start the next subject. The backend rechecks
eligibility, authorization, ordering, and schedule on every relevant action.
The live header has no subject selector. Names/order/durations come from server data.

Refresh reloads the same attempt, deadline, and server-saved answers. MCQ selection,
Unicode short answers (up to 500 characters), clearing, and review flags save as
full snapshots after a 350 ms debounce. Saves serialize; edits made during a slow
request retain their newer draft and use the newly acknowledged revision next.
A lost acknowledgement is retried with its exact original payload. Conflicting
stale data pauses that question until the candidate chooses the server answer or
explicitly saves their draft against the current revision. Cross-out affects
presentation only and never changes an answer or score.

The countdown uses `expires_at - server_time` anchored to `performance.now()`.
It conservatively subtracts request transit time and does not extend an existing
anchor during checks. Device date changes do not extend time. State checks occur
every 15 seconds while active, immediately when the display reaches zero, every
5 seconds while awaiting expiry confirmation, and on return to the visible tab.
Controls lock at zero or a save rejection for closed/unauthorized access. Backend
timing checks remain decisive even if the displayed timer is inaccurate or the
browser is suspended. Keep the expiry worker running separately.

Finish confirms the unanswered count, blocks edits, waits for all saves, and only
then requests submission. A save or submission failure does not show success.
The confirmation route fetches server state again: a URL alone is never a receipt.
The next-subject button opens its readiness screen; it does not start its timer.
Final completion uses the persisted exam status once all subjects close.
No scores are sent to the browser.

Background `/me` checks preserve an already verified profile/drafts on network
failure, with a visible warning. Server denial clears the profile and queues.
Backend access is checked regardless of frontend state. Pending drafts survive
internal app navigation within that account; exam dashboard links flush before
leaving. A browser refresh/close warns when unsaved changes remain.

## Run locally

Install/configure the tools and environment files from the root README first.
From the repository root, use separate Ubuntu/WSL terminals:

```bash
docker compose up -d db
```

```bash
cd /home/mr_laptop/cck-digital-test/backend
source .venv/bin/activate
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

```bash
cd /home/mr_laptop/cck-digital-test/backend
source .venv/bin/activate
python -m app.expiry_worker
```

```bash
cd /home/mr_laptop/cck-digital-test/frontend
npm install
npm run dev
```

Open `http://localhost:5173`. In PowerShell, use Linux npm through WSL:

```powershell
wsl -d Ubuntu -- bash -ic 'cd /home/mr_laptop/cck-digital-test/frontend && npm run dev'
```

If port 5173 is already occupied by this frontend, use that running server rather
than starting a second one. Set `VITE_ENABLE_UI_PREVIEW=false` in `frontend/.env`
and restart Vite to use the live flow. The local preview remains enabled for
the project owner's design exploration. Configure matching Google web client IDs,
register the approved candidate/admin with the CLI, and use the Milestone 2/3 admin
APIs to assemble, assign, schedule, and authorize an exam. No authentication bypass
or automatic sample admission data was added. Staff portals remain later milestones.

## Verification and limits

Frontend tests cover the preserved auth/preview interfaces plus debouncing,
slow-request edits, lost acknowledgements, stale conflicts, account disposal,
device-date changes, deadline locking, configurable assignments, explicit start,
Urdu input, refresh/resume, navigation/review, cross-out, save-before-submit,
submission failure, expiry receipt, unsaved warnings, and React StrictMode.
The stateful HTTP fixtures exercise the real API client and CSRF headers.
They are component/integration tests rather than a real Google/browser examination.

Final checks: 70 frontend tests passed; TypeScript/production build passed;
125 backend tests passed against disposable PostgreSQL 16.2, including migration
and concurrency checks; Python lint, format, and strict typing passed. The earlier
quick backend run passed 120 tests with four expected PostgreSQL-only skips before
the new summary test was added. The existing upstream Starlette/httpx TestClient
deprecation warning remains. Local runtime is Python 3.14; Docker/CI target
Python 3.12 and PostgreSQL 17 and were not executed locally.

The first PostgreSQL run failed at setup because the temporary server was started
with default port/socket settings. Restarting it with the intended private socket
and port resolved the mismatch; the complete rerun passed. Auth tests' original
sequential fetch fixtures also needed to isolate the new assignment read. Their
assertions now expect real assignments/empty states; separate live workflow tests
exercise the actual HTTP client. The frontend dev server responds successfully
at `http://localhost:5173`.
The disposable database's shutdown also exceeded `pg_ctl`'s timeout while flushing
its checkpoint; the process then completed shutdown safely without forced termination.

The live Google popup acceptance check still requires configured credentials and
approved accounts. The normal local PostgreSQL/Docker setup still needs the README
environment steps. Database tests use a separate disposable PostgreSQL instance
and isolated schemas, leaving normal data/environment files unchanged.

Unsynchronized changes are currently in memory, so refresh/offline browser closure
can lose them despite the warning. At expiry, only server-saved answers are included;
the receipt discloses any remaining local changes. IndexedDB, automatic reconnect
retry/backoff, crash recovery, cross-tab coordination, and persistent retry queues
are Milestone 5. Cross-out preferences do not survive refresh. Device readiness,
admin/proctor/examiner portals, grading/results, audit logging, full browser E2E/load
testing, and production deployment remain later milestones. Do not conduct real
admission examinations yet.

Next recommended milestone: **Milestone 5 — Resilience**, preserving these templates.
