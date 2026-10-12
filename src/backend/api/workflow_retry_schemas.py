from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ManualEvaluationRetryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_plan_version: int = Field(ge=1, strict=True)
    expected_round_revision: int = Field(ge=0, strict=True)


class ManualEvaluationRetryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: UUID
    plan_version: int
    approval_round: int
    run_id: str
    run_status: Literal["PENDING", "PROCESSING", "SUCCEEDED", "FAILED", "TIMED_OUT"]
    processing_stage: str
    decision_id: str | None
    attempt_number: int = Field(ge=1)
    result_disposition: Literal["APPLIED", "STALE"] | None
