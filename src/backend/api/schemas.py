"""HTTP DTOs; domain schemas remain framework independent."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class DTO(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Mutation(DTO):
    expected_revision: int = Field(ge=0)


class DraftPayload(DTO):
    # Drafts may be incomplete; business completeness is checked on submission.
    title: str = ''
    objective: str = ''
    summary: str = ''
    department: str = ''
    checker_id: str = ''
    start_date: str = ''
    end_date: str = ''
    budget_minor_units: str = ''
    currency: str = ''
    target_audience: str = ''
    channels: list[str] = Field(default_factory=list)
    kpi_expected: str = ''
    notes: str = ''


class Draft(Mutation):
    payload: DraftPayload


class Submission(Mutation):
    expected_policy_version: str = Field(min_length=1)


class HumanDecisionRequest(Mutation):
    action: Literal['APPROVED', 'REJECTED']
    reason: str | None = None
    override_reason: str | None = None


class ErrorResponse(DTO):
    code: str
    message: str
    correlation_id: str
    http_status: int


class PlanResponse(DTO):
    plan_id: str
    maker_id: str
    payload: dict[str, Any]
    attachments: list[dict[str, Any]]
    revision: int
    current_round: int
    state: dict[str, Any]


class HistoryResponse(DTO):
    plan: PlanResponse
    versions: list[dict[str, Any]]
    rounds: list[dict[str, Any]]
    records: list[dict[str, Any]]
    audit: list[dict[str, Any]]

class SubmissionResponse(DTO):
    snapshot: dict[str, Any]
    input_hash: str
    round: dict[str, Any]
    evaluation_ticket: dict[str, Any]


class EvaluationResponse(DTO):
    evaluation: dict[str, Any]
    decision: dict[str, Any]
    questions: list[dict[str, Any]]


class VerifyResponse(DTO):
    run_id: str
    suite: str
    rows: list[dict[str, Any]]
