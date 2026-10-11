"""Pure rules for continuous-time approval SLAs."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

# Technical bound only: keeping dates within datetime/PostgreSQL timestamp arithmetic.
# It is not a business-approved maximum SLA duration.
MAX_SLA_DURATION_MINUTES = 10 * 365 * 24 * 60


class SlaStatus(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    IN_PROGRESS = "IN_PROGRESS"
    WARNING = "WARNING"
    OVERDUE = "OVERDUE"
    CLOSED_ON_TIME = "CLOSED_ON_TIME"
    CLOSED_LATE = "CLOSED_LATE"


@dataclass(frozen=True)
class SlaDeadlines:
    started_at: datetime
    warning_at: datetime
    due_at: datetime


def validate_sla_duration(duration_minutes: object, warning_before_minutes: object) -> None:
    """Validate strict integer-minute settings and their ordering."""
    if type(duration_minutes) is not int or not 0 < duration_minutes <= MAX_SLA_DURATION_MINUTES:
        raise ValueError("SLA duration must be a positive integer within the technical limit.")
    if type(warning_before_minutes) is not int or not 0 < warning_before_minutes < duration_minutes:
        raise ValueError("SLA warning must be a positive integer smaller than the duration.")


def _as_utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone.")
    return value.astimezone(timezone.utc)


def calculate_deadlines(
    started_at: datetime,
    duration_minutes: int,
    warning_before_minutes: int,
) -> SlaDeadlines:
    validate_sla_duration(duration_minutes, warning_before_minutes)
    start = _as_utc(started_at, "started_at")
    try:
        due_at = start + timedelta(minutes=duration_minutes)
        warning_at = due_at - timedelta(minutes=warning_before_minutes)
    except OverflowError as exc:
        raise ValueError("SLA timestamps exceed the supported datetime range.") from exc
    return SlaDeadlines(started_at=start, warning_at=warning_at, due_at=due_at)


def calculate_status(
    deadlines: SlaDeadlines,
    closed_at: datetime | None,
    now: datetime,
) -> SlaStatus:
    """Calculate status using half-open warning/due intervals and inclusive lateness."""
    current = _as_utc(now, "now")
    if closed_at is not None:
        closed = _as_utc(closed_at, "closed_at")
        if closed < deadlines.started_at:
            raise ValueError("closed_at cannot precede started_at.")
        return SlaStatus.CLOSED_LATE if closed >= deadlines.due_at else SlaStatus.CLOSED_ON_TIME
    if current >= deadlines.due_at:
        return SlaStatus.OVERDUE
    if current >= deadlines.warning_at:
        return SlaStatus.WARNING
    return SlaStatus.IN_PROGRESS


def seconds_until_due(deadlines: SlaDeadlines, now: datetime) -> int:
    """Return signed server-calculable seconds remaining until the deadline."""
    current = _as_utc(now, "now")
    return int((deadlines.due_at - current).total_seconds())
