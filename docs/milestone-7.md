# Milestone 7 — Proctor system handover

Completed on 13 October 2026. This milestone adds a separate CCK proctor
workspace, exam-specific access assignments, candidate contact/position reporting,
and safe session event history. The supplied candidate login, dashboard, exam,
and submission templates are preserved. No grading or result release was added.

## Behavior and architecture

ADMIN users can monitor every exam. PROCTOR users can monitor only exams with
an active administrator-created assignment. Candidate, examiner, and anonymous
sessions cannot use monitoring endpoints. Candidate preview grants no staff
privileges. Proctors have read-only access: they cannot pause subjects, authorize
starts, extend time, change eligibility, inspect answers, or change marks.

The dashboard displays candidate name/roll number, exam state, current/next
subject, reported question position/count, original expiry, server-derived remaining
time, recent contact, and review-event count. Search supports Unicode names and
literal roll-number text. Active-subject filtering and 50-row paging limit each
roster request. Event history is paginated separately. No answer text, options,
keys, accepted answers, grading rules, scores, emails, or Google identities appear
in monitoring responses.

Dashboard requests normally poll five seconds after the previous request completes.
Requests never overlap. Failures back off to thirty seconds, label retained
snapshots as stale, and expose manual refresh. Access denial clears the snapshot.
Account/exam changes dispose the previous monitoring scope. Countdown displays
use server timestamps and monotonic elapsed time, including a conservative transit
deduction; they do not depend on the device date.

During an active live subject, a separate `PresenceReporter` normally sends every
ten seconds. It reports the subject identifier, question position, and a bounded
batch of browser events. It never receives answer content and never touches the
answer queue or IndexedDB journal. Monitoring failure does not block saving,
navigation, submission, or recovery. Closure stops the reporter.

The heartbeat endpoint checks candidate ownership/eligibility and subject state,
validates position against the paper, enforces a five-second minimum between
updates, and accepts at most eight allowlisted events. Server time is assigned
after attempt locks. It reconciles expiry but never extends a deadline or writes
an answer. The browser keeps at most 32 pending reports in memory and retries
their stable UUID identifiers; the backend deduplicates nonces within the attempt.

Connection labels reflect server evidence:

| Label | Meaning |
| --- | --- |
| Online / recent contact | An active subject has a heartbeat received within 30 seconds |
| No recent contact | The latest heartbeat is older than 30 seconds |
| Unknown | No contact has been recorded, or no subject is currently active |

These labels do not prove physical network state. Background throttling, a sleeping
device, tab closure, or a failed monitoring request can create a contact gap.
Question position is candidate-reported, not an independently verified fact.

## Event history

`session_event_service.py` appends authoritative events in the same transaction
as the engine transition: EXAM_OPENED, SUBJECT_STARTED, ANSWER_SAVED,
QUESTION_FLAGGED/UNFLAGGED, SUBJECT_SUBMITTED, SUBJECT_AUTO_SUBMITTED, and
EXAM_SUBMITTED. Actual state/revision changes create events; identical retries
and repeated expiry reconciliation do not duplicate them. Expiry events also come
from the existing independent expiry worker. Roster reads reconcile the attempts
on their selected page using the same engine and acquire attempt locks in UUID order.

Browser reports are limited to CONNECTION_LOST/RESTORED, VISIBILITY_HIDDEN/VISIBLE,
and FULLSCREEN_EXIT/ENTER. Their source is always CLIENT; they cannot claim server
transition types. Timestamps represent server receipt, so delayed reports may
arrive after reconnection. No free-text or arbitrary metadata is accepted.

The portal distinguishes browser reports from server events. Review counts include
connection-loss, visibility-hidden, and fullscreen-exit reports. They do not label
candidates as cheaters or impose penalties. Authorized human review remains necessary.
Administrator proctor assignments/revocations use the existing staff action audit.

## Database migration

`0005_proctor_monitoring`, following `0004_admin_portal`, creates:

- `proctor_exam_assignments`: unique exam/user pair, active flag, assigning staff
  identifier, timestamps, and restrictive foreign keys.
- `attempt_presence`: one latest-contact row per exam attempt, active subject
  identifier, reported position constrained to 1–200, and server last-seen time.
- `session_events`: attempt/optional subject references, constrained event/source,
  optional client nonce unique within the attempt, server timestamp, and indexed
  attempt/time lookup.

The migration does not replace or reset existing users, exam attempts, answers,
revisions, deadlines, or administrative audit history. Existing sessions initially
have unknown contact and no retroactively reconstructed event history. New events
start when the upgraded services run.

Upgrade, downgrade to 0004, re-upgrade, preserved exam data, and Alembic/model
comparison passed on PostgreSQL. A downgrade removes the new scope/contact/event
history and belongs in a reviewed recovery procedure or disposable environment.
Audit storage is append-oriented through the application; database-operator
tampering protections remain part of hardening.

## Files created or changed

