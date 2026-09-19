from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.jobs import approve_brief_and_enqueue, claim_job, complete_job, enqueue_art_revision
from app.main import create_app
from app.models import Artifact, Base, BriefRevision, Event, Job, Project, ProductionRun, Task
from app.settings import Settings
from fastapi.testclient import TestClient


def _session(tmp_path: Path) -> tuple[Session, Project, BriefRevision]:
    engine = create_engine(f"sqlite:///{tmp_path / 'execution.db'}")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    project = Project(id=uuid4(), title="Execution evidence", profile="fiction", language="en")
    brief = BriefRevision(
        id=uuid4(),
        project_id=project.id,
        revision=1,
        structured_brief={"promise_or_premise": "A bounded story", "art_direction": "A vivid cover"},
        content_hash="a" * 64,
    )
    session.add_all([project, brief])
    session.commit()
    return session, project, brief


def test_approval_persists_a_task_plan_for_the_owner(tmp_path: Path) -> None:
    session, project, brief = _session(tmp_path)
    result = approve_brief_and_enqueue(
        session,
        project_id=project.id,
        brief_id=brief.id,
        expected_content_hash=brief.content_hash,
        budget={"max_turns": 8},
    )

    plan = session.scalar(select(Event).where(Event.kind == "run.plan.created"))

    assert plan is not None
    assert plan.run_id == result.run_id
    assert {entry["task_type"] for entry in plan.data["tasks"]} == {"outline", "production", "review"}
    assert all("dedupe_key" in entry for entry in plan.data["tasks"])


def test_claim_and_completion_persist_agent_lifecycle_context(tmp_path: Path) -> None:
    session, project, brief = _session(tmp_path)
    approval = approve_brief_and_enqueue(
        session,
        project_id=project.id,
        brief_id=brief.id,
        expected_content_hash=brief.content_hash,
        budget={"max_turns": 8},
    )
    lease = claim_job(session, worker_id="trace-worker")
    assert lease is not None
    complete_job(
        session,
        job_id=lease.job_id,
        worker_id="trace-worker",
        generation=lease.generation,
        result_refs={"result": "bounded"},
    )

    events = session.scalars(
        select(Event).where(Event.run_id == approval.run_id).order_by(Event.id)
    ).all()
    started = next(event for event in events if event.kind == "agent.started")
    completed = next(event for event in events if event.kind == "agent.completed")

    assert started.data["attempt_id"] == str(lease.attempt_id)
    assert started.data["task_type"] == "outline"
    assert started.data["worker_id"] == "trace-worker"
    assert completed.data["attempt_id"] == str(lease.attempt_id)
    assert completed.data["result_refs"] == {"result": "bounded"}


def test_art_revision_enqueue_is_deduplicated_and_keeps_source_artifact(tmp_path: Path) -> None:
    session, project, brief = _session(tmp_path)
    run = ProductionRun(project_id=project.id, approved_brief_id=brief.id, state="draft_review", budget={})
    session.add(run)
    session.flush()
    source = Artifact(
        id=uuid4(),
        run_id=run.id,
        relative_path=f"{run.id}/cover.png",
        mime_type="image/png",
        byte_count=8,
        sha256="b" * 64,
    )
    session.add(source)
    session.commit()

    first = enqueue_art_revision(
        session,
        project_id=project.id,
        artifact_id=source.id,
        note="Use a more specific anime-inspired scene.",
    )
    second = enqueue_art_revision(
        session,
        project_id=project.id,
        artifact_id=source.id,
        note="Use a more specific anime-inspired scene.",
    )

    assert first == second
    revision_task = session.get(Task, first.task_id)
    revision_job = session.get(Job, first.job_id)
    assert revision_task is not None and revision_task.task_type == "art-revision"
    assert revision_task.result_refs["source_artifact_id"] == str(source.id)
    assert revision_task.result_refs["feedback"] == "Use a more specific anime-inspired scene."
    assert revision_job is not None and revision_job.job_type == "art-revision.start"
    assert session.get(Artifact, source.id).relative_path == f"{run.id}/cover.png"


