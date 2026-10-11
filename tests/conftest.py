"""Shared pytest collection rules for isolated acceptance-test categories."""
from __future__ import annotations

from pathlib import Path

import pytest


def requires_temporary_postgres(test_path: Path, fixture_names: set[str]) -> bool:
    """Classify integration tests by path or fixture so build selection stays broad."""
    return "integration" in test_path.parts and (
        "postgres" in test_path.stem.casefold()
        or any("postgres" in fixture.casefold() for fixture in fixture_names)
    )


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if (
            requires_temporary_postgres(Path(str(item.path)), set(item.fixturenames))
            and item.get_closest_marker("postgres") is None
        ):
            item.add_marker(pytest.mark.postgres)
