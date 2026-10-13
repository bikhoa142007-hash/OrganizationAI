from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    Uuid,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.db.base import Base


class AuthWorkflowConfigurationHead(Base):
    """Per-kind lock and optimistic revision counter; it contains no business defaults."""

    __tablename__ = "auth_workflow_configuration_heads"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('approval_policy', 'budget', 'media_policy', 'strategy_rubric', 'authority', 'checker_assignment')",
            name="ck_workflow_config_heads_kind",
        ),
        CheckConstraint("latest_revision >= 0", name="ck_workflow_config_heads_revision"),
    )

    kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    latest_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class AuthWorkflowConfigurationRevision(Base):
    """Append-only, effective-dated workflow configuration revision."""

    __tablename__ = "auth_workflow_configuration_revisions"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('approval_policy', 'budget', 'media_policy', 'strategy_rubric', 'authority', 'checker_assignment')",
            name="ck_workflow_config_revisions_kind",
        ),
        CheckConstraint("revision > 0", name="ck_workflow_config_revisions_revision"),
        CheckConstraint("length(configuration_hash) = 64", name="ck_workflow_config_revisions_hash"),
        UniqueConstraint("kind", "revision", name="uq_workflow_config_revisions_kind_revision"),
        UniqueConstraint("kind", "effective_at", name="uq_workflow_config_revisions_kind_effective_at"),
        Index("ix_workflow_config_revisions_effective", "kind", "effective_at", "revision"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    change_reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    value: Mapped[dict] = mapped_column(JSON, nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    changed_by: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuthWorkflowRoundConfigurationSnapshot(Base):
    """Immutable configuration and Checker assignment captured once per approval round."""

    __tablename__ = "auth_workflow_round_configuration_snapshots"
    __table_args__ = (
        CheckConstraint("plan_version > 0", name="ck_workflow_round_config_snapshots_version"),
        CheckConstraint("approval_round > 0", name="ck_workflow_round_config_snapshots_round"),
        CheckConstraint("length(snapshot_hash) = 64", name="ck_workflow_round_config_snapshots_hash"),
        UniqueConstraint("plan_id", "approval_round", name="uq_workflow_round_config_snapshots_plan_round"),
        Index("ix_workflow_round_config_snapshots_plan_version", "plan_id", "plan_version"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("auth_workflow_plans.id", ondelete="RESTRICT"), nullable=False
    )
    plan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    approval_round: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    configurations: Mapped[dict] = mapped_column(JSON, nullable=False)
    checker_assignment: Mapped[dict] = mapped_column(JSON, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuthWorkflowConfigurationLock(Base):
    """A singleton transaction lock for coherent cross-kind snapshots and updates."""

    __tablename__ = "auth_workflow_configuration_locks"
    __table_args__ = (CheckConstraint("id = 1", name="ck_workflow_config_locks_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)


def _reject_mutation(_mapper, _connection, _target) -> None:
    raise ValueError("Workflow configuration revisions and round snapshots are immutable.")


for _immutable_model in (AuthWorkflowConfigurationRevision, AuthWorkflowRoundConfigurationSnapshot):
    event.listen(_immutable_model, "before_update", _reject_mutation)
    event.listen(_immutable_model, "before_delete", _reject_mutation)
