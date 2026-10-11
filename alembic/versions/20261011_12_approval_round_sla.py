"""Persist versioned approval-round SLA settings and deadlines."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261011_12"
down_revision: Union[str, None] = "20261011_11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


IMMUTABLE_CONFIG_FUNCTION = """
CREATE FUNCTION reject_auth_workflow_sla_configuration_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'SLA configuration revisions are immutable';
END;
$$
"""
IMMUTABLE_CONFIG_TRIGGER = """
CREATE TRIGGER trg_auth_workflow_sla_configurations_immutable
BEFORE UPDATE OR DELETE ON auth_workflow_sla_configurations
FOR EACH ROW EXECUTE FUNCTION reject_auth_workflow_sla_configuration_mutation()
"""

SLA_ROUND_GUARD_FUNCTION = """
CREATE FUNCTION guard_auth_workflow_sla_round_snapshot()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'SLA round snapshots cannot be deleted';
    END IF;
    IF (to_jsonb(NEW) - 'closed_at') IS DISTINCT FROM (to_jsonb(OLD) - 'closed_at') THEN
        RAISE EXCEPTION 'SLA round snapshot fields are immutable';
    END IF;
    IF OLD.closed_at IS NOT NULL AND NEW.closed_at IS DISTINCT FROM OLD.closed_at THEN
        RAISE EXCEPTION 'A closed SLA round cannot be reopened or have its close time changed';
    END IF;
    RETURN NEW;
END;
$$
"""
SLA_ROUND_GUARD_TRIGGER = """
CREATE TRIGGER trg_auth_workflow_sla_rounds_immutable
BEFORE UPDATE OR DELETE ON auth_workflow_sla_rounds
FOR EACH ROW EXECUTE FUNCTION guard_auth_workflow_sla_round_snapshot()
"""


def upgrade() -> None:
    op.create_table(
        "auth_workflow_sla_configurations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("warning_before_minutes", sa.Integer(), nullable=False),
        sa.Column("changed_by", sa.Uuid(), nullable=False),
        sa.Column("change_reason", sa.String(length=1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("revision > 0", name="ck_auth_workflow_sla_configurations_revision"),
        sa.CheckConstraint(
            "duration_minutes > 0 AND duration_minutes <= 5256000",
            name="ck_auth_workflow_sla_configurations_duration",
        ),
        sa.CheckConstraint(
            "warning_before_minutes > 0 AND warning_before_minutes < duration_minutes",
            name="ck_auth_workflow_sla_configurations_warning",
        ),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("revision", name="uq_auth_workflow_sla_configurations_revision"),
    )
    op.create_table(
        "auth_workflow_sla_rounds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("configuration_id", sa.Uuid(), nullable=False),
        sa.Column("configuration_revision", sa.Integer(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("warning_before_minutes", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("warning_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("version_number > 0", name="ck_auth_workflow_sla_rounds_version"),
        sa.CheckConstraint("round_number > 0", name="ck_auth_workflow_sla_rounds_round"),
        sa.CheckConstraint(
            "duration_minutes > 0 AND duration_minutes <= 5256000",
            name="ck_auth_workflow_sla_rounds_duration",
        ),
        sa.CheckConstraint(
            "warning_before_minutes > 0 AND warning_before_minutes < duration_minutes",
            name="ck_auth_workflow_sla_rounds_warning",
        ),
        sa.CheckConstraint(
            "started_at < warning_at AND warning_at < due_at",
            name="ck_auth_workflow_sla_rounds_deadlines",
        ),
        sa.CheckConstraint(
            "closed_at IS NULL OR closed_at >= started_at",
            name="ck_auth_workflow_sla_rounds_closed_after_start",
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["auth_workflow_plans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["configuration_id"], ["auth_workflow_sla_configurations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "round_number", name="uq_auth_workflow_sla_rounds_plan_round"),
    )
    op.create_index(
        "ix_auth_workflow_notifications_plan_round_event",
        "auth_workflow_notifications", ["plan_id", "round_number", "event_type"],
    )
    op.create_index(
        "ix_auth_workflow_sla_rounds_open_warning", "auth_workflow_sla_rounds", ["warning_at"],
        postgresql_where=sa.text("closed_at IS NULL"),
    )
    op.create_index(
        "ix_auth_workflow_sla_rounds_open_due", "auth_workflow_sla_rounds", ["due_at"],
        postgresql_where=sa.text("closed_at IS NULL"),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(IMMUTABLE_CONFIG_FUNCTION)
        op.execute(IMMUTABLE_CONFIG_TRIGGER)
        op.execute(SLA_ROUND_GUARD_FUNCTION)
        op.execute(SLA_ROUND_GUARD_TRIGGER)

    with op.batch_alter_table("auth_workflow_notifications") as batch_op:
        batch_op.drop_constraint("ck_auth_workflow_notifications_event_type", type_="check")
        batch_op.create_check_constraint(
            "ck_auth_workflow_notifications_event_type",
            "event_type IN ('PLAN_SUBMITTED', 'PLAN_APPROVED', 'PLAN_AUTO_APPROVED', 'PLAN_REJECTED', 'SLA_WARNING', 'SLA_OVERDUE')",
        )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        op.execute(sa.text("""
            DO $$ BEGIN
                IF EXISTS (SELECT 1 FROM auth_workflow_notifications WHERE event_type IN ('SLA_WARNING', 'SLA_OVERDUE'))
                   OR EXISTS (SELECT 1 FROM auth_workflow_sla_rounds)
                   OR EXISTS (SELECT 1 FROM auth_workflow_sla_configurations)
                THEN RAISE EXCEPTION 'Cannot downgrade SLA migration while SLA history exists';
                END IF;
            END $$;
        """))
    with op.batch_alter_table("auth_workflow_notifications") as batch_op:
        batch_op.drop_constraint("ck_auth_workflow_notifications_event_type", type_="check")
        batch_op.create_check_constraint(
            "ck_auth_workflow_notifications_event_type",
            "event_type IN ('PLAN_SUBMITTED', 'PLAN_APPROVED', 'PLAN_AUTO_APPROVED', 'PLAN_REJECTED')",
        )
    if connection.dialect.name == "postgresql":
        op.execute("DROP TRIGGER trg_auth_workflow_sla_rounds_immutable ON auth_workflow_sla_rounds")
        op.execute("DROP FUNCTION guard_auth_workflow_sla_round_snapshot()")
        op.execute("DROP TRIGGER trg_auth_workflow_sla_configurations_immutable ON auth_workflow_sla_configurations")
        op.execute("DROP FUNCTION reject_auth_workflow_sla_configuration_mutation()")
    op.drop_index("ix_auth_workflow_notifications_plan_round_event", table_name="auth_workflow_notifications")
    op.drop_index("ix_auth_workflow_sla_rounds_open_due", table_name="auth_workflow_sla_rounds")
    op.drop_index("ix_auth_workflow_sla_rounds_open_warning", table_name="auth_workflow_sla_rounds")
    op.drop_table("auth_workflow_sla_rounds")
    op.drop_table("auth_workflow_sla_configurations")
