# Authentication and authorization foundation

Candidates now use admissions roll number, full name, and father's name via
`POST /api/auth/candidate`. Only existing APPROVED candidates linked to an active
CANDIDATE user can receive a session. The endpoint cannot create accounts, bind
Google identities, or grant staff access. The database enforces uniqueness of
`lower(trim(roll_number))`. Names use Unicode NFKC, whitespace collapse, and
case-folding; there is no fuzzy matching or transliteration. Missing verified
father's names on legacy records deny this login. Public profiles omit this
verification field; only administrators can read/write it with candidate records.

These details are personal information, not a strong authentication secret.
An attacker who knows them can impersonate a candidate. Before real exams, add a
separately issued private exam code/OTP or supervised verification. Rate limiting
reduces guessing; it cannot prevent impersonation by someone who knows the details.
This follows OWASP's warning against relying on knowledge-based personal details:
[credential stuffing prevention](https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html).

Login responses use the same 401 message for unknown, mismatched, disabled,
missing-field legacy, and staff records. Validated requests consume persistent,
atomic PostgreSQL throttle buckets before matching: 10 requests per normalized
roll and 1,000 per client IP per 15 minutes by default, including successful
requests. Limits survive restarts and multiple workers; 429 includes Retry-After.
Expired buckets are deleted on subsequent login requests. Buckets store SHA-256
fingerprints instead of raw rolls/IPs; these fingerprints are still pseudonymous
data and are not secret hashes of authentication factors. Tune the IP limit for
shared exam-center NAT/proxies. Configure Uvicorn/reverse-proxy trusted addresses
carefully; never trust arbitrary incoming forwarded headers. Malformed requests
are rejected before the limiter, so deployment still needs proxy request limits.
See [OWASP authentication guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html).

Staff retain the existing Google login below. The backend Google route remains
compatible with previously approved candidate identities; it is no longer offered
as candidate login in the UI. Candidate email is nullable, with no generated fake
email address. Changes to any candidate login field revoke existing sessions
without changing exam attempts or deadlines. The portal has no automatic admissions
integration: trusted staff must verify and enter/import official records.

Google Identity Services provides an ID token through its JavaScript popup callback.
The backend uses `google-auth` to verify Google's signature, token expiry/issued-at,
issuer, and the configured OAuth audience. It requires `email_verified` to be true.
Google certificate requests have a five-second timeout and use CacheControl's
HTTP cache for public certificates, honoring their response cache lifetimes.
The shared requests session is serialized within each worker; credentials and
claims are verified on every sign-in and are never cached. Provider failures return
a safe 503; invalid credentials return 401. No OAuth client secret is needed for
this ID-token flow.

Google authentication alone never creates a user or approves a candidate. Staff
accounts are preprovisioned through the trusted local CLI; approved administrators
can provision candidates through the protected portal/API. The backend checks user activity
and candidate status before issuing a session and on every authenticated request.
Backend dependencies enforce roles; frontend routing is only a usability feature.

The stable Google `sub` is the identity key. If an approved record has no sub,
first login can bind by approved email only for a Gmail address or verified Google
Workspace identity (`hd` claim). Google's verification guidance cautions that other
email addresses do not establish current third-party mailbox ownership. For those,
admissions must approve an independently verified sub through the CLI. Never ask
candidates to email raw ID tokens, and never paste them into public token decoders.
A bound subject is never replaced automatically by another account with the same
email. Subsequent logins use the stable subject even if Google email changes; the
registered contact email remains administration-controlled.

Session credentials are opaque random values delivered only in HttpOnly cookies,
scoped to `/api`, with SameSite=Lax. PostgreSQL stores hashes, not raw cookie
credentials. New sign-in revokes the previous session. Logout revokes the database
record and clears the cookie. Session expiry now uses database time, matching the
exam timing authority. Production validation requires Secure cookies,
HTTPS frontend origin and separate database credentials. Staff Google login requires
a configured Google client ID; candidate login does not.
No app signing secret is required because these sessions are database-backed,
not signed self-contained tokens.

