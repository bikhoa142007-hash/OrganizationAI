import os
from types import SimpleNamespace

import scripts.run_render_build_tests as runner
from scripts.run_render_build_tests import isolate_database_environment


def test_render_build_tests_remove_database_environment_from_child_only():
    parent = {
        "APP_ENV": "demo",
        "AUTH_DATABASE_URL": "postgresql://app-user:app-password@db.invalid/app",
        "DATABASE_URL": "postgresql://runtime-user:runtime-password@db.invalid/app",
        "DB_CONNECTION_STRING": "db-secret-value",
        "DEMO_DATABASE": "/tmp/app.sqlite3",
        "PGHOST": "db.internal",
        "PGPASSWORD": "pg-password",
        "POSTGRES_TEST_RUN_ID": "runner-marker",
        "SQLALCHEMY_DATABASE_URI": "postgresql://sql-user:sql-password@db.invalid/app",
        "JWT_SECRET": "unrelated-auth-secret",
    }
    original = dict(parent)

    child, removed = isolate_database_environment(parent)

    assert set(removed) == {
        "AUTH_DATABASE_URL",
        "DATABASE_URL",
        "DB_CONNECTION_STRING",
        "DEMO_DATABASE",
        "PGHOST",
        "PGPASSWORD",
        "POSTGRES_TEST_RUN_ID",
        "SQLALCHEMY_DATABASE_URI",
    }
    assert set(child) == {"APP_ENV", "JWT_SECRET"}
    assert parent == original


def test_runner_filters_only_the_child_environment(monkeypatch, capsys):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://synthetic-user:synthetic-password@render.invalid/runtime",
    )
    monkeypatch.setenv("PGPASSWORD", "synthetic-pg-password")
    monkeypatch.setenv("APP_ENV", "demo")
    parent_before = dict(os.environ)
    captured = {}

    def fake_run(command, *, cwd, env, check):
        captured.update(command=command, cwd=cwd, env=env, check=check)
        return SimpleNamespace(returncode=17)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    exit_code = runner.run_render_build_tests()

    assert exit_code == 17
    assert captured["env"].get("DATABASE_URL") is None
    assert captured["env"].get("PGPASSWORD") is None
    assert captured["env"]["APP_ENV"] == "demo"
    assert captured["command"][-2:] == ["-m", "not postgres"]
    assert captured["check"] is False
    assert dict(os.environ) == parent_before
    assert "synthetic-password" not in capsys.readouterr().out