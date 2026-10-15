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
Google certificate requests have a five-second timeout. Provider failures return
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
record and clears the cookie. Production validation requires Secure cookies,
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
safe messages; diagnostic logs record only error type. Auth logs include user ID
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
The result-release endpoint rejects release while grading is unavailable. A planned
date is configuration only and cannot expose scores. Candidate paper/answer schemas are unchanged.
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

Unfinished hardening: distributed rate limiting, certificate caching, an append-only
database-enforced audit immutability, broader security-event coverage, OAuth replay/nonce policy,
expired-session cleanup, security monitoring,
production reverse proxy/CSP/HSTS configuration, dependency review, and concurrent
login stress testing. Trusted-host and CORS settings are not substitutes for these.
This milestone is not production-ready and does not authorize real examinations.

Primary references:

- [Google token verification](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token)
- [Google web-client setup](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid)
- [Google sign-in button](https://developers.google.com/identity/gsi/web/guides/display-button)
