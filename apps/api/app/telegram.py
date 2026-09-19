"""Allowlisted Telegram long-polling state and durable message routing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.conversations import append_message
from app.jobs import ApprovalConflict, cancel_run, pause_job, resume_job
from app.orchestrator import enqueue_turn
from app.models import (
    Job,
    Project,
    ProductionRun,
    Task,
    TelegramLink,
    TelegramOutbox,
    TelegramState,
    TelegramUpdate,
    utc_now,
)
from app.jobs import approve_brief_and_enqueue


MAX_UPDATE_BYTES = 128 * 1024
MAX_MESSAGE_LENGTH = 4096
MAX_OUTBOX_ATTEMPTS = 5


@dataclass(frozen=True)
class TelegramConfig:
    """Non-secret allowlist state; the bot token is never stored here."""

    token_configured: bool
    allowed_chat_ids: frozenset[int]
    allowed_sender_ids: frozenset[int]

    @property
    def configured(self) -> bool:
        return self.token_configured and bool(self.allowed_chat_ids) and bool(self.allowed_sender_ids)


@dataclass(frozen=True)
class TelegramUpdateResult:
    """Durable outcome of one inbound update."""

    accepted: bool
    duplicate: bool = False
    reason: str | None = None
    message_id: UUID | None = None


@dataclass(frozen=True)
class OutboxDelivery:
    """Claimed outgoing message data safe to hand to a transport."""

    outbox_id: UUID
    chat_id: int
    text: str
    attempts: int
    reply_markup: dict[str, Any] | None = None


def _int_id(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _update_parts(update: dict[str, Any]) -> tuple[int, int | None, int | None, str | None, str | None]:
    update_id = _int_id(update.get("update_id"))
    if update_id is None or update_id < 0:
        raise ValueError("Telegram update_id must be a non-negative integer")
    message = update.get("message") or update.get("edited_message")
    callback = update.get("callback_query")
    source = message or (callback or {}).get("message") or {}
    sender = (message or callback or {}).get("from") or {}
    chat_id = _int_id((source.get("chat") or {}).get("id"))
    sender_id = _int_id(sender.get("id"))
    text = message.get("text") if message else (callback or {}).get("data")
    callback_id = (callback or {}).get("id")
    return update_id, chat_id, sender_id, text, callback_id


def _parse_ids(raw: str) -> frozenset[int]:
    values: set[int] = set()
    for item in raw.split(","):
        item = item.strip()
        if item:
            values.add(int(item))
    return frozenset(values)


def config_from_values(*, token: str | None, allowed_chat_ids: str, allowed_sender_ids: str) -> TelegramConfig:
    """Build configuration from local environment values without exposing the token."""

    return TelegramConfig(
        token_configured=bool(token),
        allowed_chat_ids=_parse_ids(allowed_chat_ids),
        allowed_sender_ids=_parse_ids(allowed_sender_ids),
    )


def _ensure_state(session: Session) -> TelegramState:
    state = session.get(TelegramState, 1, with_for_update=True)
    if state is None:
        state = TelegramState(id=1, next_update_id=0)
        session.add(state)
        session.flush()
    return state


def _ack_update(session: Session, update_id: int, *, error: str | None = None) -> None:
    if session.in_transaction():
        session.commit()
    with session.begin():
        stored = session.get(TelegramUpdate, update_id, with_for_update=True)
        if stored is None:
            return
        stored.processed_at = utc_now()
        stored.last_error = error
        state = _ensure_state(session)
        pending = session.scalar(
            select(TelegramUpdate.update_id)
            .where(
                TelegramUpdate.update_id >= state.next_update_id,
                TelegramUpdate.update_id <= update_id,
                TelegramUpdate.processed_at.is_(None),
            )
            .order_by(TelegramUpdate.update_id)
            .limit(1)
        )
        state.next_update_id = update_id + 1 if pending is None else pending


def _queue_message(session: Session, *, chat_id: int, text: str, dedupe_key: str, reply_markup: dict[str, Any] | None = None) -> TelegramOutbox:
    existing = session.scalar(select(TelegramOutbox).where(TelegramOutbox.dedupe_key == dedupe_key))
    if existing is not None:
        return existing
    outbox = TelegramOutbox(chat_id=chat_id, text=text[:MAX_MESSAGE_LENGTH], dedupe_key=dedupe_key, reply_markup=reply_markup)
    session.add(outbox)
    session.flush()
    return outbox


def link_chat(session: Session, *, chat_id: int, project_id: UUID) -> TelegramLink:
    """Bind one chat to the project's existing conversation."""

    if session.in_transaction():
        session.rollback()
    with session.begin():
        project = session.scalar(select(Project).where(Project.id == project_id).with_for_update())
        if project is None or project.conversation_id is None:
            raise ValueError("project conversation not found")
        links = session.scalars(select(TelegramLink).where(TelegramLink.chat_id == chat_id).with_for_update()).all()
        link = next((row for row in links if row.project_id == project.id), None)
        if link is None:
            link = TelegramLink(chat_id=chat_id, project_id=project.id, conversation_id=project.conversation_id, is_active=True)
            session.add(link)
        for row in links:
            if row.project_id != project.id:
                row.is_active = False
        session.flush()
        for row in links:
            if row.project_id == project.id:
                row.is_active = True
        link.is_active = True
        session.flush()
        return link


