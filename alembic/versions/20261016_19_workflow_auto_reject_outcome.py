"""Persist the disabled-by-default system rejection outcome in Auth workflow."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261016_19"
down_revision: Union[str, None] = "20261016_18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _replace_check(table: str, constraint: str, expression: str) -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table, recreate="always") as batch:
            batch.drop_constraint(constraint, type_="check")
            batch.create_check_constraint(constraint, expression)
    else:
        op.drop_constraint(constraint, table, type_="check")
        op.create_check_constraint(constraint, table, expression)


def upgrade() -> None:
    _replace_check(
        "auth_workflow_engine_decisions",
        "ck_auth_workflow_engine_decisions_outcome",
        "outcome IN ('AUTO_APPROVED', 'HUMAN_REVIEW_REQUIRED', 'AUTO_REJECTED')",
    )
    op.drop_index("uq_auth_workflow_engine_auto_approved_plan_round", table_name="auth_workflow_engine_decisions")
    op.create_index(
        "uq_auth_workflow_engine_auto_final_plan_round",
        "auth_workflow_engine_decisions",
        ["plan_id", "round_number"],
        unique=True,
        postgresql_where=sa.text("outcome IN ('AUTO_APPROVED', 'AUTO_REJECTED')"),
        sqlite_where=sa.text("outcome IN ('AUTO_APPROVED', 'AUTO_REJECTED')"),
    )
    _replace_check(
        "auth_workflow_notifications",
        "ck_auth_workflow_notifications_event_type",
        "event_type IN ('PLAN_SUBMITTED', 'PLAN_APPROVED', 'PLAN_AUTO_APPROVED', 'PLAN_REJECTED', 'PLAN_AUTO_REJECTED', 'SLA_WARNING', 'SLA_OVERDUE')",
    )


def downgrade() -> None:
    bind = op.get_bind()
    decisions = bind.execute(sa.text(
        "SELECT count(*) FROM auth_workflow_engine_decisions WHERE outcome = 'AUTO_REJECTED'"
    )).scalar_one()
    notifications = bind.execute(sa.text(
        "SELECT count(*) FROM auth_workflow_notifications WHERE event_type = 'PLAN_AUTO_REJECTED'"
    )).scalar_one()
    if decisions or notifications:
        raise RuntimeError("Cannot downgrade while system auto-rejection decisions or notifications exist.")
    op.drop_index("uq_auth_workflow_engine_auto_final_plan_round", table_name="auth_workflow_engine_decisions")
    op.create_index(
        "uq_auth_workflow_engine_auto_approved_plan_round",
        "auth_workflow_engine_decisions",
        ["plan_id", "round_number"],
        unique=True,
        postgresql_where=sa.text("outcome = 'AUTO_APPROVED'"),
        sqlite_where=sa.text("outcome = 'AUTO_APPROVED'"),
    )
    _replace_check(
        "auth_workflow_notifications",
        "ck_auth_workflow_notifications_event_type",
        "event_type IN ('PLAN_SUBMITTED', 'PLAN_APPROVED', 'PLAN_AUTO_APPROVED', 'PLAN_REJECTED', 'SLA_WARNING', 'SLA_OVERDUE')",
    )
    _replace_check(
        "auth_workflow_engine_decisions",
        "ck_auth_workflow_engine_decisions_outcome",
        "outcome IN ('AUTO_APPROVED', 'HUMAN_REVIEW_REQUIRED')",
    )
