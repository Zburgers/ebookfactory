"""Durable event and outbox helpers."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Event, Outbox


def append_event(
    session: Session,
    *,
    project_id: UUID,
    kind: str,
    payload: dict[str, Any],
    run_id: UUID | None = None,
    task_id: UUID | None = None,
) -> Event:
    """Append an event and its outbox row in the caller's transaction."""

    event = Event(project_id=project_id, run_id=run_id, task_id=task_id, kind=kind, data=payload)
    session.add(event)
    session.flush()
    session.add(Outbox(event_id=event.id))
    session.flush()
    return event


def replay_events(session: Session, *, project_id: UUID, after_id: int = 0, limit: int = 100) -> list[Event]:
    """Return ordered project events after an SSE replay cursor."""

    bounded_limit = max(1, min(limit, 500))
    statement = (
        select(Event)
        .where(Event.project_id == project_id, Event.id > after_id)
        .order_by(Event.id)
        .limit(bounded_limit)
    )
    return list(session.scalars(statement))
