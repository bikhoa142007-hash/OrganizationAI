from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
POSTGRES_ACCEPTANCE_TEST = (
    "tests/integration/test_auth_workflow_postgres_notifications.py::"
    "test_postgres_notification_lifecycle_permissions_replay_and_rollback"
)


def test_invalid_postgres_target_error_does_not_echo_connection_credentials():
    fake_values = (
        "synthetic_user",
        "synthetic_password",
        "synthetic_token",
        "synthetic_seed_password",
        "render.invalid",
        "synthetic_db",
    )
    environment = os.environ.copy()
    environment.update({
        "DATABASE_URL": (
            "postgresql://synthetic_user:synthetic_password@render.invalid/"
            "synthetic_db?token=synthetic_token"
        ),
        "AUTH_SEED_PASSWORD": "synthetic_seed_password",
        "POSTGRES_TEST_DATABASE": "organizationai_test_synthetic-run-2026",
        "POSTGRES_TEST_USER": "organizationai_test",
        "POSTGRES_TEST_RUN_ID": "synthetic-run-2026",
    })

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            POSTGRES_ACCEPTANCE_TEST,
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    report = result.stdout + result.stderr

    assert result.returncode != 0, "An application database target must be rejected."
    assert "PostgreSQL test target" in report or "temporary PostgreSQL" in report
    assert "postgresql://" not in report
    assert all(value not in report for value in fake_values)
