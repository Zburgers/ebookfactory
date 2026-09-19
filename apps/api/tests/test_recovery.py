import os
import base64
import json
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
from app.production import assemble_section_revisions, expand_outline_sections, parse_production_sections
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


def test_non_page_one_section_outline_remains_compatible() -> None:
    parsed = parse_production_sections("## Opening\nA single valid section.", page_target=False)
    assert len(parsed) == 1
    assert parsed[0].heading == "Opening"


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
    brief = database_session.scalar(
        select(BriefRevision).where(BriefRevision.project_id == database_session.info["fixture_project_id"])
    )
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
    production = database_session.get(Task, first.task_id)
    assert production is not None
    assert production.task_type == "production"
    assert len(production.dependencies) == 1
    outline = database_session.get(Task, UUID(production.dependencies[0]))
    assert outline is not None
    assert outline.task_type == "outline"
    assert len(database_session.scalars(select(Job).where(Job.task_id.in_([outline.id, production.id]))).all()) == 2


def test_production_claim_waits_for_outline_dependency(database_session: Session) -> None:
    brief = database_session.scalar(
        select(BriefRevision).where(BriefRevision.project_id == database_session.info["fixture_project_id"])
    )
    assert brief is not None
    project_id, brief_id, content_hash = brief.project_id, brief.id, brief.content_hash
    database_session.commit()
    approval = approve_brief_and_enqueue(
        database_session, project_id=project_id, brief_id=brief_id,
        expected_content_hash=content_hash, budget={"max_turns": 8},
    )
    database_session.commit()
    production = database_session.get(Task, approval.task_id)
    assert production is not None
    production_job = database_session.scalar(select(Job).where(Job.task_id == production.id))
    assert production_job is not None
    database_session.commit()
    first_lease = claim_job(database_session, worker_id="dependency-gate")
    assert first_lease is not None
    assert database_session.get(Task, first_lease.task_id).task_type == "outline"
    database_session.commit()
    assert claim_job(database_session, worker_id="dependency-gate") is None


def test_outline_result_expands_bounded_section_tasks_and_rewires_production(database_session: Session) -> None:
    brief = database_session.scalar(select(BriefRevision).where(BriefRevision.project_id == database_session.info["fixture_project_id"]))
    assert brief is not None
    project_id, brief_id, content_hash = brief.project_id, brief.id, brief.content_hash
    database_session.commit()
    approval = approve_brief_and_enqueue(database_session, project_id=project_id, brief_id=brief_id, expected_content_hash=content_hash, budget={"max_turns": 8})
    outline = database_session.scalar(select(Task).where(Task.run_id == approval.run_id, Task.task_type == "outline"))
    production = database_session.get(Task, approval.task_id)
    assert outline is not None and production is not None
    sections = expand_outline_sections(database_session, outline_task=outline, production_task=production, outline_text="\n".join(f"## Section {i}\nNotes {i}" for i in range(1, 11)))
    assert len(sections) == 10
    assert len(production.dependencies) == 10
    assert all(task.task_type == "section-draft" for task in sections)
    assert len(database_session.scalars(select(Job).where(Job.task_id.in_([task.id for task in sections]))).all()) == 10


def test_section_assembly_uses_only_persisted_revisions(database_session: Session) -> None:
    project_id = database_session.info["fixture_project_id"]
    database_session.commit()
    first = create_section(database_session, project_id=project_id, order_no=1, heading="Opening")
    second = create_section(database_session, project_id=project_id, order_no=2, heading="Close")
    save_section_revision(database_session, section_id=first, content="First bounded prose.", summary="worker")
    save_section_revision(database_session, section_id=second, content="Second bounded prose.", summary="worker")
    database_session.commit()
    run = ProductionRun(project_id=project_id, approved_brief_id=database_session.scalar(select(BriefRevision.id).where(BriefRevision.project_id == project_id)), budget={}, state="producing")
    database_session.add(run)
    database_session.flush()
    first_task = Task(run_id=run.id, task_type="section-draft", status="succeeded", result_refs={"section_id": str(first)})
    second_task = Task(run_id=run.id, task_type="section-draft", status="succeeded", result_refs={"section_id": str(second)})
    database_session.add_all([first_task, second_task])
    database_session.commit()
    assert assemble_section_revisions(database_session, project_id=project_id, section_task_ids=[first_task.id, second_task.id]) == "## Opening\n\nFirst bounded prose.\n\n## Close\n\nSecond bounded prose."


