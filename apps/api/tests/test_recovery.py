import os
import base64
from collections.abc import Iterator
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, delete, select, update
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.conversations import append_message, create_project
from app.documents import create_section, save_section_revision
from app.events import replay_events
from app.jobs import (
    CancellationRejected,
    StaleLease,
    approve_brief_and_enqueue,
    cancel_run,
    checkpoint_job,
    claim_job,
    complete_job,
    fail_job,
    heartbeat_job,
    pause_job,
    resume_job,
)
from app.models import Artifact, Attempt, BriefRevision, Event, Job, Project, ProductionRun, Section, SectionRevision, Task, UsageCall
from app.main import create_app
import app.main as main_module
from app.settings import Settings


DATABASE_URL = os.environ.get("EBOOK_FACTORY_TEST_DATABASE_URL") or os.environ.get("EBOOK_FACTORY_DATABASE_URL")


@pytest.fixture()
def database_session() -> Iterator[Session]:
    if not DATABASE_URL:
        pytest.skip("EBOOK_FACTORY_TEST_DATABASE_URL is not configured")
    engine = create_engine(DATABASE_URL)
    session = Session(engine)
    project = Project(id=uuid4(), title=f"recovery-{uuid4()}", profile="nonfiction", language="en")
    brief = BriefRevision(
        project_id=project.id,
        revision=1,
        structured_brief={"promise_or_premise": "A durable queue test"},
        content_hash="a" * 64,
    )
    session.add(project)
    session.flush()
    session.add(brief)
    session.commit()
    session.info["cleanup_project_ids"] = {project.id}
    session.info["fixture_project_id"] = project.id
    try:
        yield session
    finally:
        for cleanup_project_id in session.info["cleanup_project_ids"]:
            session.execute(
                update(Project)
                .where(Project.id == cleanup_project_id)
                .values(active_brief_id=None, conversation_id=None)
            )
            session.flush()
            session.execute(delete(Event).where(Event.project_id == cleanup_project_id))
            session.execute(
                delete(Artifact).where(
                    Artifact.run_id.in_(select(ProductionRun.id).where(ProductionRun.project_id == cleanup_project_id))
                )
            )
            session.execute(delete(UsageCall).where(UsageCall.project_id == cleanup_project_id))
            session.execute(delete(ProductionRun).where(ProductionRun.project_id == cleanup_project_id))
            session.execute(delete(BriefRevision).where(BriefRevision.project_id == cleanup_project_id))
            session.execute(delete(Project).where(Project.id == cleanup_project_id))
        session.commit()
        session.close()
        engine.dispose()


def test_duplicate_approval_enqueues_one_run_and_one_job(database_session: Session) -> None:
    brief = database_session.scalar(select(BriefRevision))
    assert brief is not None
    project_id = brief.project_id
    brief_id = brief.id
    content_hash = brief.content_hash
    database_session.commit()

    first = approve_brief_and_enqueue(
        database_session,
        project_id=project_id,
        brief_id=brief_id,
        expected_content_hash=content_hash,
        budget={"max_turns": 8},
    )
    second = approve_brief_and_enqueue(
        database_session,
        project_id=project_id,
        brief_id=brief_id,
        expected_content_hash=content_hash,
        budget={"max_turns": 8},
    )

    assert first.run_id == second.run_id
    assert first.job_id == second.job_id
    assert database_session.scalar(select(ProductionRun.id).where(ProductionRun.project_id == project_id)) == first.run_id
    assert len(database_session.scalars(select(Job).where(Job.task_id == first.task_id)).all()) == 1


