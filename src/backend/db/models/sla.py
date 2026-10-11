"""Versioned SLA configuration and immutable approval-round snapshots."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.db.base import Base


class AuthWorkflowSlaConfiguration(Base):
    """One immutable administrator-authored SLA configuration revision."""

    __tablename__ = "auth_workflow_sla_configurations"
    __table_args__ = (
        UniqueConstraint("revision", name="uq_auth_workflow_sla_configurations_revision"),
        CheckConstraint("revision > 0", name="ck_auth_workflow_sla_configurations_revision"),
        CheckConstraint(
            "duration_minutes > 0 AND duration_minutes <= 5256000",
            name="ck_auth_workflow_sla_configurations_duration",
        ),
        CheckConstraint(
            "warning_before_minutes > 0 AND warning_before_minutes < duration_minutes",
            name="ck_auth_workflow_sla_configurations_warning",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    warning_before_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    changed_by: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    change_reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuthWorkflowSlaRound(Base):
    """The immutable timing/configuration snapshot for one submitted round."""

    __tablename__ = "auth_workflow_sla_rounds"
    __table_args__ = (
        UniqueConstraint("plan_id", "round_number", name="uq_auth_workflow_sla_rounds_plan_round"),
        CheckConstraint("version_number > 0", name="ck_auth_workflow_sla_rounds_version"),
        CheckConstraint("round_number > 0", name="ck_auth_workflow_sla_rounds_round"),
        CheckConstraint(
            "duration_minutes > 0 AND duration_minutes <= 5256000",
            name="ck_auth_workflow_sla_rounds_duration",
        ),
        CheckConstraint(
            "warning_before_minutes > 0 AND warning_before_minutes < duration_minutes",
            name="ck_auth_workflow_sla_rounds_warning",
        ),
        CheckConstraint(
            "started_at < warning_at AND warning_at < due_at",
            name="ck_auth_workflow_sla_rounds_deadlines",
        ),
        CheckConstraint(
            "closed_at IS NULL OR closed_at >= started_at",
            name="ck_auth_workflow_sla_rounds_closed_after_start",
        ),
        Index(
            "ix_auth_workflow_sla_rounds_open_warning",
            "warning_at",
            postgresql_where=text("closed_at IS NULL"),
            sqlite_where=text("closed_at IS NULL"),
        ),
        Index(
            "ix_auth_workflow_sla_rounds_open_due",
            "due_at",
            postgresql_where=text("closed_at IS NULL"),
            sqlite_where=text("closed_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("auth_workflow_plans.id", ondelete="RESTRICT"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    configuration_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("auth_workflow_sla_configurations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    configuration_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    warning_before_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    warning_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
