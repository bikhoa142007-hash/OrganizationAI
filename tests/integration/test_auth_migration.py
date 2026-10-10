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
    with engine.connect() as connection:
        assert set(connection.scalars(text("SELECT code FROM roles")).all()) == {
            "MAKER", "CHECKER", "ADMIN",
        }
        assert connection.scalar(text("SELECT count(*) FROM users")) == 0
    assert {
        "users", "roles", "user_roles", "alembic_version",
        "auth_workflow_plans", "auth_workflow_attachments", "auth_workflow_versions",
        "auth_workflow_events", "auth_workflow_decisions",
        "auth_workflow_evaluation_runs", "auth_workflow_engine_decisions",
        "employee_profiles", "role_permissions", "auth_management_tokens", "admin_audit_events",
    } <= set(inspector.get_table_names())
    assert {"id", "user_code", "username", "email", "phone", "password_hash", "display_name", "status",
            "department", "job_title", "employment_start_date", "employment_status",
            "activation_pending", "session_version", "created_at", "updated_at"} == {
        column["name"] for column in inspector.get_columns("users")
    }
    columns = {column["name"]: column for column in inspector.get_columns("users")}
    assert {"activation_pending", "session_version"} <= set(columns)
    assert columns["username"]["nullable"] is False
    assert columns["email"]["nullable"] is True
    assert columns["phone"]["nullable"] is True
    unique_constraints = inspector.get_unique_constraints("users")
    assert {constraint["name"] for constraint in unique_constraints} >= {
        "uq_users_username", "uq_users_phone",
    }
    assert any(constraint["column_names"] == ["email"] for constraint in unique_constraints)
    role_columns = {column["name"] for column in inspector.get_columns("roles")}
    assert {"is_builtin", "status"} <= role_columns
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM role_permissions")) == 19
        assert connection.scalar(text("SELECT count(*) FROM roles WHERE is_builtin = 1")) == 3
    assert "ck_roles_status" in {
        constraint["name"] for constraint in inspector.get_check_constraints("roles")
    }
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
    assert {"creation_idempotency_key", "creation_request_hash"} <= {
        column["name"] for column in inspector.get_columns("auth_workflow_plans")
    }
    assert any(
        index["name"] == "uq_auth_workflow_plans_maker_creation_key" and index["unique"]
        for index in inspector.get_indexes("auth_workflow_plans")
    )
    assert {"content", "content_hash", "uploaded_by"} <= {
        column["name"] for column in inspector.get_columns("auth_workflow_attachments")
    }
    assert "sequence_number" in {
        column["name"] for column in inspector.get_columns("auth_workflow_events")
    }
    assert {"actor_type", "actor_id"} <= {
        column["name"] for column in inspector.get_columns("auth_workflow_events")
    }
    assert next(
        column for column in inspector.get_columns("auth_workflow_events")
        if column["name"] == "actor_id"
    )["nullable"] is True
    assert "snapshot_hash" in {
        column["name"] for column in inspector.get_columns("auth_workflow_versions")
    }
    assert "override_reason" in {
        column["name"] for column in inspector.get_columns("auth_workflow_decisions")
    }
    ai_runs = {column["name"] for column in inspector.get_columns("auth_workflow_evaluation_runs")}
    assert {
        "run_id", "evaluation_id", "input_hash", "provider", "model_version", "attempts", "retried",
        "policy_snapshot", "evaluation", "visual_extraction", "media_evaluation",
        "strategy_evaluation", "failure_reason",
    } <= ai_runs
    ai_run_uniques = inspector.get_unique_constraints("auth_workflow_evaluation_runs")
    assert any(item["column_names"] == ["plan_id", "round_number"] for item in ai_run_uniques)
    engine_decision_uniques = inspector.get_unique_constraints("auth_workflow_engine_decisions")
    assert any(item["column_names"] == ["plan_id", "round_number"] for item in engine_decision_uniques)
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
            "SELECT id, user_code, username, email, phone, department, job_title, "
            "employment_start_date, employment_status FROM users ORDER BY user_code"
        )).mappings().all()
        profiles = connection.execute(text(
            "SELECT user_code, user_id, department, job_title, employment_start_date, employment_status "
            "FROM employee_profiles ORDER BY user_code"
        )).mappings().all()
    assert [(user["username"], user["email"], user["phone"]) for user in users] == [
        ("maker", "maker@example.com", None),
        ("maker_000002", "maker@other.example", None),
    ]
    assert all(user["department"] is None and user["job_title"] is None for user in users)
    assert all(user["employment_start_date"] is None for user in users)
    assert all(user["employment_status"] == "ACTIVE" for user in users)
    assert {profile["user_code"]: profile["user_id"] for profile in profiles} == {
        user["user_code"]: user["id"] for user in users
    }
    assert all(profile["department"] is None and profile["job_title"] is None for profile in profiles)
    assert all(profile["employment_start_date"] is None for profile in profiles)
    assert all(profile["employment_status"] == "ACTIVE" for profile in profiles)
    engine.dispose()
