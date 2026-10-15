# Admission details login

Candidates sign in with the roll number issued through the CCK admission portal,
their full name, and their father's name. This is a change to authentication through
Milestone 7; it does not implement grading or advance to Milestone 8. The supplied
CCK logo, campus background, navy styling, dashboard, exam, and submission templates
are preserved. Staff Google login is available under **Staff sign-in** and loads
Google's script only when opened.

## Load approved records

The repository has no admission-portal API contract, credentials, or live
synchronization. Staff must verify the official admission records and import/enter
them. This app never invents, assigns, or renumbers an admissions roll number.
There is no candidate self-registration endpoint.

From the backend directory with PostgreSQL running:

```bash
source .venv/bin/activate
alembic upgrade head
python -m app.cli register-candidate \
  --roll-number "OFFICIAL-ADMISSION-ROLL" \
  --name "Full Name From Admission Record" \
  --father-name "Father Name From Admission Record"
```

`--email` and `--google-subject` are optional for candidates. Staff registration
still requires email and an explicit staff role. To load many candidates, an
approved ADMIN can open `/admin/candidates`, choose **Import CSV**, review the
records, then save them atomically:

```csv
roll_number,full_name,father_name
OFFICIAL-ROLL-1,Example Candidate,Example Father
```

Optional columns: `email,google_subject,status`. Status defaults to APPROVED.
Legacy CSV files with email/full_name/roll_number remain supported, but records
without a verified father's name cannot use candidate details login. Imports
create records and reject duplicates; they do not overwrite existing records.
Use the editor to add verified father's names to existing candidates. Creating
candidates in the UI requires father's name; legacy records can still be edited
or disabled while awaiting admissions verification. The API permits null for
compatibility with preexisting Google-only registrations.

Candidate registration and exam assignment remain separate. Only assigned,
published exams appear; existing start authorization, timing, and eligibility
checks still apply. Having a valid roll number alone never grants access.

## Sign in

Set `VITE_ENABLE_UI_PREVIEW=false` in `frontend/.env`, restart Vite, and visit
`http://localhost:5173`. Use the exact spelling of both names from admissions.
Names support Urdu and mixed-direction input. Unicode NFKC, case-folding, and
repeated whitespace normalization are allowed; partial names, punctuation changes,
transliteration, and approximate matching are not. Rolls ignore surrounding spaces
and case, retaining their registered display value and leading zeros.

`POST /api/auth/candidate` accepts only:

```json
{"roll_number":"OFFICIAL-ROLL-1","full_name":"Example Candidate","father_name":"Example Father"}
```

The backend checks Origin, rate limits, existing candidate registration, active
user, CANDIDATE role, APPROVED status, and both names. It issues the existing
HttpOnly/SameSite session cookie and CSRF profile. No credential is stored in
localStorage/sessionStorage. Invalid details return a generic 401; throttled
requests return 429 with Retry-After. Missing Google client configuration does not
block candidate login. Staff still need Google setup.

Admission details are guessable personal information, not a strong secret. Before
using this publicly for real admission exams, add a private exam code/OTP or an
approved supervised verification process. See [security design](security.md).

## Migration and compatibility

`0006_candidate_login` follows `0005_proctor_monitoring`:

- Adds nullable `candidates.father_name`; legacy records receive no invented value.
- Makes `users.email` nullable while preserving uniqueness and normalization.
- Adds a unique index on `lower(btrim(candidates.roll_number))` to prevent ambiguous login.
- Adds persistent `login_throttles` with fingerprint key, attempts, and indexed expiry.

Check for case/space-colliding rolls before upgrading an existing database. The
migration fails transactionally on collisions rather than merging identities.
Downgrade requires supplying genuine emails for any email-less accounts first;
it deliberately fails instead of deleting users or generating fake emails.
Back up the database before removing father's-name data on downgrade.

Updating roll number, full name, father's name, email, Google subject, or candidate
status revokes that candidate's session. No login or record edit resets an exam
attempt, changes a stored deadline, or deletes answers. Unknown or staff identities
cannot obtain a candidate session with this route.

`CANDIDATE_LOGIN_ROLL_LIMIT` (default 10) and `CANDIDATE_LOGIN_IP_LIMIT` (default
1000) apply per 15-minute window. Limits count validated requests, including
successful sign-ins, and are shared across backend workers. Configure the IP limit
for shared NAT and proxy topology; it cannot be treated as an individual candidate
identity. Expired buckets are deleted during later login requests. Configure proxy
request limits separately for malformed requests and request-body size.

## Current WSL runtime

Docker Desktop WSL integration was unavailable during this change. The installed
PostgreSQL 16 tools were used to start a local development cluster on
`127.0.0.1:5432`, using the existing backend database configuration. Data lives
outside Git at `~/.local/share/cck-digital-test/postgres16`. No candidate or staff
accounts were added to this development database. Verification uses a separate
`cck_auth_tests` database with randomly isolated schemas.

While those tools remain installed, stop/start this development cluster with:

```bash
/tmp/cck-pg-tools/extracted/pgserver/pginstall/bin/pg_ctl \
  -D "$HOME/.local/share/cck-digital-test/postgres16" -w stop
/tmp/cck-pg-tools/extracted/pgserver/pginstall/bin/pg_ctl \
  -D "$HOME/.local/share/cck-digital-test/postgres16" \
  -l "$HOME/.local/share/cck-digital-test/postgres16.log" \
  -o "-h 127.0.0.1 -p 5432 -k /tmp" -w start
```

The binary path under `/tmp` is temporary; Docker Compose PostgreSQL 17 remains
the documented reproducible setup and CI database. Stop the local cluster before
using Docker on the same port. Do not mount a PostgreSQL 16 data directory into a
PostgreSQL 17 container; move data through a controlled backup/restore instead.

## Verification

- Backend quick suite: 191 passed, 6 PostgreSQL-only cases skipped.
- Frontend suite: 131 passed; TypeScript and Vite production build passed.
- Chromium regression suite: 12 passed, covering admissions login and existing
  administration, proctor, and recovery flows. The affected admin/login cases were
  rerun after the final legacy-edit adjustment: 3 passed.
- Isolated real Chromium → Vite → FastAPI → PostgreSQL check passed: invalid
  details, email-less approved login, HttpOnly cookie, refresh, logout, and protected redirect.
- PostgreSQL login suite: 25 passed; concurrent fresh/expired throttle windows
  rerun against the final canonical index: 2 passed.
- PostgreSQL migration round trip and ORM comparison passed after correcting
  PostgreSQL's reflected TRIM expression to explicit btrim in both model and migration.
  The initial complete PostgreSQL run had 194 passing cases and this one schema
  comparison failure; no failure was suppressed or excluded from the repair check.
- Ruff checks/formatting, strict mypy, and Git whitespace checks passed.

The first GitHub run also caught an order-dependent assertion in the new resume
test: selecting any answer in a subject could inspect an unanswered question.
The corrected assertion selects the saved exam question explicitly and verifies
both its revision and selected option; application behavior was unchanged.

Browser regression fixtures use mocked APIs; the separate real-service smoke
check used a temporary schema in the test database and removed it afterward.
No admissions data was scraped or imported, no live candidate was provisioned,
and no Google credentials were required for candidate verification.
