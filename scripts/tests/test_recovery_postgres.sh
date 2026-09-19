#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ -f "$project_root/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . "$project_root/.env"
  set +a
fi

if [[ -z "${EBOOK_FACTORY_TEST_DATABASE_URL:-}" ]]; then
  printf 'recovery PostgreSQL behavior test skipped: EBOOK_FACTORY_TEST_DATABASE_URL is not configured\n'
  exit 0
fi

uv run --directory "$project_root/apps/api" pytest -q tests/test_recovery.py