def test_api_project_brief_and_approval_boundary(database_session: Session) -> None:
    assert DATABASE_URL is not None
    with TestClient(create_app(Settings(database_url=DATABASE_URL, worker_token="test-worker-token", owner_token="test-owner-token")), headers={"Authorization": "Bearer test-owner-token"}) as client:
        project_response = client.post(
            "/projects",
            json={"title": "API journey", "profile": "nonfiction", "language": "en"},
        )
        assert project_response.status_code == 201
        project_id = project_response.json()["project_id"]
        database_session.info["cleanup_project_ids"].add(UUID(project_id))
        brief_response = client.post(
            f"/projects/{project_id}/briefs",
            json={"structured_brief": {"promise_or_premise": "A concise durable book"}},
        )
        assert brief_response.status_code == 201
        brief = brief_response.json()
        first = client.post(
            f"/projects/{project_id}/briefs/{brief['brief_id']}/approve",
            json={"expected_content_hash": brief["content_hash"], "budget": {"max_turns": 4}},
        )
        second = client.post(
            f"/projects/{project_id}/briefs/{brief['brief_id']}/approve",
            json={"expected_content_hash": brief["content_hash"], "budget": {"max_turns": 4}},
        )
        lease_response = client.post(
            "/private/worker/claim",
            json={"worker_id": "api-test-worker", "lease_seconds": 60},
            headers={"X-Ebook-Worker-Token": "test-worker-token"},
        )
        assert lease_response.status_code == 200
        lease = lease_response.json()
        context_response = client.get(
            f"/private/worker/jobs/{lease['job_id']}/context",
            headers={
                "X-Ebook-Worker-Token": "test-worker-token",
                "X-Worker-ID": "api-test-worker",
                "X-Generation": str(lease["generation"]),
            },
        )
        output_response = client.post(
            "/private/worker/production-result",
            headers={"X-Ebook-Worker-Token": "test-worker-token"},
            json={
                "job_id": lease["job_id"],
                "worker_id": "api-test-worker",
                "generation": lease["generation"],
                "content": "# A concise durable book\n\nThis is an API boundary fixture.",
                "provider": "test-provider",
                "model": "test-model",
                "call_id": str(uuid4()),
                "usage": {"input_tokens": 4, "output_tokens": 6},
                "art": {
                    "filename": "cover.png",
                    "mime_type": "image/png",
                    "byte_count": 11,
                    "content_base64": base64.b64encode(b"\x89PNG\r\n\x1a\nart").decode(),
                    "call_id": str(uuid4()),
                    "provider_request_id": "art-response",
                    "usage": {"input_tokens": 12, "output_tokens": 3},
                },
            },
        )
        sse_response = client.get(f"/projects/{project_id}/events/stream?after=0")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert context_response.status_code == 200
    assert context_response.json()["brief"]["promise_or_premise"] == "A concise durable book"
    assert output_response.status_code == 200
    assert output_response.json()["artifact_id"]
    database_session.expire_all()
    assert database_session.scalar(select(ProductionRun.state).where(ProductionRun.project_id == UUID(project_id))) == "draft_review"
    assert database_session.scalar(select(Project.state).where(Project.id == UUID(project_id))) == "draft_review"
    assert database_session.scalar(select(Task.provider).where(Task.run_id == UUID(output_response.json()["run_id"]))) == "test-provider"
    usage_call = database_session.scalar(select(UsageCall).where(UsageCall.project_id == UUID(project_id)))
    assert usage_call is not None
    assert usage_call.input_tokens == 4
    assert usage_call.output_tokens == 6
    assert usage_call.ended_at is not None
    assert usage_call.started_at <= usage_call.ended_at
    usage_calls = database_session.scalars(select(UsageCall).where(UsageCall.project_id == UUID(project_id))).all()
    assert {call.purpose for call in usage_calls} == {"production", "art"}
    art_usage = next(call for call in usage_calls if call.purpose == "art")
    assert art_usage.input_tokens == 12
    assert art_usage.output_tokens == 3
    assert sse_response.status_code == 200
    assert sse_response.headers["content-type"].startswith("text/event-stream")
    assert "run.approved" in sse_response.text


