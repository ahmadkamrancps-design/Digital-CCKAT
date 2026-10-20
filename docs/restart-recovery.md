# API and expiry-worker restart rehearsal

This Milestone 10 check uses the existing disposable HTTPS rehearsal. It exercises
the actual browser, proxy, API processes, PostgreSQL, IndexedDB and expiry worker.
The CCK candidate interface and application authorization/timer rules are unchanged.

Run `bash ops/rehearsal_compose.sh` from the repository root after the dependencies
in [capacity and rehearsal](capacity-and-rehearsal.md) are installed. The native
fallback runs the same protocol through `ops/rehearsal_native.py`; use its `--help`
for local Nginx/PostgreSQL paths. Existing rehearsal directories are never overwritten.

The helper `ops/restart_rehearsal.py` coordinates these checks:

1. A synthetic approved candidate starts English and saves an MCQ, review flag
   and short answer. The browser retains the authoritative start/deadline values.
2. The operator stops **only the disposable API and expiry-worker services**.
   The HTTPS gateway remains running and returns an upstream failure for API calls
   (502, 503 or 504). The probe waits longer than the gateway's upstream-connect
   timeout, distinguishing an actual HTTP gateway failure from a client timeout.
3. The candidate edits the short answer during that outage. The browser must show
   `Offline / waiting to sync` and confirm that a local recovery copy is preserved.
4. The API restarts while the worker remains stopped. Liveness must recover; after
   the real 30-second worker-heartbeat allowance expires, readiness must return 503.
   No fake clock, shortened deadline or health-check override is used.
5. The browser must synchronize the pending draft. A direct candidate API read
   verifies its text and exactly one revision increase. The earlier MCQ/review
   answer, original start timestamp and original deadline must be unchanged.
6. The expiry worker restarts and readiness returns 200. The candidate signs in
   again through the normal admissions endpoint, reopens the exam and refreshes.
   The attempt ID, deadline and recovered response must survive those actions.
7. The existing three-subject/offline/submission/grading/result-release flow
   continues. Independent read-only SQL checks still verify unattended expiry,
   and the final encrypted restore must preserve critical record counts.

Browser/operator coordination uses a fresh private directory containing empty
marker files. Credentials stay in the existing private synthetic manifest/browser
session. No browser-accessible restart endpoint, fake authentication route or
production backdoor is introduced. Invalid/non-synthetic manifests and non-localhost
origins are rejected before the helper invokes any stop/start action. The Compose
helper fixes the disposable project name to `cck-rehearsal`; it is not a general
production restart tool.

Each phase has a timeout. Failure stops the rehearsal and triggers cleanup rather
than reporting success. The browser records fixed phase labels; after a failed
workflow the operator prints only the phase and an allowlisted error category.
This identifies the failing step in CI without publishing Playwright assertions,
answers, credentials or response bodies. Full browser diagnostics stay in private ignored `browser.log`;
do not publish this file, the manifest, secrets or browser storage. Successful runs
write `restart-report.json` with aggregate check outcomes and no answers/tokens.
The native aggregate report also records `restart_recovery`.

This verifies graceful service restarts and a real API outage at small functional
load. It does not certify abrupt host power loss, database/storage failure, WAL/PITR,
failover, alert delivery to operators, a three-hour soak or 7,000-candidate capacity.
Readiness failure is an observable signal; external monitoring still needs to be
configured to notify the designated operators. Run the full deployment acceptance
programme on the intended hardware before a real examination.
