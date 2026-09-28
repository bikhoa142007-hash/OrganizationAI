from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_auth_migrations_create_registration_ready_identity_tables(tmp_path, monkeypatch):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'auth-migration.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("AUTH_ALLOW_SQLITE_MIGRATION_TESTS", "true")
    config = Config("alembic.ini")

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert {
        "users", "roles", "user_roles", "alembic_version",
        "auth_workflow_plans", "auth_workflow_attachments", "auth_workflow_versions",
        "auth_workflow_events", "auth_workflow_decisions",
    } <= set(inspector.get_table_names())
    assert {"id", "user_code", "username", "email", "phone", "password_hash", "display_name", "status",
            "created_at", "updated_at"} == {column["name"] for column in inspector.get_columns("users")}
    columns = {column["name"]: column for column in inspector.get_columns("users")}
    assert columns["username"]["nullable"] is False
    assert columns["email"]["nullable"] is True
    assert columns["phone"]["nullable"] is True
    unique_constraints = inspector.get_unique_constraints("users")
    assert {constraint["name"] for constraint in unique_constraints} >= {
        "uq_users_username", "uq_users_phone",
    }
    assert any(constraint["column_names"] == ["email"] for constraint in unique_constraints)
    assert "ck_users_exactly_one_contact" in {
        constraint["name"] for constraint in inspector.get_check_constraints("users")
    }
    assert {"user_id", "role_id", "assigned_at", "assigned_by"} == {
        column["name"] for column in inspector.get_columns("user_roles")
    }
    assert inspector.get_pk_constraint("user_roles")["constrained_columns"] == ["user_id", "role_id"]
    assert {"maker_id", "checker_id", "status", "current_version", "current_round", "revision"} <= {
        column["name"] for column in inspector.get_columns("auth_workflow_plans")
    }
    assert {"content", "content_hash", "uploaded_by"} <= {
        column["name"] for column in inspector.get_columns("auth_workflow_attachments")
    }
    assert "sequence_number" in {
        column["name"] for column in inspector.get_columns("auth_workflow_events")
    }
    decision_uniques = inspector.get_unique_constraints("auth_workflow_decisions")
    assert any(item["column_names"] == ["plan_id", "round_number"] for item in decision_uniques)
    event_uniques = inspector.get_unique_constraints("auth_workflow_events")
    assert any(item["column_names"] == ["plan_id", "sequence_number"] for item in event_uniques)

    command.downgrade(config, "base")
    assert not {"users", "roles", "user_roles"}.intersection(inspect(engine).get_table_names())
    engine.dispose()


def test_registration_migration_backfills_legacy_usernames_and_preserves_email_users(
    tmp_path, monkeypatch,
):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'auth-backfill.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("AUTH_ALLOW_SQLITE_MIGRATION_TESTS", "true")
    config = Config("alembic.ini")

    command.upgrade(config, "20260925_01")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO users (id, user_code, email, password_hash, display_name, status)
            VALUES
              ('11111111-1111-1111-1111-111111111111', 'USR-000001', 'maker@example.com', 'hash', 'Maker', 'ACTIVE'),
              ('22222222-2222-2222-2222-222222222222', 'USR-000002', 'maker@other.example', 'hash', 'Maker Two', 'ACTIVE')
        """))

    command.upgrade(config, "head")

    with engine.connect() as connection:
        users = connection.execute(text(
            "SELECT user_code, username, email, phone FROM users ORDER BY user_code"
        )).mappings().all()
    assert [(user["username"], user["email"], user["phone"]) for user in users] == [
        ("maker", "maker@example.com", None),
        ("maker_000002", "maker@other.example", None),
    ]
    engine.dispose()
