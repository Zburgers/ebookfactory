#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ! -f "$1" ]]; then
  printf 'usage: %s BACKUP.dump\n' "$0" >&2
  exit 2
fi

archive="$1"
listing="$(mktemp)"
trap 'rm -f "$listing"' EXIT
pg_restore --list "$archive" > "$listing"
grep -q 'TABLE public projects ' "$listing"
grep -q 'TABLE public alembic_version ' "$listing"
printf 'backup archive structure check passed\n'