The app uses exact Origin validation for login, logout, administrator mutations,
and candidate attempt/answer mutations. The login endpoint accepts
JSON only; cross-origin JSON requires a browser CORS preflight. CORS permits only
the configured origin. This callback-to-JSON approach differs from Google's direct
form-POST delivery; Google's form-specific `g_csrf_token` is not used here. Every
authenticated mutation must also require the synchronizer CSRF token returned by
`/me`, sent in `X-CSRF-Token`. Logout, domain, and attempt mutations use this protection. Never exempt future
admin/exam mutation routes from Origin/CSRF checks.

The frontend stores session profile/CSRF state in memory. `/me` restores it on
refresh and revalidates it when the tab becomes visible or connectivity returns.
Initial network errors block protected pages with a retry message. Once a session
has been verified, a failed background network check preserves the in-memory profile
and drafts and displays a warning. A server 401/403 removes the profile and disposes
its exam queues. Every API request still requires current backend authorization;
an old profile never authorizes exam access. Authentication responses include `Cache-Control: no-store`.
Validation errors do not echo credential input. Database/unexpected errors return
safe messages; an HTTP error boundary consumes unexpected exceptions before
Starlette can re-raise them to Uvicorn's raw traceback logger. Diagnostic logs
record only error type. Auth logs include user ID
and role for success, not tokens, answers, database credentials, or Google claims.

SQLAlchemy parameterizes application queries; the frontend uses React text
rendering, `<bdi>` for mixed direction identifiers, and local `dir="rtl"` for Urdu.
There is no arbitrary HTML rendering. Answer keys, accepted values, and grading
configuration are delivered only by ADMIN-protected question endpoints. CANDIDATE,
PROCTOR, EXAMINER, and anonymous requests cannot use these endpoints. Candidate
APIs expose only the owning candidate's assignments, attempt metadata, safe started
paper content, and that candidate's saved answers. Future subjects' questions are
withheld until their subject has been started. An attempt UUID is never sufficient
authorization: assignment and candidate ownership are checked server-side.
Assigned subject summaries expose only paper ID, subject name, duration, and order.
The live renderer interprets prompts/options/answers as text, with local Urdu
direction. There is no executable administrator HTML. CSRF state exists only in
memory. Recovery drafts are scoped to the verified account in IndexedDB, with
attempt/subject IDs, revisions, and exact pending requests. No credentials, profile
details, prompts, keys, or timer authority are persisted there. Recovery data is
validated against fresh server paper data before use. Local storage never grants
access or makes an expired write valid.

Web Locks prevent simultaneous same-subject writers in one browser profile;
transactional generations protect local records and server revisions protect the
authoritative answers across devices. Explicit logout deletes that user's local
copies and increments an epoch to revoke existing writers. Involuntary session
expiry disposes in-memory queues but preserves drafts for approved reauthentication.
Closed unsynchronized drafts are retained locally and never uploaded late.
IndexedDB is not an encrypted vault: browser-profile access or same-origin script
compromise can expose local answers. Managed-device cleanup and production XSS/CSP
hardening remain necessary operational work.
The development frontend preview
contains synthetic questions with no keys and never grants backend privileges.
No submitted or expired subject accepts answer/review edits. A stale revision
returns a conflict containing only that candidate's current answer. Retries with
an identical payload do not add revisions or duplicate logical answers. Browser
timestamps are rejected, and server-clock expiry is checked after lock waits.
Revoked assignments deny subsequent candidate access while expiry continues;
reauthorizing restores the same attempt and deadline, not a retake.
Candidate management never accepts a role field or creates staff. Edits are
restricted to existing candidate-role users. Email/verified-subject/status changes
revoke existing sessions under the user lock used by authentication. Full-name/roll
changes preserve account/attempt IDs. Disabled candidates cannot authenticate or
receive new assignments. Imports validate all rows and preserve existing records
on any error. Staff actions commit with successful writes and contain actor/record
IDs, type, and server time, without answers, tokens, or raw identity values.
Admin pages require a verified ADMIN profile before fetching lists or keys;
backend role checks remain authoritative. New mutation routes enforce Origin/CSRF.

