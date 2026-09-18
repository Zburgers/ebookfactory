#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
temp_dir="$(mktemp -d /tmp/ebookfactory-migrations.XXXXXX)"
temp_db="$temp_dir/check.sqlite"

export EBOOK_FACTORY_DATABASE_URL="sqlite:///$temp_db"
uv run --directory "$project_root/apps/api" alembic -c "$project_root/alembic.ini" upgrade head
uv run --directory "$project_root/apps/api" alembic -c "$project_root/alembic.ini" downgrade base
uv run --directory "$project_root/apps/api" alembic -c "$project_root/alembic.ini" upgrade head

uv run --directory "$project_root/apps/api" python - <<'PY'
import os

from sqlalchemy import create_engine, inspect

tables = set(inspect(create_engine(os.environ["EBOOK_FACTORY_DATABASE_URL"])).get_table_names())
required = {"projects", "jobs", "events", "artifacts", "usage_calls", "quota_snapshots"}
missing = sorted(required - tables)
if missing:
    raise SystemExit(f"missing migrated tables: {missing}")
print(f"migration rollback/upgrade check passed ({len(tables)} tables)")
PY
