"""Add independent employee profiles and safe account-management tokens."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261010_10"
down_revision: Union[str, None] = "20261010_09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    op.add_column("users", sa.Column("activation_pending", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("users", sa.Column("session_version", sa.Integer(), server_default="0", nullable=False))
    op.add_column("roles", sa.Column("is_builtin", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("roles", sa.Column("status", sa.String(length=16), server_default="ACTIVE", nullable=False))
    with op.batch_alter_table("roles") as batch_op:
        batch_op.create_check_constraint("ck_roles_status", "status IN ('ACTIVE', 'INACTIVE')")
    op.execute(sa.text("UPDATE roles SET is_builtin = TRUE WHERE code IN ('MAKER', 'CHECKER', 'ADMIN')"))

    op.create_table(
        "employee_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_code", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=16), nullable=True),
        sa.Column("department", sa.String(length=120), nullable=True),
        sa.Column("job_title", sa.String(length=120), nullable=True),
        sa.Column("employment_start_date", sa.Date(), nullable=True),
        sa.Column("employment_status", sa.String(length=16), server_default="ACTIVE", nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("employment_status IN ('ACTIVE', 'INACTIVE')", name="ck_employee_profiles_employment_status"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_code"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("phone"),
        sa.UniqueConstraint("user_id"),
    )
    op.execute(sa.text("""
        INSERT INTO employee_profiles
            (id, user_code, display_name, email, phone, department, job_title,
             employment_start_date, employment_status, user_id)
        SELECT id, user_code, display_name, email, phone, department, job_title,
               employment_start_date, employment_status, id
        FROM users
    """))

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("permission_code", sa.String(length=80), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_code"),
    )
    permission_sets = {
        "MAKER": ("MARKETING_PLAN_READ", "MARKETING_PLAN_CREATE", "MARKETING_PLAN_EDIT_OWN",
                  "MARKETING_ATTACHMENT_MANAGE", "MARKETING_PLAN_SUBMIT", "MARKETING_HISTORY_READ"),
        "CHECKER": ("MARKETING_PLAN_READ", "MARKETING_REVIEW_ASSIGNED", "MARKETING_APPROVE",
                    "MARKETING_REJECT", "MARKETING_HISTORY_READ"),
        "ADMIN": ("MARKETING_PLAN_READ", "MARKETING_PLAN_VIEW_ALL", "MARKETING_HISTORY_READ",
                  "ADMIN_EMPLOYEE_MANAGE", "ADMIN_ROLE_MANAGE", "ADMIN_APPROVER_MANAGE",
                  "ADMIN_SLA_MANAGE", "ADMIN_AUDIT_READ"),
    }
    for code, permissions in permission_sets.items():
        role_id = connection.scalar(sa.text("SELECT id FROM roles WHERE code = :code"), {"code": code})
        if role_id is not None:
            connection.execute(sa.text(
                "INSERT INTO role_permissions (role_id, permission_code) VALUES (:role_id, :permission_code)"
            ), [{"role_id": role_id, "permission_code": permission} for permission in permissions])
    op.create_table(
        "auth_management_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("issued_by", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("purpose IN ('ACTIVATE', 'RESET')", name="ck_auth_management_tokens_purpose"),
        sa.ForeignKeyConstraint(["issued_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_auth_management_tokens_user_purpose", "auth_management_tokens", ["user_id", "purpose", "consumed_at"])
    op.create_table(
        "admin_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=48), nullable=False),
        sa.Column("before_state", sa.JSON(), nullable=True),
        sa.Column("after_state", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["employee_id"], ["employee_profiles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_admin_audit_events_created_at", "admin_audit_events", ["created_at"])


def downgrade() -> None:
    connection = op.get_bind()
    accountless = connection.scalar(sa.text("SELECT count(*) FROM employee_profiles WHERE user_id IS NULL"))
    if accountless:
        raise RuntimeError("Cannot downgrade employee-profile migration while accountless profiles exist.")
    op.drop_index("ix_admin_audit_events_created_at", table_name="admin_audit_events")
    op.drop_table("admin_audit_events")
    op.drop_index("ix_auth_management_tokens_user_purpose", table_name="auth_management_tokens")
    op.drop_table("auth_management_tokens")
    op.drop_table("role_permissions")
    op.drop_table("employee_profiles")
    with op.batch_alter_table("roles") as batch_op:
        batch_op.drop_constraint("ck_roles_status", type_="check")
    op.drop_column("roles", "status")
    op.drop_column("roles", "is_builtin")
    op.drop_column("users", "session_version")
    op.drop_column("users", "activation_pending")