Unpublishing an exam pauses new starts but preserves authorized active-attempt
access and deadlines; revoking an assignment or disabling a candidate blocks access.
The result-release endpoint requires paused starts and complete grading of every
attempt. A planned date alone cannot expose scores; authorization plus the server
release time and complete grades are required. Candidate paper/answer schemas are unchanged.
The CLI runs only for operators with database credentials and must not be exposed
as a web service.

Monitoring APIs require active PROCTOR or ADMIN authentication. Each PROCTOR read
also checks an active exam-specific assignment; revocation denies subsequent reads.
ADMIN controls assignments using Origin/CSRF-protected writes. Proctors cannot
change exam starts, candidate eligibility, grades, or answer content. Monitoring
responses use explicit schemas and omit question/answer/key data and identity email.
Frontend access denial clears the displayed snapshot; network failures instead
retain clearly labeled stale data. Account changes remount the monitoring scope.

Candidate presence writes use owning-attempt/assignment validation plus Origin/CSRF.
Only an active subject and valid reported question position are accepted. The server
assigns time, permits no more than one update every five seconds, and limits batches
to eight allowlisted browser events. Nonces deduplicate repeated reports. Browser
metadata cannot claim authoritative server events; source/type checks exist in SQL.
Raw answers, authentication credentials, and free-text metadata are not accepted.

Connection status represents recent server contact rather than proof of physical
network state. Browser events are untrusted and can be missing, delayed, or fabricated;
they support authorized human review and never trigger cheating judgments, score
changes, time extensions, or automatic penalties. The bounded in-memory browser
event buffer is best-effort and separate from durable answer recovery.

Milestone 9 adds shared authentication throttling, certificate caching, authentication
events, PostgreSQL history guards, cleanup tooling, request limits, response headers,
dependency auditing, and concurrent successful-login tests. See the detailed review
and remaining production risks in [Milestone 9](milestone-9.md). Deployment, operational
monitoring, full HTML script policy, and stronger candidate verification remain
unfinished. This system is not production-ready and does not authorize real examinations.

Primary references:

