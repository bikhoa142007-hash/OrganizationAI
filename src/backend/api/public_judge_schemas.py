"""Strict request models for the unauthenticated, isolated Challenge A Judge."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr


class PublicJudgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PublicJudgeRunRequest(PublicJudgeRequest):
    suite: Literal["general", "escalation"]


class PublicJudgeInputRequest(PublicJudgeRequest):
    title: StrictStr = Field(min_length=3, max_length=120)
    department: StrictStr = Field(min_length=1, max_length=80)
    objective: StrictStr = Field(min_length=1, max_length=500)
    summary: StrictStr = Field(min_length=1, max_length=1000)
    target_audience: StrictStr = Field(min_length=1, max_length=200)
    channel: StrictStr = Field(min_length=1, max_length=80)
    currency: StrictStr = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    budget_vnd: StrictInt = Field(ge=0, le=100_000_000_000)
    source_budget_vnd: StrictInt | None = Field(default=None, ge=0, le=100_000_000_000)


class PublicJudgeEvidence(PublicJudgeRequest):
    reference: StrictStr | None = None
    kind: StrictStr | None = None
    observation: StrictStr | None = None


class PublicJudgeQuestion(PublicJudgeRequest):
    category: StrictStr | None = None
    question: StrictStr | None = None
    disputed_or_missing_fact: StrictStr | None = None
    applicable_rule_or_limit: StrictStr | None = None
    reason: StrictStr | None = None
    evidence_references: list[StrictStr] = Field(default_factory=list)


class PublicJudgeAuditEvent(PublicJudgeRequest):
    event_id: StrictStr | None = None
    action: StrictStr | None = None
    timestamp: StrictStr | None = None
    input_sha256: StrictStr | None = None
    reason: StrictStr | None = None


class PublicJudgeRunRow(PublicJudgeRequest):
    case_id: StrictStr
    case_name: StrictStr | None = None
    status: Literal["PASS", "FAIL", "ERROR"]
    passed: bool
    expected_action: Literal["AUTO_APPROVED", "HUMAN_REVIEW_REQUIRED"] | None = None
    expected_category: StrictStr | None = None
    actual_action: Literal["AUTO_APPROVED", "HUMAN_REVIEW_REQUIRED"] | None = None
    actual_category: StrictStr | None = None
    started_at: StrictStr | None = None
    completed_at: StrictStr | None = None
    duration_ms: int = Field(ge=0)
    reason: StrictStr | None = None
    input: dict[str, object] | None = None
    evidence: list[PublicJudgeEvidence] = Field(default_factory=list)
    questions: list[PublicJudgeQuestion] = Field(default_factory=list)
    applied_rule_ids: list[StrictStr] = Field(default_factory=list)
    policy_version: StrictStr | None = None
    model_version: StrictStr | None = None
    audit: list[PublicJudgeAuditEvent] = Field(default_factory=list)


class PublicJudgeRunSummary(PublicJudgeRequest):
    total_cases: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    failed_cases: int = Field(ge=0)
    error_cases: int = Field(ge=0)


class PublicJudgeRunResponse(PublicJudgeRequest):
    run_id: StrictStr
    suite: Literal["general", "escalation"]
    status: Literal["COMPLETED", "ERROR"]
    mode: Literal["MOCK"]
    data_classification: Literal["SYNTHETIC"]
    started_at: StrictStr | None = None
    completed_at: StrictStr
    duration_ms: int = Field(ge=0)
    summary: PublicJudgeRunSummary
    rows: list[PublicJudgeRunRow]


class PublicJudgeInputAudit(PublicJudgeRequest):
    action: Literal["INPUT_EVALUATED"]
    timestamp: StrictStr
    input_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    reason: StrictStr


class PublicJudgeInputResponse(PublicJudgeRequest):
    run_id: StrictStr
    mode: Literal["MOCK"]
    processing_mode: Literal["DETERMINISTIC_INPUT_SIMULATION"]
    data_classification: Literal["USER_SUPPLIED_UNVERIFIED"]
    quality_status: Literal["NOT_MEASURED"]
    outcome: Literal["SIMULATED_AUTO_APPROVE", "HUMAN_REVIEW_REQUIRED"]
    category: Literal["FACT_UNCERTAIN", "POLICY_OUT_OF_SCOPE", "AUTHORITY_EXCEEDED"] | None
    policy_version: StrictStr
    reason: StrictStr
    handoff_question: StrictStr | None = None
    started_at: StrictStr
    completed_at: StrictStr
    duration_ms: int = Field(ge=0)
    audit: PublicJudgeInputAudit