def link_configured_chats(session: Session, *, chat_ids: set[int] | frozenset[int]) -> int:
    """Associate every project with configured chats without changing active selection."""

    if session.in_transaction():
        session.rollback()
    with session.begin():
        projects = session.scalars(select(Project).where(Project.conversation_id.is_not(None)).order_by(Project.created_at)).all()
        count = 0
        for chat_id in chat_ids:
            links = session.scalars(select(TelegramLink).where(TelegramLink.chat_id == chat_id).with_for_update()).all()
            by_project = {row.project_id: row for row in links}
            active_exists = any(row.is_active for row in links)
            for project in projects:
                if project.id in by_project:
                    continue
                session.add(TelegramLink(
                    chat_id=chat_id,
                    project_id=project.id,
                    conversation_id=project.conversation_id,
                    is_active=not active_exists,
                ))
                active_exists = True
                count += 1
        session.flush()
        return count


def _linked_project(session: Session, chat_id: int) -> tuple[TelegramLink, Project] | None:
    row = session.execute(
        select(TelegramLink, Project)
        .join(Project, Project.id == TelegramLink.project_id)
        .where(TelegramLink.chat_id == chat_id, TelegramLink.is_active.is_(True))
    ).first()
    return row if row else None


def _command(text: str) -> tuple[str, list[str]]:
    if text.strip().lower().startswith("switch:"):
        return "/switch", [text.strip().split(":", 1)[1]]
    if text.strip().lower().startswith("approve:"):
        return "/approve", text.strip().split(":", 1)[1].split(":")
    parts = text.strip().split()
    if not parts:
        return "", []
    name = parts[0].split("@", 1)[0].lower()
    return name, parts[1:]


def _queue_response(session: Session, *, chat_id: int, update_id: int, text: str, reply_markup: dict[str, Any] | None = None) -> UUID:
    if session.in_transaction():
        outbox = _queue_message(
            session,
            chat_id=chat_id,
            text=text,
            dedupe_key=f"telegram:{update_id}:response",
            reply_markup=reply_markup,
        )
        session.commit()
        return outbox.id
    with session.begin():
        outbox = _queue_message(
            session,
            chat_id=chat_id,
            text=text,
            dedupe_key=f"telegram:{update_id}:response",
            reply_markup=reply_markup,
        )
        return outbox.id


def _lifecycle_response(session: Session, *, project_id: UUID, command: str) -> str:
    run = session.scalar(
        select(ProductionRun)
        .where(ProductionRun.project_id == project_id, ProductionRun.state.not_in(["cancelled", "draft_review"]))
        .order_by(ProductionRun.created_at.desc())
    )
    run_id = run.id if run else None
    session.rollback()
    if run_id is None:
        return "No active production run."
    if command == "/cancel":
        cancel_run(session, run_id=run_id, reason="Telegram owner command")
        return "Production cancelled."
    job = session.scalar(
        select(Job).join(Task, Task.id == Job.task_id).where(Task.run_id == run_id).order_by(Job.created_at.desc())
    )
    job_id = job.id if job else None
    session.rollback()
    if job_id is None:
        return "No active job."
    if command == "/pause":
        pause_job(session, job_id=job_id, reason="Telegram owner command")
        return "Production paused."
    resume_job(session, job_id=job_id)
    return "Production resumed."


