"""Read-only preflight for a runner-provisioned PostgreSQL test database."""
from __future__ import annotations

import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.postgres_test_target import verify_runner_provisioned_database


def main() -> int:
    try:
        verify_runner_provisioned_database(os.environ)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1
    print("Temporary PostgreSQL test target verified before writes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
