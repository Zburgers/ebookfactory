#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
pg_bin="$(pg_config --bindir 2>/dev/null || true)"
if [[ -z "$pg_bin" || ! -x "$pg_bin/initdb" || ! -x "$pg_bin/pg_ctl" ]]; then
  printf 'restore-check test: required PostgreSQL binaries unavailable\n' >&2
  exit 1
fi

for binary in pg_dump pg_restore psql; do
  [[ -x "$pg_bin/$binary" ]] || {
    printf 'restore-check test: required PostgreSQL binary unavailable: %s\n' "$binary" >&2
    exit 1
  }
done

test_root="$(mktemp -d "${TMPDIR:-/tmp}/ebookfactory-restore-test.XXXXXX")"
source_data="$test_root/source"
source_socket="$test_root/socket"
archive="$test_root/source.dump"
source_log="$test_root/source.log"
source_port=$((52000 + (${RANDOM:-1} % 1000)))

cleanup() {
  "$pg_bin/pg_ctl" -D "$source_data" -m immediate stop >/dev/null 2>&1 || true
  rm -rf "$test_root"
}
trap cleanup EXIT

mkdir -p "$source_socket"
"$pg_bin/initdb" -D "$source_data" --auth=trust --no-locale >/dev/null
"$pg_bin/pg_ctl" -D "$source_data" -o "-k $source_socket -p $source_port" -l "$source_log" -w start >/dev/null
"$pg_bin/psql" -X -v ON_ERROR_STOP=1 -h "$source_socket" -p "$source_port" -d postgres <<'SQL' >/dev/null
CREATE TABLE projects (id uuid PRIMARY KEY, name text NOT NULL);
CREATE TABLE alembic_version (version_num varchar(32) NOT NULL);
INSERT INTO projects VALUES ('00000000-0000-0000-0000-000000000001', 'restore-proof');
INSERT INTO alembic_version VALUES ('restore-test');
SQL
"$pg_bin/pg_dump" --format=custom --no-owner --no-privileges \
  -h "$source_socket" -p "$source_port" -d postgres -f "$archive"

output="$(EBOOK_FACTORY_RESTORE_PORT_BASE="$source_port" \
  "$project_root/scripts/restore-check.sh" "$archive" 2>&1)"
grep -q 'isolated restore check passed' <<<"$output"
grep -q 'projects rows: 1' <<<"$output"
grep -q 'port attempts: 2' <<<"$output"

set +e
invalid_output="$(EBOOK_FACTORY_RESTORE_PORT_BASE=64517 \
  "$project_root/scripts/restore-check.sh" "$archive" 2>&1)"
invalid_status=$?
set -e
[[ "$invalid_status" -ne 0 ]]
grep -q 'invalid temporary port base' <<<"$invalid_output"
printf 'restore-check real isolated restore test passed\n'
