"""Persist Media Compliance and Strategy Evaluation as separate steps."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260930_06"
down_revision: Union[str, None] = "20260930_05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "auth_workflow_evaluation_runs",
        sa.Column("media_evaluation", sa.JSON(), nullable=True),
    )
    op.add_column(
        "auth_workflow_evaluation_runs",
        sa.Column("strategy_evaluation", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("auth_workflow_evaluation_runs", "strategy_evaluation")
    op.drop_column("auth_workflow_evaluation_runs", "media_evaluation")
