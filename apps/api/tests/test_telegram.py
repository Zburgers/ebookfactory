from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Base, Conversation, Message, Project, TelegramOutbox, TelegramState, TelegramUpdate
from app.telegram import TelegramConfig, process_update, record_outbox_failure, record_outbox_sent


def _session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'telegram.db'}")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_disallowed_update_is_durable_and_advances_offset(tmp_path: Path) -> None:
    with _session(tmp_path) as session:
        result = process_update(
            session,
            config=TelegramConfig(token_configured=True, allowed_chat_ids=frozenset({10}), allowed_sender_ids=frozenset({20})),
            update={"update_id": 7, "message": {"chat": {"id": 99}, "from": {"id": 20}, "text": "hello"}},
        )

        assert result.accepted is False
        assert result.reason == "chat_not_allowed"
        assert session.get(TelegramUpdate, 7) is not None
        assert session.get(TelegramState, 1).next_update_id == 8


def test_linked_message_and_outbox_are_replay_safe(tmp_path: Path) -> None:
    with _session(tmp_path) as session:
        project_row = Project(title="Telegram book", profile="fiction", language="en")
        session.add(project_row)
        session.flush()
        conversation = Conversation(project_id=project_row.id, channel="dashboard")
        session.add(conversation)
        session.flush()
        project_row.conversation_id = conversation.id
        project_id = project_row.id
        session.commit()
        config = TelegramConfig(token_configured=True, allowed_chat_ids=frozenset({10}), allowed_sender_ids=frozenset({20}))
        link = {"update_id": 1, "message": {"chat": {"id": 10}, "from": {"id": 20}, "text": f"/use {project_id}"}}
        process_update(session, config=config, update=link)
        message = {"update_id": 2, "message": {"chat": {"id": 10}, "from": {"id": 20}, "text": "A premise"}}
        first = process_update(session, config=config, update=message)
        replay = process_update(session, config=config, update=message)

        assert first.accepted is True
        assert replay.duplicate is True
        assert len(session.scalars(select(Message).where(Message.channel == "telegram")).all()) == 1
        outbox = session.scalars(select(TelegramOutbox)).all()
        assert len(outbox) >= 2
        outbox_id = outbox[0].id
        session.rollback()
        record_outbox_failure(session, outbox_id, "temporary network error")
        record_outbox_sent(session, outbox_id, "telegram-message-1")
        assert session.get(TelegramOutbox, outbox_id).state == "sent"
