# Milestone 3 — Attempt engine handover

The backend now supports assigned, authorized exams with persistent attempts,
server deadlines, answers/review flags, submission, expiry, and resume. The
frontend templates and assets are unchanged; their existing development preview
still uses local sample state. Real UI integration belongs to Milestone 4.

## Files and architecture

Created:

- `backend/app/models/attempt.py`: assignments, exam attempts, subject attempts.
- `backend/app/models/answer.py`: one revisioned answer per subject/paper question.
- `backend/app/schemas/attempt.py`: safe candidate paper/state and mutation schemas.
- `backend/app/services/attempt_service.py`: eligibility, ordered state machine,
  timing, concurrency, persistence, expiry, and receipts.
- `backend/app/api/routes/attempts.py`: protected candidate and admin start/access routes.
- `backend/app/core/clock.py`: PostgreSQL current-time source, injectable only through
  internal dependencies for tests, with no client-time API parameter.
- `backend/app/expiry_worker.py`: independent batch/polling expiry process.
- `backend/alembic/versions/0003_attempt_engine.py`: reviewed schema migration.
- `backend/tests/test_attempts.py`: attempt workflow, deadlines, security,
  constraints, and PostgreSQL concurrency tests.
- `docs/milestone-3.md`: this handover.

Updated model registration, existing exam/option/paper composite keys, exam response
schema, domain freeze checks, FastAPI route/clock registration, migration roundtrip
tests, README, and architecture/database/security/lifecycle/frontend documentation.
No additional application dependencies were introduced.

Migration `0003_attempt_engine` adds four tables and a disabled-by-default start
gate on exams. Its dependency order was reviewed and corrected: referenced composite
unique keys precede child tables on upgrade; children precede their removal on
downgrade. Downgrade restores Milestone 2 without deleting its exams but does remove
attempt/answer records. Normal application startup never creates or migrates tables.

## Important behavior

- Login approval alone does not grant exam access. ADMIN assigns the candidate
  and authorizes start after complete paper validation.
- The database allows one logical attempt per candidate/exam and one active
  subject per attempt. Repeated starts, refresh, and re-login resume existing data.
- Subject names, order, and durations are copied into subject attempts. Authorized
  exam configuration freezes; after an attempt exists it remains frozen.
- Every new subject starts in configured order after earlier subjects close.
  Its independent timer begins at that explicit start, without consuming the
  next subject's duration when the current subject expires.
- Optional schedules are authoritative. The scheduled end is a hard cutoff,
  including subjects never started; it caps each active subject's expiry.
- Answers and flags persist on each successful save and survive reopening.
  Revision conflicts preserve the newer answer. Equal retries are safe and do
  not create duplicate rows or extra revisions.
- At or after expiry, answer/review writes fail and expiry is persisted. Closing
  all subjects automatically finalizes the exam; final-submit retries return
  the same recorded submitted_at.
- Candidate paper responses omit correct flags, accepted values, grading settings,
  and future subject content. Staff cannot use candidate endpoints as candidates.
- The worker closes timed-out subjects without browser requests and supports
  multiple instances using skip-locked rows. Late writes are rejected even when
  the worker is stopped; reconciliation catches up after restart.

Start authorization is a minimal engine prerequisite. The full publication,
activation, and staff UI remain Milestone 6. Audit history, grading, and results
remain their later milestones. See [lifecycle](exam-lifecycle.md) for exact policies.

## Run commands

Use Ubuntu/WSL terminals. With the normal PostgreSQL configured and running:

