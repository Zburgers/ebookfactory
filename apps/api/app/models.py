"""SQLAlchemy metadata for the durable Ebook Factory contract records."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, Index, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import Uuid


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp for persisted records."""

    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base metadata used by Alembic and the API domain models."""


class CreatedMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class UpdatedMixin:
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class Project(CreatedMixin, UpdatedMixin, Base):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    profile: Mapped[str] = mapped_column(String(32), nullable=False)
    language: Mapped[str] = mapped_column(String(32), nullable=False)
    active_brief_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("brief_revisions.id", name="fk_projects_active_brief", use_alter=True)
    )
    conversation_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("conversations.id", name="fk_projects_conversation", use_alter=True)
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="brainstorming")


class BriefRevision(CreatedMixin, Base):
    __tablename__ = "brief_revisions"
    __table_args__ = (UniqueConstraint("project_id", "revision", name="uq_brief_project_revision"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    structured_brief: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class Conversation(CreatedMixin, UpdatedMixin, Base):
    __tablename__ = "conversations"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)


class Message(CreatedMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence", name="uq_message_conversation_sequence"),
        UniqueConstraint("channel", "external_dedupe_id", name="uq_message_channel_external_dedupe"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    external_dedupe_id: Mapped[str | None] = mapped_column(String(240))
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    turn_state: Mapped[str] = mapped_column(String(32), nullable=False, default="received")


class OrchestratorTurn(CreatedMixin, UpdatedMixin, Base):
    """Durable dashboard turn lease and completion record."""

    __tablename__ = "orchestrator_turns"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_orchestrator_turn_dedupe"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    user_message_id: Mapped[UUID] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    assistant_message_id: Mapped[UUID | None] = mapped_column(ForeignKey("messages.id"))
    dedupe_key: Mapped[str] = mapped_column(String(512), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))


class ProductionRun(CreatedMixin, UpdatedMixin, Base):
    __tablename__ = "production_runs"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    approved_brief_id: Mapped[UUID] = mapped_column(ForeignKey("brief_revisions.id"), nullable=False)
    plan_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    budget: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    cancellation_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Task(CreatedMixin, UpdatedMixin, Base):
    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("production_runs.id", ondelete="CASCADE"), nullable=False)
    parent_task_id: Mapped[UUID | None] = mapped_column(ForeignKey("tasks.id"))
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    dependencies: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    input_revision_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    session_id: Mapped[str | None] = mapped_column(String(240))
    result_refs: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")


class Attempt(CreatedMixin, Base):
    __tablename__ = "attempts"
    __table_args__ = (UniqueConstraint("task_id", "attempt_no", name="uq_attempt_task_number"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    input_revision_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    session_id: Mapped[str | None] = mapped_column(String(240))
    result_refs: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    fencing_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_class: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Job(CreatedMixin, UpdatedMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_job_dedupe_key"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    dedupe_key: Mapped[str] = mapped_column(String(512), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fencing_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    error_class: Mapped[str | None] = mapped_column(String(128))


class Event(CreatedMixin, Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    run_id: Mapped[UUID | None] = mapped_column(ForeignKey("production_runs.id"))
    task_id: Mapped[UUID | None] = mapped_column(ForeignKey("tasks.id"))
    kind: Mapped[str] = mapped_column(String(128), nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    delivery_state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")


class Outbox(CreatedMixin, UpdatedMixin, Base):
    __tablename__ = "outbox"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    delivery_state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)


class TelegramState(CreatedMixin, UpdatedMixin, Base):
    """Singleton durable long-polling cursor for the configured Telegram bot."""

    __tablename__ = "telegram_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    next_update_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)


class TelegramUpdate(CreatedMixin, Base):
    """Durable Telegram receipt used to reject replayed updates safely."""

    __tablename__ = "telegram_updates"

    update_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    chat_id: Mapped[int | None] = mapped_column(BigInteger)
    sender_id: Mapped[int | None] = mapped_column(BigInteger)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class TelegramLink(CreatedMixin, UpdatedMixin, Base):
    """Allowlisted chat-to-project association with one active project per chat."""

    __tablename__ = "telegram_links"
    __table_args__ = (
        UniqueConstraint("chat_id", "project_id", name="uq_telegram_link_chat_project"),
        Index("uq_telegram_link_active_chat", "chat_id", unique=True, sqlite_where=text("is_active = 1"), postgresql_where=text("is_active = true")),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=False)


class TelegramOutbox(CreatedMixin, UpdatedMixin, Base):
    """Durable outgoing Telegram message with bounded retry state."""

    __tablename__ = "telegram_outbox"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_telegram_outbox_dedupe"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    reply_markup: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    telegram_message_id: Mapped[str | None] = mapped_column(String(128))


class Section(CreatedMixin, Base):
    __tablename__ = "sections"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    order_no: Mapped[int] = mapped_column(Integer, nullable=False)
    heading: Mapped[str] = mapped_column(String(512), nullable=False)


class SectionRevision(CreatedMixin, Base):
    __tablename__ = "section_revisions"
    __table_args__ = (UniqueConstraint("section_id", "revision", name="uq_section_revision_number"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    section_id: Mapped[UUID] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    parent_revision_id: Mapped[UUID | None] = mapped_column(ForeignKey("section_revisions.id"))
    source_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    knowledge_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    approval_status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class KnowledgeRecord(CreatedMixin, Base):
    __tablename__ = "knowledge_records"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    scoped_type: Mapped[str] = mapped_column(String(32), nullable=False)
    facts: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    continuity: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unverified")


class Source(CreatedMixin, Base):
    __tablename__ = "sources"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    scoped_type: Mapped[str] = mapped_column(String(32), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unverified")


class Artifact(CreatedMixin, Base):
    __tablename__ = "artifacts"
    __table_args__ = (UniqueConstraint("relative_path", name="uq_artifact_relative_path"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID | None] = mapped_column(ForeignKey("production_runs.id"))
    attempt_id: Mapped[UUID | None] = mapped_column(ForeignKey("attempts.id"))
    usage_call_id: Mapped[UUID | None] = mapped_column(ForeignKey("usage_calls.id"))
    revision_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    validation_state: Mapped[str] = mapped_column(String(32), nullable=False, default="generated")
    owner_review_state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    owner_review_note: Mapped[str | None] = mapped_column(Text)
    owner_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReviewFinding(CreatedMixin, Base):
    __tablename__ = "review_findings"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    artifact_id: Mapped[UUID | None] = mapped_column(ForeignKey("artifacts.id"))
    revision_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    criterion: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    resolution_revision_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))


class UsageCall(CreatedMixin, Base):
    __tablename__ = "usage_calls"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    provider_request_id: Mapped[str | None] = mapped_column(String(255))
    project_id: Mapped[UUID | None] = mapped_column(ForeignKey("projects.id"))
    run_id: Mapped[UUID | None] = mapped_column(ForeignKey("production_runs.id"))
    task_id: Mapped[UUID | None] = mapped_column(ForeignKey("tasks.id"))
    attempt_id: Mapped[UUID | None] = mapped_column(ForeignKey("attempts.id"))
    session_id: Mapped[str | None] = mapped_column(String(255))
    agent_id: Mapped[str | None] = mapped_column(String(255))
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_account_alias: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_read_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_write_tokens: Mapped[int | None] = mapped_column(Integer)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer)
    price_version: Mapped[str | None] = mapped_column(String(128))
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    reported_billed_cost: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    provider_credit_units: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    normalization_version: Mapped[str] = mapped_column(String(32), nullable=False)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class QuotaSnapshot(CreatedMixin, Base):
    __tablename__ = "quota_snapshots"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    account_alias: Mapped[str] = mapped_column(String(128), nullable=False)
    bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stale_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    remaining: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    units: Mapped[str | None] = mapped_column(String(64))
    window_seconds: Mapped[int | None] = mapped_column(Integer)
    resets_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    plan_label: Mapped[str | None] = mapped_column(String(128))
    capability_state: Mapped[str] = mapped_column(String(32), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)


class ProviderSetting(CreatedMixin, UpdatedMixin, Base):
    __tablename__ = "provider_settings"
    __table_args__ = (UniqueConstraint("provider", "scope", name="uq_provider_setting_scope"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default="app")
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    credential_ref: Mapped[str | None] = mapped_column(String(255))
    orchestration_model: Mapped[str | None] = mapped_column(String(128))
    drafting_model: Mapped[str | None] = mapped_column(String(128))
    review_model: Mapped[str | None] = mapped_column(String(128))
