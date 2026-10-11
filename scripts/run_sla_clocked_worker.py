"""Run one SLA worker batch using the private mounted test clock file."""
from datetime import datetime
import json
import os
from pathlib import Path
import sys


repository_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repository_root))

clock_file = Path(os.environ["SLA_TEST_CLOCK_FILE"])
value = json.loads(clock_file.read_text(encoding="utf-8"))["now"]
current = datetime.fromisoformat(value.replace("Z", "+00:00"))
if current.tzinfo is None or current.utcoffset() is None:
    raise ValueError("SLA test clock value must include a timezone.")

from src.backend.application.auth_sla import process_due_sla_notifications
from src.backend.db.session import get_session_factory


created = process_due_sla_notifications(get_session_factory(), now=current)
print(f"notifications_created={created}")