```bash
cd /home/mr_laptop/cck-digital-test
docker compose up -d db
cd backend
source .venv/bin/activate
alembic upgrade head
alembic check
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

Separate expiry terminal:

```bash
cd /home/mr_laptop/cck-digital-test/backend
source .venv/bin/activate
python -m app.expiry_worker
```

Separate frontend terminal, if it is not already running:

```bash
cd /home/mr_laptop/cck-digital-test/frontend
npm run dev
```

`python -m app.expiry_worker --once` processes one batch and exits. Default batch
size is 100; the normal loop polls every second, configurable with `--interval`
from 0.1 to 60 seconds. Production needs a supervised worker and failure monitoring.

## Preparing and exercising an attempt

Configure Google and approved accounts as described in the README. Turn off
development preview and restart Vite for actual sign-in. Build a complete draft
exam using the [Milestone 2 API workflow](milestone-2.md). Give it a schedule long
enough for its configured subjects when using a hard end. Do not use browser
preview state or its sample time as a real configuration/receipt.

In the approved admin session, using that handover's `admin` helper:

```js
// exam.id comes from the configured draft; candidateId is the approved candidate UUID.
await admin(`exams/${exam.id}/candidates/${candidateId}`, 'PUT', { is_active: true });
await admin(`exams/${exam.id}/start-authorization`, 'POST', { authorized: true });
```

Candidate ID comes from the approved candidate record/profile, not its user ID
or roll number. There is no public self-assignment or approval endpoint.

In the owning candidate's signed-in browser console at localhost:5173:

```js
const profileResponse = await fetch('/api/me');
if (!profileResponse.ok) throw new Error('Sign in first');
const me = await profileResponse.json();
const candidate = async (path, method = 'GET', body) => {
  const response = await fetch(`/api/candidate/${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': me.csrf_token },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : data.detail.message);
  return data;
};
const exams = await candidate('exams');
const attempt = await candidate(`exams/${exams[0].exam_id}/attempt`, 'POST');
const subjectId = attempt.subjects[0].id;
const prefix = `attempts/${attempt.id}/subjects/${subjectId}`;
await candidate(`${prefix}/start`, 'POST');
const paper = await candidate(`${prefix}/questions`);
const question = paper.questions[0];
await candidate(`${prefix}/answers/${question.exam_question_id}`, 'PUT', {
  expected_revision: question.answer.revision,
  selected_option_id: question.type === 'MCQ' ? question.options[0].id : null,
  short_answer_text: question.type === 'SHORT_ANSWER' ? 'sample response' : null,
  is_marked_for_review: false,
});
await candidate(`${prefix}/submit`, 'POST');
// Start the next subject only after the current subject has closed.
const resumed = await candidate(`attempts/${attempt.id}`);
```

Do not log/share tokens, keys, or sensitive candidate answer data. The console
examples are a temporary API acceptance aid; Milestone 4 supplies the user flow.

## API contract and responses

All attempt mutations require a current candidate session, exact Origin, and CSRF
header. Ownership and active assignment are enforced on every candidate request.
Admin assignment/start mutations require ADMIN and the same mutation protections.
Schemas forbid client timestamps, deadlines, candidate IDs in answer bodies, and
unrecognized fields. Answer writes include the full answer/review snapshot and
an integer `expected_revision`.

| Condition | Response |
| --- | --- |
| No session | 401 |
| Wrong role, missing assignment, revoked assignment/start permission | 403 |
| Wrong candidate/attempt/subject/question mapping | 404 |
| Invalid answer shape/option/body | 422 |
| Out-of-order start, not opened, stale revision, unfinished final submit | 409 |
| Closed window or answer write to submitted/expired subject | 410 |

A stale-save 409 has `detail.message` and `detail.current_answer` with revision,
payload, and saved timestamp for the owning candidate only. Other validation
errors stay generic. Treat revisions as authoritative; do not blindly resend
stale local state. Equal retries return the current answer unchanged. `server_time`
and stored expiry timestamps support the future UI timer; browser time is never
used for backend decisions.

## Verification and remaining configuration

Quick suite: 120 passed, four expected PostgreSQL-only skips. The PostgreSQL
attempt suite passed 30 tests, including concurrent exam/subject starts,
competing revisions, a deadline crossed during a row-lock wait, worker skip-locked
behavior, and the actual database clock. The full PostgreSQL suite and migration
roundtrips cover all 124 tests. Python lint, format, strict typing, and dependency
checks pass. Frontend tests: 41 passed; production build/TypeScript check passed.

Database checks use the existing disposable PostgreSQL 16.2 instance and isolated
schemas; normal development data/environment files are untouched. Compose/CI target
PostgreSQL 17 and Python 3.12; the local Python runtime is 3.14. Docker/Compose,
those target runtimes, actual Google popup acceptance, and migration of the normal
development database still need their environment/manual checks. The existing
Starlette/httpx TestClient deprecation warning remains.

The generated migration's initial order, long constraint strings, and a missing
import in the new migration test were corrected during implementation checks.
No failed check is treated as success; final results are recorded above.

No retake/reset, time extension, manual grading, scores/results, audit history,
offline client storage, or production deployment is implemented. The UI preview
still resets responses on refresh because it is separate from real backend
attempts. Do not conduct admission examinations yet.

Next milestone: connect the existing CCK templates to safe candidate APIs,
server-derived timer display, autosave feedback, navigation/review state, and real
submission confirmation. IndexedDB recovery/reconnection remains Milestone 5.
