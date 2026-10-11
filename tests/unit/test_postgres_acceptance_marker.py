from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "organizationai_pytest_config", ROOT / "tests" / "conftest.py"
)
assert SPEC is not None and SPEC.loader is not None
pytest_config = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pytest_config)


@pytest.mark.parametrize(
    ("path", "fixtures", "expected"),
    [
        ("tests/integration/test_sla_postgres_acceptance.py", set(), True),
        ("tests/integration/sla/test_database_acceptance.py", {"postgres_session"}, True),
        ("tests/integration/test_notifications.py", {"postgres_workflow"}, True),
        ("tests/integration/test_auth_api.py", set(), False),
        ("tests/unit/test_postgres_target.py", set(), False),
    ],
)
def test_postgres_acceptance_classification(path: str, fixtures: set[str], expected: bool):
    assert pytest_config.requires_temporary_postgres(ROOT / path, fixtures) is expected


def test_collection_hook_adds_postgres_marker_to_future_acceptance_files():
    item = SimpleNamespace(
        path=ROOT / "tests" / "integration" / "test_sla_postgres_acceptance.py",
        fixturenames=[],
        get_closest_marker=lambda _name: None,
        add_marker=Mock(),
    )

    pytest_config.pytest_collection_modifyitems([item])

    item.add_marker.assert_called_once_with(pytest.mark.postgres)
