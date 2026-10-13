# Milestone 2 — Exam domain handover

This records the domain delivery. The subsequent attempt engine and start gate
are documented in [Milestone 3 handover](milestone-3.md).

Milestone 2 adds configurable exam definitions and protected administrator APIs.
The supplied login, dashboard, exam, and submission templates are preserved.
No attempt engine, candidate answer saving, countdown, grading execution, or result
release has been added. The development frontend remains a labeled local preview.

Milestone 1's actual Google browser acceptance test remains outstanding; the
owner explicitly deferred its configuration and authorized continuing development.
The backend still requires verified identity, an approved account, and ADMIN role
for these APIs. There is no backend authentication bypass.

## Files created and changed

New files:

- `backend/app/models/subject.py`: configurable subject catalog.
- `backend/app/models/exam.py`: exam, exam subject, ordered paper selection.
- `backend/app/models/question.py`: MCQ/short-answer question, option, accepted value.
- `backend/app/schemas/exam_domain.py`: validated admin request/response shapes.
- `backend/app/services/exam_domain_service.py`: transactions and domain rules.
- `backend/app/api/routes/admin_domain.py`: ADMIN-protected management routes.
- `backend/alembic/versions/0002_exam_domain.py`: seven new tables and constraints.
- `backend/tests/test_exam_domain.py`: domain, authorization, and constraint tests.
- `docs/milestone-2.md`: this handover.

Updated files: model registration, Alembic environment, FastAPI route registration
and allowed mutation methods, PostgreSQL migration tests, package description,
README, architecture, database, security, and lifecycle documentation. No frontend
source, assets, stylesheet, dependency, or template changes were needed.

## Implemented behavior

Subjects have a name, unique normalized code, and active flag. Exams have a title,
description, DRAFT/ARCHIVED status, and optional timezone-aware schedule window.
Schedule inputs and API responses normalize to UTC; scheduling does not authorize
candidate testing. Subject assignments have independent durations and configurable
sequence numbers. No subjects, questions, or answer keys are seeded automatically.

MCQs require 2–8 distinct options with exactly one correct option. Short answers
configure EXACT, NUMERIC, or MANUAL. The JSON config is discriminated by `mode`:

- EXACT: Unicode NFC (or NONE), trimming, whitespace collapse, and case sensitivity
  are explicit. Defaults preserve whitespace and case. Accepted strings remain
  stored as entered; equivalent accepted values under the configured rules are rejected.
- NUMERIC: finite decimal/scientific accepted values and a nonnegative absolute
  tolerance, default zero. Expressions, units, NaN, Infinity, and duplicate numeric
  values are rejected. Nonzero numeric magnitudes must have adjusted exponents
  between -100 and 100. Actual comparison/grading belongs to Milestone 8.
- MANUAL: no accepted values or automatic grading settings.

Paper assembly replaces an entire ordered question list atomically. It checks
active questions, active subject, correct subject mapping, and duplicate selection.
Marks can be overridden per paper; subject totals are derived from effective marks
and returned as decimal strings. An empty list clears a draft paper.

Question editing/archival is blocked while it is assigned to any paper. Remove it
from draft papers first; questions attached to archived exams stay protected.
Archived exams are immutable. API writes use row locks for exam edits and question
attachment/editing. Cross-subject selection, duplicate paper questions/order,
nonpositive marks, invalid child types, and multiple correct options also have
database protection. Child cardinality and grading JSON validation are service rules.

PUT requests replace the complete editable representation; omitted optional fields
take their defaults. Subject sequences are unique per exam but need not be contiguous.
To exchange two subject positions, move one to a spare sequence before swapping.
Paper order follows array order and is assigned contiguous sequences automatically.
Collections use `limit` (1–100, default 50) and nonnegative `offset`; questions
also support `subject_id` and `question_type` filters.

## API workflow

Use the normal PostgreSQL instance and apply migrations before trying these APIs:

