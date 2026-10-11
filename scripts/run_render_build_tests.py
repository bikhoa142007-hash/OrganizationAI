"""Run the Render backend build tests without inherited database settings."""
from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
_DATABASE_VARIABLE = re.compile(r"(?:^|_)(?:DATABASE|DB)(?:_|$)", re.IGNORECASE)
_EXPLICIT_DATABASE_VARIABLES = frozenset({
    "SQLALCHEMY_URL",
    "SQLALCHEMY_DATABASE_URI",
})


def is_database_environment_variable(name: str) -> bool:
    normalized = name.upper()
    return (
        normalized.startswith(("PG", "POSTGRES"))
        or normalized in _EXPLICIT_DATABASE_VARIABLES
        or _DATABASE_VARIABLE.search(normalized) is not None
    )


def isolate_database_environment(
    source: Mapping[str, str],
) -> tuple[dict[str, str], tuple[str, ...]]:
    """Copy the environment, excluding database connection/configuration values."""
    removed = tuple(sorted(name for name in source if is_database_environment_variable(name)))
    child_environment = {
        name: value for name, value in source.items()
        if not is_database_environment_variable(name)
    }
    return child_environment, removed


def run_render_build_tests(source: Mapping[str, str] | None = None) -> int:
    parent_environment = os.environ if source is None else source
    child_environment, removed = isolate_database_environment(parent_environment)
    if removed:
        print(
            "Running non-PostgreSQL pytest suite with database settings removed "
            f"from the test process: {', '.join(removed)}",
            flush=True,
        )
    else:
        print(
            "Running non-PostgreSQL pytest suite with no inherited database settings.",
            flush=True,
        )

    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-m", "not postgres"],
        cwd=ROOT,
        env=child_environment,
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(run_render_build_tests())