def test_owner_review_records_decision_and_queues_revision(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'review.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    project = Project(id=uuid4(), title="Reviewable cover", profile="fiction", language="en", state="draft_review")
    brief = BriefRevision(
        id=uuid4(),
        project_id=project.id,
        revision=1,
        structured_brief={"promise_or_premise": "A story", "art_direction": "A cover"},
        content_hash="c" * 64,
    )
    with Session(engine, expire_on_commit=False) as session:
        session.add_all([project, brief])
        session.flush()
        run = ProductionRun(project_id=project.id, approved_brief_id=brief.id, state="draft_review", budget={})
        session.add(run)
        session.flush()
        source = Artifact(
            id=uuid4(), run_id=run.id, relative_path=f"{run.id}/cover.png", mime_type="image/png",
            byte_count=8, sha256="d" * 64,
        )
        session.add(source)
        session.commit()
        project_id, artifact_id = project.id, source.id

    with TestClient(create_app(Settings(database_url=database_url, owner_token="owner", artifact_root=tmp_path / "artifacts")), headers={"Authorization": "Bearer owner"}) as client:
        response = client.post(
            f"/projects/{project_id}/artifacts/{artifact_id}/review",
            json={
                "decision": "request_revision",
                "note": "Make the scene more specific to the theme.",
                "expected_owner_review_state": "pending",
            },
        )

    assert response.status_code == 200
    response_payload = response.json()
    with Session(engine) as session:
        events = session.scalars(select(Event).where(Event.project_id == project_id).order_by(Event.id)).all()
        source_after = session.get(Artifact, artifact_id)
        revision_task = session.scalar(select(Task).where(Task.task_type == "art-revision"))
        revision_job = session.scalar(select(Job).where(Job.job_type == "art-revision.start"))
    assert source_after is not None and source_after.owner_review_state == "revision_requested"
    review_event = next(event for event in events if event.kind == "artifact.owner_reviewed")
    assert review_event.data["decision"] == "request_revision"
    assert review_event.data["note"] == "Make the scene more specific to the theme."
    assert revision_task is not None and revision_job is not None
    assert review_event.data["revision_job_id"] == str(revision_job.id)
    assert response_payload["revision_job_id"] == str(revision_job.id)
    assert response_payload["revision_task_id"] == str(revision_task.id)


def test_art_revision_worker_callback_persists_new_artifact_and_lineage(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'art-result.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    root = tmp_path / "artifacts"
    session = Session(engine, expire_on_commit=False)
    project = Project(id=uuid4(), title="Art callback", profile="fiction", language="en")
    brief = BriefRevision(
        id=uuid4(), project_id=project.id, revision=1,
        structured_brief={"art_direction": "A blue star"}, content_hash="e" * 64,
    )
    session.add_all([project, brief])
    session.flush()
    run = ProductionRun(project_id=project.id, approved_brief_id=brief.id, state="draft_review", budget={})
    session.add(run)
    session.flush()
    source_content = b"\x89PNG\r\n\x1a\nsource"
    source = Artifact(
        id=uuid4(), run_id=run.id, relative_path=f"{run.id}/cover.png", mime_type="image/png",
        byte_count=len(source_content), sha256=hashlib.sha256(source_content).hexdigest(),
    )
    session.add(source)
    session.commit()
    queued = enqueue_art_revision(session, project_id=project.id, artifact_id=source.id, note="Add a moonlit city.")
    lease = claim_job(session, worker_id="art-worker")
    assert lease is not None and lease.job_id == queued.job_id
    session.commit()
    project_id = project.id
    session.close()
    image = b"\x89PNG\r\n\x1a\nreplacement"

    with TestClient(
        create_app(Settings(database_url=database_url, owner_token="owner", worker_token="worker", artifact_root=root)),
    ) as client:
        response = client.post(
            "/private/worker/art-result",
            headers={"X-Ebook-Worker-Token": "worker"},
            json={
                "job_id": str(lease.job_id),
                "worker_id": "art-worker",
                "generation": lease.generation,
                "provider": "openai-codex",
                "model": "gpt-5.6-luna",
                "art": {
                    "filename": "replacement.png",
                    "mime_type": "image/png",
                    "byte_count": len(image),
                    "content_base64": base64.b64encode(image).decode(),
                    "call_id": str(uuid4()),
                    "usage": {"input_tokens": 2, "output_tokens": 3},
                },
            },
        )

    assert response.status_code == 200, response.text
    with Session(engine) as check:
        replacement = check.scalar(select(Artifact).where(Artifact.relative_path.like(f"{run.id}/art-revision-%")))
        completed = check.get(Job, lease.job_id)
        generated = check.scalar(select(Event).where(Event.project_id == project_id, Event.kind == "art.generated"))
    assert replacement is not None
    assert replacement.owner_review_state == "pending"
    assert replacement.id != source.id
    assert (root / replacement.relative_path).read_bytes() == image
    assert completed is not None and completed.state == "succeeded"
    assert generated is not None and generated.data["source_artifact_id"] == str(source.id)
