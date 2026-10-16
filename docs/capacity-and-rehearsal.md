# Capacity and mock-exam acceptance

Planning target: **7,000 simultaneous candidates**, three independently timed
60-minute subjects, configurable papers. No 7,000-candidate production capacity
claim follows from local/unit tests or the small CI rehearsal.

## Repeatable disposable rehearsal

Install Python 3.12+, Docker Engine/Compose v2, Node 24/npm, and OpenSSL. Install
frontend dependencies and Chromium, then run from the repository root:

```bash
npm ci --prefix frontend
cd frontend
npx playwright install --with-deps chromium
cd ..
bash ops/rehearsal_compose.sh
```

The script creates a fresh ignored `test-results/production-rehearsal` directory,
two-day local self-signed certificates, random file-based secrets, and an isolated
Compose project named `cck-rehearsal`. It uses localhost ports 8080/8443. It seeds
22 synthetic candidates and 90 questions through an operator-only tool restricted
to an empty database ending `_rehearsal`. A second one-minute paper is left
unattended to verify actual worker expiry by direct read-only SQL, without an API
request triggering reconciliation. Account 0 is reserved for the browser, account
1 for expiry, and accounts 2 onward for load testing.

It runs a 20-client k6 functional load check, a real Chromium workflow against the
HTTPS API/database, runtime-role checks, and an encrypted restore into a fresh
database. Cleanup removes **only the disposable Compose project's volumes**.
The private manifest contains synthetic credentials and an administrator session;
do not upload it, secrets, browser storage, or database dumps as CI artifacts.
The load summary contains aggregate measurements and sanitized route labels.
To rerun, retain desired aggregate evidence then move/remove the old rehearsal
directory deliberately; the script refuses to overwrite it.

GitHub Actions runs this production-stack rehearsal separately from unit/API tests
and existing browser tests, which mock network responses. Neither substitutes for
the other. A native fallback exists for machines without Docker:
`PYTHONPATH=backend backend/.venv/bin/python ops/rehearsal_native.py --help`.
It needs local PostgreSQL client/server tools, Nginx 1.28+, envsubst, and Chromium.
It creates and cleans up separate databases/roles and never changes the development
database. Its single database owner is not a runtime-role deployment test.

## Load profiles on the intended staging hardware

`ops/load/exam.js` uses k6 2.3.0. Only a synthetic private manifest is accepted.
Choose candidate count and duration when running `python -m app.rehearsal_seed` as
the owner in an empty staging `_rehearsal` database. Use 7,002 candidates for the
maximum profile. Never run load tests against real admissions records or an active
exam. Match staging hardware/network/database configuration to the proposed deployment.

```bash
CCK_REHEARSAL_MANIFEST=/private/path/manifest.json \
CCK_BASE_URL=https://YOUR-STAGING-HOST \
CCK_VUS=7000 CCK_RAMP_SECONDS=600 CCK_SECTION_SECONDS=3600 \
CCK_QUESTION_PAUSE_SECONDS=0 CCK_MAX_DURATION=3h30m \
  k6 run --summary-export /private/path/load-summary.json ops/load/exam.js
```

Use a valid staging certificate. `CCK_LOCAL_SELF_SIGNED=true` is only for isolated
localhost rehearsal, never a public exam. Distribute load generation across separate
hosts if the generator saturates; do not confuse generator limits with server limits.

The profile logs in each candidate, verifies assigned-exam authorization and
idempotent start, traverses three 30-question papers, saves/reviews responses,
checks duplicate acknowledgement and stale-write rejection, preserves deadlines
across reads, rejects writes after submission, and checks withheld results. Full
duration pacing includes ten-second presence heartbeats. These heartbeats alone
mean approximately **700 requests/second** at 7,000 active sessions, before saves,
navigation, staff monitoring, and login bursts. Monitor and include proctor polling
and manual grading separately; this profile does not model thousands of proctors.
Do not automatically run the small browser driver's full manual-grading loop after
a maximum-size load test; its serial grading is functional verification, not a
grading throughput benchmark.

Proceed in recorded stages: 20 functional clients, 100, 500, 1,000, 3,000, then
7,000. Run both staggered arrivals and synchronized test-center bursts. Include
three-hour soak, simultaneous subject transitions, near-deadline writes/expiry
backlog, restarts, reconnection storms, backup load, and result-release traffic.
The accelerated default profile is intentionally not a three-hour simulation.

Preliminary thresholds in the script: unexpected HTTP failures below 0.1%, checks
above 99.9%, **zero integrity failures**, answer-save p95 below 1.5 seconds and p99
below 3 seconds, no dropped iterations. Expected 409/410 responses are validated
explicitly. Investigate every mismatch, missing answer, wrong score, reset timer,
unauthorized response, and stale overwrite even if aggregate latency looks good.
Agree final service objectives with the institution before sign-off.

Capture host/image/configuration identifiers, test commit, generator specifications,
active sessions, arrival pattern, latency percentiles, failures, CPU/RAM/disk/network,
DB connections/lock waits/slow query fingerprints, expiry lag, backup duration,
restoration duration and verified record counts. Do not retain raw credentials,
answers, or private keys in public reports. Scale worker/pool counts only after
measuring; eight workers at pool size five consume up to 40 API connections, plus
background/operational connections. More API workers can exhaust PostgreSQL.

## Supervised mock examination and release gate

Before a real admission exam, complete and record:

- Valid public DNS/TLS and actual staff Google sign-in/RBAC acceptance.
- An institution-approved response to impersonation risk in roll/name/father-name
  login; supervised identity checks or a separately issued private factor.
- Verified admissions import, correct subject order/durations/questions/keys,
  Urdu input/font rendering, mathematical content and accessible keyboard operation.
- Test-center devices/network at the intended scale, with managed-profile cleanup.
- A 7,000-client capacity run on the actual deployment and an appropriate supervised
  mock examination, including clock manipulation, refresh, re-login, temporary
  network loss, API/worker restart, deadline crossing, and prohibited late edits.
- Tested WAL/PITR/off-site backup recovery, agreed RPO/RTO, alert delivery, certificate
  renewal, on-call ownership, and rehearsed outage/rescheduling procedures.
- Independent authorization/security review, institution-approved privacy/audit
  retention, result/grading review, and explicit release sign-off.

None of these external acceptance items is implied by a green CI badge.
