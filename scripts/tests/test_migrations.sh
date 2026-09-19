#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
temp_dir="$(mktemp -d /tmp/ebookfactory-migrations.XXXXXX)"
temp_db="$temp_dir/check.sqlite"

export EBOOK_FACTORY_DATABASE_URL="sqlite:///$temp_db"
uv run --directory "$project_root/apps/api" alembic -c "$project_root/alembic.ini" upgrade head
uv run --directory "$project_root/apps/api" python - <<'PY'
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, Conversation, Project, TelegramLink

engine = create_engine(os.environ["EBOOK_FACTORY_DATABASE_URL"])
with Session(engine) as session:
    projects = []
    for title in ("Rollback first", "Rollback second"):
        project = Project(title=title, profile="fiction", language="en")
        session.add(project)
        session.flush()
        conversation = Conversation(project_id=project.id, channel="dashboard")
        session.add(conversation)
        session.flush()
        project.conversation_id = conversation.id
        projects.append(project)
    session.flush()
    session.add_all([
        TelegramLink(chat_id=10, project_id=projects[0].id, conversation_id=projects[0].conversation_id, is_active=True),
        TelegramLink(chat_id=10, project_id=projects[1].id, conversation_id=projects[1].conversation_id, is_active=False),
    ])
    session.commit()
PY
if uv run --directory "$project_root/apps/api" alembic -c "$project_root/alembic.ini" downgrade base >/tmp/ebookfactory-migration-downgrade.log 2>&1; then
    echo "migration downgrade unexpectedly discarded multi-project Telegram links" >&2
    exit 1
fi
grep -q "cannot downgrade Telegram links" /tmp/ebookfactory-migration-downgrade.log
uv run --directory "$project_root/apps/api" python - <<'PY'
import os

from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session

from app.models import TelegramLink

with Session(create_engine(os.environ["EBOOK_FACTORY_DATABASE_URL"])) as session:
    session.execute(delete(TelegramLink))
    session.commit()
PY
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
