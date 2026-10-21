#!/usr/bin/env bash
# Disposable localhost rehearsal only. Never run against real candidate data.
set -euo pipefail
cd "$(dirname "$0")/.."
rehearsal_directory="$PWD/test-results/production-rehearsal"
python3 ops/prepare_staging.py --directory "$rehearsal_directory"
compose=(docker compose -p cck-rehearsal --env-file "$rehearsal_directory/staging.env" -f compose.production.yml)
cleanup() {
  rehearsal_status=$?
  if [ "$rehearsal_status" -ne 0 ]; then
    # This standalone tool emits safe error types/events, never raw DSNs or tokens.
    "${compose[@]}" logs --no-color --tail 40 backup || true
  fi
  "${compose[@]}" ps --all
  "${compose[@]}" down --volumes --remove-orphans
}
trap cleanup EXIT
"${compose[@]}" config --quiet
"${compose[@]}" build
"${compose[@]}" up -d --wait --wait-timeout 180
operator=(--user "$(id -u):$(id -g)" -v "$rehearsal_directory:/rehearsal")
"${compose[@]}" run --rm --no-deps "${operator[@]}" migrate \
  python -m app.rehearsal_seed --candidates 22 --output /rehearsal/manifest.json
"${compose[@]}" run --rm --no-deps api python -m app.rehearsal_verify runtime
docker run --rm --network host --user "$(id -u):$(id -g)" \
  -v "$rehearsal_directory:/rehearsal" -v "$PWD/ops/load:/scripts:ro" \
  -e CCK_REHEARSAL_MANIFEST=/rehearsal/manifest.json \
  -e CCK_BASE_URL=https://localhost:8443 -e CCK_LOCAL_SELF_SIGNED=true \
  grafana/k6:2.3.0 run --summary-export /rehearsal/load-summary.json /scripts/exam.js
CCK_REHEARSAL_MANIFEST="$rehearsal_directory/manifest.json" \
CCK_BASE_URL=https://localhost:8443 CCK_LOCAL_SELF_SIGNED=true \
  python3 ops/restart_rehearsal.py --directory "$rehearsal_directory"
"${compose[@]}" run --rm --no-deps "${operator[@]}" api \
  python -m app.rehearsal_verify expiry --manifest /rehearsal/manifest.json
# Stop only synthetic writers so the dump and comparison share a stable recovery
# point. In particular, worker heartbeats and auth maintenance must not drift.
"${compose[@]}" stop api expiry-worker auth-maintenance
"${compose[@]}" run --rm --no-deps backup backup
archive_name="$(python3 -c 'import pathlib,sys; print(max(pathlib.Path(sys.argv[1]).glob("*.dump.cms"), key=lambda p:p.stat().st_mtime).name)' "$rehearsal_directory/backups")"
"${compose[@]}" exec -T db psql -X --set=ON_ERROR_STOP=1 -U cck_bootstrap -d postgres \
  -c 'CREATE DATABASE cck_rehearsal_restore OWNER cck_owner'
"${compose[@]}" --profile restore run --rm --no-deps restore \
  restore --archive "/backups/$archive_name"
"${compose[@]}" run --rm --no-deps migrate python -m app.rehearsal_verify restore
echo 'PASS: disposable production Docker/HTTPS/load/browser/expiry/privileges/encrypted-recovery rehearsal'