- [Google token verification](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token)
- [Google web-client setup](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid)
- [Google sign-in button](https://developers.google.com/identity/gsi/web/guides/display-button)

Milestone 8 grading routes allow ADMIN or explicitly exam-assigned EXAMINER only;
PROCTOR and CANDIDATE cannot fetch queues, inspect grade histories, or assign marks.
Manual review exposes only submitted exam responses and required question text;
it does not send accepted answers or MCQ keys to examiners. Automatic backfill and
publication are ADMIN-only. Writes require Origin plus CSRF. Notes and candidate
responses remain plain React text and are not put in diagnostic or staff-action logs.

Manual marks use Decimal, question-specific maxima, optimistic grade revisions,
and row locks. A repeat of the immediately previous identical request by the same
actor is safely acknowledged; stale or competing edits fail with 409. Corrections
require notes and append history with staff ID and server time. Authorized or
scheduled publication freezes all grade changes until results are explicitly
withheld. API question configuration remains frozen after paper use.

Candidate result DTOs contain only titles, publication/grading status, released
subject totals, total marks, and server-computed percentage. Before release, marks,
maximum, percentage, and subject results are absent/null even if grading is done.
The endpoint filters by the authenticated candidate and current exam assignment;
it cannot accept a different candidate identity. Proctor responses remain unchanged.
Database owners can still disable triggers or change schema/permissions. Milestone 9
includes a tested least-privilege runtime-role grant template; production must actually
use separate runtime and migration credentials. These features alone do not establish
production readiness.

## Milestone 9 controls and boundaries

`RequestLimitsMiddleware` buffers only bounded API bodies before FastAPI parses
JSON: 16 KiB for authentication and `MAX_REQUEST_BYTES` (2 MiB by default) elsewhere.
It counts streamed chunks and does not trust Content-Length. Nonempty bodies require
`application/json`; compressed bodies are rejected. Empty POST requests remain valid
for start/submit/logout actions. These controls follow
[OWASP REST input guidance](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html).
They do not replace ingress connection, header, concurrency, and slow-body timeouts.

Google login consumes an atomic database IP bucket before token verification:
`GOOGLE_LOGIN_IP_LIMIT=120` per 15 minutes, including successful requests. Candidate
limits keep their existing roll/IP policy. Both use IP-before-account lock order,
stop at the first blocked bucket, cap counters at limit + 2, and return Retry-After.
Thus a blocked IP cannot create unlimited new roll buckets. Well-formed requests
are limited; invalid JSON/schema requests still need ingress limits. No blanket
answer-write throttle has been added: autosave retries retain existing behavior.
On the development proxy all users share its loopback IP; tune deployment limits
for the verified proxy topology and exam-center NAT.

The Vite proxy strips incoming Forwarded/X-Forwarded-* identity headers; the backend
Docker command disables proxy-header trust. Use `--no-proxy-headers` locally too.
Production must overwrite forwarded headers at a trusted ingress and explicitly
trust only its addresses if client-IP forwarding is enabled. Never expose a backend
which trusts client-supplied IP claims. CORS/Host configuration alone cannot do this.

`security_events` records LOGIN_SUCCESS, LOGIN_FAILURE, first LOGIN_THROTTLED for a
bucket window, and LOGOUT, with method, nullable approved user ID, and server time.
It stores no names, rolls, emails, IPs, credential hashes, tokens, answers, or notes.
Unknown/denied login events have no user ID; they support aggregate review rather
than identifying the source of an attack. Successful login/logout events commit
with session changes. Unauthenticated validation, Origin/CSRF failures, provider
outages, and all permission denials are not yet recorded in this table.
There is no new public event endpoint; authorized database operators can inspect
it with a read-only monitoring role. A retention/export/alerting policy still needs
operational design. Avoid retaining unlimited failed-login events without monitoring.

PostgreSQL migration `0008_security_hardening` rejects UPDATE, DELETE, and TRUNCATE
on audit_events, session_events, grading_records, and security_events through
statement triggers. Grading corrections must append revisions. Inserts still use
existing foreign keys, checks, transactions, and allowlists. SQLite unit tests do
not simulate this protection: dedicated PostgreSQL tests enforce it. A schema owner
or superuser can remove the guards; the tested `ops/grant-runtime.psql` template
also denies history mutation, DDL, and Alembic writes to a separate runtime role.
Local development still uses its existing owner role; the template is not applied
silently to that database. Backups/external log retention remain necessary.

API responses, including generic failures, have no-store, nosniff, DENY framing,
strict-origin referrer policy, and a CSP denying frames/objects/base URLs. Production
API responses also set one-year HSTS without includeSubDomains/preload. The Vite
development HTML adds framing protection, nosniff, and strict-origin referrer policy.
API headers do not protect the separately served production HTML: configure and
test its full CSP and HSTS at the production ingress in Milestone 10.
See [OWASP response-header scope](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html).

Google ID tokens remain bearer credentials valid until Google's expiry. The current
popup flow verifies signature/audience/issuer/time/email plus Origin, but has no
single-use nonce/token replay registry. A stolen valid token could establish another
session during that lifetime. Keep tokens out of logs/storage/URLs, enforce HTTPS,
and assess nonce-bound sign-in with the actual staff Google configuration before
production acceptance. Candidate login continues to require an existing approved
record and intentionally retains the personal-information weakness described above.

`python -m app.auth_maintenance --batch-size 1000` removes a bounded batch of expired
sessions and throttle buckets using database time and skip-locked row locks. It
preserves active sessions, accounts, attempts, answers, and every history table.
Scheduling it and managing audit retention are operator responsibilities, not app
startup side effects. Logout/rotation continue to revoke sessions immediately.

Both lockfiles were audited with no known vulnerabilities reported on 14 October
2026; CI now runs npm audit and pip-audit against pinned production/development
dependencies. This is an advisory check, not a guarantee against unknown issues.
Dependencies are pinned but Python artifact hashes and a full supply-chain attestation
are not yet enforced. Build contexts already exclude real .env files; the tracked-file
review found no credential-pattern matches. Production secrets must come from the
deployment secret store and never from committed development examples.
