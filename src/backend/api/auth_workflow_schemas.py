from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuthWorkflowDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkflowPayload(AuthWorkflowDTO):
    title: str = Field(default="", max_length=200)
    objective: str = Field(default="", max_length=2000)
    summary: str = Field(default="", max_length=10000)
    department: str = Field(default="", max_length=160)
    start_date: str = Field(default="", max_length=10)
    end_date: str = Field(default="", max_length=10)
    budget_minor_units: str = Field(default="", max_length=24)
    currency: str = Field(default="VND", max_length=3)
    target_audience: str = Field(default="", max_length=2000)
    channels: list[str] = Field(default_factory=list, max_length=20)
    kpi_expected: str = Field(default="", max_length=2000)
    notes: str = Field(default="", max_length=5000)


class CreateWorkflowPlanRequest(AuthWorkflowDTO):
    payload: WorkflowPayload = Field(default_factory=WorkflowPayload)
    checker_user_id: UUID | None = None


class UpdateWorkflowPlanRequest(AuthWorkflowDTO):
    expected_revision: int = Field(ge=0)
    payload: WorkflowPayload
    checker_user_id: UUID | None = None


class SubmitWorkflowPlanRequest(AuthWorkflowDTO):
    expected_revision: int = Field(ge=0)


class WorkflowDecisionRequest(AuthWorkflowDTO):
    action: Literal["APPROVED", "REJECTED"]
    reason: str | None = Field(default=None, max_length=5000)
    override_reason: str | None = Field(default=None, max_length=5000)


class WorkflowAttachmentResponse(AuthWorkflowDTO):
    id: str
    filename: str
    media_type: str
    byte_size: int
    content_hash: str
    created_at: datetime


class WorkflowEventResponse(AuthWorkflowDTO):
    id: str
    actor_id: str | None
    actor_type: Literal["HUMAN", "SYSTEM"]
    actor_name: str
    action: str
    status_before: str | None
    status_after: str
    details: dict[str, Any]
    created_at: datetime


class WorkflowVersionResponse(AuthWorkflowDTO):
    version_number: int
    round_number: int
    payload: dict[str, Any]
    attachments: list[dict[str, Any]]
    snapshot_hash: str | None
    submitted_by: str
    created_at: datetime


class WorkflowEvaluationResponse(AuthWorkflowDTO):
    id: str
    version_number: int
    round_number: int
    run_id: str
    evaluation_id: str
    correlation_id: str
    input_hash: str
    provider: Literal["LOCAL_VLM", "MOCK_VLM"]
    model_version: str | None
    policy_version: str
    policy_snapshot_id: str
    policy_snapshot_hash: str
    status: Literal["PENDING", "PROCESSING", "SUCCEEDED", "FAILED", "TIMED_OUT"]
    attempts: int
    retried: bool
    evaluation: dict[str, Any] | None
    failure_reason: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class WorkflowEngineDecisionResponse(AuthWorkflowDTO):
    id: str
    version_number: int
    round_number: int
    decision_id: str
    outcome: Literal["AUTO_APPROVED", "HUMAN_REVIEW_REQUIRED"]
    decision: dict[str, Any]
    created_at: datetime


class WorkflowPlanResponse(AuthWorkflowDTO):
    id: str
    code: str
    payload: dict[str, Any]
    status: str
    processing_stage: str
    maker_id: str
    maker_name: str
    checker_id: str | None
    checker_name: str | None
    current_version: int
    current_round: int
    revision: int
    decision_reason: str | None
    attachments: list[WorkflowAttachmentResponse]
    versions: list[WorkflowVersionResponse]
    ai_evaluations: list[WorkflowEvaluationResponse]
    engine_decisions: list[WorkflowEngineDecisionResponse]
    history: list[WorkflowEventResponse]
    created_at: datetime
    updated_at: datetime


class WorkflowCheckerResponse(AuthWorkflowDTO):
    id: str
    display_name: str
