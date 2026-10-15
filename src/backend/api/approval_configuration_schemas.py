from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ConfigurationKind = Literal[
    "approval_policy", "budget", "media_policy", "strategy_rubric", "authority", "checker_assignment",
]
ConfigurationStatus = Literal["UNCONFIGURED", "DISABLED", "EFFECTIVE", "SCHEDULED", "SUPERSEDED"]


class ConfigurationSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ConfigurationRevisionCreate(ConfigurationSchema):
    expected_revision: int | None = Field(default=None, strict=True, ge=1)
    effective_at: datetime
    change_reason: str = Field(min_length=1, max_length=1000)
    value: dict[str, Any]

    @field_validator("effective_at")
    @classmethod
    def require_utc_effective_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise ValueError("effective_at must be a UTC timestamp.")
        return value.astimezone(timezone.utc)


class ConfigurationRevisionResponse(ConfigurationSchema):
    revision_id: UUID
    kind: ConfigurationKind
    revision: int = Field(ge=1)
    status: ConfigurationStatus
    effective_at: str
    change_reason: str
    value: dict[str, Any]
    configuration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    changed_by: UUID
    created_at: str
    signoff: dict[str, Any] | None = None


class ExpectedConfigurationRevision(ConfigurationSchema):
    revision_id: UUID
    configuration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ApprovalPolicySignoffRequest(ConfigurationSchema):
    expected_revisions: dict[ConfigurationKind, ExpectedConfigurationRevision]


class ApprovalPolicySignoffResponse(ConfigurationSchema):
    revision: ConfigurationRevisionResponse
    replayed: bool


class ConfigurationCurrentItem(ConfigurationSchema):
    kind: ConfigurationKind
    status: Literal["UNCONFIGURED", "DISABLED", "EFFECTIVE"]
    current_revision: ConfigurationRevisionResponse | None
    next_scheduled_revision: ConfigurationRevisionResponse | None


class ConfigurationCurrentResponse(ConfigurationSchema):
    as_of: str
    items: list[ConfigurationCurrentItem]


class ConfigurationHistoryResponse(ConfigurationSchema):
    kind: ConfigurationKind
    as_of: str
    items: list[ConfigurationRevisionResponse]
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    total: int = Field(ge=0)
