"""Add shared employee profile fields used by the Admin directory."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261010_09"
down_revision: Union[str, None] = "20261009_08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing Auth accounts remain valid. Their employment attributes are
    # unknown until an authorized administrator fills them in.
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("department", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("job_title", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("employment_start_date", sa.Date(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "employment_status", sa.String(length=16), nullable=False,
                server_default=sa.text("'ACTIVE'"),
            )
        )
        batch_op.create_check_constraint(
            "ck_users_employment_status",
            "employment_status IN ('ACTIVE', 'INACTIVE')",
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("ck_users_employment_status", type_="check")
        batch_op.drop_column("employment_status")
        batch_op.drop_column("employment_start_date")
        batch_op.drop_column("job_title")
        batch_op.drop_column("department")
