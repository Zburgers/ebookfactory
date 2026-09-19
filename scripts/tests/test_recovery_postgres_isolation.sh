#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
recovery_script="$project_root/scripts/tests/test_recovery_postgres.sh"

grep -Fq 'EBOOK_FACTORY_TEST_DATABASE_URL' "$recovery_script"
if grep -Fq 'EBOOK_FACTORY_TEST_DATABASE_URL="$EBOOK_FACTORY_DATABASE_URL"' "$recovery_script"; then
  echo "recovery test must not fall back to the live database" >&2
  exit 1
fi
echo "recovery PostgreSQL isolation check passed"
