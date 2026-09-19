from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.jobs import approve_brief_and_enqueue, claim_job, complete_job
from app.main import create_app
from app.models import Base, BriefRevision, Project
from app.settings import Settings


def _app(tmp_path: Path) -> tuple[TestClient, Project, BriefRevision]:
    database_url = f"sqlite:///{tmp_path / 'execution-api.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        project = Project(id=uuid4(), title="Observable book", profile="fiction", language="en")
        brief = BriefRevision(
            id=uuid4(), project_id=project.id, revision=1,
            structured_brief={
                "title": "Observable book", "genre": "climate mystery",
                "promise_or_premise": "A bounded mystery", "art_direction": "A rainy harbor",
            }, content_hash="f" * 64,
        )
        session.add_all([project, brief])
        session.commit()
    client = TestClient(
        create_app(Settings(database_url=database_url, owner_token="owner", artifact_root=tmp_path / "artifacts")),
        headers={"Authorization": "Bearer owner"},
    )
    return client, project, brief


def test_execution_requires_owner_authentication(tmp_path: Path) -> None:
    client, project, _ = _app(tmp_path)
    client.headers.pop("Authorization", None)

    response = client.get(f"/projects/{project.id}/execution")

    assert response.status_code == 401
    client.close()


def test_execution_joins_plan_tasks_attempts_and_empty_conversation(tmp_path: Path) -> None:
    client, project, brief = _app(tmp_path)
    session = client.app.state.database.session()
    approval = approve_brief_and_enqueue(
        session,
        project_id=project.id,
        brief_id=brief.id,
        expected_content_hash=brief.content_hash,
        budget={"max_turns": 8},
    )
    lease = claim_job(session, worker_id="execution-worker")
    assert lease is not None
    complete_job(
        session,
        job_id=lease.job_id,
        worker_id="execution-worker",
        generation=lease.generation,
        result_refs={"result": "outline summary", "usage_call_id": "call-1"},
    )
    session.close()

    response = client.get(f"/projects/{project.id}/execution")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project"]["title"] == "Observable book"
    assert payload["brief"]["genre"] == "climate mystery"
    assert payload["conversation"] == []
    assert payload["runs"][0]["run_id"] == str(approval.run_id)
    task_types = {task["task_type"] for task in payload["runs"][0]["tasks"]}
    assert {"outline", "production", "review"}.issubset(task_types)
    outline = next(task for task in payload["runs"][0]["tasks"] if task["task_type"] == "outline")
    assert outline["attempts"][0]["worker_id"] == "execution-worker"
    assert any(item["kind"] == "agent.started" for item in payload["activities"])
    assert any(item["kind"] == "agent.completed" for item in payload["activities"])
    assert payload["usage_totals"]["calls"] == 0
    assert all("worker_token" not in str(payload).lower() for _ in [0])
    client.close()


def test_execution_activity_limit_and_project_scope_are_enforced(tmp_path: Path) -> None:
    client, project, _ = _app(tmp_path)

    limited = client.get(f"/projects/{project.id}/execution?limit=1")
    wrong = client.get(f"/projects/{uuid4()}/execution")

    assert limited.status_code == 200
    assert len(limited.json()["activities"]) <= 1
    assert wrong.status_code == 404
    client.close()
