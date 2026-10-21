# Production operations — Digital CCKAT

Planned address: **https://digital.cckat.edu.pk**. Target: **7,000 simultaneous
candidates**. This repository contains a deployment candidate and disposable
rehearsals, not approval to conduct an admission examination. The hostname did not
resolve during the local rehearsal. No public server, DNS record, certificate,
monitoring account, or admissions integration has been provisioned.

## Deployment configuration

Use a Linux Docker Engine host with Compose v2, current OS security updates,
adequate disk capacity, synchronized system time, and an approved recovery plan.
Run from the repository root in Linux/WSL; Windows npm against a WSL UNC path is
unsupported. Docker Desktop needs Ubuntu WSL integration enabled.

`compose.production.yml` is deliberately separate from the development stack:

- Nginx serves the production React build over TLS and proxies `/api` on the same
  origin. Preview access is disabled in production builds. The supplied CCK pages
  and assets remain the interface.
- PostgreSQL 17 has no published port. A migration owner and a restricted runtime
  role have different credentials. Migration completion gates API startup.
- Two API containers with four workers each default to five database connections
  per worker, no overflow. This is a **starting configuration**, not a capacity claim.
- Supervised expiry and authentication-maintenance services run independently.
- The backup service writes authenticated encrypted archives. The private recovery
  key is only mounted by the explicit restore profile.
- Application/gateway containers run without root or extra capabilities, with
  read-only filesystems and writable temporary storage. Logs rotate locally.

The ingress subnet must not overlap host/VPN networks. If it changes, update both
`CCK_INGRESS_SUBNET` and `CCK_INGRESS_IP`. Only that gateway address is trusted for
forwarded client addresses. Keep API/database ports private. Never use `*` for
Uvicorn's trusted proxy list. A CDN or external load balancer needs a separately
reviewed forwarding configuration; it cannot simply be added in front.

## Operator provisioning before the first deployment

1. Confirm control of `cckat.edu.pk` and create the `digital` DNS record pointing
   to the intended server/load balancer. A domain under `cck.edu.pk` is a different
   DNS zone. Obtain a valid public certificate for the confirmed hostname and
   automate renewal and gateway reload/recreation. Do not publish the rehearsal's
   two-day self-signed certificate.
2. Copy `ops/production.env.example` to ignored `.env.production`. Set real paths,
   hostname, backup UID/GID, networking, and deployment sizing. Do not put passwords
   in this environment file. Keep `GOOGLE_CLIENT_ID` consistent between frontend
   build and backend; configure Google's authorized JavaScript origin as
   `https://digital.cckat.edu.pk` for staff login. Rebuild the frontend after changes.
3. Create a private operator-owned secrets directory, mode `0700`, outside Git.
   Create independent strong `bootstrap_password`, `owner_password`, and
   `runtime_password` files. Add `owner_database_url` and `runtime_database_url`
   containing respectively
   `postgresql+psycopg://cck_owner:<URL-encoded-password>@db:5432/cck_production`
   and the corresponding `cck_runtime` URL. Never paste these values into logs or
   tracked configuration. Add the issued `tls_certificate.pem` certificate chain
   and `tls_private_key.pem` key.
4. Generate a separate long-lived RSA recovery certificate/key, keeping the private
   key encrypted/offline under the institution's recovery-key custody process.
   Deploy only `backup_certificate.pem` for normal backup operation. Provide
   `backup_private_key.pem` and `restore_database_url` only for a controlled restore
   operation. The restore URL must identify a fresh database ending `_restore`.
   Rehearse key recovery before deleting the original secure copy.
5. Compose file secrets are bind mounts, not a secret manager. Container UIDs must
   be able to read the mounted files. The local rehearsal uses readable files
   inside a `0700` host directory; a deployment may instead use reviewed groups,
   ACLs, or a secret manager. Do not expose the directory to other host users.
   Create the backups directory owned by `CCK_BACKUP_UID:CCK_BACKUP_GID`, mode `0700`.

After those inputs exist, inspect configuration without printing expanded secrets:

```bash
docker compose --env-file .env.production -f compose.production.yml config --quiet
docker compose --env-file .env.production -f compose.production.yml build
docker compose --env-file .env.production -f compose.production.yml up -d --wait --wait-timeout 180
docker compose --env-file .env.production -f compose.production.yml ps --all
curl --fail https://digital.cckat.edu.pk/api/health/ready
```

Bootstrap staff through the trusted migration-owner CLI, not the public website:

```bash
docker compose --env-file .env.production -f compose.production.yml run --rm migrate \
  python -m app.cli register-staff --email approved-staff@example.edu.pk \
  --name 'Approved Administrator' --role ADMIN
```

Replace those illustrative staff values with institution-approved records. Test
actual Google login, role restrictions, and logout before using the admin portal.
Import only verified admissions records; there is no live admissions-portal sync.

## Monitoring and test-day operations

