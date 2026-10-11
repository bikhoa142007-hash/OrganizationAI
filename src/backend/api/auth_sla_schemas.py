"""Typed API contracts for SLA configuration and plan status."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.backend.application.sla_rules import MAX_SLA_DURATION_MINUTES


class SlaApiDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SlaConfigurationUpdateRequest(SlaApiDTO):
    enabled: bool = Field(strict=True)
    duration_minutes: int = Field(strict=True, ge=1, le=MAX_SLA_DURATION_MINUTES)
    warning_before_minutes: int = Field(strict=True, ge=1)
    expected_revision: int = Field(strict=True, ge=0)
    change_reason: str = Field(strict=True, min_length=1, max_length=1000)


class SlaConfigurationResponse(SlaApiDTO):
    configured: bool
    revision: int
    enabled: bool
    duration_minutes: int | None
    warning_before_minutes: int | None
    changed_by_id: str | None
    changed_by_name: str | None
    change_reason: str | None
    updated_at: datetime | None


class SlaConfigurationHistoryResponse(SlaApiDTO):
    items: list[SlaConfigurationResponse]
    offset: int
    limit: int
    total: int


class WorkflowSlaRoundResponse(SlaApiDTO):
    version_number: int
    round_number: int
    applicable: bool
    status: Literal[
        "NOT_APPLICABLE",
        "IN_PROGRESS",
        "WARNING",
        "OVERDUE",
        "CLOSED_ON_TIME",
        "CLOSED_LATE",
    ]
    configuration_revision: int | None
    duration_minutes: int | None
    warning_before_minutes: int | None
    started_at: datetime | None
    warning_at: datetime | None
    due_at: datetime | None
    closed_at: datetime | None
    seconds_until_due: int | None
