"""Create append-only internal notes and their metadata-only audit sink."""
from alembic import op
import sqlalchemy as sa

revision = "20261012_13"
down_revision = "20261011_12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_internal_notes",
        sa.Column("note_id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("plan_id", sa.Uuid(as_uuid=True), sa.ForeignKey("auth_workflow_plans.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("approval_round", sa.Integer(), nullable=True),
        sa.Column("author_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(trim(content)) > 0", name="ck_workflow_internal_notes_content_nonblank"),
        sa.CheckConstraint("length(content) <= 4000", name="ck_workflow_internal_notes_content_length"),
        sa.CheckConstraint("approval_round IS NULL OR approval_round >= 1", name="ck_workflow_internal_notes_round"),
        sa.UniqueConstraint("plan_id", "author_id", "idempotency_key", name="uq_workflow_internal_notes_actor_key"),
    )
    op.create_index(
        "ix_workflow_internal_notes_plan_created",
        "workflow_internal_notes",
        ["plan_id", "created_at", "note_id"],
    )
    op.create_table(
        "workflow_internal_note_audit_events",
        sa.Column("note_id", sa.Uuid(as_uuid=True), sa.ForeignKey("workflow_internal_notes.note_id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("plan_id", sa.Uuid(as_uuid=True), sa.ForeignKey("auth_workflow_plans.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("actor_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("action = 'INTERNAL_NOTE_ADDED'", name="ck_workflow_internal_note_audit_action"),
    )
    op.create_index(
        "ix_workflow_internal_note_audit_plan_created",
        "workflow_internal_note_audit_events",
        ["plan_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_internal_note_audit_plan_created", table_name="workflow_internal_note_audit_events")
    op.drop_table("workflow_internal_note_audit_events")
    op.drop_index("ix_workflow_internal_notes_plan_created", table_name="workflow_internal_notes")
    op.drop_table("workflow_internal_notes")
