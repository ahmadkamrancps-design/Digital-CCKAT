# Milestone 5 — Resilience handover

Implemented on 8 October 2026. The CCK login, dashboard, exam, and submission
templates are preserved. This milestone adds persistent local recovery and safe
reconnection to the authenticated candidate interface. The separate development
preview remains available and does not simulate real storage, authorization, or
submission. No administrative portal or grading work was started.

## Behavior and architecture

1. An edit updates the displayed answer immediately and queues an IndexedDB
   transaction. The UI distinguishes local saving, locally preserved changes
   awaiting synchronization, and server-confirmed **Saved**.
2. The existing 350 ms debounce limits server traffic. Before a network write, the
   exact answer/review payload and expected revision are committed locally. After
   the transaction, account ownership and the deadline are checked again.
3. Ambiguous failures retain that exact request. Transient network/408/429/5xx
   failures retry with exponential backoff and jitter capped at 30 seconds.
   Online/visibility events also trigger retry; request outcomes determine status.
   Conflicts and permanent validation/access failures are not blindly retried.
4. Reload first verifies the session and retrieves fresh server state/questions.
   Recovery then compares server revisions, confirmed local answers, pending
   requests, and later local edits. Lost acknowledgements are recognized. A stale
   conflicting answer requires an explicit choice before replacement.
5. One Web Lock owns each account/attempt/subject journal in a browser profile.
   A second tab displays an explanation and retry action. Closing the owner tab
   permits handoff. Server revisions still guard writes across devices/profiles.
6. Deadline enforcement stays on the backend. The existing monotonic display
   anchor continues while offline. Expired edits are locked; reconnection obtains
   the authoritative receipt and never uploads late drafts.
7. Closed, fully synchronized journals are cleared. Unsent closed drafts remain
   locally with a warning. Explicit sign-out clears that account's copies and
   invalidates open writers; the dashboard advises waiting for Saved first.
   Involuntary session expiry preserves local copies for approved reauthentication.

