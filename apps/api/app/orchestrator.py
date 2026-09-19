"""Durable dashboard-turn queue and fenced trusted-worker mutations."""

from datetime import timedelta, timezone
import re
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.events import append_event
from app.models import Conversation, Message, OrchestratorTurn, Project, TelegramLink, TelegramOutbox, utc_now
from app.usage import record_usage_call

MAX_ORCHESTRATOR_ATTEMPTS = 3


def _sanitize_error(error: str) -> str:
    """Keep durable failure diagnostics useful without retaining credentials."""

    value = " ".join(error.split())
    value = re.sub(r"(?i)\bBearer\s+[^\s,;]+", "Bearer [redacted]", value)
    value = re.sub(r"(?i)(\b(?:api[_-]?key|token|password|secret)\s*[:=]\s*)[^\s,;]+", r"\1[redacted]", value)
    value = re.sub(r"(?i)(://)[^\s/@:]+:[^\s/@]+@", r"\1[redacted]@", value)
    return value[:500] or "unknown orchestrator failure"


def enqueue_turn(session: Session, *, project_id: UUID, conversation_id: UUID, message_id: UUID, dedupe_key: str) -> OrchestratorTurn:
    existing = session.scalar(select(OrchestratorTurn).where(OrchestratorTurn.dedupe_key == dedupe_key).with_for_update())
    if existing is not None:
        return existing
    turn = OrchestratorTurn(
        project_id=project_id, conversation_id=conversation_id, user_message_id=message_id,
        dedupe_key=dedupe_key, state="queued",
    )
    session.add(turn)
    session.flush()
    append_event(session, project_id=project_id, kind="orchestrator.turn.queued", payload={"turn_id": str(turn.id), "message_id": str(message_id)})
    return turn


def claim_turn(session: Session, *, worker_id: str, lease_seconds: int = 60) -> OrchestratorTurn | None:
    now = utc_now()
    with session.begin():
        turn = session.scalar(
            select(OrchestratorTurn)
            .where((OrchestratorTurn.state == "queued") | ((OrchestratorTurn.state == "running") & (OrchestratorTurn.lease_until < now)))
            .order_by(OrchestratorTurn.created_at).with_for_update(skip_locked=True).limit(1)
        )
        if turn is None:
            return None
        turn.state = "running"
        turn.lease_owner = worker_id
        turn.lease_until = now + timedelta(seconds=lease_seconds)
        turn.generation += 1
        turn.attempts += 1
        append_event(session, project_id=turn.project_id, kind="orchestrator.turn.claimed", payload={"turn_id": str(turn.id), "generation": turn.generation})
        return turn


def locked_turn(session: Session, *, turn_id: UUID, worker_id: str, generation: int) -> OrchestratorTurn:
    turn = session.scalar(select(OrchestratorTurn).where(OrchestratorTurn.id == turn_id).with_for_update())
    if turn is None or turn.state != "running" or turn.lease_owner != worker_id or turn.generation != generation:
        raise ValueError("orchestrator turn lease is no longer current")
    lease_until = turn.lease_until.replace(tzinfo=timezone.utc) if turn.lease_until and turn.lease_until.tzinfo is None else turn.lease_until
    if lease_until is None or lease_until < utc_now():
        raise ValueError("orchestrator turn lease is no longer current")
    return turn


def heartbeat_turn(session: Session, *, turn_id: UUID, worker_id: str, generation: int, lease_seconds: int = 60) -> OrchestratorTurn:
    with session.begin():
        turn = locked_turn(session, turn_id=turn_id, worker_id=worker_id, generation=generation)
        turn.lease_until = utc_now() + timedelta(seconds=lease_seconds)
        return turn


