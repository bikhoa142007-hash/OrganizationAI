from datetime import datetime, timedelta, timezone

import pytest

from src.backend.application.sla_rules import (
    MAX_SLA_DURATION_MINUTES,
    SlaStatus,
    calculate_deadlines,
    calculate_status,
    validate_sla_duration,
)

UTC = timezone.utc


def test_sla_duration_requires_positive_integer_minutes_and_valid_warning():
    validate_sla_duration(60, 15)
    validate_sla_duration(MAX_SLA_DURATION_MINUTES, 1)

    for duration, warning in (
        (0, 1),
        (-1, 1),
        (60, 0),
        (60, 60),
        (MAX_SLA_DURATION_MINUTES + 1, 1),
        (60.5, 15),
        (float("nan"), 15),
        (True, 1),
        ("60", 15),
    ):
        with pytest.raises(ValueError):
            validate_sla_duration(duration, warning)


def test_sla_deadlines_are_derived_from_one_timezone_aware_start():
    started_at = datetime(2026, 10, 11, 8, 0, tzinfo=UTC)

    result = calculate_deadlines(started_at, duration_minutes=90, warning_before_minutes=20)

    assert result.started_at == started_at
    assert result.warning_at == started_at + timedelta(minutes=70)
    assert result.due_at == started_at + timedelta(minutes=90)

    with pytest.raises(ValueError):
        calculate_deadlines(datetime(2026, 10, 11, 8, 0), 90, 20)


def test_sla_status_boundaries_are_half_open_and_closure_uses_due_inclusively():
    started_at = datetime(2026, 10, 11, 8, 0, tzinfo=UTC)
    deadlines = calculate_deadlines(started_at, 60, 15)

    assert calculate_status(deadlines, None, deadlines.warning_at - timedelta(seconds=1)) is SlaStatus.IN_PROGRESS
    assert calculate_status(deadlines, None, deadlines.warning_at) is SlaStatus.WARNING
    assert calculate_status(deadlines, None, deadlines.due_at - timedelta(seconds=1)) is SlaStatus.WARNING
    assert calculate_status(deadlines, None, deadlines.due_at) is SlaStatus.OVERDUE
    assert calculate_status(deadlines, deadlines.due_at - timedelta(seconds=1), deadlines.due_at) is SlaStatus.CLOSED_ON_TIME
    assert calculate_status(deadlines, deadlines.due_at, deadlines.due_at) is SlaStatus.CLOSED_LATE
    assert calculate_status(deadlines, deadlines.due_at + timedelta(seconds=1), deadlines.due_at) is SlaStatus.CLOSED_LATE


def test_status_calculation_requires_aware_now():
    deadlines = calculate_deadlines(datetime(2026, 10, 11, 8, 0, tzinfo=UTC), 60, 15)

    with pytest.raises(ValueError):
        calculate_status(deadlines, None, datetime(2026, 10, 11, 8, 30))