def test_production_result_rolls_back_when_final_fence_rejects(database_session: Session, monkeypatch, tmp_path) -> None:
    assert DATABASE_URL is not None
    artifact_root = tmp_path / "artifacts"
    with TestClient(create_app(Settings(database_url=DATABASE_URL, worker_token="test-worker-token", owner_token="test-owner-token", artifact_root=artifact_root)), headers={"Authorization": "Bearer test-owner-token"}) as client:
        project_response = client.post("/projects", json={"title": "Rollback", "profile": "nonfiction", "language": "en"})
        project_id = UUID(project_response.json()["project_id"])
        database_session.info["cleanup_project_ids"].add(project_id)
        brief_response = client.post(f"/projects/{project_id}/briefs", json={"structured_brief": {"promise_or_premise": "rollback"}})
        brief = brief_response.json()
        assert client.post(
            f"/projects/{project_id}/briefs/{brief['brief_id']}/approve",
            json={"expected_content_hash": brief["content_hash"], "budget": {"max_turns": 4}},
        ).status_code == 200
        lease = client.post(
            "/private/worker/claim",
            json={"worker_id": "rollback-worker", "lease_seconds": 60},
            headers={"X-Ebook-Worker-Token": "test-worker-token"},
        ).json()

        def reject_completion(*_args, **_kwargs):
            raise main_module.StaleLease("simulated final fence rejection")

        original_complete_job = main_module.complete_job
        monkeypatch.setattr(main_module, "complete_job", reject_completion)
        response = client.post(
            "/private/worker/production-result",
            headers={"X-Ebook-Worker-Token": "test-worker-token"},
            json={
                "job_id": lease["job_id"], "worker_id": "rollback-worker", "generation": lease["generation"],
                "content": "# rollback draft", "provider": "test-provider", "model": "test-model", "call_id": str(uuid4()),
                "usage": {"input_tokens": 2, "output_tokens": 3},
            },
        )
        artifact_path = artifact_root / str(lease["run_id"]) / "book.md"
        assert not artifact_path.exists()
        database_session.expire_all()
        assert database_session.scalar(select(SectionRevision).join(Section).where(Section.project_id == project_id)) is None
        assert database_session.scalar(select(Artifact).where(Artifact.run_id.in_(select(ProductionRun.id).where(ProductionRun.project_id == project_id)))) is None
        assert database_session.scalar(select(UsageCall).where(UsageCall.project_id == project_id)) is None
        assert database_session.scalar(select(Job.state).join(Task).join(ProductionRun).where(ProductionRun.project_id == project_id)) == "running"
        monkeypatch.setattr(main_module, "complete_job", original_complete_job)
        retry_response = client.post(
            "/private/worker/production-result",
            headers={"X-Ebook-Worker-Token": "test-worker-token"},
            json={
                "job_id": lease["job_id"], "worker_id": "rollback-worker", "generation": lease["generation"],
                "content": "# rollback draft", "provider": "test-provider", "model": "test-model", "call_id": str(uuid4()),
                "usage": {"input_tokens": 2, "output_tokens": 3},
            },
        )
    assert response.status_code == 409
    assert retry_response.status_code == 200
    database_session.expire_all()
    assert len(database_session.scalars(select(SectionRevision).join(Section).where(Section.project_id == project_id)).all()) == 1
    assert len(database_session.scalars(select(Artifact).where(Artifact.run_id.in_(select(ProductionRun.id).where(ProductionRun.project_id == project_id)))).all()) == 1
    assert len(database_session.scalars(select(UsageCall).where(UsageCall.project_id == project_id)).all()) == 1
    assert database_session.scalar(select(Job.state).join(Task).join(ProductionRun).where(ProductionRun.project_id == project_id)) == "succeeded"


def test_production_result_rejects_whitespace_content(database_session: Session) -> None:
    assert DATABASE_URL is not None
    with TestClient(create_app(Settings(database_url=DATABASE_URL, worker_token="test-worker-token", owner_token="test-owner-token"),), headers={"Authorization": "Bearer test-owner-token"}, raise_server_exceptions=False) as client:
        project_response = client.post("/projects", json={"title": "Whitespace", "profile": "nonfiction", "language": "en"})
        project_id = UUID(project_response.json()["project_id"])
        database_session.info["cleanup_project_ids"].add(project_id)
        brief_response = client.post(f"/projects/{project_id}/briefs", json={"structured_brief": {"promise_or_premise": "whitespace"}})
        brief = brief_response.json()
        client.post(f"/projects/{project_id}/briefs/{brief['brief_id']}/approve", json={"expected_content_hash": brief["content_hash"], "budget": {"max_turns": 4}})
        lease = client.post("/private/worker/claim", json={"worker_id": "whitespace-worker", "lease_seconds": 60}, headers={"X-Ebook-Worker-Token": "test-worker-token"}).json()
        response = client.post(
            "/private/worker/production-result",
            headers={"X-Ebook-Worker-Token": "test-worker-token"},
            json={"job_id": lease["job_id"], "worker_id": "whitespace-worker", "generation": lease["generation"], "content": "   ", "provider": "test", "model": "test"},
        )
    assert response.status_code == 409


