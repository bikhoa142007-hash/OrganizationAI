from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.db.base import Base


class AuthWorkflowPlan(Base):
    """A marketing plan owned by an authenticated Maker."""

    __tablename__ = "auth_workflow_plans"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'REJECTED')",
            name="ck_auth_workflow_plans_status",
        ),
        Index("ix_auth_workflow_plans_maker_status", "maker_id", "status"),
        Index("ix_auth_workflow_plans_checker_status", "checker_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    maker_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    checker_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="DRAFT")
    processing_stage: Mapped[str] = mapped_column(String(40), nullable=False, default="DRAFT")
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_round: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AuthWorkflowAttachment(Base):
    """Private uploaded media stored in PostgreSQL with its content hash."""

    __tablename__ = "auth_workflow_attachments"
    __table_args__ = (Index("ix_auth_workflow_attachments_plan", "plan_id"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("auth_workflow_plans.id", ondelete="RESTRICT"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    uploaded_by: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuthWorkflowVersion(Base):
    """Immutable snapshot captured for a plan submission and approval round."""

    __tablename__ = "auth_workflow_versions"
    __table_args__ = (
        UniqueConstraint("plan_id", "version_number", name="uq_auth_workflow_versions_plan_version"),
        UniqueConstraint("plan_id", "round_number", name="uq_auth_workflow_versions_plan_round"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("auth_workflow_plans.id", ondelete="RESTRICT"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    attachment_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    submitted_by: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuthWorkflowEvent(Base):
    """Append-only history for authenticated workflow actions."""

    __tablename__ = "auth_workflow_events"
    __table_args__ = (
        UniqueConstraint("plan_id", "sequence_number", name="uq_auth_workflow_events_plan_sequence"),
        Index("ix_auth_workflow_events_plan_sequence", "plan_id", "sequence_number"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("auth_workflow_plans.id", ondelete="RESTRICT"), nullable=False
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    actor_type: Mapped[str] = mapped_column(String(12), nullable=False, default="HUMAN")
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    status_before: Mapped[str | None] = mapped_column(String(24), nullable=True)
    status_after: Mapped[str] = mapped_column(String(24), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuthWorkflowDecision(Base):
    """At most one final Checker decision per submitted approval round."""

    __tablename__ = "auth_workflow_decisions"
    __table_args__ = (
        UniqueConstraint("plan_id", "round_number", name="uq_auth_workflow_decisions_plan_round"),
        CheckConstraint("action IN ('APPROVED', 'REJECTED')", name="ck_auth_workflow_decisions_action"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("auth_workflow_plans.id", ondelete="RESTRICT"), nullable=False
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    checker_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuthWorkflowEvaluationRun(Base):
    """One immutable, schema-validated AI evaluation per submitted round."""

    __tablename__ = "auth_workflow_evaluation_runs"
    __table_args__ = (
        UniqueConstraint("plan_id", "round_number", name="uq_auth_workflow_ai_run_plan_round"),
        UniqueConstraint("run_id", name="uq_auth_workflow_ai_run_id"),
        UniqueConstraint("evaluation_id", name="uq_auth_workflow_ai_evaluation_id"),
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'SUCCEEDED', 'FAILED', 'TIMED_OUT')",
            name="ck_auth_workflow_ai_run_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("auth_workflow_plans.id", ondelete="RESTRICT"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    run_id: Mapped[str] = mapped_column(String(100), nullable=False)
    evaluation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(200), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(160), nullable=True)
    policy_version: Mapped[str] = mapped_column(String(160), nullable=False)
    policy_snapshot_id: Mapped[str] = mapped_column(String(160), nullable=False)
    policy_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retried: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evaluation: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    visual_extraction: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    media_evaluation: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    strategy_evaluation: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuthWorkflowEngineDecision(Base):
    """Immutable deterministic engine route for a submitted approval round."""

    __tablename__ = "auth_workflow_engine_decisions"
    __table_args__ = (
        UniqueConstraint("plan_id", "round_number", name="uq_auth_workflow_engine_decisions_plan_round"),
        UniqueConstraint("decision_id", name="uq_auth_workflow_engine_decisions_id"),
        CheckConstraint(
            "outcome IN ('AUTO_APPROVED', 'HUMAN_REVIEW_REQUIRED')",
            name="ck_auth_workflow_engine_decisions_outcome",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("auth_workflow_plans.id", ondelete="RESTRICT"), nullable=False
    )
    evaluation_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("auth_workflow_evaluation_runs.id", ondelete="RESTRICT"),
        nullable=False, unique=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    decision_id: Mapped[str] = mapped_column(String(100), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    decision: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
