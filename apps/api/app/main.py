"""FastAPI application entry point and installation health endpoints."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from app.database import Database
from app.events import replay_events
from app.jobs import (
    ApprovalConflict,
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
from app.settings import Settings


class HealthResponse(BaseModel):
    """Stable process-health response."""

    service: str
    status: str
    version: str


class DependencyStatus(BaseModel):
    """Sanitized status for one external dependency."""

    status: str
    reason: str | None = None


class ReadinessResponse(BaseModel):
    """Stable readiness response used by supervisors and dashboards."""

    service: str
    status: str
    dependencies: dict[str, DependencyStatus]


class ApprovalRequest(BaseModel):
    """Hash-bound approval request."""

    expected_content_hash: str = Field(min_length=64, max_length=64)
    budget: dict[str, Any] = Field(default_factory=dict)


class ApprovalResponse(BaseModel):
    """Durable identifiers created by approval."""

    run_id: UUID
    task_id: UUID
    job_id: UUID


class WorkerClaimRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=128)
    lease_seconds: int = Field(default=60, ge=-3600, le=3600)


class WorkerLeaseResponse(BaseModel):
    job_id: UUID
    task_id: UUID
    run_id: UUID
    attempt_id: UUID
    generation: int
    cancellation_epoch: int
    lease_until: datetime


class WorkerMutationRequest(BaseModel):
    job_id: UUID
    worker_id: str = Field(min_length=1, max_length=128)
    generation: int = Field(ge=1)


class HeartbeatRequest(WorkerMutationRequest):
    lease_seconds: int = Field(default=60, ge=1, le=3600)


class CheckpointRequest(WorkerMutationRequest):
    checkpoint: dict[str, Any] = Field(default_factory=dict)


class CompleteRequest(WorkerMutationRequest):
    result_refs: dict[str, Any] = Field(default_factory=dict)


class FailRequest(WorkerMutationRequest):
    error_class: str = Field(min_length=1, max_length=128)
    retryable: bool = False
    retry_after_seconds: float | None = Field(default=None, ge=0, le=86400)


class RunCancelRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=512)


def _require_worker_token(settings: Settings, supplied: str) -> None:
    """Reject private callbacks unless a local operator configured the token."""

    import hmac

    if not settings.worker_token:
        raise HTTPException(status_code=503, detail="worker callbacks are not configured")
    if not hmac.compare_digest(supplied, settings.worker_token):
        raise HTTPException(status_code=401, detail="unauthorized worker callback")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the API application with explicit settings for tests and workers."""

    resolved_settings = settings or Settings()
    database = Database(resolved_settings.database_url)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.database = database
        yield
        database.close()

    application = FastAPI(
        title="Ebook Factory API",
        version=resolved_settings.version,
        lifespan=lifespan,
    )
    application.state.database = database
    application.state.settings = resolved_settings

    @application.get("/health", response_model=HealthResponse, tags=["operations"])
    def health() -> HealthResponse:
        """Return process health without requiring external dependencies."""

        return HealthResponse(service=resolved_settings.service_name, status="ok", version=resolved_settings.version)

    @application.get("/ready", response_model=ReadinessResponse, tags=["operations"])
    def ready(request: Request) -> Any:
        """Return dependency readiness with sanitized database status."""

        result = request.app.state.database.check()
        payload = {
            "service": resolved_settings.service_name,
            "status": "ok" if result.status == "ok" else "not_ready",
            "dependencies": {"database": {"status": result.status}},
        }
        if result.reason:
            payload["dependencies"]["database"]["reason"] = result.reason
        status_code = 200 if result.status == "ok" else 503
        return JSONResponse(status_code=status_code, content=payload)

    @application.post("/projects/{project_id}/briefs/{brief_id}/approve", response_model=ApprovalResponse)
    def approve(project_id: UUID, brief_id: UUID, payload: ApprovalRequest) -> ApprovalResponse:
        session = database.session()
        try:
            result = approve_brief_and_enqueue(
                session,
                project_id=project_id,
                brief_id=brief_id,
                expected_content_hash=payload.expected_content_hash,
                budget=payload.budget,
            )
            return ApprovalResponse(run_id=result.run_id, task_id=result.task_id, job_id=result.job_id)
        except (ApprovalConflict, SQLAlchemyError) as exc:
            session.rollback()
            if isinstance(exc, ApprovalConflict):
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            raise HTTPException(status_code=503, detail="database operation unavailable") from exc
        finally:
            session.close()

    @application.get("/projects/{project_id}/events")
    def events(project_id: UUID, after: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        session = database.session()
        try:
            return [
                {
                    "id": event.id,
                    "version": 1,
                    "timestamp": event.created_at,
                    "project_id": event.project_id,
                    "run_id": event.run_id,
                    "task_id": event.task_id,
                    "kind": event.kind,
                    "payload": event.data,
                }
                for event in replay_events(session, project_id=project_id, after_id=after, limit=limit)
            ]
        finally:
            session.close()

    @application.post("/private/worker/claim", response_model=WorkerLeaseResponse | None, tags=["private-worker"])
    def worker_claim(
        payload: WorkerClaimRequest,
        x_ebook_worker_token: str = Header(default="", alias="X-Ebook-Worker-Token"),
    ) -> WorkerLeaseResponse | None:
        _require_worker_token(resolved_settings, x_ebook_worker_token)
        session = database.session()
        try:
            lease = claim_job(session, worker_id=payload.worker_id, lease_seconds=payload.lease_seconds)
            if lease is None:
                return None
            return WorkerLeaseResponse(
                job_id=lease.job_id,
                task_id=lease.task_id,
                run_id=lease.run_id,
                attempt_id=lease.attempt_id,
                generation=lease.generation,
                cancellation_epoch=lease.cancellation_epoch,
                lease_until=lease.lease_until,
            )
        finally:
            session.close()

    @application.post("/private/worker/heartbeat", tags=["private-worker"])
    def worker_heartbeat(
        payload: HeartbeatRequest,
        x_ebook_worker_token: str = Header(default="", alias="X-Ebook-Worker-Token"),
    ) -> dict[str, datetime]:
        _require_worker_token(resolved_settings, x_ebook_worker_token)
        session = database.session()
        try:
            result = heartbeat_job(
                session,
                job_id=payload.job_id,
                worker_id=payload.worker_id,
                generation=payload.generation,
                lease_seconds=payload.lease_seconds,
            )
            return {"lease_until": result.lease_until}
        except (StaleLease, CancellationRejected) as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        finally:
            session.close()

    @application.post("/private/worker/checkpoint", status_code=204, tags=["private-worker"])
    def worker_checkpoint(
        payload: CheckpointRequest,
        x_ebook_worker_token: str = Header(default="", alias="X-Ebook-Worker-Token"),
    ) -> None:
        _require_worker_token(resolved_settings, x_ebook_worker_token)
        session = database.session()
        try:
            checkpoint_job(
                session,
                job_id=payload.job_id,
                worker_id=payload.worker_id,
                generation=payload.generation,
                checkpoint=payload.checkpoint,
            )
        except (StaleLease, CancellationRejected) as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        finally:
            session.close()

    @application.post("/private/worker/complete", status_code=204, tags=["private-worker"])
    def worker_complete(
        payload: CompleteRequest,
        x_ebook_worker_token: str = Header(default="", alias="X-Ebook-Worker-Token"),
    ) -> None:
        _require_worker_token(resolved_settings, x_ebook_worker_token)
        session = database.session()
        try:
            complete_job(
                session,
                job_id=payload.job_id,
                worker_id=payload.worker_id,
                generation=payload.generation,
                result_refs=payload.result_refs,
            )
        except (StaleLease, CancellationRejected) as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        finally:
            session.close()

    @application.post("/private/worker/fail", status_code=204, tags=["private-worker"])
    def worker_fail(
        payload: FailRequest,
        x_ebook_worker_token: str = Header(default="", alias="X-Ebook-Worker-Token"),
    ) -> None:
        _require_worker_token(resolved_settings, x_ebook_worker_token)
        session = database.session()
        try:
            fail_job(
                session,
                job_id=payload.job_id,
                worker_id=payload.worker_id,
                generation=payload.generation,
                error_class=payload.error_class,
                retryable=payload.retryable,
                retry_after=(
                    timedelta(seconds=payload.retry_after_seconds)
                    if payload.retry_after_seconds is not None
                    else None
                ),
            )
        except (StaleLease, CancellationRejected) as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        finally:
            session.close()

    @application.post("/private/runs/{run_id}/cancel", tags=["private-worker"])
    def worker_cancel(
        run_id: UUID,
        payload: RunCancelRequest,
        x_ebook_worker_token: str = Header(default="", alias="X-Ebook-Worker-Token"),
    ) -> dict[str, int]:
        _require_worker_token(resolved_settings, x_ebook_worker_token)
        session = database.session()
        try:
            return {"cancellation_epoch": cancel_run(session, run_id=run_id, reason=payload.reason)}
        finally:
            session.close()

    return application


app = create_app()