def fail_turn(session: Session, *, turn_id: UUID, worker_id: str, generation: int, error: str) -> OrchestratorTurn:
    """Fenced, idempotent failure transition with bounded retry and owner feedback."""
    safe_error = _sanitize_error(error)
    with session.begin():
        turn = session.scalar(select(OrchestratorTurn).where(OrchestratorTurn.id == turn_id).with_for_update())
        if turn is None:
            raise ValueError("orchestrator turn not found")
        if turn.state in {"failed", "succeeded"}:
            return turn
        if turn.state != "running" or turn.lease_owner != worker_id or turn.generation != generation:
            raise ValueError("orchestrator turn lease is no longer current")
        lease_until = turn.lease_until.replace(tzinfo=timezone.utc) if turn.lease_until and turn.lease_until.tzinfo is None else turn.lease_until
        if lease_until is None or lease_until < utc_now():
            raise ValueError("orchestrator turn lease is no longer current")
        turn.lease_owner, turn.lease_until = None, None
        if turn.attempts < MAX_ORCHESTRATOR_ATTEMPTS:
            turn.state = "queued"
            append_event(session, project_id=turn.project_id, kind="orchestrator.turn.retryable_failure", payload={"turn_id": str(turn.id), "attempt": turn.attempts, "error": safe_error})
            return turn
        conversation = session.scalar(select(Conversation).where(Conversation.id == turn.conversation_id).with_for_update())
        user_message = session.scalar(select(Message).where(Message.id == turn.user_message_id))
        next_sequence = max([m.sequence for m in session.scalars(select(Message).where(Message.conversation_id == turn.conversation_id)).all()] or [0]) + 1
        content = "I couldn’t complete that request after several attempts. Please try again later."
        message = Message(project_id=turn.project_id, conversation_id=turn.conversation_id, sequence=next_sequence, channel=conversation.channel, role="assistant", content=content, turn_state="failed")
        session.add(message)
        session.flush()
        turn.assistant_message_id, turn.state = message.id, "failed"
        if user_message is not None and user_message.channel == "telegram":
            link = session.scalar(select(TelegramLink).where(TelegramLink.conversation_id == conversation.id))
            if link is not None:
                session.add(TelegramOutbox(chat_id=link.chat_id, text=content[:4096], dedupe_key=f"orchestrator:{turn.id}:assistant"))
        append_event(session, project_id=turn.project_id, kind="orchestrator.turn.failed", payload={"turn_id": str(turn.id), "message_id": str(message.id), "attempt": turn.attempts, "error": safe_error})
        return turn


def complete_turn(session: Session, *, turn_id: UUID, worker_id: str, generation: int, content: str, provider: str, model: str, call_id: UUID, usage: dict | None) -> tuple[Message, bool]:
    if not content.strip():
        raise ValueError("assistant content is empty")
    with session.begin():
        turn = session.scalar(select(OrchestratorTurn).where(OrchestratorTurn.id == turn_id).with_for_update())
        if turn is None:
            raise ValueError("orchestrator turn not found")
        existing = session.scalar(select(Message).where(Message.id == turn.assistant_message_id)) if turn.assistant_message_id else None
        if existing is not None:
            return existing, True
        if turn.state != "running" or turn.lease_owner != worker_id or turn.generation != generation:
            raise ValueError("orchestrator turn lease is no longer current")
        lease_until = turn.lease_until.replace(tzinfo=timezone.utc) if turn.lease_until and turn.lease_until.tzinfo is None else turn.lease_until
        if lease_until is None or lease_until < utc_now():
            raise ValueError("orchestrator turn lease is no longer current")
        conversation = session.scalar(select(Conversation).where(Conversation.id == turn.conversation_id).with_for_update())
        user_message = session.scalar(select(Message).where(Message.id == turn.user_message_id))
        next_sequence = (max([m.sequence for m in session.scalars(select(Message).where(Message.conversation_id == turn.conversation_id)).all()] or [0]) + 1)
        message = Message(project_id=turn.project_id, conversation_id=turn.conversation_id, sequence=next_sequence, channel=conversation.channel, role="assistant", content=content, turn_state="completed")
        session.add(message)
        session.flush()
        record_usage_call(session, call_id=call_id, provider=provider, model=model, purpose="orchestration", outcome="succeeded", project_id=turn.project_id, started_at=utc_now(), ended_at=utc_now(), input_tokens=(usage or {}).get("input_tokens"), output_tokens=(usage or {}).get("output_tokens"), source_metadata={"source": "pi-orchestrator"}, manage_transaction=False)
        turn.assistant_message_id = message.id
        turn.provider, turn.model, turn.state, turn.lease_owner, turn.lease_until = provider, model, "succeeded", None, None
        if user_message is not None and user_message.channel == "telegram":
            link = session.scalar(select(TelegramLink).where(TelegramLink.conversation_id == conversation.id))
            if link is not None:
                session.add(TelegramOutbox(
                    chat_id=link.chat_id,
                    text=content[:4096],
                    dedupe_key=f"orchestrator:{turn.id}:assistant",
                ))
        append_event(session, project_id=turn.project_id, kind="orchestrator.turn.completed", payload={"turn_id": str(turn.id), "message_id": str(message.id), "provider": provider, "model": model})
        return message, False