def _response_for_command(session: Session, *, chat_id: int, update_id: int, text: str) -> UUID | None:
    session.rollback()
    command, args = _command(text)
    if command in {"/use", "/switch"}:
        if len(args) != 1:
            raise ValueError("usage: /use PROJECT_ID")
        link_chat(session, chat_id=chat_id, project_id=UUID(args[0]))
        return _queue_response(
            session,
            chat_id=chat_id,
            update_id=update_id,
            text="Telegram is now linked to this project.",
        )
    if command == "/projects":
        projects = session.scalars(select(Project).order_by(Project.updated_at.desc()).limit(20)).all()
        text = "No projects yet." if not projects else "Projects:\n" + "\n".join(
            f"{project.id} · {project.title}" for project in projects
        )
        session.rollback()
        return _queue_response(session, chat_id=chat_id, update_id=update_id, text=text)

    if command == "/help":
        projects = session.scalars(select(Project).where(Project.conversation_id.is_not(None)).order_by(Project.updated_at.desc()).limit(20)).all()
        keyboard = {"inline_keyboard": [[{"text": project.title[:64], "callback_data": f"switch:{project.id}"}] for project in projects]}
        return _queue_response(
            session,
            chat_id=chat_id,
            update_id=update_id,
            text="Choose the active project:" if projects else "No projects yet.",
            reply_markup=keyboard if projects else None,
        )

    linked = _linked_project(session, chat_id)
    if linked is None:
        session.rollback()
        return _queue_response(
            session,
            chat_id=chat_id,
            update_id=update_id,
            text="Link a project first with /use PROJECT_ID.",
        )
    link, project = linked
    project_id = project.id
    conversation_id = link.conversation_id
    project_title = project.title
    project_state = project.state
    session.rollback()
    if command == "/status":
        response = f"{project_title}: {project_state}"
    elif command in {"/pause", "/resume", "/cancel"}:
        response = _lifecycle_response(session, project_id=project_id, command=command)
    elif command == "/approve":
        if len(args) != 2:
            raise ValueError("usage: /approve BRIEF_ID CONTENT_HASH")
        approval = approve_brief_and_enqueue(
            session,
            project_id=project_id,
            brief_id=UUID(args[0]),
            expected_content_hash=args[1],
            budget={"max_turns": 8, "source": "telegram"},
        )
        response = f"Approved and queued run {approval.run_id}."
    else:
        result = append_message(
            session,
            project_id=project_id,
            conversation_id=conversation_id,
            channel="telegram",
            external_dedupe_id=f"telegram:{update_id}",
            role="user",
            content=text,
            manage_transaction=False,
        )
        enqueue_turn(
            session,
            project_id=project_id,
            conversation_id=conversation_id,
            message_id=result.message_id,
            dedupe_key=f"telegram:{update_id}",
        )
        response_id = _queue_response(
            session,
            chat_id=chat_id,
            update_id=update_id,
            text="Message received by the Ebook Factory.",
        )
        return response_id if result.message_id else None
    return _queue_response(session, chat_id=chat_id, update_id=update_id, text=response)


