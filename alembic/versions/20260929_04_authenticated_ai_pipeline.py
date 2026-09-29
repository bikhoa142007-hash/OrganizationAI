"""Persist AI evaluations and deterministic decisions for authenticated rounds."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260929_04"
down_revision: Union[str, None] = "20260928_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "auth_workflow_versions",
        sa.Column("snapshot_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "auth_workflow_events",
        sa.Column("actor_type", sa.String(length=12), server_default="HUMAN", nullable=False),
    )
    with op.batch_alter_table("auth_workflow_events") as batch_op:
        batch_op.alter_column(
            "actor_id", existing_type=sa.Uuid(as_uuid=True), nullable=True
        )
    op.add_column(
        "auth_workflow_decisions",
        sa.Column("override_reason", sa.Text(), nullable=True),
    )

    op.create_table(
        "auth_workflow_evaluation_runs",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("plan_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=100), nullable=False),
        sa.Column("evaluation_id", sa.String(length=100), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("correlation_id", sa.String(length=200), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("model_version", sa.String(length=160), nullable=True),
        sa.Column("policy_version", sa.String(length=160), nullable=False),
        sa.Column("policy_snapshot_id", sa.String(length=160), nullable=False),
        sa.Column("policy_snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("policy_snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("retried", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("evaluation", sa.JSON(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'SUCCEEDED', 'FAILED', 'TIMED_OUT')",
            name="ck_auth_workflow_ai_run_status",
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["auth_workflow_plans.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "round_number", name="uq_auth_workflow_ai_run_plan_round"),
        sa.UniqueConstraint("run_id", name="uq_auth_workflow_ai_run_id"),
        sa.UniqueConstraint("evaluation_id", name="uq_auth_workflow_ai_evaluation_id"),
    )

    op.create_table(
        "auth_workflow_engine_decisions",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("plan_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("evaluation_run_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("decision_id", sa.String(length=100), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("decision", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('AUTO_APPROVED', 'HUMAN_REVIEW_REQUIRED')",
            name="ck_auth_workflow_engine_decisions_outcome",
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["auth_workflow_plans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["evaluation_run_id"], ["auth_workflow_evaluation_runs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "round_number", name="uq_auth_workflow_engine_decisions_plan_round"),
        sa.UniqueConstraint("evaluation_run_id", name="uq_auth_workflow_engine_decisions_run"),
        sa.UniqueConstraint("decision_id", name="uq_auth_workflow_engine_decisions_id"),
    )


def downgrade() -> None:
    op.drop_table("auth_workflow_engine_decisions")
    op.drop_table("auth_workflow_evaluation_runs")
    op.drop_column("auth_workflow_decisions", "override_reason")
    with op.batch_alter_table("auth_workflow_events") as batch_op:
        batch_op.alter_column(
            "actor_id", existing_type=sa.Uuid(as_uuid=True), nullable=False
        )
    op.drop_column("auth_workflow_events", "actor_type")
    op.drop_column("auth_workflow_versions", "snapshot_hash")
