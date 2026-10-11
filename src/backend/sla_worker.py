"""Opt-in continuous-hour SLA reminder worker.

Run ``python -m src.backend.sla_worker --once`` for a single bounded scan, or
omit ``--once`` to run an explicitly started polling process. The API never
starts this worker implicitly.
"""
import argparse
import logging
import time

from src.backend.application.auth_sla import process_due_sla_notifications
from src.backend.db.session import get_session_factory


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send configured approval SLA reminders.")
    parser.add_argument("--once", action="store_true", help="process one bounded batch and exit")
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument("--batch-size", type=int, default=100)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not 1 <= args.interval_seconds <= 86_400:
        raise SystemExit("--interval-seconds must be between 1 and 86400")
    if not 1 <= args.batch_size <= 1000:
        raise SystemExit("--batch-size must be between 1 and 1000")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    factory = get_session_factory()
    try:
        while True:
            created = process_due_sla_notifications(factory, batch_size=args.batch_size)
            logging.info("SLA scan complete; notifications_created=%s", created)
            if args.once:
                return 0
            time.sleep(args.interval_seconds)
    except KeyboardInterrupt:
        logging.info("SLA worker stopped by operator")
        return 0

if __name__ == "__main__":
    raise SystemExit(main())