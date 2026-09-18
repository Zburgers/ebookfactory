"""FastAPI application entry point and installation health endpoints."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select

from app.database import Database
from app.conversations import append_message, create_project
from app.documents import create_brief_revision, create_section, save_section_revision
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
)
from app.models import Artifact, BriefRevision, Job, Message, ProductionRun, Project, ProviderSetting, Task
from app.providers import save_provider_setting
from app.production import accept_production_output
from app.artifacts import write_artifact
from app.tools import InvalidCapability, issue_capability, verify_capability
from app.usage import finalize_usage_call, record_usage_call, usage_totals
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


class ProjectCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    profile: str = Field(min_length=1, max_length=32)
    language: str = Field(min_length=2, max_length=32)


class ProjectResponse(BaseModel):
    project_id: UUID
    conversation_id: UUID
    title: str
    profile: str
    language: str
    state: str


class BriefCreateRequest(BaseModel):
    structured_brief: dict[str, Any]


class BriefResponse(BaseModel):
    brief_id: UUID
    content_hash: str


class MessageCreateRequest(BaseModel):
    conversation_id: UUID
    channel: str = Field(default="dashboard", min_length=1, max_length=32)
    external_dedupe_id: str | None = Field(default=None, max_length=240)
    content: str = Field(min_length=1)


class MessageResponse(BaseModel):
    message_id: UUID
    sequence: int
    duplicate: bool


class MessageView(BaseModel):
    message_id: UUID
    sequence: int
    channel: str
    role: str
    content: str
    turn_state: str
    created_at: datetime


class ProviderSettingRequest(BaseModel):
    scope: str = Field(default="app", min_length=1, max_length=32)
    endpoint: str | None = Field(default=None, max_length=2048)
    protocol: str | None = Field(default=None, max_length=64)
    credential_ref: str | None = Field(default=None, max_length=255)
    orchestration_model: str | None = Field(default=None, max_length=128)
    drafting_model: str | None = Field(default=None, max_length=128)
    review_model: str | None = Field(default=None, max_length=128)


class ProviderSettingResponse(BaseModel):
    setting_id: UUID
    provider: str
    scope: str
    endpoint: str | None
    protocol: str | None
    orchestration_model: str | None
    drafting_model: str | None
    review_model: str | None
    credential_configured: bool


class UsageCallRequest(BaseModel):
    call_id: UUID
    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=128)
    purpose: str = Field(min_length=1, max_length=64)
    outcome: str = Field(min_length=1, max_length=32)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    provider_request_id: str | None = Field(default=None, max_length=255)


class UsageFinalizeRequest(BaseModel):
    outcome: str | None = Field(default=None, max_length=32)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)


class SectionCreateRequest(BaseModel):
    order_no: int = Field(ge=1)
    heading: str = Field(min_length=1, max_length=512)


class SectionResponse(BaseModel):
    section_id: UUID


class SectionRevisionRequest(BaseModel):
    content: str = Field(min_length=1)
    summary: str = ""
    expected_parent_revision_id: UUID | None = None
    source_refs: list[str] = Field(default_factory=list)
    knowledge_refs: list[str] = Field(default_factory=list)


class SectionRevisionResponse(BaseModel):
    section_id: UUID
    revision_id: UUID
    revision: int
    content_hash: str


class CapabilityRequest(BaseModel):
    job_id: UUID
    worker_id: str = Field(min_length=1, max_length=128)
    generation: int = Field(ge=1)
    tool: str = Field(min_length=1, max_length=64)


class CapabilityResponse(BaseModel):
    capability: str
    expires_in_seconds: int


class ProductionOutputRequest(BaseModel):
    job_id: UUID
    worker_id: str = Field(min_length=1, max_length=128)
    generation: int = Field(ge=1)
    content: str = Field(min_length=1)
    provider: str | None = Field(default=None, min_length=1, max_length=64)
    model: str | None = Field(default=None, min_length=1, max_length=128)


class ProductionOutputResponse(BaseModel):
    run_id: UUID
    task_id: UUID
    revision_id: UUID
    artifact_id: UUID
    content_hash: str
    duplicate: bool


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

    @application.post("/projects", response_model=ProjectResponse, status_code=201)
    def create_project_route(payload: ProjectCreateRequest) -> ProjectResponse:
        session = database.session()
        try:
            result = create_project(
                session,
                title=payload.title,
                profile=payload.profile,
                language=payload.language,
            )
            project = session.get(Project, result.project_id)
            if project is None:
                raise HTTPException(status_code=503, detail="project creation unavailable")
            return ProjectResponse(
                project_id=project.id,
                conversation_id=result.conversation_id,
                title=project.title,
                profile=project.profile,
                language=project.language,
                state=project.state,
            )
        finally:
            session.close()

    @application.get("/projects/{project_id}", response_model=ProjectResponse)
    def get_project(project_id: UUID) -> ProjectResponse:
        session = database.session()
        try:
            project = session.get(Project, project_id)
            if project is None or project.conversation_id is None:
                raise HTTPException(status_code=404, detail="project not found")
            return ProjectResponse(
                project_id=project.id,
                conversation_id=project.conversation_id,
                title=project.title,
                profile=project.profile,
                language=project.language,
                state=project.state,
            )
        finally:
            session.close()

    @application.get("/projects", response_model=list[ProjectResponse])
    def list_projects() -> list[ProjectResponse]:
        session = database.session()
        try:
            projects = session.scalars(select(Project).order_by(Project.updated_at.desc())).all()
            return [
                ProjectResponse(
                    project_id=project.id,
                    conversation_id=project.conversation_id,
                    title=project.title,
                    profile=project.profile,
                    language=project.language,
                    state=project.state,
                )
                for project in projects
                if project.conversation_id is not None
            ]
        finally:
            session.close()

    @application.post("/projects/{project_id}/messages", response_model=MessageResponse, status_code=201)
    def post_message(project_id: UUID, payload: MessageCreateRequest) -> MessageResponse:
        session = database.session()
        try:
            result = append_message(
                session,
                project_id=project_id,
                conversation_id=payload.conversation_id,
                channel=payload.channel,
                external_dedupe_id=payload.external_dedupe_id,
                role="user",
                content=payload.content,
            )
            return MessageResponse(
                message_id=result.message_id,
                sequence=result.sequence,
                duplicate=result.duplicate,
            )
        except ValueError as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        finally:
            session.close()

    @application.get("/projects/{project_id}/messages", response_model=list[MessageView])
    def list_messages(project_id: UUID, limit: int = 100) -> list[MessageView]:
        session = database.session()
        try:
            messages = session.scalars(
                select(Message)
                .where(Message.project_id == project_id)
                .order_by(Message.sequence)
                .limit(max(1, min(limit, 500)))
            ).all()
            return [
                MessageView(
                    message_id=message.id,
                    sequence=message.sequence,
                    channel=message.channel,
                    role=message.role,
                    content=message.content,
                    turn_state=message.turn_state,
                    created_at=message.created_at,
                )
                for message in messages
            ]
        finally:
            session.close()

    @application.get("/providers", response_model=list[ProviderSettingResponse])
    def list_providers() -> list[ProviderSettingResponse]:
        session = database.session()
        try:
            settings = session.scalars(select(ProviderSetting).order_by(ProviderSetting.provider)).all()
            return [
                ProviderSettingResponse(
                    setting_id=setting.id,
                    provider=setting.provider,
                    scope=setting.scope,
                    endpoint=setting.config.get("endpoint"),
                    protocol=setting.config.get("protocol"),
                    orchestration_model=setting.orchestration_model,
                    drafting_model=setting.drafting_model,
                    review_model=setting.review_model,
                    credential_configured=bool(setting.credential_ref),
                )
                for setting in settings
            ]
        finally:
            session.close()

    @application.post("/usage/calls", response_model=dict[str, Any], status_code=201)
    def record_usage(payload: UsageCallRequest) -> dict[str, Any]:
        session = database.session()
        try:
            result = record_usage_call(session, **payload.model_dump())
            return result.__dict__
        finally:
            session.close()

    @application.post("/usage/calls/{call_id}/finalize", response_model=dict[str, Any])
    def finalize_usage(call_id: UUID, payload: UsageFinalizeRequest) -> dict[str, Any]:
        session = database.session()
        try:
            result = finalize_usage_call(session, call_id=call_id, **payload.model_dump())
            return result.__dict__
        except ValueError as exc:
            session.rollback()
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        finally:
            session.close()

    @application.get("/usage", response_model=dict[str, Any])
    def get_usage(project_id: UUID | None = None) -> dict[str, Any]:
        session = database.session()
        try:
            return usage_totals(session, project_id=project_id)
        finally:
            session.close()

    @application.post("/projects/{project_id}/sections", response_model=SectionResponse, status_code=201)
    def create_section_route(project_id: UUID, payload: SectionCreateRequest) -> SectionResponse:
        session = database.session()
        try:
            section_id = create_section(
                session,
                project_id=project_id,
                order_no=payload.order_no,
                heading=payload.heading,
            )
            return SectionResponse(section_id=section_id)
        finally:
            session.close()

    @application.post("/sections/{section_id}/revisions", response_model=SectionRevisionResponse, status_code=201)
    def save_section_route(section_id: UUID, payload: SectionRevisionRequest) -> SectionRevisionResponse:
        session = database.session()
        try:
            result = save_section_revision(
                session,
                section_id=section_id,
                content=payload.content,
                summary=payload.summary,
                expected_parent_revision_id=payload.expected_parent_revision_id,
                source_refs=payload.source_refs,
                knowledge_refs=payload.knowledge_refs,
            )
            return SectionRevisionResponse(**result.__dict__)
        except ValueError as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        finally:
            session.close()

    @application.put("/providers/{provider}", response_model=ProviderSettingResponse)
    def put_provider(provider: str, payload: ProviderSettingRequest) -> ProviderSettingResponse:
        session = database.session()
        try:
            result = save_provider_setting(
                session,
                provider=provider,
                scope=payload.scope,
                endpoint=payload.endpoint,
                protocol=payload.protocol,
                credential_ref=payload.credential_ref,
                orchestration_model=payload.orchestration_model,
                drafting_model=payload.drafting_model,
                review_model=payload.review_model,
            )
            return ProviderSettingResponse(**result.__dict__)
        except ValueError as exc:
            session.rollback()
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        finally:
            session.close()

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

    @application.post("/projects/{project_id}/briefs", response_model=BriefResponse, status_code=201)
    def create_brief_route(project_id: UUID, payload: BriefCreateRequest) -> BriefResponse:
        session = database.session()
        try:
            result = create_brief_revision(
                session,
                project_id=project_id,
                structured_brief=payload.structured_brief,
            )
            return BriefResponse(brief_id=result.brief_id, content_hash=result.content_hash)
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

    @application.get("/projects/{project_id}/events/stream")
    def events_stream(project_id: UUID, after: int = 0, limit: int = 100) -> StreamingResponse:
        """Replay a bounded event cursor as SSE, then close for safe reconnect."""

        session = database.session()
        try:
            replay = replay_events(session, project_id=project_id, after_id=after, limit=limit)
            envelopes = [
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
                for event in replay
            ]
        finally:
            session.close()

        def stream():
            for envelope in envelopes:
                yield f"id: {envelope['id']}\nevent: {envelope['kind']}\ndata: {json.dumps(envelope, default=str)}\n\n"

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

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

    @application.post("/private/worker/capability", response_model=CapabilityResponse, tags=["private-worker"])
    def worker_capability(
        payload: CapabilityRequest,
        x_ebook_worker_token: str = Header(default="", alias="X-Ebook-Worker-Token"),
    ) -> CapabilityResponse:
        _require_worker_token(resolved_settings, x_ebook_worker_token)
        session = database.session()
        try:
            row = session.execute(
                select(Job, Task, ProductionRun)
                .join(Task, Task.id == Job.task_id)
                .join(ProductionRun, ProductionRun.id == Task.run_id)
                .where(
                    Job.id == payload.job_id,
                    Job.lease_owner == payload.worker_id,
                    Job.fencing_generation == payload.generation,
                    Job.state == "running",
                )
            ).first()
            if row is None:
                raise HTTPException(status_code=409, detail="worker lease is not current")
            _, _, run = row
            if run.state == "cancelled":
                raise HTTPException(status_code=409, detail="run is cancelled")
            capability = issue_capability(
                resolved_settings.worker_token or "",
                project_id=run.project_id,
                job_id=payload.job_id,
                generation=payload.generation,
                tool=payload.tool,
            )
            return CapabilityResponse(capability=capability, expires_in_seconds=300)
        finally:
            session.close()

    @application.get("/private/worker/jobs/{job_id}/context", tags=["private-worker"])
    def worker_job_context(
        job_id: UUID,
        x_ebook_worker_token: str = Header(default="", alias="X-Ebook-Worker-Token"),
        x_worker_id: str = Header(alias="X-Worker-ID"),
        x_generation: int = Header(alias="X-Generation"),
    ) -> dict[str, Any]:
        _require_worker_token(resolved_settings, x_ebook_worker_token)
        session = database.session()
        try:
            row = session.execute(
                select(Job, Task, ProductionRun, Project, BriefRevision)
                .join(Task, Task.id == Job.task_id)
                .join(ProductionRun, ProductionRun.id == Task.run_id)
                .join(Project, Project.id == ProductionRun.project_id)
                .join(BriefRevision, BriefRevision.id == ProductionRun.approved_brief_id)
                .where(
                    Job.id == job_id,
                    Job.lease_owner == x_worker_id,
                    Job.fencing_generation == x_generation,
                    Job.state == "running",
                )
            ).first()
            if row is None:
                raise HTTPException(status_code=409, detail="worker lease is not current")
            job, task, run, project, brief = row
            if run.state == "cancelled":
                raise HTTPException(status_code=409, detail="run is cancelled")
            return {
                "project_id": project.id,
                "run_id": run.id,
                "task_id": task.id,
                "job_id": job.id,
                "cancellation_epoch": run.cancellation_epoch,
                "profile": project.profile,
                "language": project.language,
                "brief": brief.structured_brief,
                "budget": run.budget,
            }
        finally:
            session.close()

    @application.post("/private/worker/production-result", response_model=ProductionOutputResponse, tags=["private-worker"])
    def worker_production_result(
        payload: ProductionOutputRequest,
        x_ebook_worker_token: str = Header(default="", alias="X-Ebook-Worker-Token"),
    ) -> ProductionOutputResponse:
        _require_worker_token(resolved_settings, x_ebook_worker_token)
        session = database.session()
        try:
            output = accept_production_output(
                session,
                job_id=payload.job_id,
                worker_id=payload.worker_id,
                generation=payload.generation,
                content=payload.content,
                provider=payload.provider,
                model=payload.model,
            )
        except (StaleLease, CancellationRejected, ValueError) as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        finally:
            session.close()

        artifact_session = database.session()
        try:
            artifact = write_artifact(
                artifact_session,
                root=resolved_settings.artifact_root,
                relative_path=f"{output.run_id}/book.md",
                content=payload.content.encode(),
                mime_type="text/markdown",
                run_id=output.run_id,
                revision_id=output.revision_id,
            )
        except FileExistsError:
            artifact = artifact_session.scalar(
                select(Artifact).where(Artifact.relative_path == f"{output.run_id}/book.md")
            )
            if artifact is None:
                raise HTTPException(status_code=503, detail="artifact registration unavailable")
        finally:
            artifact_session.close()

        completion_session = database.session()
        try:
            complete_job(
                completion_session,
                job_id=payload.job_id,
                worker_id=payload.worker_id,
                generation=payload.generation,
                result_refs={"revision_id": str(output.revision_id), "artifact_id": str(artifact.id)},
            )
        except (StaleLease, CancellationRejected) as exc:
            completion_session.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        finally:
            completion_session.close()
        return ProductionOutputResponse(
            run_id=output.run_id,
            task_id=output.task_id,
            revision_id=output.revision_id,
            artifact_id=artifact.id,
            content_hash=output.content_hash,
            duplicate=output.duplicate,
        )

    @application.post("/private/tools/{tool}", tags=["private-worker"])
    def scoped_tool(
        tool: str,
        payload: dict[str, Any],
        x_tool_capability: str = Header(default="", alias="X-Tool-Capability"),
        x_project_id: UUID = Header(alias="X-Project-ID"),
        x_job_id: UUID = Header(alias="X-Job-ID"),
        x_generation: int = Header(alias="X-Generation"),
    ) -> dict[str, Any]:
        try:
            verify_capability(
                x_tool_capability,
                resolved_settings.worker_token or "",
                project_id=x_project_id,
                job_id=x_job_id,
                generation=x_generation,
                tool=tool,
            )
        except InvalidCapability as exc:
            raise HTTPException(status_code=403, detail="invalid tool capability") from exc
        if tool != "get_job_status":
            raise HTTPException(status_code=404, detail="tool is not enabled")
        session = database.session()
        try:
            row = session.execute(
                select(Job, Task, ProductionRun)
                .join(Task, Task.id == Job.task_id)
                .join(ProductionRun, ProductionRun.id == Task.run_id)
                .where(Job.id == x_job_id, ProductionRun.project_id == x_project_id)
            ).first()
            if row is None:
                raise HTTPException(status_code=404, detail="job not found")
            job, task, run = row
            return {
                "job_id": job.id,
                "task_id": task.id,
                "run_id": run.id,
                "job_state": job.state,
                "task_status": task.status,
                "run_state": run.state,
                "cancellation_epoch": run.cancellation_epoch,
            }
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

    web_root = Path(__file__).resolve().parents[2] / "web"
    if (web_root / "index.html").exists():
        application.mount("/", StaticFiles(directory=web_root, html=True), name="dashboard")
    return application


app = create_app()