def test_section_assembly_uses_the_revision_fenced_to_each_task(database_session: Session) -> None:
    project_id = database_session.info["fixture_project_id"]
    database_session.commit()
    section_id = create_section(database_session, project_id=project_id, order_no=1, heading="Opening")
    first = save_section_revision(database_session, section_id=section_id, content="First draft.", summary="worker")
    second = save_section_revision(database_session, section_id=section_id, content="Later unrelated draft.", summary="editor")
    database_session.commit()
    run = ProductionRun(
        project_id=project_id,
        approved_brief_id=database_session.scalar(select(BriefRevision.id).where(BriefRevision.project_id == project_id)),
        budget={},
        state="producing",
    )
    database_session.add(run)
    database_session.flush()
    task = Task(
        run_id=run.id,
        task_type="section-draft",
        status="succeeded",
        result_refs={"section_id": str(section_id), "revision_id": str(first.revision_id)},
    )
    database_session.add(task)
    database_session.commit()
    assert assemble_section_revisions(database_session, project_id=project_id, section_task_ids=[task.id]) == "## Opening\n\nFirst draft."


def test_section_assembly_rejects_dependencies_from_another_run(database_session: Session) -> None:
    project_id = database_session.info["fixture_project_id"]
    brief_id = database_session.scalar(select(BriefRevision.id).where(BriefRevision.project_id == project_id))
    database_session.commit()
    section_id = create_section(database_session, project_id=project_id, order_no=1, heading="Opening")
    revision = save_section_revision(database_session, section_id=section_id, content="Scoped draft.", summary="worker")
    first_run = ProductionRun(project_id=project_id, approved_brief_id=brief_id, budget={}, state="producing")
    second_run = ProductionRun(project_id=project_id, approved_brief_id=brief_id, budget={}, state="producing")
    database_session.add_all([first_run, second_run])
    database_session.flush()
    other_run_task = Task(
        run_id=second_run.id,
        task_type="section-draft",
        status="succeeded",
        result_refs={"section_id": str(section_id), "revision_id": str(revision.revision_id)},
    )
    database_session.add(other_run_task)
    database_session.commit()
    with pytest.raises(ValueError, match="same production run"):
        assemble_section_revisions(
            database_session,
            project_id=project_id,
            run_id=first_run.id,
            section_task_ids=[other_run_task.id],
        )


def test_section_assembly_nests_internal_headings(database_session: Session) -> None:
    project_id = database_session.info["fixture_project_id"]
    brief_id = database_session.scalar(select(BriefRevision.id).where(BriefRevision.project_id == project_id))
    database_session.commit()
    section_id = create_section(database_session, project_id=project_id, order_no=1, heading="Opening")
    revision = save_section_revision(database_session, section_id=section_id, content="## Subheading\n\nBody.", summary="worker")
    run = ProductionRun(project_id=project_id, approved_brief_id=brief_id, budget={}, state="producing")
    database_session.add(run)
    database_session.flush()
    task = Task(
        run_id=run.id,
        task_type="section-draft",
        status="succeeded",
        result_refs={"section_id": str(section_id), "revision_id": str(revision.revision_id)},
    )
    database_session.add(task)
    database_session.commit()
    assembled = assemble_section_revisions(database_session, project_id=project_id, run_id=run.id, section_task_ids=[task.id])
    assert "## Opening" in assembled
    assert "### Subheading" in assembled
    assert len(parse_production_sections(assembled, page_target=True)) == 1


