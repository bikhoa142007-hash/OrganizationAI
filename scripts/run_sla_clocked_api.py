"""Start a test-only API whose workflow clock is read from a private mounted file.

This helper is for isolated PostgreSQL/browser acceptance runs. It adds no API
route and must never be used with an application database.
"""
from datetime import datetime as BaseDatetime, timezone
import json
import os
from pathlib import Path
import sys


repository_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repository_root))

clock_file = Path(os.environ["SLA_TEST_CLOCK_FILE"])


def _clock_now() -> BaseDatetime:
    value = json.loads(clock_file.read_text(encoding="utf-8"))["now"]
    current = BaseDatetime.fromisoformat(value.replace("Z", "+00:00"))
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("SLA test clock value must include a timezone.")
    return current


class ControlledDatetime(BaseDatetime):
    @classmethod
    def now(cls, tz=None):
        current = _clock_now()
        return current.astimezone(tz) if tz is not None else current.replace(tzinfo=None)


from src.backend.application import auth_sla, auth_workflow, employee_admin

auth_sla.datetime = ControlledDatetime
auth_workflow._now_datetime = lambda: ControlledDatetime.now(timezone.utc)
employee_admin.datetime = ControlledDatetime

import uvicorn
from src.backend.api.app import app


def main() -> None:
    port = int(os.getenv("SLA_TEST_API_PORT", "8008"))
    if not 1 <= port <= 65535:
        raise ValueError("SLA_TEST_API_PORT must be between 1 and 65535.")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


if __name__ == "__main__":
    main()
