import pytest

import scripts.postgres_test_target as target


@pytest.mark.parametrize("scenario", ["legacy-scheme", "external-host", "application-database"])
def test_application_database_target_is_rejected_before_connection_without_echoing_values(monkeypatch, scenario):
    secrets = (
        "synthetic_user",
        "synthetic_password",
        "synthetic_token",
        "render.invalid",
        "production_database",
    )
    if scenario == "legacy-scheme":
        database_url = (
            "postgresql://synthetic_user:synthetic_password@render.invalid/"
            "production_database?token=synthetic_token"
        )
    elif scenario == "external-host":
        database_url = (
            "postgresql+psycopg://synthetic_user:synthetic_password@render.invalid/"
            "production_database?token=synthetic_token"
        )
    else:
        database_url = (
            "postgresql+psycopg://organizationai_test:synthetic_password@127.0.0.1:5432/"
            "production_database?token=synthetic_token"
        )
    environment = {
        "DATABASE_URL": database_url,
        "POSTGRES_TEST_DATABASE": "organizationai_test_synthetic-run-2026",
        "POSTGRES_TEST_USER": "organizationai_test",
        "POSTGRES_TEST_RUN_ID": "synthetic-run-2026",
    }

    def no_connection(*args, **kwargs):
        pytest.fail("An application target must be rejected before connecting.")

    monkeypatch.setattr(target, "create_engine", no_connection)
    with pytest.raises(RuntimeError) as error:
        target.verify_runner_provisioned_database(environment)

    diagnostic = f"{error.type.__name__}: {error.value}"
    assert "No database writes were attempted" in diagnostic
    assert all(secret not in diagnostic for secret in secrets)
    assert "postgresql://" not in diagnostic
    assert "postgresql+psycopg://" not in diagnostic


def test_runner_target_verifies_database_and_role_before_returning_url(monkeypatch):
    run_id = "synthetic-run-2026"
    database = f"organizationai_test_{run_id}"
    environment = {
        "DATABASE_URL": (
            f"postgresql+psycopg://organizationai_test:synthetic-password@"
            f"127.0.0.1:5432/{database}"
        ),
        "POSTGRES_TEST_DATABASE": database,
        "POSTGRES_TEST_USER": "organizationai_test",
        "POSTGRES_TEST_RUN_ID": run_id,
    }

    class Result:
        def one(self):
            return database, "organizationai_test"

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, statement):
            assert "current_database()" in str(statement)
            return Result()

    class Engine:
        disposed = False

        def connect(self):
            return Connection()

        def dispose(self):
            self.disposed = True

    engine = Engine()
    captured = {}

    def create_readonly_engine(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return engine

    monkeypatch.setattr(target, "create_engine", create_readonly_engine)

    verified = target.verify_runner_provisioned_database(environment)

    assert verified.database == database
    assert captured["kwargs"]["connect_args"] == {
        "options": "-c default_transaction_read_only=on",
    }
    assert engine.disposed