Wire external alerts to HTTPS availability, `/api/health/ready`, container restart
counts, gateway 429/503 rates, request latency, CPU/RAM, database connections/locks,
backup freshness, free disk space, and certificate expiry. Container health status
alone does not notify anyone. Establish a named primary operator and backup operator.

`/api/health` is process liveness. Readiness checks the actual migration head and,
when `REQUIRE_EXPIRY_WORKER=true`, the expiry worker's last successful DB heartbeat
(stale after 30 seconds). API container probes call its HTTP readiness endpoint;
worker probes check the database heartbeat. Answer writes still enforce deadlines
even during worker failure. Investigate unhealthy services before permitting starts.

The gateway logs request ID, method, status, duration, and upstream duration. It
omits URL/query, cookies, credentials, answer text, and client IP. Application logs
and append-oriented audit histories remain distinct. Forward safe logs to restricted
external retention and alerting; define institution-approved retention periods.
PostgreSQL statement/error-statement logging is suppressed to avoid answer leakage.
Do not enable SQL parameter logging during an exam.

The default login quota allows a shared exam-center NAT (20,000 requests/IP per
15 minutes); the per-roll quota remains 10. Gateway rates and per-worker concurrency
are initial limits to validate under the capacity plan, including simultaneous login.

For an incident: pause new starts using the admin control, retain existing answers
and volumes, inspect readiness/worker/DB/disk status, restore connectivity, and have
candidates resume their existing attempt. A restart must never recreate attempts or
extend deadlines. Do not delete volumes, reset timestamps, clear IndexedDB, or run
schema downgrades as an incident shortcut. If a central outage crosses deadlines,
follow the institution's authorized rescheduling process and preserve the evidence.

Use dedicated managed browser profiles and supervised workstations. After verified
submission/synchronization, clear that candidate's browser profile according to the
test-center policy. Recoverable local answers are sensitive; do not reuse a profile
between candidates without cleanup. Browser events require human review.

## Backups and restoration

The backup loop runs hourly. Archives use PostgreSQL custom format inside
OpenSSL CMS AES-256-GCM encryption; a SHA-256/size sidecar detects incomplete copies.
Restore authenticates the complete encrypted payload before executing any SQL,
requires an empty `_restore` database, and runs `pg_restore` as one transaction.
No live application table is overwritten. Temporary plaintext exists only during
restore in private temporary storage (a 1 GB tmpfs in the supplied profile).

```bash
docker compose --env-file .env.production -f compose.production.yml run --rm backup backup
docker compose --env-file .env.production -f compose.production.yml run --rm backup status
# After creating an EMPTY database and providing its restore URL/private key:
docker compose --env-file .env.production -f compose.production.yml --profile restore \
  run --rm restore restore --archive /backups/SELECTED-ARCHIVE.dump.cms
```

Select the archive deliberately; the placeholder above is not a real filename.
Validate migration version, row counts, raw answer samples under authorized access,
grading/audit history, constraints/triggers, and application behavior against the
restored copy. Reapply the runtime grants when provisioning a replacement database;
archives deliberately omit original ownership and ACLs. Switching the application
to a recovered copy requires an operator-reviewed recovery plan and new credentials.

The disposable [restore rehearsal](restore-verification.md) automatically compares
all row contents and column/primary-key metadata, including answer revisions,
deadlines, grades and release settings. Its verifier requires synthetic rehearsal
and restore database names and must not be pointed at production records. It does
not replace the operator's schema, privilege and application acceptance checks.

**Hourly logical snapshots can lose up to an hour of acknowledged answers if the
database/storage is lost. They are insufficient as the sole exam recovery strategy.**
Before real exams, provide tested PostgreSQL WAL/PITR or a managed equivalent,
encrypted off-site copies, monitored replication/storage durability, agreed RPO/RTO,
and measured restoration times on the intended data volume. No automatic off-site
copy, retention deletion, failover, or certificate issuance is implemented here.
Size restore scratch space for the uncompressed dump; enlarge/replace the tmpfs
after measuring it. Keep multiple recovery points, and rehearse loss of the host
and loss of the primary operator, not just a healthy local restore.

## Updates and rollback

Use reviewed, passing Git commits and record image IDs/digests, database migration
head, configuration revision, and the latest tested recovery point. Freeze software
and question configuration before an exam window. Rebuild current base images and
scan them before deployment; tags alone are not immutable deployment records.
Back up before migration. Deploy and rehearse schema/application compatibility in
staging first; do not assume an Alembic downgrade is a safe data rollback. Keep
production volumes and recovery keys through application rollback.

References: [Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/),
[startup order](https://docs.docker.com/compose/how-tos/startup-order/),
[PostgreSQL restoration](https://www.postgresql.org/docs/17/app-pgrestore.html),
[OpenSSL CMS](https://docs.openssl.org/3.6/man1/openssl-cms/).
