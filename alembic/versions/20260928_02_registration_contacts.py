"""Add normalized usernames and optional international phone contacts."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260928_02"
down_revision: Union[str, None] = "20260925_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("username", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("phone", sa.String(length=16), nullable=True))
        batch_op.alter_column("email", existing_type=sa.String(length=320), nullable=True)
        batch_op.create_unique_constraint("uq_users_username", ["username"])
        batch_op.create_unique_constraint("uq_users_phone", ["phone"])
        batch_op.create_check_constraint(
            "ck_users_exactly_one_contact",
            "(email IS NOT NULL AND phone IS NULL) OR (email IS NULL AND phone IS NOT NULL)",
        )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT user_code, email FROM users ORDER BY user_code")
    ).mappings().all()
    used: set[str] = set()
    for row in rows:
        email = row["email"] or ""
        base = email.split("@", 1)[0].strip().lower()
        username = "".join(char if char.isalnum() or char in "._-" else "_" for char in base)
        if len(username) < 3:
            username = row["user_code"].lower().replace("-", "_")
        username = username[:72]
        if username in used:
            suffix_id = "".join(char for char in row["user_code"] if char.isdigit())[-8:]
            suffix = "_" + (suffix_id or "legacy")
            original = username
            username = original[:80 - len(suffix)] + suffix
            counter = 2
            while username in used:
                numbered_suffix = f"{suffix}_{counter}"
                username = original[:80 - len(numbered_suffix)] + numbered_suffix
                counter += 1
        used.add(username)
        connection.execute(
            sa.text("UPDATE users SET username = :username WHERE user_code = :user_code"),
            {"username": username, "user_code": row["user_code"]},
        )

    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "username", existing_type=sa.String(length=80), nullable=False
        )


def downgrade() -> None:
    connection = op.get_bind()
    phone_only_count = connection.scalar(
        sa.text("SELECT count(*) FROM users WHERE email IS NULL")
    )
    if phone_only_count:
        raise RuntimeError(
            "Cannot remove phone registration while phone-only accounts exist; add email first."
        )

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("ck_users_exactly_one_contact", type_="check")
        batch_op.drop_constraint("uq_users_phone", type_="unique")
        batch_op.drop_constraint("uq_users_username", type_="unique")
        batch_op.alter_column("email", existing_type=sa.String(length=320), nullable=False)
        batch_op.drop_column("phone")
        batch_op.drop_column("username")