def test_conversation_messages_are_ordered_and_deduplicated(database_session: Session) -> None:
    database_session.commit()
    created = create_project(database_session, title="Conversation test", profile="fiction", language="en")
    database_session.info["cleanup_project_ids"].add(created.project_id)
    first = append_message(
        database_session,
        project_id=created.project_id,
        conversation_id=created.conversation_id,
        channel="dashboard",
        external_dedupe_id="turn-1",
        role="user",
        content="A durable opening idea",
    )
    second = append_message(
        database_session,
        project_id=created.project_id,
        conversation_id=created.conversation_id,
        channel="dashboard",
        external_dedupe_id="turn-1",
        role="user",
        content="replayed delivery",
    )

    assert first.sequence == 1
    assert second.message_id == first.message_id
    assert second.duplicate is True


def test_section_revisions_are_immutable_and_stale_writes_are_rejected(database_session: Session) -> None:
    database_session.commit()
    project = database_session.scalar(select(Project))
    assert project is not None
    project_id = project.id
    database_session.commit()
    section_id = create_section(database_session, project_id=project_id, order_no=1, heading="Opening")
    first = save_section_revision(
        database_session,
        section_id=section_id,
        content="First accepted draft.",
        summary="Opening draft",
    )
    second = save_section_revision(
        database_session,
        section_id=section_id,
        content="Second accepted draft.",
        summary="Owner revision",
        expected_parent_revision_id=first.revision_id,
    )

    assert second.revision == 2
    with pytest.raises(ValueError, match="stale"):
        save_section_revision(
            database_session,
            section_id=section_id,
            content="Conflicting draft.",
            summary="Stale editor",
            expected_parent_revision_id=first.revision_id,
        )
    database_session.rollback()


def _approve(database_session: Session) -> tuple[object, object]:
    brief = database_session.scalar(
        select(BriefRevision).where(BriefRevision.project_id == database_session.info["fixture_project_id"])
    )
    assert brief is not None
    project_id = brief.project_id
    brief_id = brief.id
    content_hash = brief.content_hash
    database_session.commit()
    result = approve_brief_and_enqueue(
        database_session,
        project_id=project_id,
        brief_id=brief_id,
        expected_content_hash=content_hash,
        budget={"max_turns": 8},
    )
    database_session.commit()
    return result, project_id


def test_claim_heartbeat_checkpoint_and_completion_are_fenced(database_session: Session) -> None:
    approval, project_id = _approve(database_session)

    lease = claim_job(database_session, worker_id="worker-a", lease_seconds=60)
    assert lease is not None
    assert lease.job_id == approval.job_id
    assert lease.generation == 1
    database_session.commit()

    with pytest.raises(StaleLease):
        complete_job(
            database_session,
            job_id=lease.job_id,
            worker_id="worker-a",
            generation=lease.generation + 1,
            result_refs={"artifact": "wrong"},
        )
    database_session.rollback()

    heartbeat = heartbeat_job(
        database_session,
        job_id=lease.job_id,
        worker_id="worker-a",
        generation=lease.generation,
        lease_seconds=90,
    )
    assert heartbeat.lease_until is not None
    checkpoint_job(
        database_session,
        job_id=lease.job_id,
        worker_id="worker-a",
        generation=lease.generation,
        checkpoint={"completed_sections": ["section-1"]},
    )
    complete_job(
        database_session,
        job_id=lease.job_id,
        worker_id="worker-a",
        generation=lease.generation,
        result_refs={"artifact": "private/draft.md"},
    )
    database_session.commit()

    job = database_session.get(Job, lease.job_id)
    task = database_session.get(Task, approval.task_id)
    assert job is not None and job.state == "succeeded"
    assert task is not None and task.status == "succeeded"
    assert database_session.scalar(select(Attempt).where(Attempt.task_id == approval.task_id)).result_refs == {
        "artifact": "private/draft.md"
    }
    event_kinds = [event.kind for event in replay_events(database_session, project_id=project_id)]
    assert event_kinds == ["run.approved", "job.claimed", "job.checkpointed", "job.completed"]


