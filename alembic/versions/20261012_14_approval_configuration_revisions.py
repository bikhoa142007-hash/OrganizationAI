"""Add immutable, effective-dated approval configuration and round snapshots."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261012_14"
down_revision: Union[str, None] = "20261011_12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


IMMUTABLE_FUNCTION = """
CREATE FUNCTION reject_auth_workflow_configuration_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Workflow configuration revisions and round snapshots are immutable';
END;
$$
"""


def upgrade() -> None:
    op.create_table(
        "auth_workflow_configuration_heads",
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("latest_revision", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint(
            "kind IN ('approval_policy', 'budget', 'media_policy', 'strategy_rubric', 'authority', 'checker_assignment')",
            name="ck_workflow_config_heads_kind",
        ),
        sa.CheckConstraint("latest_revision >= 0", name="ck_workflow_config_heads_revision"),
        sa.PrimaryKeyConstraint("kind"),
    )
    head_table = sa.table(
        "auth_workflow_configuration_heads",
        sa.column("kind", sa.String(length=32)),
        sa.column("latest_revision", sa.Integer()),
    )
    op.bulk_insert(head_table, [
        {"kind": kind, "latest_revision": 0}
        for kind in ("approval_policy", "budget", "media_policy", "strategy_rubric", "authority", "checker_assignment")
    ])
    op.create_table(
        "auth_workflow_configuration_locks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_workflow_config_locks_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.bulk_insert(
        sa.table("auth_workflow_configuration_locks", sa.column("id", sa.Integer())),
        [{"id": 1}],
    )
    op.create_table(
        "auth_workflow_configuration_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("change_reason", sa.String(length=1000), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("configuration_hash", sa.String(length=64), nullable=False),
        sa.Column("changed_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('approval_policy', 'budget', 'media_policy', 'strategy_rubric', 'authority', 'checker_assignment')",
            name="ck_workflow_config_revisions_kind",
        ),
        sa.CheckConstraint("revision > 0", name="ck_workflow_config_revisions_revision"),
        sa.CheckConstraint("length(configuration_hash) = 64", name="ck_workflow_config_revisions_hash"),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "revision", name="uq_workflow_config_revisions_kind_revision"),
        sa.UniqueConstraint("kind", "effective_at", name="uq_workflow_config_revisions_kind_effective_at"),
    )
    op.create_index(
        "ix_workflow_config_revisions_effective",
        "auth_workflow_configuration_revisions",
        ["kind", "effective_at", "revision"],
    )
    op.create_table(
        "auth_workflow_round_configuration_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("plan_version", sa.Integer(), nullable=False),
        sa.Column("approval_round", sa.Integer(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("configurations", sa.JSON(), nullable=False),
        sa.Column("checker_assignment", sa.JSON(), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("plan_version > 0", name="ck_workflow_round_config_snapshots_version"),
        sa.CheckConstraint("approval_round > 0", name="ck_workflow_round_config_snapshots_round"),
        sa.CheckConstraint("length(snapshot_hash) = 64", name="ck_workflow_round_config_snapshots_hash"),
        sa.ForeignKeyConstraint(["plan_id"], ["auth_workflow_plans.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "approval_round", name="uq_workflow_round_config_snapshots_plan_round"),
    )
    op.create_index(
        "ix_workflow_round_config_snapshots_plan_version",
        "auth_workflow_round_configuration_snapshots",
        ["plan_id", "plan_version"],
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(IMMUTABLE_FUNCTION)
        for table_name, suffix in (
            ("auth_workflow_configuration_revisions", "revisions"),
            ("auth_workflow_round_configuration_snapshots", "round_snapshots"),
        ):
            op.execute(
                f"CREATE TRIGGER trg_auth_workflow_configuration_{suffix}_immutable "
                f"BEFORE UPDATE OR DELETE ON {table_name} "
                "FOR EACH ROW EXECUTE FUNCTION reject_auth_workflow_configuration_mutation()"
            )


def downgrade() -> None:
    bind = op.get_bind()
    revisions = bind.execute(sa.text(
        "SELECT count(*) FROM auth_workflow_configuration_revisions"
    )).scalar_one()
    snapshots = bind.execute(sa.text(
        "SELECT count(*) FROM auth_workflow_round_configuration_snapshots"
    )).scalar_one()
    if revisions or snapshots:
        raise RuntimeError("Cannot downgrade while immutable workflow configuration history exists.")

    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER trg_auth_workflow_configuration_round_snapshots_immutable ON auth_workflow_round_configuration_snapshots")
        op.execute("DROP TRIGGER trg_auth_workflow_configuration_revisions_immutable ON auth_workflow_configuration_revisions")
        op.execute("DROP FUNCTION reject_auth_workflow_configuration_mutation()")
    op.drop_index(
        "ix_workflow_round_config_snapshots_plan_version",
        table_name="auth_workflow_round_configuration_snapshots",
    )
    op.drop_table("auth_workflow_round_configuration_snapshots")
    op.drop_index(
        "ix_workflow_config_revisions_effective",
        table_name="auth_workflow_configuration_revisions",
    )
    op.drop_table("auth_workflow_configuration_revisions")
    op.drop_table("auth_workflow_configuration_locks")
    op.drop_table("auth_workflow_configuration_heads")
