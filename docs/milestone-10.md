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

See the GitHub Actions run for the delivered commit for complete automated results.
Local verification includes the 142-test frontend suite and a real HTTPS/Chromium
workflow through three subjects, offline recovery, refresh with unchanged deadline,
submission, manual grading, publication and withholding, plus encrypted restoration
of critical record counts. PostgreSQL tests additionally exercise schema migrations,
start concurrency, credentials, worker readiness, and archive tamper rejection.
The local machine has PostgreSQL 16; CI and the deployment use PostgreSQL 17.
Docker Desktop was unavailable locally, so the actual container deployment is
validated separately by GitHub Actions rather than inferred from native execution.

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
