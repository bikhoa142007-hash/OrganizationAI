"""Persist recipient-scoped in-app workflow notifications."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261011_11"
down_revision: Union[str, None] = "20261010_10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auth_workflow_notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("recipient_user_id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("event_key", sa.String(length=200), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('PLAN_SUBMITTED', 'PLAN_APPROVED', 'PLAN_AUTO_APPROVED', 'PLAN_REJECTED')",
            name="ck_auth_workflow_notifications_event_type",
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["auth_workflow_plans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_key", name="uq_auth_workflow_notifications_event_key"),
    )
    op.create_index(
        "ix_auth_workflow_notifications_recipient_created",
        "auth_workflow_notifications", ["recipient_user_id", "created_at"],
    )
    op.create_index(
        "ix_auth_workflow_notifications_recipient_unread",
        "auth_workflow_notifications", ["recipient_user_id", "read_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_auth_workflow_notifications_recipient_unread", table_name="auth_workflow_notifications")
    op.drop_index("ix_auth_workflow_notifications_recipient_created", table_name="auth_workflow_notifications")
    op.drop_table("auth_workflow_notifications")
