#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backup_root="${EBOOK_FACTORY_BACKUP_ROOT:-$project_root/var/backups}"
database="${EBOOK_FACTORY_BACKUP_DB:-ebookfactory}"
role="${EBOOK_FACTORY_BACKUP_ROLE:-naki}"
socket="${EBOOK_FACTORY_BACKUP_SOCKET:-/var/run/postgresql}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup_root"
output="$backup_root/${database}-${stamp}.dump"

pg_dump --format=custom --no-owner --no-privileges \
  --dbname="$database" --username="$role" --host="$socket" --file="$output"
chmod 600 "$output"
printf '%s\n' "$output"
