# Railway deployment candidate

This adapts the existing CCK application for Railway. It is preparation for a live
staging deployment, not approval for admission examinations or a claim of capacity
for 7,000 simultaneous candidates. Existing local data is not uploaded automatically.

## Staging deployment record — 15 November 2026

- Public HTTPS address: https://web-staging-f483f7e6.up.railway.app
- [Railway project dashboard](https://railway.com/project/45d57217-e4fc-435e-a29b-2edbf22e32a0),
  environment `staging`. The separately created default `production` environment is empty.
- Web and expiry-worker were built from repository commit `178c985` using CLI uploads.
  GitHub-triggered automatic deployments are not configured. Future source updates
  must be deliberately deployed to both services after passing checks.
- Railway's current PostgreSQL template provisioned PostgreSQL 18 with persistent
  storage. All Alembic migrations completed on that instance. Runtime traffic uses
  `cck_runtime`, without schema-creation or audit-update privileges; migrations use
  the distinct `cck_owner` account. The database has no public TCP endpoint.
- The cloud bank contains the 90 original practice items. A separately labelled
  six-question practice demo has English, Mathematics and Urdu/Islamiat sections,
  each configured for 60 minutes. The previously supplied demo candidate is assigned
  and its attempt was left unstarted. Local candidate records, edited exams and
  existing attempts were not copied from WSL.
- Live HTTPS API verification covered readiness, login/secure cookies, three subject
  starts, answer saving and idempotent retries, review flags, refresh with unchanged
  deadlines, submission and rejection of post-submission edits. Candidate responses
  contained no keys; results remained withheld. The separate verification candidate
  was disabled after testing and its submitted evidence was retained.

The administrator account is provisioned, but **public staff Google sign-in still
requires a Google OAuth web client ID**, configured with the exact HTTPS origin in
Google Cloud and both Railway client-ID variables. Rebuild web after setting its
frontend client ID. Candidate admissions-details login works without Google.
The localhost-only free-administration entry does not exist on the public site.
No institutional custom domain, external alerts, backup/PITR acceptance, full-scale
load test or real-exam approval is implied by this staging deployment.

## Services

| Service       | Source                                               | Start command                                                  | Public domain |
| ------------- | ---------------------------------------------------- | -------------------------------------------------------------- | ------------- |
| Postgres      | Railway PostgreSQL template, with persistent storage | Template default                                               | No            |
| web           | Repository root, `Dockerfile.railway`                | `python -m app.railway web`                                    | Yes, HTTPS    |
| expiry-worker | Same repository/image                                | `python -m app.railway worker --interval 0.5 --batch-size 100` | No            |

The image builds React with preview and management-sandbox flags disabled. FastAPI
serves the built assets and application routes on the same origin as `/api`.
Candidate roll/name/father-name authentication, HttpOnly secure cookies, CSRF,
roles, timing, grading and result-release checks use the existing implementation.
The local free-administration helper is excluded. Real administration requires an
approved staff account and configured Google sign-in.

Railway supplies TLS at its public ingress; the container listens on `PORT` without
requiring certificate files. The existing Nginx/Compose deployment remains available
for other hosting. Only the built `static/assets` directory and known React routes
are served; backend source, question keys, dotfiles and unknown API paths are not.
The web adapter applies the browser security policy previously supplied by Nginx.

## Account and repository connection

Install/connect Railway in ChatGPT/Codex and authorize the intended workspace, or
use Railway's own dashboard. Grant Railway's GitHub integration access to the
private repository `ahmadkamrancps-design/Digital-CCKAT`. Confirm the workspace,
billing plan and spending limit before creating resources. Credentials belong in
Railway variables, not chat, commits or screenshots.

Create a project with a staging environment, then add PostgreSQL and the two services
above from the same repository. Keep each application service's source root at `/`.
Set `RAILWAY_DOCKERFILE_PATH=Dockerfile.railway` on each application service. Railway
service settings supply the commands and health checks; no deprecated `railway.json`
or `railway.toml` is required.

## Database ownership and runtime account

Use a new database, separate from development and the management sandbox. Before
deploying the application, provision the fixed `cck_runtime` LOGIN role using the
private PostgreSQL owner connection. Use an independent generated password and
`NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS`, with no
owner-role memberships. Do not print the password in a command, log or commit.
If that role already exists, inspect its ownership and grants; do not replace its
credentials as an automatic retry.

The web service's **pre-deploy command** is:

```text
python -m app.railway migrate
```

This uses `CCK_MIGRATION_DATABASE_URL` to run the existing Alembic migrations and
grant the existing restricted runtime permissions to `cck_runtime`. Ordinary web
requests and expiry processing use `DATABASE_URL` with that runtime account.
Do not use the owner connection for ongoing application traffic. Give the worker
only the runtime connection. Run pre-deploy migrations on web only; deploy the
worker after migrations complete.

The entry point accepts Railway's `postgresql://` URL and selects the installed
`postgresql+psycopg` driver while retaining escaped passwords and query options.
Use the PostgreSQL service's **private** hostname/URL inside Railway. Never use a
WSL localhost URL or a published database TCP proxy for application traffic.

## Variables and deployment order

On web and expiry-worker:

```text
ENVIRONMENT=production
DATABASE_URL=<private URL using cck_runtime and its independent password>
FRONTEND_ORIGIN=https://<web Railway domain or confirmed custom domain>
ALLOWED_HOSTS=["<web hostname>","healthcheck.railway.app"]
SESSION_COOKIE_SECURE=true
REQUIRE_EXPIRY_WORKER=true
DATABASE_POOL_SIZE=5
DATABASE_MAX_OVERFLOW=0
CANDIDATE_LOGIN_IP_LIMIT=20000
GOOGLE_CLIENT_ID=<approved staff OAuth web client ID>
```

Additionally, on web only:

```text
CCK_MIGRATION_DATABASE_URL=<private owner URL, used by pre-deploy only>
VITE_GOOGLE_CLIENT_ID=<same staff OAuth client ID, available at build time>
```

Set worker `DATABASE_POOL_SIZE=1`. Do not set `DATABASE_URL_FILE` in this adapter.
Variables must contain actual private values, not these placeholders. Railway
reference variables can share the origin/client ID and refer to the database
service's host/port/database; ensure generated passwords are properly URL encoded.
Keep worker and web in the same environment and region.

Generate the web domain and set the exact origin/allowed hosts before deployment.
For a custom domain, verify ownership, DNS and certificate provisioning before
switching the origin. The planned `digital.cckat.edu.pk` is not automatically owned
or configured by adding it to an environment variable.

Deploy web with the migration pre-deploy command; start expiry-worker after the
migration step succeeds. Set the web deployment health-check path to
`/api/health/ready`, timeout 300 seconds. Readiness waits for both the schema and a
fresh expiry-worker heartbeat, so start the worker while web waits for readiness.
Keep worker always running, without a public domain or HTTP health-check path.
Disable sleeping/serverless mode on both services. Use restart-on-failure or always
restart policies, and avoid deployments during an exam.

Railway's startup health check is not continuous monitoring. Add independent HTTPS
readiness/worker alerts. This adapter deliberately distrusts incoming forwarded-IP
headers; login quotas by IP consequently apply to a shared ingress address. The
shared-center quota above is an initial staging value, not a substitute for
reviewed ingress abuse limits. Configure provider-level request limits and review
trusted client-IP handling before public admission use. Per-roll limits still apply.

## First staff account and smoke test

Configure the staff OAuth client with the exact public HTTPS origin, then rebuild
web if its frontend client ID changed. Through an authorized Railway service shell,
run the trusted CLI (replace with institution-approved staff details):

```text
python -m app.railway cli register-staff --email APPROVED_EMAIL --name "Approved Administrator" --role ADMIN
```

Open the public domain, expand **Staff sign-in**, authenticate and confirm `/admin`
loads. Register a synthetic candidate through the portal, configure a small paper,
assign/publish/enable starts, then test candidate login, refresh/resume, autosave,
expiry, submission and released/withheld results on HTTPS. Confirm anonymous and
candidate sessions cannot fetch `/api/admin/questions` or answer keys. Never deploy
the local `ops/management_sandbox.py` helper to gain public admin access.

Run `python -m app.railway maintenance --batch-size 1000` as a private scheduled job
(for example every five minutes). Its image and runtime variables match the worker;
it has no public endpoint. Configure PostgreSQL backups, off-site recovery and a
tested restore process separately. The Railway adapter does not automatically
schedule the Compose backup service or copy local databases.

Before importing actual admissions data, complete the existing
[production acceptance gates](milestone-10.md#acceptance-gaps), including stronger or
supervised candidate verification, teacher-reviewed questions, recovery testing,
monitoring, host sizing and a realistic mock exam. A successful Railway build is
not a completed production acceptance test.

## References

- [Railway Dockerfiles](https://docs.railway.com/builds/dockerfiles)
- [Railway health checks and PORT](https://docs.railway.com/deployments/healthchecks)
- [Railway private networking](https://docs.railway.com/networking/private-networking)
- [Config-as-code migration notice](https://docs.railway.com/config-as-code)
