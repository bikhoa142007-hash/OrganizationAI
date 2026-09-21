"""Trusted request models and pipeline result types.

The provider boundary deliberately uses the frozen WP1/WP2 ``EvaluationResult``
wire shape. These models describe orchestration input and outcome only; they do
not add fields to the persisted evaluation contract.
"""

from dataclasses import dataclass, field
from typing import Any, Mapping

from src.backend.domain.models import MarketingPlan
from src.backend.domain.policy import ApprovalConfiguration


@dataclass(frozen=True)
class EvaluationRequest:
    """Server-owned immutable snapshot and correlation data for one run."""

    plan: MarketingPlan
    policy_version: str
    evaluation_id: str
    run_id: str
    correlation_id: str
    provider: str = "MOCK_VLM"
    model_version: str | None = None
    configuration: ApprovalConfiguration | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def plan_id(self) -> str:
        return self.plan.plan_id

    @property
    def plan_version(self) -> int:
        if self.plan.plan_version is None:
            raise ValueError("Submitted plan version is required")
        return self.plan.plan_version

    @property
    def approval_round(self) -> int:
        if self.plan.approval_round is None:
            raise ValueError("Submitted approval round is required")
        return self.plan.approval_round

    @property
    def input_hash(self) -> str:
        return self.plan.input_hash


@dataclass(frozen=True)
class PipelineResult:
    """Validated advisory evidence plus retry metadata."""

    evaluation: dict
    attempts: int
    retried: bool

    @property
    def outcome_recommendation(self) -> str | None:
        return self.evaluation.get("proposed_action")
