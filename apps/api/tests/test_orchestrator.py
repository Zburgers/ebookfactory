from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.main import create_app
from app.models import Base, Conversation, Event, Message, Project
from app.settings import Settings


def test_dashboard_message_enqueues_durable_orchestrator_turn_and_dedupes(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'orchestrator.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        project = Project(id=uuid4(), title="Turn", profile="fiction", language="en")
        conversation = Conversation(id=uuid4(), project_id=project.id, channel="dashboard")
        project_id, conversation_id = project.id, conversation.id
        project.conversation_id = conversation.id
        session.add_all([project, conversation])
        session.commit()

    with TestClient(create_app(Settings(database_url=database_url, worker_token="worker"))) as client:
        first = client.post(
            f"/projects/{project_id}/messages",
            json={"conversation_id": str(conversation_id), "external_dedupe_id": "turn-1", "content": "Help me outline this."},
        )
        second = client.post(
            f"/projects/{project_id}/messages",
            json={"conversation_id": str(conversation_id), "external_dedupe_id": "turn-1", "content": "Help me outline this."},
        )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["turn_id"] == second.json()["turn_id"]
    assert first.json()["queued"] is True
    with Session(engine) as session:
        messages = session.scalars(select(Message).where(Message.project_id == project_id)).all()
        events = session.scalars(select(Event).where(Event.project_id == project_id)).all()
        assert len(messages) == 1
        assert {event.kind for event in events} >= {"conversation.message.received", "orchestrator.turn.queued"}


def test_trusted_orchestrator_worker_claims_and_persists_assistant_lineage(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'orchestrator-worker.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        project = Project(id=uuid4(), title="Worker turn", profile="fiction", language="en")
        conversation = Conversation(id=uuid4(), project_id=project.id, channel="dashboard")
        project_id, conversation_id = project.id, conversation.id
        project.conversation_id = conversation.id
        session.add_all([project, conversation])
        session.commit()

    with TestClient(create_app(Settings(database_url=database_url, worker_token="worker"))) as client:
        created = client.post(
            f"/projects/{project_id}/messages",
            json={"conversation_id": str(conversation_id), "external_dedupe_id": "turn-2", "content": "Draft a hook."},
        ).json()
        headers = {"X-Ebook-Worker-Token": "worker"}
        lease = client.post("/private/orchestrator/claim", json={"worker_id": "pi-1"}, headers=headers)
        assert lease.status_code == 200
        lease_data = lease.json()
        context = client.get(
            f"/private/orchestrator/{lease_data['turn_id']}/context",
            headers={**headers, "X-Worker-ID": "pi-1", "X-Generation": str(lease_data["generation"])},
        )
        assert context.status_code == 200
        assert context.json()["messages"][-1]["content"] == "Draft a hook."
        heartbeat = client.post("/private/orchestrator/heartbeat", headers=headers, json={**lease_data, "lease_seconds": 120})
        assert heartbeat.status_code == 200
        result = client.post(
            "/private/orchestrator/result",
            headers=headers,
            json={
                **lease_data,
                "content": "Here is a durable hook.",
                "provider": "openai-codex",
                "model": "openai-codex/gpt-5.6-luna",
                "call_id": str(uuid4()),
                "usage": {"input_tokens": 7, "output_tokens": 11},
            },
        )
        assert result.status_code == 200
        assert result.json()["message_id"]
        replay = client.post("/private/orchestrator/result", headers=headers, json={**lease_data, "content": "duplicate", "provider": "openai-codex", "model": "openai-codex/gpt-5.6-luna", "call_id": str(uuid4())})
        assert replay.status_code == 200
        assert replay.json()["duplicate"] is True


def test_orchestrator_context_is_cut_off_at_claimed_user_message(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'orchestrator-context.db'}"
    engine = create_engine(database_url); Base.metadata.create_all(engine)
    with Session(engine) as session:
        project = Project(id=uuid4(), title="Context", profile="fiction", language="en")
        conversation = Conversation(id=uuid4(), project_id=project.id, channel="dashboard"); project.conversation_id = conversation.id
        session.add_all([project, conversation]); session.commit()
        project_id, conversation_id = project.id, conversation.id

    with TestClient(create_app(Settings(database_url=database_url, worker_token="worker"))) as client:
        first = client.post(f"/projects/{project_id}/messages", json={"conversation_id": str(conversation_id), "external_dedupe_id": "first", "content": "first question"}).json()
        second = client.post(f"/projects/{project_id}/messages", json={"conversation_id": str(conversation_id), "external_dedupe_id": "second", "content": "newer question"}).json()
        headers = {"X-Ebook-Worker-Token": "worker"}
        lease = client.post("/private/orchestrator/claim", json={"worker_id": "pi-1"}, headers=headers).json()
        context = client.get(f"/private/orchestrator/{lease['turn_id']}/context", headers={**headers, "X-Worker-ID": "pi-1", "X-Generation": str(lease["generation"])})

    assert first["turn_id"] == lease["turn_id"]
    assert second["turn_id"] != lease["turn_id"]
    contents = [message["content"] for message in context.json()["messages"]]
    assert contents == ["first question"]


def test_dashboard_message_rejects_oversized_content(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'message-limit.db'}"
    engine = create_engine(database_url); Base.metadata.create_all(engine)
    with Session(engine) as session:
        project = Project(id=uuid4(), title="Limit", profile="fiction", language="en")
        conversation = Conversation(id=uuid4(), project_id=project.id, channel="dashboard"); project.conversation_id = conversation.id
        project_id, conversation_id = project.id, conversation.id
        session.add_all([project, conversation]); session.commit()
    client = TestClient(create_app(Settings(database_url=database_url, worker_token="worker")))
    response = client.post(f"/projects/{project_id}/messages", json={"conversation_id": str(conversation_id), "content": "x" * 200_001})
    assert response.status_code == 422
