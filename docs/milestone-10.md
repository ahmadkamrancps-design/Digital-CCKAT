# Milestone 10 — production-readiness engineering

Deployment candidate for **Digital CCKAT**, planned at
**https://digital.cckat.edu.pk**, with a **7,000 simultaneous-candidate planning
target**. Public deployment and final production acceptance remain outstanding.

## Delivered

- Separate production Compose stack: same-origin TLS Nginx/React, PostgreSQL 17,
  migrations, bounded multi-worker API pools, supervised expiry and authentication
  maintenance, encrypted backups, and an explicit isolated restore profile.
- Distinct migration-owner/runtime credentials and applied least-privilege grants.
  Gateway forwarding trust, safe structured access logs, production CSP/HSTS,
  body/time/concurrency limits, health checks and restart supervision.
- Migration `0009_operational_readiness`, adding only `worker_heartbeats`.
  Readiness requires the deployed schema head and a fresh worker heartbeat in
  production. It does not reset any existing exam, answer, grade, or deadline.
- Candidate system checks now verify secure context, Web Locks, an actual IndexedDB
  write/read/delete, and API readiness. Local free preview does not call the backend.
- A focused start-path optimization: shared configuration locks allow distinct
  candidates to enter concurrently while exclusive administrative mutations remain
  serialized. Paper/key validation occurs at start authorization, which freezes
  configuration, instead of reloading every key for each candidate start. Strong
  query-count and PostgreSQL concurrency tests cover this change.
- Authenticated AES-256-GCM encrypted database snapshots, private temporary pgpass,
  atomic archive completion, freshness checks, safe fresh-database restore, and
  tamper-rejection/real PostgreSQL recovery tests. Runtime backups receive only the
  public recovery certificate; restoration requires the separate private key.
- Isolated synthetic seeding, k6 candidate profiles, native HTTPS rehearsal, real
  Chromium integration against the live API/database, an unattended expiry probe,
  and a Docker production-rehearsal CI job. Existing mock browser tests remain.
- Deployment, monitoring, recovery, capacity, and mock-exam runbooks linked below.

The supplied CCK layouts/assets and admissions login are preserved. No public
authentication bypass was added. Synthetic operator tools require disposable
`_rehearsal` databases, and manifests/secrets are ignored by Git.

## Verification record

Implementation commit `2ec5797` passed all four jobs in
[GitHub Actions run 39249496772](https://github.com/ahmadkamrancps-design/Digital-CCKAT/actions/runs/39249496772)
on 19 October 2026:

| Check | Result |
| --- | --- |
| Backend quick suite | 269 passed, 13 PostgreSQL-only tests skipped |
| PostgreSQL 17 suite | 282 passed |
| Frontend suite | 142 passed across 12 files |
| Existing Chromium end-to-end suite | 19 passed |
| Ruff, formatting, mypy, TypeScript/build | Passed |
| Python and npm dependency audits | No known vulnerabilities reported |
| Production Docker rehearsal | HTTPS, runtime privileges, load, real browser, unattended expiry, encrypted recovery passed |

The Docker load rehearsal completed 20 candidate iterations and 2,440 requests
with zero unexpected HTTP or integrity failures. Answer-save p95 was **190.26 ms**
and p99 **264.54 ms** on that CI runner. The separately executed native/local
20-candidate rehearsal completed 2,519 requests with zero integrity failures;
answer-save p95 was **662.18 ms**, p99 **803.15 ms**. These are accelerated functional
rehearsals on different machines, not a benchmark of the intended production host.

Both real-browser rehearsals traversed three subjects, offline recovery, refresh
with unchanged deadline, submission, manual grading, publication and withholding.
Direct read-only verification confirmed the worker expired an unattended subject
without a candidate API call. Docker recovery compared 1,891 synthetic answer rows
and 1,891 grading rows plus user, audit, security, session-event and subject-attempt
counts in a fresh restored database. PostgreSQL tests additionally exercise schema
migrations, start concurrency, worker readiness and encrypted-archive tamper rejection.

The local machine has PostgreSQL 16; CI and the deployment use PostgreSQL 17.
Docker Desktop was unavailable locally, so the actual container deployment is
validated by the passing GitHub Actions rehearsal rather than inferred from native
execution. CI setup failures in tmpfs YAML, PostgreSQL client provisioning, and the
backup image's incomplete Python installation were corrected and the full stack
was rerun successfully.

No full 7,000-client/three-hour test has been performed on production hardware.
Small rehearsal results must not be advertised as production capacity certification.
Real admissions records and Google credentials are not used by synthetic tests.

## Running the system

Local development instructions remain in the [README](../README.md). Use separate
WSL/Linux terminals for backend and frontend. Start PostgreSQL, migrate, then run:

```bash
cd backend
source .venv/bin/activate
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log --no-proxy-headers --no-server-header
```

```bash
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. If that port is in use, check the already running
instance rather than starting duplicates. Free preview remains local-only.
For a local worker in a third backend terminal:
`python -m app.expiry_worker --interval 0.5 --batch-size 100`.

Production commands and required secret/certificate names:
[production operations](production-operations.md). Repeatable Docker/native/mock
and 7,000-client profiles: [capacity and rehearsal](capacity-and-rehearsal.md).

The rehearsal also includes [API/worker restart recovery](restart-recovery.md):
a candidate edits during a real API outage, the pending draft synchronizes after
API recovery, worker readiness fails and recovers, and re-login preserves the
existing attempt/deadline. This runs only against disposable local synthetic data.

The [recovered-data verification](restore-verification.md) now compares every
application table's row contents and column/primary-key metadata after freezing
the disposable writers. This supersedes the earlier row-count-only comparison;
same-count changes to answers, revisions, deadlines, grades, audit history or
result visibility fail verification. The native aggregate report also records
the duration of backup, restore and verification without claiming a production RTO.

## Acceptance gaps

The domain needs institutional DNS control, a deployment host, and valid renewable
TLS. Real staff Google acceptance remains necessary. Roll/name/father-name values
are personal information and permit impersonation by someone who knows them;
institution-approved stronger or supervised verification is still required.
There is no automatic admissions-portal integration.

Hourly local encrypted dumps are not sufficient exam durability: WAL/PITR or a
managed equivalent, off-site retention, measured recovery objectives, host-loss
rehearsal, external monitoring/alerts, immutable deployment records and an independent
security review remain operational work. The single-host stack provides no HA.
The production hardware/network must pass the full capacity and supervised mock
exam gates. Accordingly, **the platform is not yet approved for real examinations**.

Recommended next work is the institution's staging deployment and acceptance
rehearsal under these gates; no additional feature milestone is started implicitly.
