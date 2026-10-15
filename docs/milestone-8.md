# Milestone 8 — Grading and results

Implemented after Milestone 7 and the admission-details login update. The existing
CCK candidate/login/dashboard/exam/submission designs and assets are retained.
The local free-access preview remains enabled and now includes a sample `/results`
page. Grading and administrator access still require approved staff identities.

## Delivered behavior

- MCQ, EXACT, and NUMERIC grading runs on the backend when a subject is submitted
  or expires. Marks commit with the closure; saved answers are never replaced.
- EXACT follows the question's explicit NFC/NONE, trimming, whitespace-collapse,
  and case-sensitivity settings. It supports Unicode/Urdu without transliteration.
- NUMERIC accepts bounded ASCII decimal/scientific numbers and applies absolute
  tolerance using Decimal with sufficient precision for boundary comparisons.
  Expressions, fractions, units, NaN/Infinity, non-ASCII numerals, and nonzero
  adjusted exponents outside -100..100 are rejected as incorrect responses.
- Automatic questions receive full marks or zero. Effective marks include paper
  overrides. Nonblank MANUAL responses wait for authorized human review; blank
  short answers get zero without entering an obligatory manual workflow.
- A paper closed before it started contributes zero against its full maximum.
  A started paper missing expected answers/grades stays pending instead of silently
  treating missing persisted work as zero. Invalid grading configuration also
  stays pending without blocking subject submission/expiry.
- Legacy completed attempts can be backfilled by an administrator through `/grading`.
  Repeated runs do not duplicate grades or override manual records.
- Examiners see only explicitly assigned exams. Review begins only after the
  whole exam attempt is submitted. The queue shows required prompt/answer content,
  subject and question position, effective maximum, and current grade. It does
  not expose MCQ keys or accepted answers. It omits candidate names from responses;
  the separate grading roster identifies candidate progress.
- Manual marks support partial credit, two decimal places, staff attribution,
  server timestamps, notes, complete revision history, and stale-write protection.
  Corrections require a reason. Repeating the immediately previous identical write
  by the same actor acknowledges that revision; older/competing writes return 409.
- Subject marks, total marks, and percentage are computed from the current grade
  revisions. Percentages round to two places using ROUND_HALF_UP. React displays
  the server values without calculating scores.
- Results remain withheld until explicitly authorized by ADMIN. Release requires
  paused new starts and every existing attempt submitted and completely graded.
  A future release timestamp additionally gates candidate visibility by server
  time. A date alone never publishes results.
- Authorized publication freezes grading even before a scheduled release time.
  Withhold, record an audited correction, then release again. Released exams
  cannot enable new starts. Publication never reopens an attempt or changes time.
- Candidate result DTOs omit all subject results/marks/maxima/percentage before
  release. They never include answer keys, raw responses, grading rules, or examiner
  notes. Reads enforce authenticated ownership, active assignment, and eligibility.

## Architecture and migration

`0007_grading_results` follows `0006_candidate_login` and adds:

| Table | Purpose | Key constraints |
| --- | --- | --- |
| examiner_exam_assignments | Explicit exam-specific staff scope | Unique exam/user, active flag, assigning actor and restrictive foreign keys |
| grading_records | Independent append-oriented marks history | Unique answer/revision, answer revision snapshot, bounded decimal marks, maximum, method/actor checks, timestamp, bounded notes |

Upgrade retains existing users, candidates, papers, attempts, answers, and timing.
Both upgrade and downgrade force release flags false to prevent accidental
publication without valid grading. Downgrade deletes the new grading/grant history;
back up before any rollback. Legacy grades are not invented during migration.

`auto_grading_service.py` implements scoring and bulk-loads private keys/current
record identities so subject closure avoids a separate lookup per question.
`grading_service.py` coordinates scopes, manual queues, row locks, history and
backfill. `result_service.py` computes totals and enforces release readiness.
Routes use explicit public schemas. Existing attempt code receives only focused
hooks at subject closure and a released-exam start guard.

Manual grading and publication acquire exam → attempt → subject → answer locks;
examiner grants use the same exam lock. Candidate result reads lock exams in UUID
order to serialize visibility with withholding/corrections without cross-exam
lock-order inversion. Automatic scoring runs under the existing attempt/subject
locks. PostgreSQL is authoritative; SQLite is used only for fast tests.

No runtime dependency, WebSocket broker, frontend scoring engine, or production
schema auto-creation was introduced. History is append-only through application
services, not protected from a privileged database operator.

## Files

Backend additions: `app/models/grading.py`, `app/schemas/grading.py`,
`app/services/auto_grading_service.py`, `grading_service.py`, `result_service.py`,
`app/api/routes/grading.py`, migration `alembic/versions/0007_grading_results.py`,
and `tests/test_grading.py`. Existing main/model registration, attempt closure,
result-release service, and migration verification received focused updates.

Frontend additions: `features/grading/GradingPage.tsx`, `ResultsPage.tsx`,
`grading.css`, `features/admin/ExaminerAssignments.tsx`, `types/grading.ts`,
`services/grading.ts`, `tests/grading.test.tsx`, and `e2e/grading.spec.ts`.
Routes/sidebar/staff dashboard/admin exam controls and existing browser fixtures
were extended. README, architecture, database, security, lifecycle, and frontend
structure documentation were updated. Existing assets and exam/recovery modules
were retained.

## API

