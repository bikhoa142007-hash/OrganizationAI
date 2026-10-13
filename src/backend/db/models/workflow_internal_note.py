from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.db.base import Base


class WorkflowInternalNote(Base):
    """Private, append-only note visible only to the currently assigned Checker."""

    __tablename__ = "workflow_internal_notes"
    __table_args__ = (
        CheckConstraint("length(trim(content)) > 0", name="ck_workflow_internal_notes_content_nonblank"),
        CheckConstraint("length(content) <= 4000", name="ck_workflow_internal_notes_content_length"),
        CheckConstraint("approval_round IS NULL OR approval_round >= 1", name="ck_workflow_internal_notes_round"),
        UniqueConstraint(
            "plan_id", "author_id", "idempotency_key",
            name="uq_workflow_internal_notes_actor_key",
        ),
        Index("ix_workflow_internal_notes_plan_created", "plan_id", "created_at", "note_id"),
    )

    note_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("auth_workflow_plans.id", ondelete="RESTRICT"), nullable=False
    )
    approval_round: Mapped[int | None] = mapped_column(Integer, nullable=True)
    author_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WorkflowInternalNoteAuditEvent(Base):
    """Metadata-only audit record kept outside plan history and user-visible feeds."""

    __tablename__ = "workflow_internal_note_audit_events"
    __table_args__ = (
        CheckConstraint("action = 'INTERNAL_NOTE_ADDED'", name="ck_workflow_internal_note_audit_action"),
        Index("ix_workflow_internal_note_audit_plan_created", "plan_id", "created_at"),
    )

    note_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workflow_internal_notes.note_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    plan_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("auth_workflow_plans.id", ondelete="RESTRICT"), nullable=False
    )
    actor_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False, default="INTERNAL_NOTE_ADDED")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
