# Editable local administration sandbox

Open **http://localhost:5175/api/local-management** and click
**Open test administration**. This enters the real administration pages, backed by
a separate PostgreSQL test database. Google configuration is unnecessary here.
The normal development/design preview remains at port 5173.

## Try question editing and marking rules

1. Choose **Question bank** in the administration sidebar.
2. Click **Edit question** on an example, or **Create question**.
3. For MCQs, edit the options, select the correct option and set the marks.
4. For short answers, choose a grading mode:
   - **EXACT:** accepted answers and explicit normalization/case/whitespace rules.
   - **NUMERIC:** accepted number(s) and absolute tolerance.
   - **MANUAL:** maximum marks; an assigned examiner later grades responses.
5. Click **Save question**, then refresh or reopen it to inspect the saved values.

Sample English, Mathematics and Urdu questions demonstrate all four configurations.
They are initially unassigned to papers so their editing controls are usable.
Existing rules still prevent editing questions already used in a paper; remove
them from an editable draft paper first, or create a new question.

For a larger practice bank informed by CCK's scanned 2020–2023 papers, see the
[90-question calibration pack and safe import commands](question-bank-calibration.md).
It includes original English, Mathematics, Urdu and labelled Islamiat practice,
with keys and marking guidance. It requires subject-teacher review before real use.

The other sidebar pages support candidate registration/import, subjects, exam
creation, ordered papers, staff assignments, publication/start controls and history.
The sample exam starts as an unpublished draft with no papers; configure it through
the normal builder. Three sample candidates are included. For example, candidate
sign-in uses `TEST-001`, `Sample Candidate 1`, `Sample Father 1` after sign-out.
The local entry page restores the test administrator session when you need it again.

## Start or resume

From the repository root in WSL/Linux, with PostgreSQL and existing development
dependencies installed:

```bash
PYTHONPATH=backend backend/.venv/bin/python ops/management_sandbox.py
```

The development database account needs permission to create a database on first
launch. The tool creates a uniquely named `cck_management_*_rehearsal` database,
applies Alembic migrations and provisions only synthetic sample data and a local
test administrator. It runs a separate API on `127.0.0.1:8003`, Vite on
`127.0.0.1:5175`, and an expiry worker. Occupied ports are rejected before launch.
The frontend receives its API target and sandbox flags through process environment;
the normal `.env` files and development services are not modified.

Ctrl+C stops its services. Test changes remain in PostgreSQL. Running the same
command resumes the existing sandbox and applies current migrations without
reseeding it. Private `test-results/management-sandbox/sandbox.json` identifies the
database and test administrator; keep it to resume your test changes. It contains
local database credentials, is mode `0600`, and must not be shared or committed.
Service/migration logs live in the same ignored private directory. The tool never
automatically drops a database or deletes test progress.

An additional isolated workspace can use a different private directory and ports:

```bash
PYTHONPATH=backend backend/.venv/bin/python ops/management_sandbox.py \
  --directory test-results/another-management-sandbox \
  --frontend-port 5176 --api-port 8004
```

Use separate browser profiles for different simultaneous sandboxes; their local
sandbox cookie name is shared. Actual development/production sessions use a
different cookie name and a different database.

## Boundaries and verification

Use synthetic information only. This is a local test workspace, not an admissions
deployment. The entry helper exists only in the explicitly launched root `ops/`
tool, outside production application routes and Docker application build context.
Its factory rejects production settings, non-loopback databases, regular database
names and the normal application cookie. Both services bind only to loopback.

The entry button sends a same-origin JSON POST with the entry page's nonce. Before
issuing a session, it verifies the actual database name and the fixed, active
test administrator's role. The browser receives the normal HttpOnly/SameSite
session cookie; subsequent management requests use real backend RBAC, CSRF,
validation, transactions and audit records. Sessions last two hours; reopen the
entry page after expiry or logout. No Google identity is fabricated and no
production authentication route is changed.

Tests cover absent helper routes in the regular app, production/nonlocal
configuration rejection, origin/nonce/database/user checks, session issuance and
CSRF enforcement. Browser verification covers question marks, accepted answers,
numeric tolerance, MCQ keys, manual configuration, candidate creation and refresh
persistence against the isolated PostgreSQL API. The production HTTPS rehearsal
also confirms that the helper GET/POST routes are absent from the deployed app.
