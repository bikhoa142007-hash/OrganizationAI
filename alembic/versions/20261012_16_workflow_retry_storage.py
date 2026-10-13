"""Persist one bounded, idempotent evaluation retry per approval round."""

from alembic import op
import sqlalchemy as sa


revision = "20261012_16"
down_revision = "20261012_15"
branch_labels = None
depends_on = None


TABLE = "auth_workflow_evaluation_runs"
DECISIONS_TABLE = "auth_workflow_engine_decisions"


def upgrade() -> None:
    with op.batch_alter_table(TABLE) as batch:
        batch.add_column(sa.Column(
            "attempt_number", sa.Integer(), server_default="1", nullable=False,
        ))
        batch.add_column(sa.Column("retry_parent_run_id", sa.Uuid(as_uuid=True), nullable=True))
        batch.add_column(sa.Column("retry_idempotency_key", sa.String(length=200), nullable=True))
        batch.add_column(sa.Column("retry_request_hash", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("result_disposition", sa.String(length=16), nullable=True))
        batch.create_foreign_key(
            "fk_auth_workflow_ai_run_retry_parent",
            TABLE,
            ["retry_parent_run_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.drop_constraint("uq_auth_workflow_ai_run_plan_round", type_="unique")
        batch.create_unique_constraint(
            "uq_auth_workflow_ai_run_attempt",
            ["plan_id", "round_number", "attempt_number"],
        )
        batch.create_unique_constraint(
            "uq_auth_workflow_ai_run_retry_key",
            ["plan_id", "round_number", "retry_idempotency_key"],
        )
        batch.create_check_constraint(
            "ck_auth_workflow_ai_run_attempt", "attempt_number IN (1, 2)",
        )
        batch.create_check_constraint(
            "ck_auth_workflow_ai_run_retry_metadata",
            "(attempt_number = 1 AND retry_parent_run_id IS NULL AND retry_idempotency_key IS NULL AND retry_request_hash IS NULL) OR "
            "(attempt_number = 2 AND retry_parent_run_id IS NOT NULL AND retry_idempotency_key IS NOT NULL AND retry_request_hash IS NOT NULL)",
        )
        batch.create_check_constraint(
            "ck_auth_workflow_ai_run_result_disposition",
            "result_disposition IS NULL OR result_disposition IN ('APPLIED', 'STALE')",
        )
    with op.batch_alter_table(DECISIONS_TABLE) as batch:
        batch.drop_constraint("uq_auth_workflow_engine_decisions_plan_round", type_="unique")
    op.create_index(
        "uq_auth_workflow_engine_auto_approved_plan_round",
        DECISIONS_TABLE,
        ["plan_id", "round_number"],
        unique=True,
        postgresql_where=sa.text("outcome = 'AUTO_APPROVED'"),
        sqlite_where=sa.text("outcome = 'AUTO_APPROVED'"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    has_retry_history = bind.execute(sa.text(
        f"SELECT count(*) FROM {TABLE} "
        "WHERE attempt_number > 1 OR retry_parent_run_id IS NOT NULL "
        "OR result_disposition IS NOT NULL"
    )).scalar_one()
    if has_retry_history:
        raise RuntimeError("Cannot downgrade while evaluation retry disposition/history exists.")
    duplicate_routing_rows = bind.execute(sa.text(
        f"SELECT count(*) FROM (SELECT plan_id, round_number FROM {DECISIONS_TABLE} "
        "GROUP BY plan_id, round_number HAVING count(*) > 1) AS duplicate_rounds"
    )).scalar_one()
    if duplicate_routing_rows:
        raise RuntimeError("Cannot downgrade while a round has multiple immutable engine routes.")

    op.drop_index("uq_auth_workflow_engine_auto_approved_plan_round", table_name=DECISIONS_TABLE)
    with op.batch_alter_table(DECISIONS_TABLE) as batch:
        batch.create_unique_constraint(
            "uq_auth_workflow_engine_decisions_plan_round",
            ["plan_id", "round_number"],
        )
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_constraint("ck_auth_workflow_ai_run_result_disposition", type_="check")
        batch.drop_constraint("ck_auth_workflow_ai_run_retry_metadata", type_="check")
        batch.drop_constraint("ck_auth_workflow_ai_run_attempt", type_="check")
        batch.drop_constraint("uq_auth_workflow_ai_run_retry_key", type_="unique")
        batch.drop_constraint("uq_auth_workflow_ai_run_attempt", type_="unique")
        batch.drop_constraint("fk_auth_workflow_ai_run_retry_parent", type_="foreignkey")
        batch.drop_column("result_disposition")
        batch.drop_column("retry_request_hash")
        batch.drop_column("retry_idempotency_key")
        batch.drop_column("retry_parent_run_id")
        batch.drop_column("attempt_number")
        batch.create_unique_constraint(
            "uq_auth_workflow_ai_run_plan_round",
            ["plan_id", "round_number"],
        )
