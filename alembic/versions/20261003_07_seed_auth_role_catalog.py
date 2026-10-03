"""Ensure Auth roles exist without creating demo user accounts."""
from typing import Sequence, Union
from uuid import UUID

from alembic import op
import sqlalchemy as sa

revision: str = "20261003_07"
down_revision: Union[str, None] = "20260930_06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLE_CATALOG = (
    ("MAKER", "Maker", "Creates and revises marketing plans.", "f9a1d6d2-f2c8-4c9b-9aa0-15b2f4fd2e01"),
    ("CHECKER", "Checker", "Reviews assigned marketing plans.", "f9a1d6d2-f2c8-4c9b-9aa0-15b2f4fd2e02"),
    ("ADMIN", "Administrator", "Administrative role foundation.", "f9a1d6d2-f2c8-4c9b-9aa0-15b2f4fd2e03"),
)


def upgrade() -> None:
    connection = op.get_bind()
    existing = set(connection.scalars(sa.text("SELECT code FROM roles")).all())
    roles = sa.table(
        "roles",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.String()),
    )
    for code, name, description, role_id in ROLE_CATALOG:
        if code not in existing:
            connection.execute(roles.insert().values(
                id=UUID(role_id), code=code, name=name, description=description,
            ))


def downgrade() -> None:
    connection = op.get_bind()
    roles = sa.table("roles", sa.column("id", sa.Uuid()))
    assignments = sa.table("user_roles", sa.column("role_id", sa.Uuid()))
    for _, _, _, role_id in ROLE_CATALOG:
        connection.execute(
            sa.delete(roles).where(roles.c.id == UUID(role_id)).where(
                ~sa.exists(sa.select(assignments.c.role_id).where(
                    assignments.c.role_id == roles.c.id,
                ))
            )
        )
