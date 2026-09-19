from pathlib import Path
import pytest
from uuid import UUID, uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.models import Base, Conversation, Message, OrchestratorTurn, Project, TelegramLink, TelegramOutbox, TelegramState, TelegramUpdate
import app.telegram as telegram_module
from app.telegram import TelegramConfig, link_configured_chats, link_chat, process_update, record_outbox_failure, record_outbox_sent
from app.main import create_app
from app.settings import Settings


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
        turns = session.scalars(select(OrchestratorTurn)).all()
        assert len(turns) == 1
        assert turns[0].user_message_id == session.scalar(select(Message).where(Message.channel == "telegram")).id
        assert turns[0].dedupe_key == "telegram:2"
        assert session.get(TelegramUpdate, 2).processed_at is not None
        outbox = session.scalars(select(TelegramOutbox)).all()
        assert len(outbox) == 2
        assert sum(item.dedupe_key == "telegram:2:response" for item in outbox) == 1
        outbox_id = outbox[0].id
        session.rollback()
        record_outbox_failure(session, outbox_id, "temporary network error")
        record_outbox_sent(session, outbox_id, "telegram-message-1")
        assert session.get(TelegramOutbox, outbox_id).state == "sent"


def test_later_update_does_not_advance_offset_past_failed_update(tmp_path: Path, monkeypatch) -> None:
    with _session(tmp_path) as session:
        config = TelegramConfig(token_configured=True, allowed_chat_ids=frozenset({10}), allowed_sender_ids=frozenset({20}))
        monkeypatch.setattr(telegram_module, "_response_for_command", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("temporary")))
        with pytest.raises(RuntimeError):
            process_update(session, config=config, update={"update_id": 7, "message": {"chat": {"id": 10}, "from": {"id": 20}, "text": "first"}})
        monkeypatch.setattr(telegram_module, "_response_for_command", lambda *args, **kwargs: None)
        result = process_update(session, config=config, update={"update_id": 8, "message": {"chat": {"id": 10}, "from": {"id": 20}, "text": "second"}})

        assert result.accepted is True
        assert session.get(TelegramState, 1).next_update_id == 7


def _project(session: Session, title: str) -> Project:
    project = Project(title=title, profile="fiction", language="en")
    session.add(project)
    session.flush()
    conversation = Conversation(project_id=project.id, channel="dashboard")
    session.add(conversation)
    session.flush()
    project.conversation_id = conversation.id
    session.flush()
    return project


def test_configured_chat_backfill_is_idempotent_and_preserves_active_project(tmp_path: Path) -> None:
    with _session(tmp_path) as session:
        first = _project(session, "First")
        second = _project(session, "Second")
        session.commit()
        link_chat(session, chat_id=10, project_id=second.id)

        assert link_configured_chats(session, chat_ids={10}) == 1
        assert link_configured_chats(session, chat_ids={10}) == 0
        rows = session.scalars(select(TelegramLink).where(TelegramLink.chat_id == 10).order_by(TelegramLink.project_id)).all()
        assert len(rows) == 2
        assert sum(row.is_active for row in rows) == 1
        assert next(row for row in rows if row.project_id == second.id).is_active is True
        assert next(row for row in rows if row.project_id == first.id).is_active is False


def test_use_switches_active_project_without_duplicate_plain_messages(tmp_path: Path) -> None:
    with _session(tmp_path) as session:
        first = _project(session, "First")
        second = _project(session, "Second")
        session.commit()
        config = TelegramConfig(token_configured=True, allowed_chat_ids=frozenset({10}), allowed_sender_ids=frozenset({20}))
        link_configured_chats(session, chat_ids={10})
        process_update(session, config=config, update={"update_id": 1, "message": {"chat": {"id": 10}, "from": {"id": 20}, "text": f"/use {second.id}"}})
        process_update(session, config=config, update={"update_id": 2, "message": {"chat": {"id": 10}, "from": {"id": 20}, "text": "only second"}})
        assert session.scalar(select(Message.project_id).where(Message.channel == "telegram")) == second.id
        rows = session.scalars(select(TelegramLink).where(TelegramLink.chat_id == 10)).all()
        assert next(row for row in rows if row.project_id == second.id).is_active is True
        assert next(row for row in rows if row.project_id == first.id).is_active is False


def test_new_project_route_auto_links_configured_chat(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'project.db'}",
        artifact_root=tmp_path / "artifacts",
        owner_token="owner",
        telegram_bot_token="token",
        telegram_allowed_chat_ids="10",
        telegram_allowed_sender_ids="20",
    )
    bootstrap = create_engine(settings.database_url)
    Base.metadata.create_all(bootstrap)
    bootstrap.dispose()
    with TestClient(create_app(settings), headers={"Authorization": "Bearer owner"}) as client:
        response = client.post("/projects", json={"title": "New", "profile": "fiction", "language": "en"})
        assert response.status_code == 201
        project_id = response.json()["project_id"]
        with client.app.state.database.session() as session:
            link = session.scalar(select(TelegramLink).where(TelegramLink.project_id == UUID(project_id), TelegramLink.chat_id == 10))
            assert link is not None


def test_help_menu_and_allowlisted_callback_switch_are_durable_and_replay_safe(tmp_path: Path) -> None:
    with _session(tmp_path) as session:
        first = _project(session, "First")
        second = _project(session, "Second")
        session.commit()
        config = TelegramConfig(token_configured=True, allowed_chat_ids=frozenset({10}), allowed_sender_ids=frozenset({20}))
        link_configured_chats(session, chat_ids={10})
        process_update(session, config=config, update={"update_id": 10, "message": {"chat": {"id": 10}, "from": {"id": 20}, "text": "/help"}})
        menu = session.scalar(select(TelegramOutbox).where(TelegramOutbox.dedupe_key == "telegram:10:response"))
        assert menu is not None
        callback_data = {button["callback_data"] for row in menu.reply_markup["inline_keyboard"] for button in row}
        assert callback_data == {f"switch:{first.id}", f"switch:{second.id}"}
        callback = {"update_id": 11, "callback_query": {"id": "cb-11", "from": {"id": 20}, "data": f"switch:{second.id}", "message": {"chat": {"id": 10}}}}
        result = process_update(session, config=config, update=callback)
        replay = process_update(session, config=config, update=callback)
        assert result.accepted is True
        assert replay.duplicate is True
        links = session.scalars(select(TelegramLink).where(TelegramLink.chat_id == 10)).all()
        assert next(row for row in links if row.project_id == second.id).is_active is True
        assert sum(row.is_active for row in links) == 1


def test_help_callback_respects_chat_and_sender_allowlists(tmp_path: Path) -> None:
    with _session(tmp_path) as session:
        project = _project(session, "Private")
        session.commit()
        config = TelegramConfig(token_configured=True, allowed_chat_ids=frozenset({10}), allowed_sender_ids=frozenset({20}))
        update = {"update_id": 12, "callback_query": {"id": "cb-12", "from": {"id": 99}, "data": f"switch:{project.id}", "message": {"chat": {"id": 10}}}}
        result = process_update(session, config=config, update=update)
        assert result.accepted is False
        assert result.reason == "sender_not_allowed"
        assert session.scalar(select(TelegramLink).where(TelegramLink.project_id == project.id)) is None