def test_terminal_outline_failure_fails_dependents_and_run(database_session: Session) -> None:
    brief = database_session.scalar(
        select(BriefRevision).where(BriefRevision.project_id == database_session.info["fixture_project_id"])
    )
    assert brief is not None
    project_id, brief_id, content_hash = brief.project_id, brief.id, brief.content_hash
    database_session.commit()
    approval = approve_brief_and_enqueue(
        database_session, project_id=project_id, brief_id=brief_id,
        expected_content_hash=content_hash, budget={"max_turns": 4},
    )
    database_session.commit()
    outline_lease = claim_job(database_session, worker_id="failing-outline", lease_seconds=60)
    assert outline_lease is not None
    sibling_task = Task(run_id=approval.run_id, task_type="section-draft", dependencies=[], status="queued")
    database_session.add(sibling_task)
    database_session.flush()
    database_session.add(Job(
        task_id=sibling_task.id,
        job_type="zzz-sibling.start",
        payload={"run_id": str(approval.run_id), "cancellation_epoch": 0},
        dedupe_key=f"test-sibling:{sibling_task.id}",
        state="queued",
    ))
    database_session.commit()
    sibling_lease = claim_job(database_session, worker_id="sibling-worker", lease_seconds=60)
    assert sibling_lease is not None
    fail_job(
        database_session,
        job_id=outline_lease.job_id,
        worker_id="failing-outline",
        generation=outline_lease.generation,
        error_class="outline_provider_failure",
        retryable=False,
    )
    database_session.commit()

    production = database_session.get(Task, approval.task_id)
    assert production is not None and production.status == "failed"
    production_job = database_session.scalar(select(Job).where(Job.task_id == production.id))
    assert production_job is not None and production_job.state == "failed"
    review = database_session.scalar(select(Task).where(Task.run_id == approval.run_id, Task.task_type == "review"))
    assert review is not None and review.status == "failed"
    review_job = database_session.scalar(select(Job).where(Job.task_id == review.id))
    assert review_job is not None and review_job.state == "failed"
    assert database_session.scalar(select(ProductionRun.state).where(ProductionRun.id == approval.run_id)) == "failed"
    assert database_session.scalar(select(Project.state).where(Project.id == project_id)) == "failed"
    failure_events = database_session.scalars(
        select(Event).where(Event.run_id == approval.run_id, Event.kind == "job.failed").order_by(Event.id)
    ).all()
    assert {event.task_id for event in failure_events} >= {production.id, review.id}
    assert any(event.task_id == review.id and event.data.get("dependency_task_id") == str(production.id) for event in failure_events)
    sibling_attempt = database_session.scalar(select(Attempt).where(Attempt.task_id == sibling_task.id))
    assert sibling_attempt is not None and sibling_attempt.status == "failed" and sibling_attempt.finished_at is not None
    database_session.commit()
    assert claim_job(database_session, worker_id="after-outline-failure") is None


def test_outline_task_result_is_fenced_and_flows_into_production_context(database_session: Session) -> None:
    assert DATABASE_URL is not None
    with TestClient(
        create_app(Settings(database_url=DATABASE_URL, worker_token="outline-worker-token", owner_token="test-owner-token")),
        headers={"Authorization": "Bearer test-owner-token"},
    ) as client:
        project_response = client.post("/projects", json={"title": "Outline callback", "profile": "nonfiction", "language": "en"})
        project_id = UUID(project_response.json()["project_id"])
        database_session.info["cleanup_project_ids"].add(project_id)
        brief_response = client.post(f"/projects/{project_id}/briefs", json={"structured_brief": {"promise_or_premise": "bounded outline"}})
        brief = brief_response.json()
        approval = client.post(
            f"/projects/{project_id}/briefs/{brief['brief_id']}/approve",
            json={"expected_content_hash": brief["content_hash"], "budget": {"max_turns": 4}},
        ).json()
        headers = {"X-Ebook-Worker-Token": "outline-worker-token"}
        outline_lease = client.post("/private/worker/claim", json={"worker_id": "outline-worker"}, headers=headers).json()
        context = client.get(
            f"/private/worker/jobs/{outline_lease['job_id']}/context",
            headers={**headers, "X-Worker-ID": "outline-worker", "X-Generation": str(outline_lease["generation"])},
        )
        assert context.json()["task_type"] == "outline"
        result = client.post(
            "/private/worker/task-result",
            headers=headers,
            json={
                "job_id": outline_lease["job_id"], "worker_id": "outline-worker", "generation": outline_lease["generation"],
                "result": "## Opening\nA bounded outline.", "provider": "test-provider", "model": "test-model",
                "call_id": str(uuid4()), "usage": {"input_tokens": 5, "output_tokens": 7},
            },
        )
        assert result.status_code == 200
        database_session.expire_all()
        outline_task = database_session.scalar(
            select(Task).where(Task.run_id == UUID(approval["run_id"]), Task.task_type == "outline")
        )
        assert outline_task is not None and outline_task.provider == "test-provider" and outline_task.model == "test-model"
        outline_attempt = database_session.scalar(select(Attempt).where(Attempt.task_id == outline_task.id))
        assert outline_attempt is not None and outline_attempt.provider == "test-provider" and outline_attempt.model == "test-model"
        database_session.commit()
        production_lease = client.post("/private/worker/claim", json={"worker_id": "production-worker"}, headers=headers).json()
        production_context = client.get(
            f"/private/worker/jobs/{production_lease['job_id']}/context",
            headers={**headers, "X-Worker-ID": "production-worker", "X-Generation": str(production_lease["generation"])},
        )
        assert production_context.json()["task_type"] == "production"
        assert production_context.json()["outline"]["result"] == "## Opening\nA bounded outline."


