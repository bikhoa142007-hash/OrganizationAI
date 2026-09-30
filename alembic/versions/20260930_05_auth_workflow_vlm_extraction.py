"""Persist Local VLM model identity and immutable extraction provenance."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260930_05"
down_revision: Union[str, None] = "20260929_04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "auth_workflow_evaluation_runs",
        sa.Column("model_id", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "auth_workflow_evaluation_runs",
        sa.Column("visual_extraction", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("auth_workflow_evaluation_runs", "visual_extraction")
    op.drop_column("auth_workflow_evaluation_runs", "model_id")