Storage errors block further editing and show a retry action. Existing data is
not silently replaced when validation or storage fails. Journal writes resolve
only when the transaction completes, following the browser's
[IndexedDB transaction lifecycle](https://developer.mozilla.org/en-US/docs/Web/API/IDBTransaction).
Web Lock ownership follows the callback promise lifetime described in
[LockManager.request](https://developer.mozilla.org/en-US/docs/Web/API/LockManager/request).

## Files created or changed for this milestone

| Area | Files |
| --- | --- |
| Persistent storage | New `frontend/src/storage/recovery.ts` |
| Session construction | New `frontend/src/features/exam/createSession.ts` |
| Synchronization | Updated `AnswerQueue.ts`, `ExamSessions.tsx` in that feature directory |
| Live interface | Updated `LiveExam.tsx`, `LiveSubmission.tsx`, `pages/DashboardPage.tsx` |
| Account cleanup | Updated `frontend/src/features/auth/AuthProvider.tsx` |
| Unit/component tests | New `tests/recovery.test.ts`, `tests/browser-storage.ts`; updated `tests/setup.ts`, `tests/exam-state.test.ts`, `tests/live-exam.test.tsx` |
| Browser tests | New `frontend/e2e/resilience.spec.ts`, `frontend/playwright.config.ts` |
| Tooling | Updated frontend `package.json`, `package-lock.json`, `tsconfig.json`, `vite.config.ts`, and `.github/workflows/checks.yml` |
| Documentation | Updated README, architecture, frontend structure, security, lifecycle, database docs; this handover |

Paths within the tests row are relative to `frontend/`. No backend source changes
were needed. Playwright and fake-indexeddb are development dependencies; recovery
uses native browser APIs with no added runtime dependency.

## Database changes

No Alembic migration. PostgreSQL remains at `0003_attempt_engine`, following
`0001_auth_foundation` and `0002_exam_domain`.

Browser database `cck-answer-recovery`, schema version 1, contains:

- `drafts`: records keyed by verified user/attempt/subject, with confirmed answers,
  local drafts, exact pending requests, generation, and account epoch.
- `accounts`: logout epochs used to invalidate old writers atomically.

Generations reject stale local writes. All persistent answer fields are validated
against freshly authorized questions/options before replay. No authentication/CSRF
credentials, profile details, prompts, answer keys, or authoritative deadlines are
stored in the journal. Browser records remain untrusted input to the backend.

## Verification

| Check | Result |
| --- | --- |
| Frontend unit/component/storage suite | 89 passed across 7 files |
| Real Chromium recovery suite | 5 passed |
| TypeScript and Vite production build | Passed |
| Backend attempt regression suite | 28 passed; 3 PostgreSQL-only tests skipped in the quick SQLite setup |
| npm dependency audit during install | 0 reported vulnerabilities |

Chromium scenarios use real IndexedDB and Web Locks with stateful synthetic API
responses: offline editing and reload/reconnection, lost acknowledgement,
cross-tab handoff, offline expiry without late saves, and explicit stale-draft
conflict resolution. They do not constitute real Google/backend end-to-end
acceptance. PostgreSQL migration/concurrency tests were not rerun this milestone;
CI is configured to run the PostgreSQL suite and the new browser tests, but a
remote CI execution has not been demonstrated here.

Failures found and addressed:

- Lock release initially returned before browser ownership had ended. Release now
  awaits the lock request promise; handoff tests pass.
- An old test expected a manual retry button after reconnection. It now verifies
  the newly required automatic synchronization instead.
- The unrestricted parallel unit run encountered a one-second dashboard loading
  timeout. The configuration now bounds concurrent jsdom workers to two and the
  two-stage dashboard load gets a three-second assertion window. A second test's
  one-second limit was shorter than the intentional reconnect retry backoff;
  its four-second window now accommodates that path without changing assertions.
- WSL lacked three Chromium shared libraries. Browser tests passed using Ubuntu
  library packages extracted under `/tmp/cck-browser-libs`, without changing system
  packages. Standard installations should use Playwright's dependency command below.
- A closed-port readiness probe stalled in this WSL environment. The isolated
  Playwright server now waits for Vite's ready output and starts successfully.

## Run and verify

Use Ubuntu/WSL terminals, not Windows npm in a UNC working directory. Existing
environment files should be retained. Initial setup and Google configuration are
documented in the root README.

Infrastructure, from the repository root:

```bash
docker compose up -d db
```

Backend, in its own terminal:

```bash
cd /home/mr_laptop/cck-digital-test/backend
source .venv/bin/activate
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

Expiry worker, in another terminal:

```bash
cd /home/mr_laptop/cck-digital-test/backend
source .venv/bin/activate
python -m app.expiry_worker
```

Frontend, in another terminal (reuse an existing server on 5173):

```bash
cd /home/mr_laptop/cck-digital-test/frontend
npm ci
npm run dev
```

Open `http://localhost:5173`. To exercise real recovery, set
`VITE_ENABLE_UI_PREVIEW=false`, configure matching Google client IDs, register an
approved candidate, and assign/authorize a populated exam through the existing
admin APIs. Restart Vite after configuration changes. The local development
preview flag has been preserved; preview screens do not test persistent recovery.

Frontend checks:

```bash
cd /home/mr_laptop/cck-digital-test/frontend
npm test
npm run typecheck
npm run build
npx playwright install --with-deps chromium
npm run test:e2e
```

The browser suite uses its own port 5174 and does not need Google credentials or
the backend. On this session's WSL environment, the temporary library workaround
was `LD_LIBRARY_PATH=/tmp/cck-browser-libs/root/usr/lib/x86_64-linux-gnu npm run test:e2e`.
That temporary directory is not a repository dependency or durable setup method.
See [Playwright browser installation](https://playwright.dev/docs/browsers).

Backend checks used for this change:

```bash
cd /home/mr_laptop/cck-digital-test/backend
.venv/bin/python -m pytest tests/test_attempts.py -q
```

## Limits and next milestone

- Live recovery requires IndexedDB and Web Locks on HTTPS or localhost. Unsupported
  or blocked storage produces an explicit error. A started server timer continues
  even if local storage subsequently fails.
- Loaded papers tolerate temporary network loss. Cold offline refresh requires
  reconnection to load application assets and verify authentication/server state.
  No service worker, offline authentication, or persisted timer is implemented.
- Browser storage is confined to a browser profile and is not an encrypted vault.
  Disk failure, site-data clearing, storage eviction, or interruption before a
  transaction commits can still lose local-only work. Server confirmation matters.
- Explicit sign-out removes local recovery copies, including unsynchronized ones.
  Closed unsynchronized copies otherwise remain until cleanup/sign-out; they cannot
  extend an exam or become late answers.
- Option elimination and the current question position are presentation state;
  answer values and review flags are the persisted exam work.
- Real Google acceptance, production browser/device qualification, operational
  cleanup, load tests, security hardening, and realistic mock examinations remain.

Next: **Milestone 6 — Admin Portal**, reusing the existing protected domain APIs
and CCK design language. This milestone is not a production-readiness declaration.
