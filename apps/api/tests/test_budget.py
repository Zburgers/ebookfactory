from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.budget import enforce_budget
from app.jobs import claim_job
from app.models import Base, BriefRevision, Job, Project, ProductionRun, Task, Event


def test_budget_exhaustion_blocks_the_fenced_job_before_publication(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'budget.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        project = Project(title="Budget test", profile="fiction", language="en")
        session.add(project)
        session.flush()
        brief = BriefRevision(project_id=project.id, revision=1, structured_brief={"promise_or_premise": "test"}, content_hash="a" * 64)
        session.add(brief)
        session.flush()
        run = ProductionRun(project_id=project.id, approved_brief_id=brief.id, budget={"max_turns": 0}, state="queued")
        session.add(run)
        session.flush()
        task = Task(run_id=run.id, task_type="production", input_revision_ids=[str(brief.id)], status="queued")
        session.add(task)
        session.flush()
        job = Job(
            task_id=task.id,
            job_type="production.start",
            payload={"cancellation_epoch": run.cancellation_epoch},
            dedupe_key=str(uuid4()),
            state="queued",
        )
        session.add(job)
        session.commit()
        lease = claim_job(session, worker_id="budget-worker")
        assert lease is not None

        allowed, reason = enforce_budget(
            session,
            job_id=lease.job_id,
            worker_id="budget-worker",
            generation=lease.generation,
            input_tokens=10,
            output_tokens=10,
        )

        assert allowed is False
        assert reason == "max_turns_exceeded"
        assert session.get(Job, lease.job_id).state == "blocked"
        assert session.get(ProductionRun, run.id).state == "blocked"
        assert session.scalar(select(Event.kind).where(Event.run_id == run.id).order_by(Event.id.desc())) == "job.blocked"
        session.commit()
        assert claim_job(session, worker_id="after-budget-block") is None