def test_concurrent_claims_have_one_owner(database_session: Session) -> None:
    approval, _ = _approve(database_session)
    assert DATABASE_URL is not None

    def claim(worker_id: str):
        engine = create_engine(DATABASE_URL)
        session = Session(engine)
        try:
            return claim_job(session, worker_id=worker_id, lease_seconds=60)
        finally:
            session.close()
            engine.dispose()

    with ThreadPoolExecutor(max_workers=2) as executor:
        leases = list(executor.map(claim, ["worker-a", "worker-b"]))

    assert sum(lease is not None for lease in leases) == 1
    assert leases[0] is not None or leases[1] is not None


def test_expired_lease_reclaims_with_new_generation_and_rejects_late_completion(
    database_session: Session,
) -> None:
    approval, _ = _approve(database_session)

    first = claim_job(database_session, worker_id="worker-a", lease_seconds=-1)
    assert first is not None
    database_session.commit()
    second = claim_job(database_session, worker_id="worker-b", lease_seconds=60)
    assert second is not None
    assert second.generation == 2
    database_session.commit()

    with pytest.raises(StaleLease):
        complete_job(
            database_session,
            job_id=approval.job_id,
            worker_id="worker-a",
            generation=first.generation,
            result_refs={"artifact": "stale"},
        )
    database_session.rollback()
    complete_job(
        database_session,
        job_id=approval.job_id,
        worker_id="worker-b",
        generation=second.generation,
        result_refs={"artifact": "accepted"},
    )
    database_session.commit()


def test_cancel_persists_epoch_and_rejects_late_worker_output(database_session: Session) -> None:
    approval, _ = _approve(database_session)
    lease = claim_job(database_session, worker_id="worker-a", lease_seconds=60)
    assert lease is not None
    database_session.commit()

    new_epoch = cancel_run(database_session, run_id=approval.run_id, reason="owner requested stop")
    assert new_epoch == 1
    database_session.commit()

    with pytest.raises(CancellationRejected):
        complete_job(
            database_session,
            job_id=approval.job_id,
            worker_id="worker-a",
            generation=lease.generation,
            result_refs={"artifact": "late"},
        )
    database_session.rollback()
    job = database_session.get(Job, approval.job_id)
    run = database_session.get(ProductionRun, approval.run_id)
    attempt = database_session.scalar(select(Attempt).where(Attempt.id == lease.attempt_id))
    assert job is not None and job.state == "cancelled"
    assert job.lease_owner is None and job.lease_until is None
    assert attempt is not None and attempt.status == "cancelled" and attempt.lease_owner is None and attempt.lease_until is None
    assert run is not None and run.cancellation_epoch == 1 and run.state == "cancelled"


def test_pause_resume_and_bounded_retry_are_persisted(database_session: Session) -> None:
    approval, _ = _approve(database_session)
    pause_job(database_session, job_id=approval.job_id, reason="owner pause")
    database_session.commit()
    assert database_session.get(Job, approval.job_id).state == "paused"
    database_session.commit()

    resume_job(database_session, job_id=approval.job_id)
    database_session.commit()
    lease = claim_job(database_session, worker_id="worker-a", lease_seconds=60)
    assert lease is not None
    database_session.commit()

    fail_job(
        database_session,
        job_id=approval.job_id,
        worker_id="worker-a",
        generation=lease.generation,
        error_class="provider_rate_limit",
        retryable=True,
        retry_after=timedelta(seconds=0),
    )
    database_session.commit()
    assert database_session.get(Job, approval.job_id).state == "retry_wait"
    database_session.commit()

    retry = claim_job(database_session, worker_id="worker-b", lease_seconds=60)
    assert retry is not None and retry.generation == 2
    database_session.commit()
    fail_job(
        database_session,
        job_id=approval.job_id,
        worker_id="worker-b",
        generation=retry.generation,
        error_class="invalid_output",
        retryable=False,
    )
    database_session.commit()
    assert database_session.get(Job, approval.job_id).state == "failed"