| Area | Files |
| --- | --- |
| Backend monitoring | New `app/models/proctor.py`, `app/schemas/proctor.py`, `app/api/routes/proctor.py`, `app/services/proctor_service.py` |
| Engine event integration | New `app/services/session_event_service.py`; updated `app/services/attempt_service.py`, `app/models/__init__.py`, `app/main.py` |
| Migration | New `alembic/versions/0005_proctor_monitoring.py` |
| Backend tests | New `tests/test_proctor.py`; updated `tests/test_foundation.py` |
| Proctor interface | New `frontend/src/features/proctor/ProctorPage.tsx`, `usePoll.ts`, `proctor.css`, `services/proctor.ts`, `types/proctor.ts` |
| Candidate reporting | New `frontend/src/features/exam/presence.ts`, `useExamPresence.ts`; updated `LiveExam.tsx` with a focused hook call |
| Administrative access | New `frontend/src/features/admin/ProctorAssignments.tsx`; updated `ExamsPage.tsx`, `services/admin.ts` |
| Navigation | Updated `frontend/src/App.tsx`, `pages/DashboardPage.tsx` |
| Frontend tests | New `frontend/tests/proctor.test.tsx`, `presence.test.ts`, `e2e/proctor.spec.ts`; updated live/admin/recovery fixtures for the new safe channel |
| Documentation | README, architecture, database, security, lifecycle, frontend structure, and this handover |

Backend paths in the table are relative to `backend/`. No runtime or development
dependency was added. Candidate styling, assets, and answer recovery storage were
not replaced.

## Verification

| Check | Result |
| --- | --- |
| Backend quick suite | 162 passed; 4 PostgreSQL-only checks skipped |
| Full isolated PostgreSQL suite | 166 passed, including migration roundtrips and attempt concurrency |
| Frontend unit/component/storage suite | 125 passed across 10 files |
| Real Chromium workflows | 10 passed: existing admin/recovery plus candidate-to-proctor and access-assignment scenarios |
| Backend Ruff lint/format and strict mypy | Passed |
| TypeScript and Vite production build | Passed |

Tests cover role exclusion and scoped access/revocation, ownership, origin/CSRF,
invalid position/context, event nonce deduplication, heartbeat rate limits, expiry,
safe response field allowlists, lifecycle event idempotence, monotonic timing,
bounded reporting/retries, stale-data labeling, and stopping/aborting reporters.
The browser suite proves answers continue saving when the monitoring channel fails,
then checks recovered events reach the proctor and revoked access clears the roster.
Its dashboard screenshot was inspected at a laptop resolution.

Two initial test issues were corrected: an administrator fixture reused an existing
email, and component tests selected an exam before its asynchronously loaded option
was available. Fixtures now use a distinct identity and wait for the expected option.
No production authorization was bypassed and assertions were retained.

Local PostgreSQL tests used an isolated 16.2 instance; CI uses PostgreSQL 17.
Browser tests use real Chromium with stateful synthetic API identities/responses.
They are not actual Google-to-deployed-backend acceptance. The existing local
Starlette/httpx test-client deprecation warning remains unrelated to these changes.

## Running and configuring

Keep existing `.env` files. Initial software, Google client setup, and WSL/Docker
instructions remain in README. From the project root:

```bash
docker compose up -d db
```

Backend terminal:

```bash
cd /home/mr_laptop/cck-digital-test/backend
source .venv/bin/activate
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

Expiry-worker terminal:

```bash
cd /home/mr_laptop/cck-digital-test/backend
source .venv/bin/activate
python -m app.expiry_worker
```

Frontend terminal (reuse a running Vite server on 5173):

```bash
cd /home/mr_laptop/cck-digital-test/frontend
npm ci
npm run dev
```

An operator provisions approved staff once using the normal database:

```bash
cd /home/mr_laptop/cck-digital-test/backend
source .venv/bin/activate
python -m app.cli register-staff --email "approved-admin@gmail.com" --name "CCK Administrator" --role ADMIN
python -m app.cli register-staff --email "approved-proctor@gmail.com" --name "CCK Proctor" --role PROCTOR
```

Set `VITE_ENABLE_UI_PREVIEW=false`, configure matching Google client IDs, and restart
Vite. Sign in as ADMIN, open the configured exam in `/admin`, and use **Proctor access**
to assign the approved proctor. Sign in as that proctor and open
`http://localhost:5173/proctor`. Only assigned exams are selectable. Candidates
send contact data after loading an active live subject, not while merely reading
instructions or viewing development preview. Keep the worker running on test day.

Checks:

```bash
cd backend
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app
.venv/bin/python -m pytest -q
TEST_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/DISPOSABLE_TEST_DB .venv/bin/python -m pytest -q
```

```bash
cd frontend
npm test
npm run build
npx playwright install --with-deps chromium
npm run test:e2e
```

## Limits and next milestone

- Normal local Google credentials and Docker/PostgreSQL still require the README's
  external setup. Existing environment files were retained and no live staff
  accounts were silently provisioned. Candidate preview remains available.
- Polling provides periodic snapshots, not instantaneous delivery. Performance
  qualification and deployment sizing remain outstanding; high concurrent demand
  may justify batched queries or a properly authorized real-time transport later.
- Browser reports are best-effort, untrusted, nonpersistent observations. Reload,
  overflow, subject closure, or interrupted requests can lose them. They have
  weaker recovery guarantees than answers and do not control exam integrity.
- Proctors can read assigned rosters/events only. There is no proctor suspension,
  retake, time-extension, note-writing, or answer-inspection workflow.
- Application append orientation does not provide database-enforced immutability,
  archival/retention policy, or a complete login/security-event history.
- Real Google acceptance, operational device qualification, security hardening,
  monitoring/backup operations, and realistic mock examinations remain necessary.

Next: **Milestone 8 — Grading & Results**, preserving raw submitted answers,
enforcing examiner access, and keeping grades withheld until authorized release.
The system is not production-ready for real examinations.
