# Recovered exam data verification

Milestone 10's encrypted restore rehearsal now verifies recovered table contents,
in addition to archive authentication, successful restoration and record counts.
It operates only on disposable synthetic PostgreSQL databases; it is not a public
API, a production database repair tool or a declaration of production readiness.

## What the check verifies

`app.rehearsal_verify.verify_restored_content` compares every `public` table,
including the migration version, candidate assignments, exam/question/key
configuration, attempts, answer values/revisions/review flags/save timestamps,
grading history, audit/security/session history and result-release configuration.
It also compares table names, column names/reflected types/nullability and primary
key columns, including empty tables. Missing/extra tables or differing content
cause the rehearsal to fail.

Rows are streamed in primary-key order through SHA-256 with length-delimited
canonical JSONB records and per-column SQL-NULL flags, preserving the distinction
between a SQL NULL and a JSON `null`. Both reads use read-only repeatable-read transactions
and UTC timestamp output. This bounds client memory and avoids differences from
JSON object key order or connection time zones. Plaintext rows and content digests
are never printed or included in the aggregate report. Successful evidence contains
only table counts and a `restored_content: verified` marker.

Source and target must respectively end in `_rehearsal` and `_restore`. The
source must contain a migrated schema. These checks do not authorize comparison
against real candidate data. There are no application schema migrations or changes
to candidate authentication, scoring, timers, autosave or the supplied frontend.

## Stable recovery point

After the browser/load and unattended-expiry checks finish, the operator stops
only the disposable API, expiry worker and, in Compose, authentication-maintenance
service. That drains synthetic writers before the encrypted dump is taken. Worker
heartbeats, presence and session maintenance therefore cannot change between the
backup and comparison. The database and gateway remain running. This freeze is a
rehearsal procedure, not a recommendation to stop production exams for backups.

The Docker script uses the shared verifier after restoring to its fresh isolated
database. The native script now uses the same verifier and adds
`backup_restore_verify_seconds` and `restored_counts` to private `report.json`.
The duration covers the local backup, decryption/restore and verification after
writers stop. It excludes incident detection, infrastructure provisioning, key
retrieval, traffic switching and operator response, so it is not an achieved RTO.
Native `--keep-running` restarts its API/worker after the recovery check.

Run the complete rehearsal using the existing commands in
[capacity and rehearsal](capacity-and-rehearsal.md). The focused real-database
regression test is:

```bash
cd backend
PG_CLIENT_BIN=/path/to/matching/postgresql/bin \
TEST_DATABASE_URL=postgresql+psycopg://TEST_ROLE:TEST_PASSWORD@localhost/TEST_DATABASE \
  .venv/bin/pytest -q tests/test_backup.py
```

Use an isolated local test server and a test role permitted to create disposable
databases. The test creates and removes randomly named databases and never drops
or rewrites the supplied database's application tables. Its fixtures include saved
MCQ/Urdu text, review flags, timestamps, grades and an audit event. After a real
encrypted restore, it injects same-count corruption in that restored fixture and
checks rejection. Owner-only trigger disabling for the grading/audit fault fixtures
is confined to those disposable restored tables; guards are re-enabled before
each check. A separate assertion still verifies append-only protection survives
the actual restore. Different source/target session time zones, equivalent JSON
object key order, SQL NULL versus JSON `null`, an altered empty table and a missing
table are covered.

## Limits and remaining acceptance

This is logical row-content verification at a frozen recovery point, not a full
schema/privilege equivalence checker. Existing tests check migrations and history
guards; operators must still inspect constraints, triggers, runtime grants and
application behavior during recovery acceptance. Sequence state, extensions,
collation/version upgrades, files outside the database and performance on the
intended production data volume require separate review.

It does not supply WAL/PITR, off-site storage, retention enforcement, failover or
host-loss recovery. Hourly dumps can still lose acknowledged answers since the
last snapshot. Institutional RPO/RTO decisions and an actual host-loss exercise
remain required. A small successful rehearsal does not certify 7,000 candidates.

Implementation references: PostgreSQL 17
[repeatable-read transactions](https://www.postgresql.org/docs/17/transaction-iso.html#XACT-REPEATABLE-READ)
and [JSON conversion functions](https://www.postgresql.org/docs/17/functions-json.html).