def process_update(session: Session, *, config: TelegramConfig, update: dict[str, Any]) -> TelegramUpdateResult:
    """Persist, allowlist, route, and acknowledge one Telegram update."""

    if session.in_transaction():
        session.rollback()
    encoded_size = len(json.dumps(update, separators=(",", ":")).encode())
    if encoded_size > MAX_UPDATE_BYTES:
        raise ValueError("Telegram update exceeds size limit")
    update_id, chat_id, sender_id, text, _ = _update_parts(update)
    with session.begin():
        existing = session.get(TelegramUpdate, update_id, with_for_update=True)
        duplicate = existing is not None
        if existing is not None and existing.processed_at is not None:
            return TelegramUpdateResult(accepted=True, duplicate=True)
        if existing is None:
            existing = TelegramUpdate(update_id=update_id, chat_id=chat_id, sender_id=sender_id, payload=update)
            session.add(existing)
        allowed = config.configured and chat_id in config.allowed_chat_ids and sender_id in config.allowed_sender_ids
        if not allowed:
            reason = "telegram_not_configured" if not config.configured else (
                "chat_not_allowed" if chat_id not in config.allowed_chat_ids else "sender_not_allowed"
            )
    if not allowed:
        _ack_update(session, update_id, error=reason)
        return TelegramUpdateResult(accepted=False, duplicate=duplicate, reason=reason)
    if chat_id is None or text is None:
        reason = "unsupported_update"
        _ack_update(session, update_id, error=reason)
        return TelegramUpdateResult(accepted=False, duplicate=duplicate, reason=reason)
    try:
        message_id = _response_for_command(session, chat_id=chat_id, update_id=update_id, text=text)
    except (ApprovalConflict, ValueError, KeyError) as exc:
        with session.begin():
            stored = session.get(TelegramUpdate, update_id)
            stored.last_error = str(exc)
        return TelegramUpdateResult(accepted=False, duplicate=duplicate, reason=str(exc))
    _ack_update(session, update_id)
    return TelegramUpdateResult(accepted=True, duplicate=duplicate, message_id=message_id)


def claim_outbox(session: Session, *, now=None) -> OutboxDelivery | None:
    """Claim one pending message for a sender using a short transaction."""

    now = now or utc_now()
    with session.begin():
        row = session.scalar(
            select(TelegramOutbox)
            .where(
                or_(
                    and_(TelegramOutbox.state == "pending", TelegramOutbox.available_at <= now),
                    and_(TelegramOutbox.state == "sending", TelegramOutbox.available_at <= now),
                )
            )
            .order_by(TelegramOutbox.available_at, TelegramOutbox.created_at)
            .with_for_update(skip_locked=True)
        )
        if row is None:
            return None
        row.state = "sending"
        row.attempts += 1
        row.available_at = now + timedelta(minutes=5)
        return OutboxDelivery(row.id, row.chat_id, row.text, row.attempts, row.reply_markup)


def record_outbox_sent(session: Session, outbox_id: UUID, telegram_message_id: str) -> None:
    """Mark an outgoing message delivered without exposing transport details."""

    with session.begin():
        row = session.get(TelegramOutbox, outbox_id, with_for_update=True)
        if row is not None:
            row.state = "sent"
            row.sent_at = utc_now()
            row.telegram_message_id = telegram_message_id[:128]
            row.last_error = None


def record_outbox_failure(session: Session, outbox_id: UUID, error: str) -> None:
    """Retry transient delivery failures with bounded exponential backoff."""

    with session.begin():
        row = session.get(TelegramOutbox, outbox_id, with_for_update=True)
        if row is None or row.state == "sent":
            return
        row.state = "failed" if row.attempts >= MAX_OUTBOX_ATTEMPTS else "pending"
        row.available_at = utc_now() + timedelta(seconds=min(300, 2 ** row.attempts))
        row.last_error = error[:1000]


class TelegramBotClient:
    """Small HTTPS-only Telegram Bot API client; token bytes never enter logs or DB."""

    def __init__(self, token: str, *, api_root: str = "https://api.telegram.org") -> None:
        if not token or not api_root.startswith("https://"):
            raise ValueError("Telegram requires a token and HTTPS API root")
        self._base = f"{api_root.rstrip('/')}/bot{token}"

    def _call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            f"{self._base}/{method}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=60) as response:  # noqa: S310 - HTTPS root is validated above
            result = json.loads(response.read())
        if not result.get("ok"):
            raise RuntimeError("Telegram API request failed")
        return result["result"]

    def get_updates(self, *, offset: int, timeout: int = 30) -> list[dict[str, Any]]:
        bounded_timeout = max(1, min(timeout, 50))
        return self._call(
            "getUpdates",
            {"offset": offset, "timeout": bounded_timeout, "allowed_updates": ["message", "callback_query"]},
        )

    def send_message(self, *, chat_id: int, text: str, reply_markup: dict[str, Any] | None = None) -> str:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text[:MAX_MESSAGE_LENGTH]}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        result = self._call("sendMessage", payload)
        return str(result.get("message_id", "unknown"))
