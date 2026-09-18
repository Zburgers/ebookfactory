"""Durable project conversations and idempotent inbound messages."""

from dataclasses import dataclass
from contextlib import nullcontext
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.events import append_event
from app.models import Conversation, Message, Project


@dataclass(frozen=True)
class ProjectResult:
    project_id: UUID
    conversation_id: UUID


@dataclass(frozen=True)
class MessageResult:
    message_id: UUID
    sequence: int
    duplicate: bool


def create_project(session: Session, *, title: str, profile: str, language: str) -> ProjectResult:
    """Create a project and its primary conversation in one transaction."""

    with session.begin():
        project = Project(title=title, profile=profile, language=language)
        session.add(project)
        session.flush()
        conversation = Conversation(project_id=project.id, channel="dashboard")
        session.add(conversation)
        session.flush()
        project.conversation_id = conversation.id
        append_event(
            session,
            project_id=project.id,
            kind="project.created",
            payload={"project_id": str(project.id), "conversation_id": str(conversation.id)},
        )
        return ProjectResult(project_id=project.id, conversation_id=conversation.id)


def append_message(
    session: Session,
    *,
    project_id: UUID,
    conversation_id: UUID,
    channel: str,
    external_dedupe_id: str | None,
    role: str,
    content: str,
    manage_transaction: bool = True,
) -> MessageResult:
    """Append one ordered message, returning the existing row on replay."""

    with (session.begin() if manage_transaction else nullcontext()):
        conversation = session.scalar(
            select(Conversation)
            .where(Conversation.id == conversation_id, Conversation.project_id == project_id)
            .with_for_update()
        )
        if conversation is None:
            raise ValueError("conversation does not belong to project")
        if external_dedupe_id is not None:
            existing = session.scalar(
                select(Message).where(
                    Message.channel == channel,
                    Message.external_dedupe_id == external_dedupe_id,
                )
            )
            if existing is not None:
                if existing.project_id != project_id or existing.conversation_id != conversation_id:
                    raise ValueError("external dedupe ID belongs to another conversation")
                return MessageResult(message_id=existing.id, sequence=existing.sequence, duplicate=True)
        next_sequence = (session.scalar(
            select(func.coalesce(func.max(Message.sequence), 0) + 1).where(Message.conversation_id == conversation_id)
        ) or 1)
        message = Message(
            project_id=project_id,
            conversation_id=conversation_id,
            sequence=next_sequence,
            channel=channel,
            external_dedupe_id=external_dedupe_id,
            role=role,
            content=content,
            turn_state="received",
        )
        session.add(message)
        session.flush()
        append_event(
            session,
            project_id=project_id,
            kind="conversation.message.received",
            payload={"message_id": str(message.id), "sequence": message.sequence, "channel": channel},
        )
        return MessageResult(message_id=message.id, sequence=message.sequence, duplicate=False)