def test_task_result_budget_block_is_durable(database_session: Session) -> None:
    """A rejected callback must commit the blocked state before returning 409."""

    assert DATABASE_URL is not None
    with TestClient(
        create_app(Settings(database_url=DATABASE_URL, worker_token="budget-worker-token", owner_token="test-owner-token")),
        headers={"Authorization": "Bearer test-owner-token"},
    ) as client:
        project_response = client.post("/projects", json={"title": "Budget callback", "profile": "nonfiction", "language": "en"})
        assert project_response.status_code == 201
        project_id = UUID(project_response.json()["project_id"])
        database_session.info["cleanup_project_ids"].add(project_id)
        brief_response = client.post(
            f"/projects/{project_id}/briefs",
            json={"structured_brief": {"promise_or_premise": "budget callback"}},
        )
        assert brief_response.status_code == 201
        brief = brief_response.json()
        approval = client.post(
            f"/projects/{project_id}/briefs/{brief['brief_id']}/approve",
            json={"expected_content_hash": brief["content_hash"], "budget": {"max_turns": 0}},
        )
        assert approval.status_code in {200, 201}
        headers = {"X-Ebook-Worker-Token": "budget-worker-token"}
        lease_response = client.post(
            "/private/worker/claim",
            json={"worker_id": "budget-worker"},
            headers=headers,
        )
        assert lease_response.status_code == 200
        lease = lease_response.json()
        result = client.post(
            "/private/worker/task-result",
            headers=headers,
            json={
                "job_id": lease["job_id"],
                "worker_id": "budget-worker",
                "generation": lease["generation"],
                "result": "## Opening\nA blocked outline.",
                "provider": "test-provider",
                "model": "test-model",
                "call_id": str(uuid4()),
                "usage": {"input_tokens": 2, "output_tokens": 3},
            },
        )
        assert result.status_code == 409
        assert "task budget blocked" in result.json()["detail"]

    database_session.expire_all()
    run_id = UUID(approval.json()["run_id"])
    run = database_session.get(ProductionRun, run_id)
    project = database_session.get(Project, project_id)
    assert run is not None and run.state == "blocked"
    assert project is not None and project.state == "blocked"
    outline = database_session.scalar(select(Task).where(Task.run_id == run_id, Task.task_type == "outline"))
    assert outline is not None and outline.status == "blocked"
    job = database_session.scalar(select(Job).where(Job.task_id == outline.id))
    assert job is not None and job.state == "blocked"
    assert database_session.scalar(select(UsageCall).where(UsageCall.run_id == run_id)) is None


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
        outline_lease = lease_response.json()
        outline_result = client.post(
            "/private/worker/task-result",
            headers={"X-Ebook-Worker-Token": "test-worker-token"},
            json={
                "job_id": outline_lease["job_id"], "worker_id": "api-test-worker", "generation": outline_lease["generation"],
                "result": "## Opening\nA bounded outline.", "provider": "test-provider", "model": "test-model",
                "call_id": str(uuid4()), "usage": {"input_tokens": 2, "output_tokens": 3},
            },
        )
        assert outline_result.status_code == 200
        lease = client.post(
            "/private/worker/claim",
            json={"worker_id": "api-test-worker", "lease_seconds": 60},
            headers={"X-Ebook-Worker-Token": "test-worker-token"},
        ).json()
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
        review_lease = client.post(
            "/private/worker/claim",
            json={"worker_id": "api-test-worker", "lease_seconds": 60},
            headers={"X-Ebook-Worker-Token": "test-worker-token"},
        ).json()
        assert review_lease
        review_response = client.post(
            "/private/worker/task-result",
            headers={"X-Ebook-Worker-Token": "test-worker-token"},
            json={
                "job_id": review_lease["job_id"], "worker_id": "api-test-worker", "generation": review_lease["generation"],
                "result": "PASS: reviewed", "provider": "test-provider", "model": "review-model",
                "call_id": str(uuid4()), "usage": {"input_tokens": 7, "output_tokens": 8},
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
    assert review_response.status_code == 200
    database_session.expire_all()
    assert database_session.scalar(select(ProductionRun.state).where(ProductionRun.project_id == UUID(project_id))) == "draft_review"
    assert database_session.scalar(select(Project.state).where(Project.id == UUID(project_id))) == "draft_review"
    assert database_session.scalar(
        select(Task.provider).where(
            Task.run_id == UUID(output_response.json()["run_id"]), Task.task_type == "production"
        )
    ) == "test-provider"
    usage_call = database_session.scalar(
        select(UsageCall).where(UsageCall.project_id == UUID(project_id), UsageCall.purpose == "production")
    )
    assert usage_call is not None
    assert usage_call.input_tokens == 4
    assert usage_call.output_tokens == 6
    assert usage_call.ended_at is not None
    assert usage_call.started_at <= usage_call.ended_at
    usage_calls = database_session.scalars(select(UsageCall).where(UsageCall.project_id == UUID(project_id))).all()
    assert {call.purpose for call in usage_calls} == {"outline", "production", "review", "art"}
    art_usage = next(call for call in usage_calls if call.purpose == "art")
    assert art_usage.input_tokens == 12
    assert art_usage.output_tokens == 3
    art_artifact = database_session.scalar(
        select(Artifact).where(Artifact.run_id == UUID(output_response.json()["run_id"]), Artifact.mime_type == "image/png")
    )
    assert art_artifact is not None
    assert art_artifact.attempt_id == art_usage.attempt_id
    assert sse_response.status_code == 200
    assert sse_response.headers["content-type"].startswith("text/event-stream")
    assert "run.approved" in sse_response.text


def test_review_stage_is_ordered_bounded_and_finalizes_run(database_session: Session) -> None:
    assert DATABASE_URL is not None
    with TestClient(create_app(Settings(database_url=DATABASE_URL, worker_token="review-worker-token", owner_token="review-owner-token")), headers={"Authorization": "Bearer review-owner-token"}) as client:
        project = client.post("/projects", json={"title": "Review graph", "profile": "nonfiction", "language": "en"}).json()
        project_id = UUID(project["project_id"])
        database_session.info["cleanup_project_ids"].add(project_id)
        brief = client.post(f"/projects/{project_id}/briefs", json={"structured_brief": {"promise_or_premise": "A reviewed book"}}).json()
        approval = client.post(f"/projects/{project_id}/briefs/{brief['brief_id']}/approve", json={"expected_content_hash": brief["content_hash"], "budget": {}}).json()
        duplicate = client.post(f"/projects/{project_id}/briefs/{brief['brief_id']}/approve", json={"expected_content_hash": brief["content_hash"], "budget": {}}).json()
        assert duplicate == approval
        headers = {"X-Ebook-Worker-Token": "review-worker-token"}
        def claim_for_run():
            for _ in range(12):
                lease = client.post("/private/worker/claim", json={"worker_id": "review-worker"}, headers=headers).json()
                if lease is None:
                    return None
                if lease["run_id"] == approval["run_id"]:
                    return lease
                client.post("/private/worker/fail", headers=headers, json={"job_id": lease["job_id"], "worker_id": "review-worker", "generation": lease["generation"], "error_class": "test-unrelated-lease", "retryable": False})
            raise AssertionError("target run was not claimable")

        outline = claim_for_run()
        assert outline
        assert client.post("/private/worker/task-result", headers=headers, json={"job_id": outline["job_id"], "worker_id": "review-worker", "generation": outline["generation"], "result": "## Opening\nOutline", "provider": "test", "model": "test-model", "call_id": str(uuid4()), "usage": {"input_tokens": 1, "output_tokens": 1}}).status_code == 200
        production = claim_for_run()
        production_context = client.get(f"/private/worker/jobs/{production['job_id']}/context", headers={**headers, "X-Worker-ID": "review-worker", "X-Generation": str(production["generation"])}).json()
        assert production_context["task_type"] == "production"
        assert client.post("/private/worker/production-result", headers=headers, json={"job_id": production["job_id"], "worker_id": "review-worker", "generation": production["generation"], "content": "## Opening\nA durable section.", "provider": "test", "model": "test-model", "call_id": str(uuid4()), "usage": {"input_tokens": 2, "output_tokens": 3}}).status_code == 200
        assert database_session.scalar(select(ProductionRun.state).where(ProductionRun.id == UUID(approval["run_id"]))) == "producing"
        section = database_session.scalar(select(Section).where(Section.project_id == project_id))
        assert section is not None
        section.heading = "H" * 512
        revision = database_session.scalar(
            select(SectionRevision).where(SectionRevision.section_id == section.id).order_by(SectionRevision.revision.desc())
        )
        assert revision is not None
        revision.content = "C" * (64 * 1024)
        database_session.commit()
        foreign_run = ProductionRun(project_id=project_id, approved_brief_id=UUID(brief["brief_id"]), budget={}, state="producing")
        database_session.add(foreign_run)
        database_session.flush()
        foreign_task = Task(
            run_id=foreign_run.id,
            task_type="section-draft",
            status="succeeded",
            result_refs={"section_id": str(section.id), "revision_id": str(revision.id)},
        )
        database_session.add(foreign_task)
        database_session.flush()
        production_task = database_session.get(Task, UUID(production["task_id"]))
        assert production_task is not None
        production_task.dependencies = [str(foreign_task.id)]
        database_session.commit()
        review = claim_for_run()
        assert review
        invalid_review_context = client.get(
            f"/private/worker/jobs/{review['job_id']}/context",
            headers={**headers, "X-Worker-ID": "review-worker", "X-Generation": str(review["generation"])},
        )
        assert invalid_review_context.status_code == 409
        production_task.dependencies = []
        database_session.commit()
        review_context = client.get(f"/private/worker/jobs/{review['job_id']}/context", headers={**headers, "X-Worker-ID": "review-worker", "X-Generation": str(review["generation"])}).json()
        assert review_context["task_type"] == "review"
        assert len(review_context["review_sections"][0]["heading"].encode()) == 512
        assert len(review_context["review_sections"][0]["content"].encode()) == 48 * 1024 - 512
        assert sum(len(section["heading"].encode()) + len(section["content"].encode()) for section in review_context["review_sections"]) <= 48 * 1024
        assert len(review_context["review_sections"][0]["heading"]) < 64 * 1024
        assert len(json.dumps(review_context, ensure_ascii=False, separators=(",", ":"), default=str).encode()) < 64 * 1024
        assert client.post("/private/worker/task-result", headers=headers, json={"job_id": review["job_id"], "worker_id": "review-worker", "generation": review["generation"], "result": "PASS: reviewed", "provider": "test", "model": "review-model", "call_id": str(uuid4()), "usage": {"input_tokens": 8, "output_tokens": 9}}).status_code == 200
    database_session.expire_all()
    assert database_session.scalar(select(ProductionRun.state).where(ProductionRun.id == UUID(approval["run_id"]))) == "draft_review"
    assert database_session.scalar(select(Project.state).where(Project.id == project_id)) == "draft_review"
    tasks = database_session.scalars(select(Task).where(Task.run_id == UUID(approval["run_id"])).order_by(Task.created_at)).all()
    assert [task.task_type for task in tasks] == ["outline", "production", "review"]
    assert tasks[2].dependencies == [str(tasks[1].id)]
    review_usage = database_session.scalar(select(UsageCall).where(UsageCall.task_id == tasks[2].id))
    assert review_usage is not None and review_usage.purpose == "review" and review_usage.input_tokens == 8 and review_usage.output_tokens == 9


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
        outline_lease = client.post(
            "/private/worker/claim",
            json={"worker_id": "rollback-worker", "lease_seconds": 60},
            headers={"X-Ebook-Worker-Token": "test-worker-token"},
        ).json()
        assert client.post(
            "/private/worker/task-result",
            headers={"X-Ebook-Worker-Token": "test-worker-token"},
            json={
                "job_id": outline_lease["job_id"], "worker_id": "rollback-worker", "generation": outline_lease["generation"],
                "result": "## Opening\nA bounded outline.", "provider": "test-provider", "model": "test-model",
                "call_id": str(uuid4()), "usage": {"input_tokens": 2, "output_tokens": 3},
            },
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
        outline_usage = database_session.scalar(select(UsageCall).where(UsageCall.project_id == project_id))
        assert outline_usage is not None and outline_usage.purpose == "outline"
        assert database_session.scalar(
            select(Job.state).join(Task).join(ProductionRun).where(
                ProductionRun.project_id == project_id, Task.task_type == "production"
            )
        ) == "running"
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
    usage_calls = database_session.scalars(select(UsageCall).where(UsageCall.project_id == project_id)).all()
    assert len(usage_calls) == 2
    assert {call.purpose for call in usage_calls} == {"outline", "production"}
    assert database_session.scalar(
        select(Job.state).join(Task).join(ProductionRun).where(
            ProductionRun.project_id == project_id, Task.task_type == "production"
        )
    ) == "succeeded"


def test_production_result_rejects_whitespace_content(database_session: Session) -> None:
    assert DATABASE_URL is not None
    with TestClient(create_app(Settings(database_url=DATABASE_URL, worker_token="test-worker-token", owner_token="test-owner-token"),), headers={"Authorization": "Bearer test-owner-token"}, raise_server_exceptions=False) as client:
        project_response = client.post("/projects", json={"title": "Whitespace", "profile": "nonfiction", "language": "en"})
        project_id = UUID(project_response.json()["project_id"])
        database_session.info["cleanup_project_ids"].add(project_id)
        brief_response = client.post(f"/projects/{project_id}/briefs", json={"structured_brief": {"promise_or_premise": "whitespace"}})
        brief = brief_response.json()
        client.post(f"/projects/{project_id}/briefs/{brief['brief_id']}/approve", json={"expected_content_hash": brief["content_hash"], "budget": {"max_turns": 4}})
        outline_lease = client.post("/private/worker/claim", json={"worker_id": "whitespace-worker", "lease_seconds": 60}, headers={"X-Ebook-Worker-Token": "test-worker-token"}).json()
        assert client.post(
            "/private/worker/task-result",
            headers={"X-Ebook-Worker-Token": "test-worker-token"},
            json={
                "job_id": outline_lease["job_id"], "worker_id": "whitespace-worker", "generation": outline_lease["generation"],
                "result": "## Opening\nA bounded outline.", "provider": "test", "model": "test",
                "call_id": str(uuid4()), "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        ).status_code == 200
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
    outline_lease = claim_job(database_session, worker_id="outline-worker", lease_seconds=60)
    assert outline_lease is not None
    complete_job(
        database_session,
        job_id=outline_lease.job_id,
        worker_id="outline-worker",
        generation=outline_lease.generation,
        result_refs={"result": "## Opening\nA bounded outline."},
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
    assert event_kinds == ["run.approved", "job.claimed", "job.completed", "job.claimed", "job.checkpointed", "job.completed"]


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
