"""Persist immutable Policy Owner sign-off for an exact enabled approval policy revision."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261015_17"
down_revision: Union[str, None] = "20261012_16"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


IMMUTABLE_FUNCTION = """
CREATE FUNCTION reject_auth_workflow_approval_policy_signoff_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Approval Policy Owner sign-offs are immutable';
END;
$$
"""


def upgrade() -> None:
    op.create_table(
        "auth_workflow_approval_policy_signoffs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_revision_id", sa.Uuid(), nullable=False),
        sa.Column("approval_policy_revision_id", sa.Uuid(), nullable=False),
        sa.Column("approved_configuration_hash", sa.String(length=64), nullable=False),
        sa.Column("policy_owner_id", sa.Uuid(), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("authority_revision_id", sa.Uuid(), nullable=False),
        sa.Column("authority_configuration_hash", sa.String(length=64), nullable=False),
        sa.Column("configuration_revisions", sa.JSON(), nullable=False),
        sa.CheckConstraint("length(approved_configuration_hash) = 64", name="ck_approval_signoffs_policy_hash"),
        sa.CheckConstraint("length(authority_configuration_hash) = 64", name="ck_approval_signoffs_authority_hash"),
        sa.ForeignKeyConstraint(["candidate_revision_id"], ["auth_workflow_configuration_revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approval_policy_revision_id"], ["auth_workflow_configuration_revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["authority_revision_id"], ["auth_workflow_configuration_revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["policy_owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_revision_id", name="uq_approval_signoffs_candidate_revision"),
        sa.UniqueConstraint("approval_policy_revision_id", name="uq_approval_signoffs_policy_revision"),
    )
    op.create_index(
        "ix_approval_signoffs_policy_revision",
        "auth_workflow_approval_policy_signoffs",
        ["approval_policy_revision_id", "approved_configuration_hash"],
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(IMMUTABLE_FUNCTION)
        op.execute(
            "CREATE TRIGGER trg_auth_workflow_approval_policy_signoff_immutable "
            "BEFORE UPDATE OR DELETE ON auth_workflow_approval_policy_signoffs "
            "FOR EACH ROW EXECUTE FUNCTION reject_auth_workflow_approval_policy_signoff_mutation()"
        )


def downgrade() -> None:
    bind = op.get_bind()
    count = bind.execute(sa.text("SELECT count(*) FROM auth_workflow_approval_policy_signoffs")).scalar_one()
    if count:
        raise RuntimeError("Cannot downgrade while Policy Owner sign-off records exist.")
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER trg_auth_workflow_approval_policy_signoff_immutable ON auth_workflow_approval_policy_signoffs")
        op.execute("DROP FUNCTION reject_auth_workflow_approval_policy_signoff_mutation()")
    op.drop_index("ix_approval_signoffs_policy_revision", table_name="auth_workflow_approval_policy_signoffs")
    op.drop_table("auth_workflow_approval_policy_signoffs")
