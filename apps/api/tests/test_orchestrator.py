from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.main import create_app
from app.models import Base, Conversation, Event, Message, OrchestratorTurn, Project, TelegramOutbox
from app.telegram import link_chat
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

    with TestClient(create_app(Settings(database_url=database_url, worker_token="worker", owner_token="owner")), headers={"Authorization": "Bearer owner"}) as client:
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

    with TestClient(create_app(Settings(database_url=database_url, worker_token="worker", owner_token="owner")), headers={"Authorization": "Bearer owner"}) as client:
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


def test_completed_telegram_turn_enqueues_assistant_outbox(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'telegram-completion.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    project = Project(id=uuid4(), title="Telegram book", profile="fiction", language="en")
    project_id = project.id
    conversation = Conversation(id=uuid4(), project_id=project.id, channel="dashboard")
    conversation_id = conversation.id
    project.conversation_id = conversation.id
    with Session(engine) as session:
        session.add_all([project, conversation])
        session.commit()
    with Session(engine) as session:
        link_chat(session, chat_id=6165158640, project_id=project_id)
    with TestClient(create_app(Settings(database_url=database_url, worker_token="worker", owner_token="owner")), headers={"Authorization": "Bearer owner"}) as client:
        message = client.post(f"/projects/{project_id}/messages", json={"conversation_id": str(conversation_id), "content": "Hello", "channel": "telegram", "external_dedupe_id": "telegram:88"}).json()
        headers = {"X-Ebook-Worker-Token": "worker"}
        lease = client.post("/private/orchestrator/claim", json={"worker_id": "pi-1"}, headers=headers).json()
        completed = client.post("/private/orchestrator/result", headers=headers, json={
            **lease, "content": "Assistant reply", "provider": "test", "model": "test-model", "call_id": str(uuid4()),
        })
        assert completed.status_code == 200

        with client.app.state.database.session() as session:
            rows = session.scalars(select(TelegramOutbox)).all()
            assert [(row.chat_id, row.text, row.dedupe_key) for row in rows] == [
                (6165158640, "Assistant reply", f"orchestrator:{lease['turn_id']}:assistant")
            ]


def test_orchestrator_context_is_cut_off_at_claimed_user_message(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'orchestrator-context.db'}"
    engine = create_engine(database_url); Base.metadata.create_all(engine)
    with Session(engine) as session:
        project = Project(id=uuid4(), title="Context", profile="fiction", language="en")
        conversation = Conversation(id=uuid4(), project_id=project.id, channel="dashboard"); project.conversation_id = conversation.id
        session.add_all([project, conversation]); session.commit()
        project_id, conversation_id = project.id, conversation.id

    with TestClient(create_app(Settings(database_url=database_url, worker_token="worker", owner_token="owner")), headers={"Authorization": "Bearer owner"}) as client:
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
    client = TestClient(create_app(Settings(database_url=database_url, worker_token="worker", owner_token="owner")), headers={"Authorization": "Bearer owner"})
    response = client.post(f"/projects/{project_id}/messages", json={"conversation_id": str(conversation_id), "content": "x" * 200_001})
    assert response.status_code == 422


def test_orchestrator_failure_requeues_then_terminally_publishes_owner_error(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'orchestrator-failure.db'}"
    engine = create_engine(database_url); Base.metadata.create_all(engine)
    with Session(engine) as session:
        project = Project(id=uuid4(), title="Failure", profile="fiction", language="en")
        conversation = Conversation(id=uuid4(), project_id=project.id, channel="dashboard"); project.conversation_id = conversation.id
        project_id, conversation_id = project.id, conversation.id
        session.add_all([project, conversation]); session.commit()

    with TestClient(create_app(Settings(database_url=database_url, worker_token="worker", owner_token="owner")), headers={"Authorization": "Bearer owner"}) as client:
        owner_headers = {"Authorization": "Bearer owner"}
        created_response = client.post(f"/projects/{project_id}/messages", headers=owner_headers, json={"conversation_id": str(conversation_id), "content": "Try this"})
        assert created_response.status_code == 201, created_response.text
        created = created_response.json()
        assert created["queued"] is True
        headers = {"X-Ebook-Worker-Token": "worker"}
        first = client.post("/private/orchestrator/claim", json={"worker_id": "pi-1"}, headers=headers).json()
        failed = client.post("/private/orchestrator/failure", headers=headers, json={**first, "error": "provider unavailable"})
        assert failed.status_code == 200
        assert failed.json()["state"] == "queued"
        second = client.post("/private/orchestrator/claim", json={"worker_id": "pi-1"}, headers=headers).json()
        terminal = client.post("/private/orchestrator/failure", headers=headers, json={**second, "error": "provider unavailable"})
        assert terminal.status_code == 200
        assert terminal.json()["state"] == "queued"
        third = client.post("/private/orchestrator/claim", json={"worker_id": "pi-1"}, headers=headers).json()
        terminal = client.post("/private/orchestrator/failure", headers=headers, json={**third, "error": "provider unavailable"})
        assert terminal.status_code == 200
        assert terminal.json()["state"] == "failed"

    with Session(engine) as session:
        turn = session.get(OrchestratorTurn, UUID(created["turn_id"]))
        messages = session.scalars(select(Message).where(Message.conversation_id == conversation_id).order_by(Message.sequence)).all()
        events = session.scalars(select(Event).where(Event.project_id == project_id)).all()
        assert turn.state == "failed"
        assert messages[-1].role == "assistant"
        assert "couldn’t complete" in messages[-1].content
        assert {event.kind for event in events} >= {"orchestrator.turn.retryable_failure", "orchestrator.turn.failed"}


def test_orchestrator_failure_rejects_stale_fence_and_is_idempotent_after_terminal(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'orchestrator-fence.db'}"
    engine = create_engine(database_url); Base.metadata.create_all(engine)
    with Session(engine) as session:
        project = Project(id=uuid4(), title="Fence", profile="fiction", language="en")
        conversation = Conversation(id=uuid4(), project_id=project.id, channel="dashboard"); project.conversation_id = conversation.id
        project_id, conversation_id = project.id, conversation.id
        session.add_all([project, conversation]); session.commit()
    with TestClient(create_app(Settings(database_url=database_url, worker_token="worker", owner_token="owner")), headers={"Authorization": "Bearer owner"}) as client:
        owner_headers = {"Authorization": "Bearer owner"}
        created = client.post(f"/projects/{project_id}/messages", headers=owner_headers, json={"conversation_id": str(conversation_id), "content": "Try this"}).json()
        headers = {"X-Ebook-Worker-Token": "worker"}
        lease = client.post("/private/orchestrator/claim", json={"worker_id": "pi-1"}, headers=headers).json()
        stale = client.post("/private/orchestrator/failure", headers=headers, json={**lease, "generation": lease["generation"] + 1, "error": "stale"})
        assert stale.status_code == 409
        for _ in range(3):
            response = client.post("/private/orchestrator/failure", headers=headers, json={**lease, "error": "provider unavailable"})
            if response.status_code == 200 and response.json()["state"] == "failed":
                break
            lease = client.post("/private/orchestrator/claim", json={"worker_id": "pi-1"}, headers=headers).json()
        replay = client.post("/private/orchestrator/failure", headers=headers, json={**lease, "error": "late duplicate"})
        assert replay.status_code == 200
        assert replay.json()["state"] == "failed"
    with Session(engine) as session:
        assert len(session.scalars(select(Message).where(Message.conversation_id == conversation_id, Message.role == "assistant")).all()) == 1
