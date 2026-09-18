#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ! -f "$1" ]]; then
  printf 'usage: %s BACKUP.dump\n' "$0" >&2
  exit 2
fi

archive="$1"
pg_bin="$(pg_config --bindir 2>/dev/null || true)"
if [[ -z "$pg_bin" ]]; then
  printf 'restore-check: PostgreSQL binary directory unavailable\n' >&2
  exit 1
fi
for binary in initdb pg_ctl pg_restore psql; do
  if [[ ! -x "$pg_bin/$binary" ]]; then
    printf 'restore-check: required PostgreSQL binary unavailable: %s\n' "$binary" >&2
    exit 1
  fi
done

work_root="$(mktemp -d "${TMPDIR:-/tmp}/ebookfactory-restore.XXXXXX")"
target_data="$work_root/data"
target_socket="$work_root/socket"
target_log="$work_root/server.log"
restore_error="$work_root/restore.error"
query_error="$work_root/query.error"
port_base="${EBOOK_FACTORY_RESTORE_PORT_BASE:-$((52000 + (${RANDOM:-1} % 1000)))}"
if [[ ! "$port_base" =~ ^[0-9]+$ || "$port_base" -lt 1024 || "$port_base" -gt 64516 ]]; then
  printf 'restore-check: invalid temporary port base\n' >&2
  exit 1
fi

cleanup() {
  "$pg_bin/pg_ctl" -D "$target_data" -m immediate stop >/dev/null 2>&1 || true
  rm -rf "$work_root"
}
trap cleanup EXIT

mkdir "$target_socket"
"$pg_bin/initdb" -D "$target_data" --auth=trust --no-locale >/dev/null 2>&1 || {
  printf 'restore-check: unable to initialize isolated cluster\n' >&2
  exit 1
}
target_port=""
port_attempts=0
for offset in $(seq 0 19); do
  candidate_port=$((port_base + offset))
  port_attempts=$((offset + 1))
  if "$pg_bin/pg_ctl" -D "$target_data" \
    -o "-k $target_socket -p $candidate_port" -l "$target_log" -w start \
    >/dev/null 2>&1; then
    target_port="$candidate_port"
    break
  fi
done
if [[ -z "$target_port" ]]; then
  printf 'restore-check: unable to start isolated cluster\n' >&2
  exit 1
fi

target_identity="$("$pg_bin/psql" -X -Atq -v ON_ERROR_STOP=1 \
  -h "$target_socket" -p "$target_port" -d postgres \
  -c "SELECT current_setting('data_directory');" 2>"$query_error" || true)"
if [[ "$target_identity" != "$target_data" ]]; then
  printf 'restore-check: isolated cluster identity check failed\n' >&2
  exit 1
fi
"$pg_bin/pg_restore" --exit-on-error --no-owner --no-privileges \
  -h "$target_socket" -p "$target_port" -d postgres "$archive" \
  >/dev/null 2>"$restore_error" || {
  printf 'restore-check: isolated restore failed\n' >&2
  exit 1
}

if ! projects_rows="$("$pg_bin/psql" -X -Atq -v ON_ERROR_STOP=1 \
  -h "$target_socket" -p "$target_port" -d postgres \
  -c "SELECT count(*) FROM public.projects;" 2>"$query_error")"; then
  printf 'restore-check: projects data sanity check failed\n' >&2
  exit 1
fi
if ! alembic_rows="$("$pg_bin/psql" -X -Atq -v ON_ERROR_STOP=1 \
  -h "$target_socket" -p "$target_port" -d postgres \
  -c "SELECT count(*) FROM public.alembic_version;" 2>"$query_error")"; then
  printf 'restore-check: migration marker data sanity check failed\n' >&2
  exit 1
fi

[[ "$projects_rows" =~ ^[0-9]+$ ]] || {
  printf 'restore-check: projects data sanity check failed\n' >&2
  exit 1
}
[[ "$alembic_rows" =~ ^[0-9]+$ && "$alembic_rows" -gt 0 ]] || {
  printf 'restore-check: migration marker data sanity check failed\n' >&2
  exit 1
}
printf 'isolated restore check passed (projects rows: %s; migration markers: %s)\n' \
  "$projects_rows" "$alembic_rows"
printf 'port attempts: %s\n' "$port_attempts"
