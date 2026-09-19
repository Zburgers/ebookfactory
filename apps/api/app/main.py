"""FastAPI application entry point and installation health endpoints."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from decimal import Decimal
import json
import hashlib
import base64
import fcntl
import threading
import time
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import aliased

from app.database import Database
from app.conversations import append_message, create_project
from app.orchestrator import append_delta, claim_turn, complete_turn, enqueue_turn, fail_turn, heartbeat_turn, locked_turn
from app.documents import create_brief_revision, create_section, save_section_revision
from app.exports import MIME_TYPES, PACKAGE_FILES, export_book, verify_export_members
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
    complete_task_result,
    fail_job,
    heartbeat_job,
)
from app.models import (
    Artifact,
    Attempt,
    BriefRevision,
    Job,
    Message,
    OrchestratorTurn,
    ProductionRun,
    Project,
    ProviderSetting,
    ReviewFinding,
    Section,
    SectionRevision,
    Task,
    TelegramLink,
    TelegramState,
    utc_now,
)
from app.providers import connection_test, save_provider_setting
from app import model_catalog
from app import codex_quota
from app.production import accept_production_output, assemble_section_revisions, expand_outline_sections
from app.reviews import record_finding
from app.artifacts import reconcile_pending_artifacts, safe_artifact_path, write_artifact
from app.budget import enforce_budget
from app.tools import InvalidCapability, issue_capability, verify_capability
from app.usage import finalize_usage_call, list_usage_calls, record_usage_call, usage_totals
from app.quota import list_quota_snapshots, record_quota_snapshot
from app.settings import Settings
from app.telegram import config_from_values, link_chat, process_update


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


class LiveQuotaWindow(BaseModel):
    account_index: int = Field(ge=1)
    window_seconds: int
    used: int
    remaining: int
    reset: str


class LiveQuotaResponse(BaseModel):
    fetched_at: datetime
    source: str
    windows: list[LiveQuotaWindow]


class TelegramStatusResponse(BaseModel):
    configured: bool
    token_configured: bool
    allowed_chat_count: int
    allowed_sender_count: int
    linked_chat_count: int
    next_update_id: int


class TelegramLinkRequest(BaseModel):
    chat_id: int


class OwnerLoginRequest(BaseModel):
    token: str = Field(min_length=1, max_length=4096)


class OwnerAuthResponse(BaseModel):
    authenticated: bool


class TelegramUpdateResponse(BaseModel):
    accepted: bool
    duplicate: bool
    reason: str | None = None
    message_id: UUID | None = None


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
    lease_seconds: int = Field(default=60, ge=1, le=3600)


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


class WorkerOutlineContext(BaseModel):
    task_id: UUID
    result: str


class WorkerReviewSection(BaseModel):
    section_id: UUID
    revision_id: UUID
    heading: str
    content: str


class WorkerSectionContext(BaseModel):
    section_id: UUID
    heading: str
    outline: str


# Keep review material well below the worker's 64 KiB context-response limit.
# The remaining 16 KiB covers the response envelope, brief/budget, and JSON
# escaping overhead; headings and bodies both consume this budget.
WORKER_CONTEXT_LIMIT_BYTES = 64 * 1024
REVIEW_SECTION_BUDGET_BYTES = 48 * 1024


class WorkerJobContextResponse(BaseModel):
    project_id: UUID
    run_id: UUID
    task_id: UUID
    job_id: UUID
    task_type: str
    cancellation_epoch: int
    profile: str
    language: str
    brief: dict[str, Any]
    budget: dict[str, Any]
    outline: WorkerOutlineContext | None = None
    section: WorkerSectionContext | None = None
    assembly: bool = False
    review_sections: list[WorkerReviewSection] = Field(default_factory=list)


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

    @model_validator(mode="after")
    def validate_target_ranges(self) -> "BriefCreateRequest":
        pages = self.structured_brief.get("target_pages")
        words = self.structured_brief.get("target_length")
        if pages and pages.get("minimum", 0) > pages.get("maximum", 0):
            raise ValueError("minimum must not exceed maximum")
        if words and words.get("minimum_words", 0) > words.get("maximum_words", 0):
            raise ValueError("minimum must not exceed maximum")
        return self


class BriefResponse(BaseModel):
    brief_id: UUID
    content_hash: str


class MessageCreateRequest(BaseModel):
    conversation_id: UUID
    channel: str = Field(default="dashboard", min_length=1, max_length=32)
    external_dedupe_id: str | None = Field(default=None, max_length=240)
    content: str = Field(min_length=1, max_length=200_000)


class MessageResponse(BaseModel):
    message_id: UUID
    sequence: int
    duplicate: bool
    turn_id: UUID | None = None
    queued: bool = False


class MessageView(BaseModel):
    message_id: UUID
    sequence: int
    channel: str
    role: str
    content: str
    turn_state: str
    created_at: datetime


class OrchestratorClaimRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=128)
    lease_seconds: int = Field(default=60, ge=1, le=3600)


class OrchestratorLeaseResponse(BaseModel):
    turn_id: UUID
    worker_id: str
    generation: int
    lease_until: datetime


class OrchestratorResultRequest(BaseModel):
    turn_id: UUID
    worker_id: str = Field(min_length=1, max_length=128)
    generation: int = Field(ge=1)
    content: str = Field(min_length=1, max_length=1_000_000)
    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=128)
    call_id: UUID
    usage: dict[str, int | None] | None = None


class OrchestratorDeltaRequest(BaseModel):
    turn_id: UUID
    worker_id: str = Field(min_length=1, max_length=128)
    generation: int = Field(ge=1)
    delta: str = Field(min_length=1, max_length=8192)


class OrchestratorHeartbeatRequest(BaseModel):
    turn_id: UUID
    worker_id: str = Field(min_length=1, max_length=128)
    generation: int = Field(ge=1)
    lease_seconds: int = Field(default=60, ge=1, le=3600)


class OrchestratorFailureRequest(BaseModel):
    turn_id: UUID
    worker_id: str = Field(min_length=1, max_length=128)
    generation: int = Field(ge=1)
    error: str = Field(min_length=1, max_length=2000)


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


class ProviderMetadataResponse(BaseModel):
    provider: str
    scope: str
    protocol: str | None
    orchestration_model: str | None
    drafting_model: str | None
    review_model: str | None
    credential_configured: bool


class ProviderConnectionTestResponse(BaseModel):
    provider: str
    protocol: str
    model: str | None
    outcome: str
    http_status: int | None
    response_id: str | None
    usage: dict[str, Any] | None
    error: str | None


class ModelCatalogEntry(BaseModel):
    provider: str
    model: str
    qualified_model: str
    context: str
    max_output: str
    thinking: bool
    images: bool


class ProviderCatalogResponse(BaseModel):
    fetched_at: datetime
    source: str
    models: list[ModelCatalogEntry]


class UsageCallRequest(BaseModel):
    call_id: UUID
    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=128)
    purpose: str = Field(min_length=1, max_length=64)
    outcome: str = Field(min_length=1, max_length=32)
    project_id: UUID | None = None
    run_id: UUID | None = None
    task_id: UUID | None = None
    attempt_id: UUID | None = None
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    provider_request_id: str | None = Field(default=None, max_length=255)


class UsageFinalizeRequest(BaseModel):
    outcome: str | None = Field(default=None, max_length=32)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)


class QuotaSnapshotRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=64)
    account_alias: str = Field(min_length=1, max_length=128)
    bucket: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=255)
    observed_at: datetime
    stale_after: datetime
    used: Decimal | None = None
    remaining: Decimal | None = None
    units: str | None = Field(default=None, max_length=64)
    window_seconds: int | None = Field(default=None, ge=0)
    resets_at: datetime | None = None
    plan_label: str | None = Field(default=None, max_length=128)
    capability_state: str = Field(min_length=1, max_length=32)
    error: str | None = None


class SectionCreateRequest(BaseModel):
    order_no: int = Field(ge=1)
    heading: str = Field(min_length=1, max_length=512)


class SectionResponse(BaseModel):
    section_id: UUID


class SectionView(BaseModel):
    section_id: UUID
    order_no: int
    heading: str
    latest_revision_id: UUID | None
    latest_revision: int | None
    content: str | None
    content_hash: str | None


class ArtifactView(BaseModel):
    artifact_id: UUID
    revision_id: UUID | None
    relative_path: str
    mime_type: str
    byte_count: int
    sha256: str
    validation_state: str
    download_path: str


class ReviewFindingView(BaseModel):
    finding_id: UUID
    revision_id: UUID | None
    artifact_id: UUID | None
    severity: str
    criterion: str
    evidence: str
    resolution_revision_id: UUID | None


class ReviewFindingRequest(BaseModel):
    revision_id: UUID | None = None
    artifact_id: UUID | None = None
    severity: str = Field(min_length=1, max_length=32)
    criterion: str = Field(min_length=1, max_length=128)
    evidence: str = Field(min_length=1)


class ReviewFindingResponse(BaseModel):
    finding_id: UUID


class ReviewResolutionRequest(BaseModel):
    resolution_revision_id: UUID


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
    call_id: UUID | None = None
    provider_request_id: str | None = Field(default=None, max_length=255)
    usage: "ProductionUsageRequest | None" = None
    art: "ProductionArtRequest | None" = None


class ProductionArtRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=128)
    mime_type: str = Field(min_length=1, max_length=64)
    byte_count: int = Field(ge=1, le=10 * 1024 * 1024)
    content_base64: str = Field(min_length=4, max_length=14_000_000)
    call_id: UUID | None = None
    provider_request_id: str | None = Field(default=None, max_length=255)
    usage: "ProductionUsageRequest | None" = None


class ProductionUsageRequest(BaseModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cache_read_tokens: int | None = Field(default=None, ge=0)
    cache_write_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)


class TaskResultRequest(WorkerMutationRequest):
    result: str = Field(min_length=1, max_length=64 * 1024)
    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=128)
    call_id: UUID | None = None
    provider_request_id: str | None = Field(default=None, max_length=255)
    usage: ProductionUsageRequest | None = None


class TaskResultResponse(BaseModel):
    accepted: bool


class ProductionOutputResponse(BaseModel):
    run_id: UUID
    task_id: UUID
    revision_id: UUID
    artifact_id: UUID
    content_hash: str
    duplicate: bool
    usage_call_id: UUID | None = None


def _verify_existing_production_artifact(*, artifact: Artifact, path: Path, run_id: UUID, revision_id: UUID, content: bytes, mime_type: str = "text/markdown", attempt_id: UUID | None = None, usage_call_id: UUID | None = None) -> None:
    """Allow immutable artifact reuse only when disk and registration agree."""
    if (not path.is_file() or hashlib.sha256(content).hexdigest() != artifact.sha256
        or path.stat().st_size != artifact.byte_count
        or hashlib.sha256(path.read_bytes()).hexdigest() != artifact.sha256
        or artifact.mime_type != mime_type or artifact.run_id != run_id
        or artifact.revision_id != revision_id
        or (attempt_id is not None and (
            artifact.attempt_id != attempt_id or artifact.usage_call_id != usage_call_id
        ))):
        raise ValueError("existing artifact does not match production result")


def _decode_production_art(*, payload: ProductionArtRequest) -> tuple[str, bytes]:
    allowed = {"image/png": ((".png",), b"\x89PNG\r\n\x1a\n"), "image/jpeg": ((".jpg", ".jpeg"), b"\xff\xd8\xff"), "image/webp": ((".webp",), b"RIFF")}
    if payload.mime_type not in allowed:
        raise ValueError("unsupported art MIME type")
    name = Path(payload.filename).name
    suffixes, magic = allowed[payload.mime_type]
    if name != payload.filename or Path(name).suffix.lower() not in suffixes:
        raise ValueError("art filename does not match MIME type")
    try:
        content = base64.b64decode(payload.content_base64, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError("art payload is not valid base64") from exc
    if len(content) != payload.byte_count or len(content) > 10 * 1024 * 1024 or not content.startswith(magic):
        raise ValueError("art payload failed size or signature validation")
    return name, content


class ExportArtifactResponse(BaseModel):
    artifact_id: UUID
    filename: str
    sha256: str
    byte_count: int
    download_path: str


class ExportResponse(BaseModel):
    revision_id: UUID
    title: str
    package_state: str
    artifacts: list[ExportArtifactResponse]


class ExportRequest(BaseModel):
    art_artifact_id: UUID | None = None


def _require_worker_token(settings: Settings, supplied: str) -> None:
    """Reject private callbacks unless a local operator configured the token."""

    import hmac

    if not settings.worker_token:
        raise HTTPException(status_code=503, detail="worker callbacks are not configured")
    if not hmac.compare_digest(supplied, settings.worker_token):
        raise HTTPException(status_code=401, detail="unauthorized worker callback")


def _owner_token_matches(settings: Settings, supplied: str) -> bool:
    import hmac

    return bool(settings.owner_token and supplied and hmac.compare_digest(supplied, settings.owner_token))


def _owner_exempt_path(path: str) -> bool:
    return path in {"/health", "/ready", "/auth/login", "/docs", "/redoc", "/openapi.json"} or path.startswith("/src/") or path in {"/", "/favicon.ico"}


def _worker_path(path: str) -> bool:
    return path.startswith(("/private/",))


LOGIN_WINDOW_SECONDS = 60.0
LOGIN_MAX_FAILURES = 5


def _update_login_attempts(application: FastAPI, client_host: str, now: float, *, outcome: str) -> tuple[int, int]:
    """Update a short-lived host-wide login ledger shared by bound listeners."""

    path = application.state.settings.auth_rate_limit_file
    if path is None:
        with application.state.login_attempts_lock:
            attempts = application.state.login_attempts
            for host, timestamps in list(attempts.items()):
                attempts[host] = [timestamp for timestamp in timestamps if now - timestamp < LOGIN_WINDOW_SECONDS]
                if not attempts[host]:
                    del attempts[host]
            recent = attempts.setdefault(client_host, [])
            if outcome == "failure":
                recent.append(now)
            elif outcome == "success":
                attempts.pop(client_host, None)
            retry_after = max(1, int(LOGIN_WINDOW_SECONDS - (now - recent[0]))) if recent else 0
            return len(recent), retry_after

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.seek(0)
            try:
                attempts = json.load(handle)
            except (json.JSONDecodeError, OSError):
                attempts = {}
            if not isinstance(attempts, dict):
                attempts = {}
            attempts = {
                host: [float(timestamp) for timestamp in timestamps if now - float(timestamp) < LOGIN_WINDOW_SECONDS]
                for host, timestamps in attempts.items()
                if isinstance(timestamps, list)
            }
            recent = attempts.setdefault(client_host, [])
            if outcome == "failure":
                recent.append(now)
            elif outcome == "success":
                attempts.pop(client_host, None)
                recent = []
            handle.seek(0)
            handle.truncate()
            json.dump(attempts, handle, separators=(",", ":"))
            handle.flush()
            retry_after = max(1, int(LOGIN_WINDOW_SECONDS - (now - recent[0]))) if recent else 0
            return len(recent), retry_after
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the API application with explicit settings for tests and workers."""

    resolved_settings = settings or Settings()
    database = Database(resolved_settings.database_url)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.database = database
        if resolved_settings.database_url and resolved_settings.artifact_root:
            reconciliation_session = database.session()
            try:
                reconcile_pending_artifacts(reconciliation_session, resolved_settings.artifact_root)
            finally:
                reconciliation_session.close()
        yield
        database.close()

    application = FastAPI(
        title="Ebook Factory API",
        version=resolved_settings.version,
        lifespan=lifespan,
    )
    application.state.database = database
    application.state.settings = resolved_settings
    application.state.login_attempts = {}
    application.state.login_attempts_lock = threading.Lock()

    def custom_openapi() -> dict[str, Any]:
        if application.openapi_schema:
            return application.openapi_schema
        schema = get_openapi(
            title=application.title,
            version=application.version,
            description=application.description,
            routes=application.routes,
        )
        schemes = schema.setdefault("components", {}).setdefault("securitySchemes", {})
        schemes["OwnerBearer"] = {"type": "http", "scheme": "bearer"}
        schemes["WorkerToken"] = {"type": "apiKey", "in": "header", "name": "X-Ebook-Worker-Token"}
        schemes["ToolCapability"] = {"type": "apiKey", "in": "header", "name": "X-Tool-Capability"}
        for path, operations in schema.get("paths", {}).items():
            for method, operation in operations.items():
                if path.startswith("/private/tools/"):
                    security = [{"ToolCapability": []}]
                elif path in {"/usage/calls", "/usage/calls/{call_id}/finalize"} and method == "post":
                    security = [{"OwnerBearer": [], "WorkerToken": []}]
                elif _worker_path(path):
                    security = [{"WorkerToken": []}]
                elif _owner_exempt_path(path):
                    security = []
                else:
                    security = [{"OwnerBearer": []}]
                if isinstance(operation, dict):
                    operation["security"] = security
                    if path == "/providers/{provider}/connection-test" and method == "post":
                        operation["x-ebook-factory-access-policy"] = "owner-bearer-and-loopback-or-worker-token"
                        operation["description"] = "Requires owner bearer authentication and either a loopback client or the trusted worker token."
        application.openapi_schema = schema
        return schema

    application.openapi = custom_openapi  # type: ignore[method-assign]

    @application.middleware("http")
    async def owner_auth(request: Request, call_next: Any) -> Any:
        """Fail closed for owner routes while leaving health, boot and workers separate."""

        if _owner_exempt_path(request.url.path) or _worker_path(request.url.path):
            return await call_next(request)
        if not resolved_settings.owner_token:
            return JSONResponse(status_code=503, content={"detail": "owner authentication is not configured"})
        authorization = request.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not _owner_token_matches(resolved_settings, token):
            return JSONResponse(status_code=401, content={"detail": "owner authentication required"})
        return await call_next(request)

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

    @application.post("/auth/login", response_model=OwnerAuthResponse, tags=["authentication"])
    def owner_login(request: Request, payload: OwnerLoginRequest) -> OwnerAuthResponse:
        if not resolved_settings.owner_token:
            raise HTTPException(status_code=503, detail="owner authentication is not configured")
        client_host = request.client.host if request.client else "unknown"
        now = time.time()
        recent_count, retry_after = _update_login_attempts(application, client_host, now, outcome="check")
        if recent_count >= LOGIN_MAX_FAILURES:
            raise HTTPException(status_code=429, detail="too many invalid login attempts", headers={"Retry-After": str(retry_after)})
        if not _owner_token_matches(resolved_settings, payload.token):
            _update_login_attempts(application, client_host, now, outcome="failure")
            raise HTTPException(status_code=401, detail="invalid owner token")
        _update_login_attempts(application, client_host, now, outcome="success")
        return OwnerAuthResponse(authenticated=True)

    @application.get("/auth/verify", response_model=OwnerAuthResponse, tags=["authentication"])
    def owner_verify(request: Request) -> OwnerAuthResponse:
        return OwnerAuthResponse(authenticated=True)

    @application.get("/telegram/status", response_model=TelegramStatusResponse, tags=["telegram"])
    def telegram_status() -> TelegramStatusResponse:
        config = config_from_values(
            token=resolved_settings.telegram_bot_token,
            allowed_chat_ids=resolved_settings.telegram_allowed_chat_ids,
            allowed_sender_ids=resolved_settings.telegram_allowed_sender_ids,
        )
        session = database.session()
        try:
            state = session.get(TelegramState, 1)
            linked_chat_count = session.scalar(select(func.count(TelegramLink.id))) or 0
            return TelegramStatusResponse(
                configured=config.configured,
                token_configured=config.token_configured,
                allowed_chat_count=len(config.allowed_chat_ids),
                allowed_sender_count=len(config.allowed_sender_ids),
                linked_chat_count=linked_chat_count,
                next_update_id=state.next_update_id if state else 0,
            )
        finally:
            session.close()

    @application.post("/projects/{project_id}/telegram/link", response_model=TelegramStatusResponse, tags=["telegram"])
    def telegram_link(project_id: UUID, payload: TelegramLinkRequest) -> TelegramStatusResponse:
        config = config_from_values(
            token=resolved_settings.telegram_bot_token,
            allowed_chat_ids=resolved_settings.telegram_allowed_chat_ids,
            allowed_sender_ids=resolved_settings.telegram_allowed_sender_ids,
        )
        if not config.configured:
            raise HTTPException(status_code=503, detail="Telegram is not configured")
        if payload.chat_id not in config.allowed_chat_ids:
            raise HTTPException(status_code=403, detail="Telegram chat is not allowed")
        session = database.session()
        try:
            link_chat(session, chat_id=payload.chat_id, project_id=project_id)
        except ValueError as exc:
            session.rollback()
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        finally:
            session.close()
        return telegram_status()

    @application.post("/private/telegram/updates", response_model=TelegramUpdateResponse, tags=["private-worker"])
    def telegram_update(
        payload: dict[str, Any],
        x_ebook_worker_token: str = Header(default="", alias="X-Ebook-Worker-Token"),
    ) -> TelegramUpdateResponse:
        _require_worker_token(resolved_settings, x_ebook_worker_token)
        config = config_from_values(
            token=resolved_settings.telegram_bot_token,
            allowed_chat_ids=resolved_settings.telegram_allowed_chat_ids,
            allowed_sender_ids=resolved_settings.telegram_allowed_sender_ids,
        )
        session = database.session()
        try:
            result = process_update(session, config=config, update=payload)
            return TelegramUpdateResponse(
                accepted=result.accepted,
                duplicate=result.duplicate,
                reason=result.reason,
                message_id=result.message_id,
            )
        except ValueError as exc:
            session.rollback()
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        finally:
            session.close()

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
            with session.begin():
                result = append_message(session, project_id=project_id, conversation_id=payload.conversation_id, channel=payload.channel, external_dedupe_id=payload.external_dedupe_id, role="user", content=payload.content, manage_transaction=False)
                dedupe_key = f"dashboard:{payload.channel}:{payload.external_dedupe_id or result.message_id}"
                turn = enqueue_turn(session, project_id=project_id, conversation_id=payload.conversation_id, message_id=result.message_id, dedupe_key=dedupe_key)
            return MessageResponse(
                message_id=result.message_id,
                sequence=result.sequence,
                duplicate=result.duplicate,
                turn_id=turn.id,
                queued=turn.state in {"queued", "running"},
            )
        except ValueError as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        finally:
            session.close()

    @application.post("/private/orchestrator/claim", response_model=OrchestratorLeaseResponse | None, tags=["private-worker"])
    def orchestrator_claim(payload: OrchestratorClaimRequest, x_ebook_worker_token: str = Header(default="", alias="X-Ebook-Worker-Token")) -> OrchestratorLeaseResponse | None:
        _require_worker_token(resolved_settings, x_ebook_worker_token)
        session = database.session()
        try:
            turn = claim_turn(session, worker_id=payload.worker_id, lease_seconds=payload.lease_seconds)
            if turn is None:
                return None
            return OrchestratorLeaseResponse(turn_id=turn.id, worker_id=payload.worker_id, generation=turn.generation, lease_until=turn.lease_until)
        finally:
            session.close()

    @application.get("/private/orchestrator/{turn_id}/context", tags=["private-worker"])
    def orchestrator_context(turn_id: UUID, x_ebook_worker_token: str = Header(default="", alias="X-Ebook-Worker-Token"), x_worker_id: str = Header(alias="X-Worker-ID"), x_generation: int = Header(alias="X-Generation")) -> dict[str, Any]:
        _require_worker_token(resolved_settings, x_ebook_worker_token)
        session = database.session()
        try:
            with session.begin():
                turn = locked_turn(session, turn_id=turn_id, worker_id=x_worker_id, generation=x_generation)
                user_message = session.scalar(select(Message).where(Message.id == turn.user_message_id))
                if user_message is None:
                    raise ValueError("orchestrator user message not found")
                messages = session.scalars(
                    select(Message)
                    .where(Message.conversation_id == turn.conversation_id, Message.sequence <= user_message.sequence)
                    .order_by(Message.sequence.desc()).limit(40)
                ).all()[::-1]
                bounded = []
                total = 0
                for message in messages:
                    content = message.content[:20_000]
                    if total + len(content.encode()) > 100_000:
                        break
                    bounded.append({"role": message.role, "content": content}); total += len(content.encode())
                return {"turn_id": turn.id, "project_id": turn.project_id, "messages": bounded}
        except ValueError as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        finally:
            session.close()

    @application.post("/private/orchestrator/heartbeat", tags=["private-worker"])
    def orchestrator_heartbeat(payload: OrchestratorHeartbeatRequest, x_ebook_worker_token: str = Header(default="", alias="X-Ebook-Worker-Token")) -> dict[str, datetime]:
        _require_worker_token(resolved_settings, x_ebook_worker_token)
        session = database.session()
        try:
            turn = heartbeat_turn(session, turn_id=payload.turn_id, worker_id=payload.worker_id, generation=payload.generation, lease_seconds=payload.lease_seconds)
            return {"lease_until": turn.lease_until}
        except ValueError as exc:
            session.rollback(); raise HTTPException(status_code=409, detail=str(exc)) from exc
        finally:
            session.close()

    @application.post("/private/orchestrator/failure", tags=["private-worker"])
    def orchestrator_failure(payload: OrchestratorFailureRequest, x_ebook_worker_token: str = Header(default="", alias="X-Ebook-Worker-Token")) -> dict[str, str]:
        _require_worker_token(resolved_settings, x_ebook_worker_token)
        session = database.session()
        try:
            turn = fail_turn(session, turn_id=payload.turn_id, worker_id=payload.worker_id, generation=payload.generation, error=payload.error)
            return {"state": turn.state}
        except ValueError as exc:
            session.rollback(); raise HTTPException(status_code=409, detail=str(exc)) from exc
        finally:
            session.close()

    @application.post("/private/orchestrator/delta", tags=["private-worker"])
    def orchestrator_delta(payload: OrchestratorDeltaRequest, x_ebook_worker_token: str = Header(default="", alias="X-Ebook-Worker-Token")) -> dict[str, bool]:
        _require_worker_token(resolved_settings, x_ebook_worker_token)
        session = database.session()
        try:
            append_delta(session, turn_id=payload.turn_id, worker_id=payload.worker_id, generation=payload.generation, delta=payload.delta)
            return {"accepted": True}
        except ValueError as exc:
            session.rollback(); raise HTTPException(status_code=409, detail=str(exc)) from exc
        finally:
            session.close()

    @application.post("/private/orchestrator/result", tags=["private-worker"])
    def orchestrator_result(payload: OrchestratorResultRequest, x_ebook_worker_token: str = Header(default="", alias="X-Ebook-Worker-Token")) -> dict[str, UUID | bool]:
        _require_worker_token(resolved_settings, x_ebook_worker_token)
        session = database.session()
        try:
            message, duplicate = complete_turn(session, turn_id=payload.turn_id, worker_id=payload.worker_id, generation=payload.generation, content=payload.content, provider=payload.provider, model=payload.model, call_id=payload.call_id, usage=payload.usage)
            return {"message_id": message.id, "duplicate": duplicate}
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

    @application.get("/providers", response_model=list[ProviderMetadataResponse])
    def list_providers() -> list[ProviderMetadataResponse]:
        session = database.session()
        try:
            settings = session.scalars(select(ProviderSetting).order_by(ProviderSetting.provider)).all()
            return [
                ProviderMetadataResponse(
                    provider=setting.provider,
                    scope=setting.scope,
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

    @application.get("/providers/catalog", response_model=ProviderCatalogResponse)
    def provider_catalog() -> ProviderCatalogResponse:
        try:
            return ProviderCatalogResponse(**model_catalog.fetch_model_catalog())
        except model_catalog.ModelCatalogError as exc:
            raise HTTPException(status_code=503, detail="Pi model catalog unavailable") from exc

    @application.get("/private/worker/providers", response_model=list[ProviderMetadataResponse], tags=["private-worker"])
    def list_worker_providers(
        x_ebook_worker_token: str = Header(default="", alias="X-Ebook-Worker-Token"),
    ) -> list[ProviderMetadataResponse]:
        _require_worker_token(resolved_settings, x_ebook_worker_token)
        session = database.session()
        try:
            settings = session.scalars(
                select(ProviderSetting)
                .where(ProviderSetting.scope == "app")
                .order_by(ProviderSetting.provider)
            ).all()
            return [
                ProviderMetadataResponse(
                    provider=setting.provider,
                    scope=setting.scope,
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
    def record_usage(payload: UsageCallRequest, x_ebook_worker_token: str = Header(default="", alias="X-Ebook-Worker-Token")) -> dict[str, Any]:
        _require_worker_token(resolved_settings, x_ebook_worker_token)
        session = database.session()
        try:
            result = record_usage_call(session, **payload.model_dump())
            return result.__dict__
        finally:
            session.close()

    @application.post("/usage/calls/{call_id}/finalize", response_model=dict[str, Any])
    def finalize_usage(call_id: UUID, payload: UsageFinalizeRequest, x_ebook_worker_token: str = Header(default="", alias="X-Ebook-Worker-Token")) -> dict[str, Any]:
        _require_worker_token(resolved_settings, x_ebook_worker_token)
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

    @application.get("/usage/calls", response_model=list[dict[str, Any]], tags=["usage"])
    def get_usage_calls(project_id: UUID | None = None) -> list[dict[str, Any]]:
        """Return the latest bounded usage-call lineage for an optional project."""

        session = database.session()
        try:
            return list_usage_calls(session, project_id=project_id)
        finally:
            session.close()

    @application.post("/private/quota/snapshots", response_model=dict[str, Any], status_code=201, tags=["private-worker"])
    def record_quota_snapshot_route(
        payload: QuotaSnapshotRequest,
        x_ebook_worker_token: str = Header(default="", alias="X-Ebook-Worker-Token"),
    ) -> dict[str, Any]:
        """Accept one redacted provider quota observation from the local worker."""

        _require_worker_token(resolved_settings, x_ebook_worker_token)
        session = database.session()
        try:
            snapshot_id = record_quota_snapshot(session, **payload.model_dump())
            return {"snapshot_id": snapshot_id}
        finally:
            session.close()

    @application.get("/quota", response_model=list[dict[str, Any]], tags=["operations"])
    def get_quota(provider: str | None = None) -> list[dict[str, Any]]:
        """Return recent quota observations with expired supported windows marked stale."""

        session = database.session()
        try:
            return list_quota_snapshots(session, provider=provider)
        finally:
            session.close()

    @application.get("/quota/live", response_model=LiveQuotaResponse, tags=["operations"])
    def get_live_quota() -> LiveQuotaResponse:
        try:
            return LiveQuotaResponse.model_validate(codex_quota.fetch_live_quota())
        except codex_quota.CodexQuotaError as exc:
            raise HTTPException(status_code=503, detail="Codex live quota unavailable") from exc

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

    @application.post("/projects/{project_id}/exports/{revision_id}", response_model=ExportResponse, tags=["publishing"])
    def create_export(project_id: UUID, revision_id: UUID, payload: ExportRequest | None = None) -> ExportResponse:
        session = database.session()
        try:
            project = session.get(Project, project_id)
            if project is None:
                raise HTTPException(status_code=404, detail="project not found")
            session.rollback()
            result = export_book(
                session,
                root=resolved_settings.artifact_root,
                project_id=project_id,
                revision_id=revision_id,
                language=project.language,
                profile=project.profile,
                art_artifact_id=payload.art_artifact_id if payload else None,
            )
            return ExportResponse(
                revision_id=result.revision_id,
                title=result.title,
                package_state=result.package_state,
                artifacts=[
                    ExportArtifactResponse(
                        artifact_id=artifact.artifact_id,
                        filename=artifact.filename,
                        sha256=artifact.sha256,
                        byte_count=artifact.byte_count,
                        download_path=f"/projects/{project_id}/exports/{revision_id}/{artifact.filename}",
                    )
                    for artifact in result.artifacts
                ],
            )
        except ValueError as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        finally:
            session.close()

    @application.get("/projects/{project_id}/exports/{revision_id}/{filename}", tags=["publishing"])
    def download_export(project_id: UUID, revision_id: UUID, filename: str) -> FileResponse:
        if filename not in PACKAGE_FILES:
            raise HTTPException(status_code=404, detail="export member not found")
        session = database.session()
        try:
            artifact = session.scalar(
                select(Artifact)
                .join(SectionRevision, SectionRevision.id == Artifact.revision_id)
                .join(Section, Section.id == SectionRevision.section_id)
                .where(
                    Artifact.revision_id == revision_id,
                    Artifact.relative_path == f"exports/{revision_id}/{filename}",
                    Section.project_id == project_id,
                )
            )
            if artifact is None:
                raise HTTPException(status_code=404, detail="export member not found")
            try:
                members = verify_export_members(
                    session, root=resolved_settings.artifact_root, revision_id=revision_id
                )
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            artifact = next(member for member in members if member.id == artifact.id)
            path = safe_artifact_path(resolved_settings.artifact_root, artifact.relative_path)
            media_type = MIME_TYPES[filename.rsplit(".", 1)[-1]]
            return FileResponse(path, media_type=media_type, filename=filename)
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

    @application.get("/projects/{project_id}/sections", response_model=list[SectionView], tags=["documents"])
    def list_sections(project_id: UUID) -> list[SectionView]:
        session = database.session()
        try:
            if session.get(Project, project_id) is None:
                raise HTTPException(status_code=404, detail="project not found")
            sections = session.scalars(select(Section).where(Section.project_id == project_id).order_by(Section.order_no)).all()
            views: list[SectionView] = []
            for section in sections:
                revision = session.scalar(
                    select(SectionRevision)
                    .where(SectionRevision.section_id == section.id)
                    .order_by(SectionRevision.revision.desc())
                )
                views.append(
                    SectionView(
                        section_id=section.id,
                        order_no=section.order_no,
                        heading=section.heading,
                        latest_revision_id=revision.id if revision else None,
                        latest_revision=revision.revision if revision else None,
                        content=revision.content if revision else None,
                        content_hash=revision.content_hash if revision else None,
                    )
                )
            return views
        finally:
            session.close()

    @application.get("/projects/{project_id}/artifacts", response_model=list[ArtifactView], tags=["publishing"])
    def list_artifacts(project_id: UUID) -> list[ArtifactView]:
        session = database.session()
        try:
            rows = session.scalars(
                select(Artifact)
                .where(
                    or_(
                        Artifact.revision_id.in_(
                            select(SectionRevision.id)
                            .join(Section, Section.id == SectionRevision.section_id)
                            .where(Section.project_id == project_id)
                        ),
                        Artifact.run_id.in_(
                            select(ProductionRun.id).where(ProductionRun.project_id == project_id)
                        ),
                    )
                )
                .order_by(Artifact.created_at.desc())
            ).all()
            return [
                ArtifactView(
                    artifact_id=artifact.id,
                    revision_id=artifact.revision_id,
                    relative_path=artifact.relative_path,
                    mime_type=artifact.mime_type,
                    byte_count=artifact.byte_count,
                    sha256=artifact.sha256,
                    validation_state=artifact.validation_state,
                    download_path=f"/projects/{project_id}/artifacts/{artifact.id}/download",
                )
                for artifact in rows
            ]
        finally:
            session.close()

    @application.get("/projects/{project_id}/artifacts/{artifact_id}/download", tags=["publishing"])
    def download_artifact(project_id: UUID, artifact_id: UUID) -> FileResponse:
        session = database.session()
        try:
            artifact = session.scalar(
                select(Artifact)
                .where(
                    Artifact.id == artifact_id,
                    or_(
                        Artifact.run_id.in_(select(ProductionRun.id).where(ProductionRun.project_id == project_id)),
                        Artifact.revision_id.in_(
                            select(SectionRevision.id)
                            .join(Section, Section.id == SectionRevision.section_id)
                            .where(Section.project_id == project_id)
                        ),
                    ),
                )
            )
            if artifact is None:
                raise HTTPException(status_code=404, detail="artifact not found")
            path = safe_artifact_path(resolved_settings.artifact_root, artifact.relative_path)
            if not path.is_file() or path.stat().st_size != artifact.byte_count:
                raise HTTPException(status_code=409, detail="artifact is not available")
            if hashlib.sha256(path.read_bytes()).hexdigest() != artifact.sha256:
                raise HTTPException(status_code=409, detail="artifact integrity check failed")
            return FileResponse(path, media_type=artifact.mime_type, filename=Path(artifact.relative_path).name)
        finally:
            session.close()

    @application.get("/projects/{project_id}/reviews", response_model=list[ReviewFindingView], tags=["documents"])
    def list_reviews(project_id: UUID) -> list[ReviewFindingView]:
        session = database.session()
        try:
            finding_revision = aliased(SectionRevision)
            finding_section = aliased(Section)
            artifact_revision = aliased(SectionRevision)
            artifact_section = aliased(Section)
            rows = session.scalars(
                select(ReviewFinding)
                .outerjoin(finding_revision, finding_revision.id == ReviewFinding.revision_id)
                .outerjoin(finding_section, finding_section.id == finding_revision.section_id)
                .outerjoin(Artifact, Artifact.id == ReviewFinding.artifact_id)
                .outerjoin(artifact_revision, artifact_revision.id == Artifact.revision_id)
                .outerjoin(artifact_section, artifact_section.id == artifact_revision.section_id)
                .outerjoin(ProductionRun, ProductionRun.id == Artifact.run_id)
                .where(
                    or_(
                        finding_section.project_id == project_id,
                        artifact_section.project_id == project_id,
                        ProductionRun.project_id == project_id,
                    )
                )
                .order_by(ReviewFinding.created_at.desc())
            ).all()
            return [
                ReviewFindingView(
                    finding_id=finding.id,
                    revision_id=finding.revision_id,
                    artifact_id=finding.artifact_id,
                    severity=finding.severity,
                    criterion=finding.criterion,
                    evidence=finding.evidence,
                    resolution_revision_id=finding.resolution_revision_id,
                )
                for finding in rows
            ]
        finally:
            session.close()

    @application.post("/projects/{project_id}/reviews", response_model=ReviewFindingResponse, status_code=201, tags=["documents"])
    def create_review_finding(project_id: UUID, payload: ReviewFindingRequest) -> ReviewFindingResponse:
        session = database.session()
        try:
            if session.get(Project, project_id) is None:
                raise HTTPException(status_code=404, detail="project not found")
            if payload.revision_id is not None:
                valid = session.scalar(
                    select(SectionRevision.id)
                    .join(Section, Section.id == SectionRevision.section_id)
                    .where(SectionRevision.id == payload.revision_id, Section.project_id == project_id)
                )
                if valid is None:
                    raise HTTPException(status_code=404, detail="revision not found")
            if payload.artifact_id is not None:
                valid = session.scalar(
                    select(Artifact.id)
                    .outerjoin(SectionRevision, SectionRevision.id == Artifact.revision_id)
                    .outerjoin(Section, Section.id == SectionRevision.section_id)
                    .outerjoin(ProductionRun, ProductionRun.id == Artifact.run_id)
                    .where(
                        Artifact.id == payload.artifact_id,
                        or_(
                            Section.project_id == project_id,
                            ProductionRun.project_id == project_id,
                        ),
                    )
                )
                if valid is None:
                    raise HTTPException(status_code=404, detail="artifact not found")
            session.rollback()
            finding_id = record_finding(
                session,
                revision_id=payload.revision_id,
                artifact_id=payload.artifact_id,
                severity=payload.severity,
                criterion=payload.criterion,
                evidence=payload.evidence,
            )
            return ReviewFindingResponse(finding_id=finding_id)
        except ValueError as exc:
            session.rollback()
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        finally:
            session.close()

    @application.post("/projects/{project_id}/reviews/{finding_id}/resolve", response_model=ReviewFindingView, tags=["documents"])
    def resolve_review_finding(
        project_id: UUID, finding_id: UUID, payload: ReviewResolutionRequest
    ) -> ReviewFindingView:
        session = database.session()
        try:
            finding_revision = aliased(SectionRevision)
            finding_section = aliased(Section)
            artifact_revision = aliased(SectionRevision)
            artifact_section = aliased(Section)
            row = session.execute(
                select(ReviewFinding)
                .outerjoin(finding_revision, finding_revision.id == ReviewFinding.revision_id)
                .outerjoin(finding_section, finding_section.id == finding_revision.section_id)
                .outerjoin(Artifact, Artifact.id == ReviewFinding.artifact_id)
                .outerjoin(artifact_revision, artifact_revision.id == Artifact.revision_id)
                .outerjoin(artifact_section, artifact_section.id == artifact_revision.section_id)
                .outerjoin(ProductionRun, ProductionRun.id == Artifact.run_id)
                .where(
                    ReviewFinding.id == finding_id,
                    or_(
                        finding_section.project_id == project_id,
                        artifact_section.project_id == project_id,
                        ProductionRun.project_id == project_id,
                    ),
                )
                .with_for_update()
            ).first()
            if row is None:
                raise HTTPException(status_code=404, detail="review finding not found")
            finding = row[0]
            valid = session.scalar(
                select(SectionRevision.id)
                .join(Section, Section.id == SectionRevision.section_id)
                .where(SectionRevision.id == payload.resolution_revision_id, Section.project_id == project_id)
            )
            if valid is None:
                raise HTTPException(status_code=404, detail="resolution revision not found")
            finding.resolution_revision_id = payload.resolution_revision_id
            session.commit()
            return ReviewFindingView(
                finding_id=finding.id,
                revision_id=finding.revision_id,
                artifact_id=finding.artifact_id,
                severity=finding.severity,
                criterion=finding.criterion,
                evidence=finding.evidence,
                resolution_revision_id=finding.resolution_revision_id,
            )
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

    @application.post("/providers/{provider}/connection-test", response_model=ProviderConnectionTestResponse)
    def test_provider_connection(
        provider: str,
        request: Request,
        x_ebook_worker_token: str = Header(default="", alias="X-Ebook-Worker-Token"),
    ) -> ProviderConnectionTestResponse:
        import hmac

        local_client = request.client is not None and request.client.host in {"127.0.0.1", "::1"}
        worker_client = bool(resolved_settings.worker_token) and hmac.compare_digest(
            x_ebook_worker_token, resolved_settings.worker_token or ""
        )
        if not local_client and not worker_client:
            raise HTTPException(status_code=403, detail="provider connection tests require local control access")
        session = database.session()
        try:
            result = connection_test(session, provider=provider)
            return ProviderConnectionTestResponse(**result.__dict__)
        except ValueError as exc:
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
    def events_stream(project_id: UUID, after: int = 0, limit: int = 100, follow: bool = False) -> StreamingResponse:
        """Replay events and optionally follow new durable events for a short reconnect window."""

        def stream():
            cursor = after
            deadline = time.monotonic() + 25 if follow else time.monotonic()
            idle_ticks = 0
            while True:
                session = database.session()
                try:
                    replay = replay_events(session, project_id=project_id, after_id=cursor, limit=limit)
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
                if envelopes:
                    for envelope in envelopes:
                        cursor = max(cursor, envelope["id"])
                        yield f"id: {envelope['id']}\nevent: {envelope['kind']}\ndata: {json.dumps(envelope, default=str)}\n\n"
                    idle_ticks = 0
                    if not follow:
                        break
                    if time.monotonic() >= deadline:
                        break
                    continue
                if not follow or time.monotonic() >= deadline:
                    break
                idle_ticks += 1
                if idle_ticks % 10 == 0:
                    yield ": keep-alive\n\n"
                time.sleep(0.25)

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
    ) -> WorkerJobContextResponse:
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
            review_sections: list[dict[str, Any]] = []
            section_context: dict[str, str] | None = None
            assembly_ready = False
            if task.task_type == "section-draft":
                section_context = {
                    "section_id": str(task.result_refs.get("section_id", "")),
                    "heading": str(task.result_refs.get("heading", ""))[:512],
                    "outline": str(task.result_refs.get("outline", ""))[:8192],
                }
            if task.task_type == "production":
                dependencies = [UUID(value) for value in (task.dependencies or [])]
                assembly_ready = bool(dependencies) and all(
                    (dependency := session.get(Task, dependency_id)) is not None
                    and dependency.task_type == "section-draft"
                    and dependency.status == "succeeded"
                    for dependency_id in dependencies
                )
            if task.task_type == "review":
                production_task = session.scalar(
                    select(Task).where(Task.run_id == run.id, Task.task_type == "production")
                )
                section_rows: list[tuple[Section, SectionRevision]] = []
                if production_task is not None:
                    for dependency_value in production_task.dependencies or []:
                        section_task = session.get(Task, UUID(dependency_value))
                        if section_task is None or section_task.run_id != run.id:
                            raise HTTPException(status_code=409, detail="review dependency is outside the current production run")
                        if section_task.task_type != "section-draft" or section_task.status != "succeeded":
                            continue
                        section_id = section_task.result_refs.get("section_id")
                        revision_id = section_task.result_refs.get("revision_id")
                        section = session.get(Section, UUID(section_id)) if section_id else None
                        revision = session.get(SectionRevision, UUID(revision_id)) if revision_id else None
                        if section is not None and revision is not None and revision.section_id == section.id and section.project_id == project.id:
                            section_rows.append((section, revision))
                    if not section_rows:
                        revision_id = production_task.result_refs.get("revision_id")
                        revision = session.get(SectionRevision, UUID(revision_id)) if revision_id else None
                        section = session.get(Section, revision.section_id) if revision is not None else None
                        if revision is not None and section is not None and section.project_id == project.id:
                            section_rows.append((section, revision))
                    section_rows.sort(key=lambda pair: pair[0].order_no)
                total_bytes = 0
                for section, revision in section_rows:
                    remaining = REVIEW_SECTION_BUDGET_BYTES - total_bytes
                    if remaining <= 0:
                        break
                    heading = section.heading.encode()[:remaining].decode("utf-8", errors="ignore")
                    total_bytes += len(heading.encode())
                    remaining = REVIEW_SECTION_BUDGET_BYTES - total_bytes
                    content = revision.content.encode()[:max(remaining, 0)].decode("utf-8", errors="ignore")
                    review_sections.append({
                        "section_id": section.id,
                        "revision_id": revision.id,
                        "heading": heading,
                        "content": content,
                    })
                    total_bytes += len(content.encode())
            response = {
                "project_id": project.id,
                "run_id": run.id,
                "task_id": task.id,
                "job_id": job.id,
                "task_type": task.task_type,
                "cancellation_epoch": run.cancellation_epoch,
                "profile": project.profile,
                "language": project.language,
                "brief": brief.structured_brief,
                "budget": run.budget,
                "outline": (
                    {"task_id": parent.id, "result": parent.result_refs.get("result", "")}
                    if task.parent_task_id
                    and (parent := session.get(Task, task.parent_task_id)) is not None
                    and parent.status == "succeeded"
                    else None
                ),
                "review_sections": review_sections,
                "section": section_context,
                "assembly": assembly_ready,
            }
            # Assert the actual serialized response remains inside the worker
            # contract even when the persisted brief/budget contains JSON.
            if len(json.dumps(response, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")) >= WORKER_CONTEXT_LIMIT_BYTES:
                raise HTTPException(status_code=413, detail="worker context exceeds 64 KiB limit")
            return response
        finally:
            session.close()

    @application.post("/private/worker/task-result", response_model=TaskResultResponse, tags=["private-worker"])
    def worker_task_result(
        payload: TaskResultRequest,
        x_ebook_worker_token: str = Header(default="", alias="X-Ebook-Worker-Token"),
    ) -> TaskResultResponse:
        _require_worker_token(resolved_settings, x_ebook_worker_token)
        session = database.session()
        try:
            with session.begin():
                row = session.execute(
                    select(Job, Task, ProductionRun, Attempt)
                    .join(Task, Task.id == Job.task_id)
                    .join(ProductionRun, ProductionRun.id == Task.run_id)
                    .join(Attempt, Attempt.task_id == Task.id)
                    .where(
                        Job.id == payload.job_id,
                        Task.task_type != "production",
                        Attempt.fencing_generation == payload.generation,
                    )
                    .with_for_update()
                ).first()
                if row is None:
                    raise HTTPException(status_code=409, detail="task result lease is no longer current")
                _, task, run, attempt = row
                budget_allowed, budget_reason = enforce_budget(
                    session, job_id=payload.job_id, worker_id=payload.worker_id,
                    generation=payload.generation,
                    input_tokens=payload.usage.input_tokens if payload.usage else None,
                    output_tokens=payload.usage.output_tokens if payload.usage else None,
                    reasoning_tokens=payload.usage.reasoning_tokens if payload.usage else None,
                    manage_transaction=False,
                )
                if budget_allowed:
                    task.provider = payload.provider
                    task.model = payload.model
                    attempt.provider = payload.provider
                    attempt.model = payload.model
                    usage_call_id = None
                    if payload.call_id is not None:
                        usage_result = record_usage_call(
                            session, call_id=payload.call_id, provider=payload.provider, model=payload.model,
                            purpose=task.task_type, outcome="succeeded", started_at=utc_now(), ended_at=utc_now(),
                            provider_request_id=payload.provider_request_id, project_id=run.project_id, run_id=run.id,
                            task_id=task.id, attempt_id=attempt.id,
                            input_tokens=payload.usage.input_tokens if payload.usage else None,
                            output_tokens=payload.usage.output_tokens if payload.usage else None,
                            cache_read_tokens=payload.usage.cache_read_tokens if payload.usage else None,
                            cache_write_tokens=payload.usage.cache_write_tokens if payload.usage else None,
                            reasoning_tokens=payload.usage.reasoning_tokens if payload.usage else None,
                            source_metadata={"source": "pi-task-result"}, manage_transaction=False,
                        )
                        usage_call_id = str(usage_result.call_id)
                    if task.task_type == "outline":
                        production_task = session.scalar(select(Task).where(Task.run_id == run.id, Task.task_type == "production").with_for_update())
                        if production_task is None:
                            raise HTTPException(status_code=409, detail="production task is missing")
                        expand_outline_sections(session, outline_task=task, production_task=production_task, outline_text=payload.result)
                    elif task.task_type == "section-draft":
                        section_id = task.result_refs.get("section_id")
                        section = session.get(Section, UUID(section_id)) if section_id else None
                        if section is None:
                            raise HTTPException(status_code=409, detail="section task has no stable section")
                        section_revision = SectionRevision(
                            section_id=section.id,
                            revision=(session.scalar(select(SectionRevision.revision).where(SectionRevision.section_id == section.id).order_by(SectionRevision.revision.desc()).limit(1)) or 0) + 1,
                            content=payload.result,
                            summary="Pi section-draft output",
                            source_refs=[f"task:{task.id}", f"provider:{payload.provider}", f"model:{payload.model}"] + ([f"usage:{usage_call_id}"] if usage_call_id else []),
                            knowledge_refs=[], approval_status="draft", content_hash=hashlib.sha256(payload.result.encode()).hexdigest(),
                        )
                        session.add(section_revision)
                        session.flush()
                        task.result_refs = {**task.result_refs, "revision_id": str(section_revision.id), "usage_call_id": usage_call_id}
                    complete_task_result(
                        session, job_id=payload.job_id, worker_id=payload.worker_id,
                        generation=payload.generation,
                        result_refs={**task.result_refs, "result": payload.result, "provider": payload.provider, "model": payload.model, **({"usage_call_id": usage_call_id} if usage_call_id else {})},
                        manage_transaction=False,
                    )
            if not budget_allowed:
                raise HTTPException(status_code=409, detail=f"task budget blocked: {budget_reason}")
            return TaskResultResponse(accepted=True)
        except (StaleLease, CancellationRejected, ValueError) as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        finally:
            session.close()

    @application.post("/private/worker/production-result", response_model=ProductionOutputResponse, tags=["private-worker"])
    def worker_production_result(
        payload: ProductionOutputRequest,
        x_ebook_worker_token: str = Header(default="", alias="X-Ebook-Worker-Token"),
    ) -> ProductionOutputResponse:
        _require_worker_token(resolved_settings, x_ebook_worker_token)
        session = database.session()
        created_artifact_path: Path | None = None
        try:
            with session.begin():
                budget_allowed, budget_reason = enforce_budget(
                    session,
                    job_id=payload.job_id,
                    worker_id=payload.worker_id,
                    generation=payload.generation,
                    input_tokens=payload.usage.input_tokens if payload.usage else None,
                    output_tokens=payload.usage.output_tokens if payload.usage else None,
                    reasoning_tokens=payload.usage.reasoning_tokens if payload.usage else None,
                    manage_transaction=False,
                )
                if budget_allowed:
                    production_row = session.execute(
                        select(Task, ProductionRun, Attempt)
                        .join(ProductionRun, ProductionRun.id == Task.run_id)
                        .join(Job, Job.task_id == Task.id)
                        .join(
                            Attempt,
                            (Attempt.task_id == Task.id)
                            & (Attempt.fencing_generation == payload.generation),
                        )
                        .where(Job.id == payload.job_id)
                        .with_for_update()
                    ).first()
                    if production_row is None or production_row[0].task_type != "production":
                        raise HTTPException(status_code=409, detail="production result is only valid for production tasks")
                    production_task, production_run, attempt = production_row
                    if payload.content == "__server_assembly__":
                        dependencies = [UUID(value) for value in (production_task.dependencies or [])]
                        payload.content = assemble_section_revisions(
                            session,
                            project_id=production_run.project_id,
                            run_id=production_run.id,
                            section_task_ids=dependencies,
                        )
                    output = accept_production_output(
                        session,
                        job_id=payload.job_id,
                        worker_id=payload.worker_id,
                        generation=payload.generation,
                        content=payload.content,
                        provider=payload.provider,
                        model=payload.model,
                        manage_transaction=False,
                    )
                    try:
                        relative_artifact_path = f"{output.run_id}/book.md"
                        artifact_candidate_path = safe_artifact_path(resolved_settings.artifact_root, relative_artifact_path)
                        artifact = write_artifact(
                            session,
                            root=resolved_settings.artifact_root,
                            relative_path=relative_artifact_path,
                            content=payload.content.encode(),
                            mime_type="text/markdown",
                            run_id=output.run_id,
                            attempt_id=attempt.id,
                            revision_id=output.revision_id,
                            manage_transaction=False,
                        )
                        created_artifact_path = artifact_candidate_path

                    except FileExistsError:
                        artifact = session.scalar(select(Artifact).where(Artifact.relative_path == f"{output.run_id}/book.md"))
                        if artifact is None:
                            raise HTTPException(status_code=503, detail="artifact registration unavailable")
                        existing_path = safe_artifact_path(resolved_settings.artifact_root, artifact.relative_path)
                        content = payload.content.encode()
                        _verify_existing_production_artifact(
                            artifact=artifact, path=existing_path, run_id=output.run_id,
                            revision_id=output.revision_id, content=content, attempt_id=attempt.id,
                        )

                    art_artifact = None
                    art_usage_call_id = None
                    if payload.art is not None:
                        if payload.art.call_id and payload.provider and payload.model:
                            art_usage = payload.art.usage
                            art_usage_result = record_usage_call(
                                session,
                                call_id=payload.art.call_id,
                                provider=payload.provider,
                                model=payload.model,
                                purpose="art",
                                outcome="succeeded",
                                started_at=utc_now(),
                                ended_at=utc_now(),
                                provider_request_id=payload.art.provider_request_id,
                                project_id=output.project_id,
                                run_id=output.run_id,
                                task_id=output.task_id,
                                attempt_id=attempt.id if attempt else None,
                                input_tokens=art_usage.input_tokens if art_usage else None,
                                output_tokens=art_usage.output_tokens if art_usage else None,
                                cache_read_tokens=art_usage.cache_read_tokens if art_usage else None,
                                cache_write_tokens=art_usage.cache_write_tokens if art_usage else None,
                                reasoning_tokens=art_usage.reasoning_tokens if art_usage else None,
                                source_metadata={"source": "codex-app-server-image", "reported_usage": art_usage.model_dump() if art_usage else None},
                                manage_transaction=False,
                            )
                            art_usage_call_id = art_usage_result.call_id
                        art_filename, art_content = _decode_production_art(payload=payload.art)
                        art_relative_path = f"{output.run_id}/{art_filename}"
                        art_candidate_path = safe_artifact_path(resolved_settings.artifact_root, art_relative_path)
                        try:
                            art_artifact = write_artifact(
                                session, root=resolved_settings.artifact_root, relative_path=art_relative_path,
                                content=art_content, mime_type=payload.art.mime_type, run_id=output.run_id,
                                attempt_id=attempt.id,
                                usage_call_id=art_usage_call_id,
                                revision_id=output.revision_id, manage_transaction=False,
                            )
                        except FileExistsError:
                            art_artifact = session.scalar(select(Artifact).where(Artifact.relative_path == art_relative_path))
                            if art_artifact is None:
                                raise HTTPException(status_code=503, detail="art artifact registration unavailable")
                            _verify_existing_production_artifact(
                                artifact=art_artifact, path=art_candidate_path, run_id=output.run_id,
                                revision_id=output.revision_id, content=art_content, mime_type=payload.art.mime_type,
                                attempt_id=attempt.id, usage_call_id=art_usage_call_id,
                            )

                    usage_call_id = None
                    if payload.provider and payload.model:
                        usage = payload.usage
                        usage_result = record_usage_call(
                            session,
                            call_id=payload.call_id or uuid4(),
                            provider=payload.provider,
                            model=payload.model,
                            purpose="production",
                            outcome="succeeded",
                            started_at=utc_now(),
                            ended_at=utc_now(),
                            provider_request_id=payload.provider_request_id,
                            project_id=output.project_id,
                            run_id=output.run_id,
                            task_id=output.task_id,
                            attempt_id=attempt.id if attempt else None,
                            input_tokens=usage.input_tokens if usage else None,
                            output_tokens=usage.output_tokens if usage else None,
                            cache_read_tokens=usage.cache_read_tokens if usage else None,
                            cache_write_tokens=usage.cache_write_tokens if usage else None,
                            reasoning_tokens=usage.reasoning_tokens if usage else None,
                            source_metadata={"source": "pi-final-message", "reported_usage": usage.model_dump() if usage else None},
                            manage_transaction=False,
                        )
                        usage_call_id = usage_result.call_id
                    complete_job(
                        session,
                        job_id=payload.job_id,
                        worker_id=payload.worker_id,
                        generation=payload.generation,
                        result_refs={
                            "revision_id": str(output.revision_id),
                            "artifact_id": str(artifact.id),
                            **({"art_artifact_id": str(art_artifact.id)} if art_artifact else {}),
                            **({"usage_call_id": str(usage_call_id)} if usage_call_id else {}),
                            **({"art_usage_call_id": str(art_usage_call_id)} if art_usage_call_id else {}),
                        },
                        manage_transaction=False,
                    )
                else:
                    output = artifact = None
                    usage_call_id = None
            if not budget_allowed:
                raise HTTPException(status_code=409, detail=f"production budget blocked: {budget_reason}")
        except (StaleLease, CancellationRejected, ValueError) as exc:
            session.rollback()
            if created_artifact_path is not None:
                created_artifact_path.unlink(missing_ok=True)
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception:
            session.rollback()
            if created_artifact_path is not None:
                created_artifact_path.unlink(missing_ok=True)
            raise
        finally:
            session.close()
        return ProductionOutputResponse(
            run_id=output.run_id,
            task_id=output.task_id,
            revision_id=output.revision_id,
            artifact_id=artifact.id,
            content_hash=output.content_hash,
            duplicate=output.duplicate,
            usage_call_id=usage_call_id,
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
