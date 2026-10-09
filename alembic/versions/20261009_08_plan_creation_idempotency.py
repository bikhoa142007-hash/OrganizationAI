"""Persist Maker draft creation intents so network retries do not duplicate plans."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261009_08"
down_revision: Union[str, None] = "20261003_07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "auth_workflow_plans",
        sa.Column("creation_idempotency_key", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "auth_workflow_plans",
        sa.Column("creation_request_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "uq_auth_workflow_plans_maker_creation_key",
        "auth_workflow_plans",
        ["maker_id", "creation_idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_auth_workflow_plans_maker_creation_key",
        table_name="auth_workflow_plans",
    )
    op.drop_column("auth_workflow_plans", "creation_request_hash")
    op.drop_column("auth_workflow_plans", "creation_idempotency_key")
