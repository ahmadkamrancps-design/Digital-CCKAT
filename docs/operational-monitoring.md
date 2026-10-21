# Operational monitoring — Milestone 10 continuation

`app.monitoring` is an operator-only Linux/WSL command. It reads health signals and
keeps a private local incident state file. It does not authenticate as a candidate,
read answers, change exams, run backup/restore operations, stop services, or send
notifications. No web endpoint, migration, frontend change or new dependency is added.

## Checks and defaults

| Check | Healthy condition | Default threshold |
| --- | --- | --- |
| Readiness | Direct HTTP 200 with a bounded JSON body containing `status: ready` | 6-second socket-operation timeout |
| TLS | Trusted certificate chain, matching hostname, sufficient certificate lifetime | More than 14 days remaining |
| Disk space, when configured | Both absolute and percentage free-space requirements met | At least 5 GiB and 15% free |
| Backup freshness, when configured | Existing completed encrypted archive/sidecar with a recent, non-future creation time | At most 7,200 seconds old |

Readiness uses the existing database/schema/expiry-worker check. It reports a
failure without exposing the server's error body. It follows no redirects, sends
no authentication, ignores environment proxy settings and limits the response
body to 1 KiB. TLS validation uses system roots or an explicit CA file; there is
no insecure HTTPS option. HTTP is accepted only for an explicit loopback check.
The monitor disables TLS key logging on its SSL context.

Disk paths must refer to the actual filesystem being monitored. A host working
directory or a container's temporary layer does not establish database-volume
capacity. Run separate monitors when database and backup storage use different
filesystems. A freshness check reuses the backup command's completed-archive
metadata check; it does **not** decrypt, authenticate or restore an archive, prove
off-site replication, or establish WAL/PITR coverage. Retain the encrypted restore
rehearsal and required production recovery work.

## Try it locally

With the backend running at port 8000, from the repository root:

```bash
install -d -m 700 test-results/monitoring
PYTHONPATH=backend backend/.venv/bin/python -m app.monitoring \
  --origin http://localhost:8000 --allow-local-http \
  --state-file "$PWD/test-results/monitoring/local-state.json"
```

This checks local readiness only. `skipped_checks` explicitly lists TLS, backup and
disk checks omitted from this command. Local development may not require an expiry
worker; production readiness does. Do not interpret a local `READY` as production
acceptance. To repeat, append `--loop --interval 30`; Ctrl+C stops the monitor.
The command also runs with Python's standard library alone when `PYTHONPATH` points
to `backend`; the venv shown above is convenient for existing development setup.

## Configure an operator host

Once the institution provides the actual server and storage mounts, create a
private state directory owned by the monitoring operator. Run the monitor with its
own read-only access to backup metadata and storage, without application sessions,
database credentials or recovery private keys. For example, after replacing the
storage paths with the actual mounts:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m app.monitoring \
  --origin https://digital.cckat.edu.pk \
  --state-file /private/cck-monitor/state.json \
  --disk-path /actual/database-storage-mount \
  --backup-directory /actual/encrypted-backups \
  --loop --interval 30
```

These paths are operator-provided placeholders, not directories created by the
application. Use a trusted CA file for private staging HTTPS with `--ca-file`.
For a rehearsal's deliberately two-day certificate, explicitly lower
`--certificate-warning-days` to `0`; retain a suitable warning period for public
deployment. Other limits can be configured using the flags shown by `--help`.

Supervise the process and collect its JSON lines into restricted, rotated storage.
For cron/timer use, omit `--loop` and reuse the **same state file and configuration**
on every invocation. Keep scheduling frequent enough for the agreed response time.
Exit codes: `0` means enabled checks are healthy and no incident is awaiting
recovery confirmation; `1` means a check failed or an incident remains open; `2`
means invalid configuration, unreadable/corrupt state, overlapping invocation, or
an inability to persist the observation. A missing state parent is an error; the
tool does not silently fall back to temporary memory.

## Incidents and recovery

Every observation contains check codes, safe numeric measurements, UTC timestamps,
the configuration fingerprint, active incident identifiers, and transition events.
It contains no origin URL, storage path, raw exception, response body, answer,
authentication token or database connection string.

By default, three consecutive failures of a check open one `MONITOR_INCIDENT`.
Further failures keep that incident open without producing duplicate transition
events. Two consecutive healthy observations close it with `MONITOR_RECOVERED`,
using the original incident ID. A new failure interrupts the recovery streak.
The sample's overall health is false immediately on a failed check, even before
the incident threshold is reached. Recovery confirmation also keeps overall health
false until its threshold is met.

Counters and incident IDs persist across invocations and monitor restarts. Updates
use a private `0600` file, atomic replacement and an exclusive nonblocking lock.
The state is bound to the monitored origin, absolute configured paths and limits.
Changing them deliberately requires a separate state file or an operator-reviewed
state transition. Corrupt state, permissive file modes or symlinks are rejected;
they never cause an automatic counter reset. Do not delete state to silence an
incident. Use an operator-owned `0700` parent directory and retain its lock file.

The JSON stream is an integration input, **not a notification service or guaranteed
message queue**. Persistence and stdout delivery are not one transaction. Collectors
should reconcile the active-incident snapshots as well as transition events, and
detect missing observations/monitor crashes. Operators must still choose and test
an approved alert destination, acknowledgement/escalation policy and on-call owners.
The current implementation sends no emails, chat messages or webhooks.

Monitor public HTTPS from an independent host as well as checking private storage
on the deployment host. A host-local process cannot report the loss of its own
host or network. CPU, memory, database locks/connections, container restarts, request
latencies/error rates and log aggregation still need the deployment's telemetry.

## Automated verification

From `backend/`, run:

```bash
.venv/bin/pytest -q tests/test_monitoring.py
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app
```

Tests include real local HTTP and HTTPS servers, unknown-CA/hostname rejection,
certificate lifetime warnings, redirect refusal, malformed/private response bodies,
low storage, backup freshness errors, incident flapping, persistent deduplication,
state corruption/permissions/locking, and CLI exit codes.

The existing Docker/native [restart rehearsal](restart-recovery.md) also runs the
actual monitor through healthy services, API outage, live API with stale worker,
and full recovery. It verifies one persistent readiness incident and its matching
recovery, with `monitoring-report.json` containing safe observations. Rehearsal
thresholds are explicitly one failure/one recovery to bound its duration; unit
tests cover the normal three/two thresholds. This does not test external alert
delivery or certify the planned 7,000-candidate deployment.

References: Python's [TLS client contexts](https://docs.python.org/3.12/library/ssl.html#ssl.create_default_context)
and [redirect handlers](https://docs.python.org/3.12/library/urllib.request.html#urllib.request.HTTPRedirectHandler).