| Endpoint | Authorization / behavior |
| --- | --- |
| GET /api/admin/examiners | ADMIN; active examiner selector |
| GET /api/admin/exams/{exam_id}/examiners | ADMIN; grant history/current state |
| PUT /api/admin/exams/{exam_id}/examiners/{user_id} | ADMIN + Origin/CSRF; assign/revoke scope |
| GET /api/grading/exams | ADMIN or EXAMINER; only permitted exams |
| GET /api/grading/exams/{exam_id}/attempts | Scoped grading role; progress and totals |
| GET /api/grading/exams/{exam_id}/queue | Scoped grading role; paginated manual responses, optional include_graded |
| GET /api/grading/answers/{answer_id}/history | Scoped grading role; persisted revisions |
| POST /api/grading/answers/{answer_id}/grade | Scoped grading role + Origin/CSRF; marks and expected revision |
| POST /api/admin/attempts/{attempt_id}/grade | ADMIN + Origin/CSRF; automatic backfill for completed attempts |
| POST /api/admin/exams/{exam_id}/result-release | ADMIN + Origin/CSRF; explicit release/withhold plus optional time |
| GET /api/candidate/results | Approved owning CANDIDATE; only released totals |

Lists use limit/offset, default 50 and maximum 100, except individual grade history.
Manual-write example:

```json
{"expected_revision":0,"marks_awarded":"1.50","notes":"Rubric applied"}
```

On 409, review refreshed current marks/history before resubmitting. A failed request
retains draft marks. A permission denial clears the examiner response from view.

## Run and configure

Keep existing `.env` files. From the repository root, normally use
`docker compose up -d db`; the existing WSL local PostgreSQL fallback is documented
in [candidate-login.md](candidate-login.md). The current development database has
no silently provisioned live candidates or staff.

Backend terminal:

```bash
cd /home/mr_laptop/cck-digital-test/backend
source .venv/bin/activate
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

Independent expiry-worker terminal:

```bash
cd /home/mr_laptop/cck-digital-test/backend
source .venv/bin/activate
python -m app.expiry_worker
```

Frontend terminal (reuse an existing server on port 5173):

```bash
cd /home/mr_laptop/cck-digital-test/frontend
npm ci
npm run dev
```

For real grading, an operator provisions approved staff once:

```bash
cd /home/mr_laptop/cck-digital-test/backend
source .venv/bin/activate
python -m app.cli register-staff --email "approved-examiner@gmail.com" --name "CCK Examiner" --role EXAMINER
```

Set `VITE_ENABLE_UI_PREVIEW=false` and configure staff Google sign-in as documented
in README. ADMIN opens the exam at `/admin/exams`, assigns **Examiner access**, and
checks `/grading`. Examiners grade pending responses or enable **Include graded
responses** to inspect/correct history. For older completed attempts ADMIN chooses
**Grade automatic answers** first. Pause starts in exam management, then **Authorize
result release**, optionally selecting a future local time (converted to UTC).
Candidates open `/results`; changing a release plan with **keep withheld** withdraws
publication. Official candidate records/assignments and approved staff credentials
remain external operational inputs; no admission-portal integration was added.

For free interface testing, leave `VITE_ENABLE_UI_PREVIEW=true` and visit
`http://localhost:5173/results`. It shows an explicitly labeled sample result.
It grants no examiner/admin permissions and submits no real marks.

## Verification and limits

| Local check | Result |
| --- | --- |
| Complete backend quick suite | 230 passed; 7 PostgreSQL-only cases skipped |
| PostgreSQL grading scenarios | 40 passed across the main run and focused final additions |
| PostgreSQL migration roundtrip and ORM comparison | Passed |
| Frontend suite | 139 passed across 11 files |
| Chromium regression suite | 15 passed |
| Separate real-service Chromium grading/publication workflow | Passed |
| Ruff lint/format, strict mypy, TypeScript and Vite build | Passed |

- Backend quick suite and PostgreSQL grading/migration checks cover automatic
  correctness, numeric boundaries, normalization, marks overrides, blanks, raw-answer
  preservation, expiry, never-started papers, malformed configuration, grade bounds,
  role/scope exclusions, Origin/CSRF, revocation, repeated requests, stale edits,
  concurrent manual saves, scheduling, withholding, and candidate ownership.
- Frontend suite covers manual saves/history, preserved stale drafts, permission
  revocation, role guards, withheld/released views, and the no-request preview.
- Chromium workflows cover examiner partial marks/correction/history, candidate
  publication/withdrawal, admin examiner grants/release checks, and all existing
  admission-login/admin/proctor/recovery browser tests. Laptop screenshots of the
  new examiner/results interfaces were inspected.
- A separate real Chromium → Vite → FastAPI → PostgreSQL smoke check verified
  automatic grading, scoped manual marks, withheld scores, ADMIN release, the
  server-computed 75.00% result, and withdrawal. Its synthetic records lived in
  a separate test schema and were removed afterward. Staff sessions were issued by
  the test harness; actual Google acceptance still requires your OAuth setup.
- Ruff formatting/lint, strict mypy, TypeScript, production build, migration round
  trip, and Alembic/model comparison are required checks.

During implementation, type checks caught a queue query not being executed and a
missing type annotation; both were corrected before workflow verification. A
malformed-configuration test initially changed a question before exam start, which
correctly triggered existing paper validation; it now changes the fixture only
after opening the subject to verify safe closure. No assertion or authorization
check was removed to bypass these failures.

Scope remains Milestone 8. No ranking, admission decisions, negative marking,
manual adjustment to automatic keys, result export, or live regrading of published
results was added. Invalid immutable grading configuration requires an authorized
repair process; it cannot silently produce a complete result. Shared database
least privilege, immutable audit enforcement, comprehensive request limits,
dependency review, load testing, backups, and realistic mock-exam acceptance remain
Milestones 9 and 10. Do not use this local milestone completion as a production
readiness claim. Next: Milestone 9 security review and hardening.
