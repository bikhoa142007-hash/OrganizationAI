"""Add disabled-by-default auto-reject revisions and immutable Policy Owner sign-off."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261016_18"
down_revision: Union[str, None] = "20261015_17"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_KINDS = "'approval_policy', 'budget', 'media_policy', 'strategy_rubric', 'authority', 'checker_assignment'"
NEW_KINDS = OLD_KINDS + ", 'auto_reject_policy'"
IMMUTABLE_FUNCTION = """
CREATE FUNCTION reject_auth_workflow_auto_reject_signoff_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Auto-reject Policy Owner sign-offs are immutable';
END;
$$
"""


def _replace_kind_check(table_name: str, old_kinds: str, new_kinds: str) -> None:
    constraint_name = "ck_workflow_config_heads_kind" if table_name.endswith("heads") else "ck_workflow_config_revisions_kind"
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table_name, recreate="always") as batch:
            batch.drop_constraint(constraint_name, type_="check")
            batch.create_check_constraint(constraint_name, f"kind IN ({new_kinds})")
    else:
        op.drop_constraint(constraint_name, table_name, type_="check")
        op.create_check_constraint(constraint_name, table_name, f"kind IN ({new_kinds})")


def upgrade() -> None:
    _replace_kind_check("auth_workflow_configuration_heads", OLD_KINDS, NEW_KINDS)
    _replace_kind_check("auth_workflow_configuration_revisions", OLD_KINDS, NEW_KINDS)
    op.execute(sa.text(
        "INSERT INTO auth_workflow_configuration_heads (kind, latest_revision) "
        "VALUES ('auto_reject_policy', 0) ON CONFLICT (kind) DO NOTHING"
        if op.get_bind().dialect.name != "sqlite"
        else "INSERT OR IGNORE INTO auth_workflow_configuration_heads (kind, latest_revision) VALUES ('auto_reject_policy', 0)"
    ))
    op.create_table(
        "auth_workflow_auto_reject_policy_signoffs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_revision_id", sa.Uuid(), nullable=False),
        sa.Column("auto_reject_policy_revision_id", sa.Uuid(), nullable=False),
        sa.Column("approved_configuration_hash", sa.String(length=64), nullable=False),
        sa.Column("policy_owner_id", sa.Uuid(), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("configuration_revisions", sa.JSON(), nullable=False),
        sa.CheckConstraint("length(approved_configuration_hash) = 64", name="ck_auto_reject_signoffs_policy_hash"),
        sa.ForeignKeyConstraint(["candidate_revision_id"], ["auth_workflow_configuration_revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["auto_reject_policy_revision_id"], ["auth_workflow_configuration_revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["policy_owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_revision_id", name="uq_auto_reject_signoffs_candidate_revision"),
        sa.UniqueConstraint("auto_reject_policy_revision_id", name="uq_auto_reject_signoffs_policy_revision"),
    )
    op.create_index(
        "ix_auto_reject_signoffs_policy_revision",
        "auth_workflow_auto_reject_policy_signoffs",
        ["auto_reject_policy_revision_id", "approved_configuration_hash"],
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(IMMUTABLE_FUNCTION)
        op.execute(
            "CREATE TRIGGER trg_auth_workflow_auto_reject_signoff_immutable "
            "BEFORE UPDATE OR DELETE ON auth_workflow_auto_reject_policy_signoffs "
            "FOR EACH ROW EXECUTE FUNCTION reject_auth_workflow_auto_reject_signoff_mutation()"
        )


def downgrade() -> None:
    bind = op.get_bind()
    signoffs = bind.execute(sa.text(
        "SELECT count(*) FROM auth_workflow_auto_reject_policy_signoffs"
    )).scalar_one()
    revisions = bind.execute(sa.text(
        "SELECT count(*) FROM auth_workflow_configuration_revisions WHERE kind = 'auto_reject_policy'"
    )).scalar_one()
    if signoffs or revisions:
        raise RuntimeError("Cannot downgrade while auto-reject policy history or sign-offs exist.")
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER trg_auth_workflow_auto_reject_signoff_immutable ON auth_workflow_auto_reject_policy_signoffs")
        op.execute("DROP FUNCTION reject_auth_workflow_auto_reject_signoff_mutation()")
    op.drop_index("ix_auto_reject_signoffs_policy_revision", table_name="auth_workflow_auto_reject_policy_signoffs")
    op.drop_table("auth_workflow_auto_reject_policy_signoffs")
    op.execute(sa.text("DELETE FROM auth_workflow_configuration_heads WHERE kind = 'auto_reject_policy'"))
    _replace_kind_check("auth_workflow_configuration_revisions", NEW_KINDS, OLD_KINDS)
    _replace_kind_check("auth_workflow_configuration_heads", NEW_KINDS, OLD_KINDS)
