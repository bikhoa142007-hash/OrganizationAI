"""Add PostgreSQL persistence for authenticated marketing-plan workflow."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260928_03"
down_revision: Union[str, None] = "20260928_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auth_workflow_plans",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("maker_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("checker_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("processing_stage", sa.String(length=40), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("current_round", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'REJECTED')",
            name="ck_auth_workflow_plans_status",
        ),
        sa.ForeignKeyConstraint(["maker_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["checker_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_auth_workflow_plans_maker_status", "auth_workflow_plans", ["maker_id", "status"])
    op.create_index("ix_auth_workflow_plans_checker_status", "auth_workflow_plans", ["checker_id", "status"])

    op.create_table(
        "auth_workflow_attachments",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("plan_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["auth_workflow_plans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_workflow_attachments_plan", "auth_workflow_attachments", ["plan_id"])

    op.create_table(
        "auth_workflow_versions",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("plan_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("payload_snapshot", sa.JSON(), nullable=False),
        sa.Column("attachment_snapshot", sa.JSON(), nullable=False),
        sa.Column("submitted_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["auth_workflow_plans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["submitted_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "version_number", name="uq_auth_workflow_versions_plan_version"),
        sa.UniqueConstraint("plan_id", "round_number", name="uq_auth_workflow_versions_plan_round"),
    )

    op.create_table(
        "auth_workflow_events",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("plan_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("actor_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("status_before", sa.String(length=24), nullable=True),
        sa.Column("status_after", sa.String(length=24), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["auth_workflow_plans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "sequence_number", name="uq_auth_workflow_events_plan_sequence"),
    )
    op.create_index("ix_auth_workflow_events_plan_sequence", "auth_workflow_events", ["plan_id", "sequence_number"])

    op.create_table(
        "auth_workflow_decisions",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("plan_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("checker_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("action IN ('APPROVED', 'REJECTED')", name="ck_auth_workflow_decisions_action"),
        sa.ForeignKeyConstraint(["plan_id"], ["auth_workflow_plans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["checker_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "round_number", name="uq_auth_workflow_decisions_plan_round"),
    )


def downgrade() -> None:
    op.drop_table("auth_workflow_decisions")
    op.drop_index("ix_auth_workflow_events_plan_sequence", table_name="auth_workflow_events")
    op.drop_table("auth_workflow_events")
    op.drop_table("auth_workflow_versions")
    op.drop_index("ix_auth_workflow_attachments_plan", table_name="auth_workflow_attachments")
    op.drop_table("auth_workflow_attachments")
    op.drop_index("ix_auth_workflow_plans_checker_status", table_name="auth_workflow_plans")
    op.drop_index("ix_auth_workflow_plans_maker_status", table_name="auth_workflow_plans")
    op.drop_table("auth_workflow_plans")