```bash
cd /home/mr_laptop/cck-digital-test
docker compose up -d db
cd backend
source .venv/bin/activate
alembic upgrade head
alembic check
python -m app.cli register-staff \
  --email "your-approved-admin@gmail.com" --name "Test Administrator" --role ADMIN
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

Use the CLI only for genuinely authorized staff; do not repeat it for an existing
account. If Docker's WSL integration is still unavailable, enable it or supply an
existing PostgreSQL instance with matching `backend/.env` configuration. The isolated
PostgreSQL used for automated checks is not the persistent development database.

In another terminal:

```bash
cd /home/mr_laptop/cck-digital-test/frontend
npm run dev
```

Configure the same public Google client ID in backend/frontend environments as
described in the README. Set `VITE_ENABLE_UI_PREVIEW=false` and restart Vite to
sign in at `http://localhost:5173` as the approved administrator. The admin portal
is Milestone 6; these APIs can currently be exercised from that browser's console.
The following helper keeps the CSRF value in memory and sends mutations through
the existing Vite proxy. Do not share session credentials or console output with
sensitive question keys.

```js
const profileResponse = await fetch('/api/me');
if (!profileResponse.ok) throw new Error('Sign in first');
const me = await profileResponse.json();
if (me.user.role !== 'ADMIN') throw new Error('An approved administrator is required');
const admin = async (path, method = 'GET', body) => {
  const response = await fetch(`/api/admin/${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': me.csrf_token },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!response.ok) throw new Error((await response.json()).detail);
  return response.status === 204 ? null : response.json();
};

const english = await admin('subjects', 'POST', { name: 'English', code: 'ENG' });
const exam = await admin('exams', 'POST', { title: 'CCK test configuration' });
const paper = await admin(`exams/${exam.id}/subjects`, 'POST', {
  subject_id: english.id, duration_minutes: 60, sequence: 1,
});
const question = await admin('questions', 'POST', {
  subject_id: english.id, type: 'MCQ', prompt: 'Choose the correctly spelled word.',
  marks: '1.00', options: [
    { text: 'beautiful', is_correct: true },
    { text: 'beautifull', is_correct: false },
  ],
});
await admin(`exam-subjects/${paper.id}/questions`, 'PUT', {
  questions: [{ question_id: question.id }],
});
await admin(`exams/${exam.id}/subjects`);
```

Admin mutations require the actual application session, exact allowed Origin, and
the session's CSRF header. Anonymous requests return 401; non-admin roles return
403. Reads containing correct options, accepted values, or grading configuration
are restricted to ADMIN. Candidate endpoints still expose no questions or keys.

## Verification

Checks run using the existing virtual environment and installed dependencies:

| Check | Result |
| --- | --- |
| Quick backend suite | 93 passed; 1 expected PostgreSQL-only skip |
| Complete PostgreSQL suite | 94 passed |
| Alembic upgrade, foundation downgrade preserving user, full downgrade/re-upgrade | Passed in an isolated database |
| `alembic check` | No model/schema drift |
| `ruff check .` and `ruff format --check .` | Passed |
| `mypy app` | Passed |
| `python -m pip check` | No broken requirements |
| Frontend `npm test` | 41 passed |
| Frontend `npm run build` | Passed, including TypeScript check |

An initial PostgreSQL run exposed a timezone formatting mismatch: PostgreSQL
returned the correct instant in its configured local timezone. API schedule
responses now normalize to UTC. UTC and +05:00 input roundtrips pass on SQLite
and PostgreSQL. Initial generated migration constraint names and long SQL strings
were corrected during review; final lint and migration checks pass.

PostgreSQL tests use a disposable PostgreSQL 16.2 instance with private Unix socket
and isolated schemas, not the normal database or candidate records. Compose/CI
target PostgreSQL 17. The local Python runtime is 3.14; Docker/CI target 3.12.
The existing upstream Starlette/httpx TestClient deprecation warning remains.

## Remaining work and next milestone

Real Google browser acceptance, Docker/Compose execution, PostgreSQL 17/Python 3.12
runtime checks, and normal development database migration remain environment/manual
steps. No new secrets or external credentials are needed by this milestone.

Publication/activation, assignments, attempt snapshots, audit history, candidate
question delivery, attempt deadlines, answers, grading, and results are not claimed
implemented. The frontend preview is not connected to these domain records. The
admin portal remains Milestone 6. Archived exams cannot be reopened by this API;
define an authorized workflow if that becomes a product requirement.

Next: Milestone 3 — assignments and the exam attempt engine, with server deadlines,
unique logical attempts, revisioned answer saves, review flags, submission/expiry,
and resume tests. Preserve the supplied frontend templates and connect them during
the candidate UI milestone. This platform must not conduct real examinations yet.
