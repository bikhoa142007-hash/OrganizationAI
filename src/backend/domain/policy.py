"""Internal configuration, not additions to WP1 wire schemas."""
from dataclasses import dataclass
from collections.abc import Mapping
from typing import Any, Literal
from src.shared.validation import Contract, Positive, Nonnegative, MinorUnits, require, distinct

MANDATORY_FIELDS = ('title', 'maker_id', 'checker_id', 'department', 'objective',
                    'summary', 'start_date', 'end_date', 'budget_minor_units', 'currency')

STRATEGY_CRITERIA = (
    ("objective", "Mục tiêu", 15),
    ("audience", "Đối tượng", 15),
    ("channel", "Kênh", 15),
    ("timeline", "Thời gian", 15),
    ("kpi", "KPI", 15),
    ("budget_efficiency", "Hiệu quả ngân sách", 15),
    ("risk_control", "Kiểm soát rủi ro", 10),
)

MEDIA_EVIDENCE_KINDS = frozenset({
    "OCR_TEXT", "OBSERVATION", "OBJECT_DETECTION", "VISUAL_QUALITY", "VISUAL_INSPECTION",
})

RULE_IDS = (
    'INPUT_INTEGRITY', 'EVAL_VALID', 'MEDIA_PASS', 'MEDIA_CONFIDENCE',
    'FEASIBILITY_SCORE', 'FEASIBILITY_CONFIDENCE', 'BUDGET_LIMIT', 'AUTHORITY_LIMIT',
    'NO_HARD_VIOLATION', 'NO_EVIDENCE_CONFLICT', 'POLICY_ENABLED', 'PLAN_PENDING', 'ROUND_ACTIVE',
)


@dataclass(frozen=True)
class Criterion(Contract):
    criterion_id: str
    maximum_score: Positive


@dataclass(frozen=True)
class MediaPolicyRule(Contract):
    rule_id: str
    severity: Literal["HARD_VIOLATION", "WARNING"]
    description: str
    required_evidence_kinds: tuple[str, ...]
    forbidden_literals: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value):
        # Existing scoped policies remain readable; literal checks are opt-in.
        if isinstance(value, Mapping) and "forbidden_literals" not in value:
            value = {**value, "forbidden_literals": []}
        return super().from_dict(value)

    def validate(self):
        require(bool(self.required_evidence_kinds), "Media policy rules need evidence requirements")
        require(set(self.required_evidence_kinds) <= MEDIA_EVIDENCE_KINDS,
                "Media policy has an unsupported evidence kind")
        distinct(self.required_evidence_kinds)
        distinct(self.forbidden_literals)
        require(all(isinstance(item, str) and item.strip() for item in self.forbidden_literals),
                "Media policy literal checks need nonblank text")
        if self.forbidden_literals:
            require("OCR_TEXT" in self.required_evidence_kinds,
                    "Forbidden literal checks require OCR_TEXT evidence")


@dataclass(frozen=True)
class MediaCompliancePolicy(Contract):
    policy_id: str
    policy_version: str
    status: Literal["ACTIVE", "DISABLED"]
    scope_departments: tuple[str, ...]
    scope_channels: tuple[str, ...]
    rules: tuple[MediaPolicyRule, ...]

    def validate(self):
        require(bool(self.scope_departments) and bool(self.scope_channels),
                "Media policy requires an explicit department and channel scope")
        require(bool(self.rules), "Media policy requires at least one configured rule")
        distinct(self.scope_departments)
        distinct(self.scope_channels)
        distinct([rule.rule_id for rule in self.rules])

    def applies_to(self, payload: dict) -> bool:
        department = payload.get("department")
        channels = payload.get("channels")
        if not isinstance(department, str) or not isinstance(channels, (list, tuple)):
            return False
        department_matches = "*" in self.scope_departments or department in self.scope_departments
        channel_matches = "*" in self.scope_channels or (
            bool(channels) and set(channels) <= set(self.scope_channels)
        )
        return department_matches and channel_matches


@dataclass(frozen=True)
class StrategyCriterion(Contract):
    criterion_id: str
    label: str
    weight: Positive


@dataclass(frozen=True)
class StrategyRubric(Contract):
    rubric_id: str
    rubric_version: str
    status: Literal["ACTIVE", "DISABLED"]
    criteria: tuple[StrategyCriterion, ...]

    def validate(self):
        distinct([criterion.criterion_id for criterion in self.criteria])
        configured = {criterion.criterion_id: criterion.weight for criterion in self.criteria}
        expected = {criterion_id: weight for criterion_id, _label, weight in STRATEGY_CRITERIA}
        require(configured == expected, "Strategy rubric must use the seven BA criteria and weights")
        require(sum(criterion.weight for criterion in self.criteria) == 100,
                "Strategy rubric weights must total 100")


@dataclass(frozen=True)
class PolicySnapshot(Contract):
    snapshot_id: str
    policy_version: str
    auto_approval_policy_enabled: bool
    mandatory_fields: tuple[str, ...]
    criteria: tuple[Criterion, ...]
    known_model_versions: tuple[str, ...]
    allowed_media_types: tuple[str, ...]
    max_attachment_bytes: Positive
    rule_ids: tuple[str, ...] = RULE_IDS
    feasibility_threshold: Literal[70] = 70
    media_confidence_threshold: Literal[0.85] = .85
    feasibility_confidence_threshold: Literal[0.8] = .80

    def validate(self):
        require(self.rule_ids == RULE_IDS, 'Required rules cannot be disabled')
        require(set(MANDATORY_FIELDS) <= set(self.mandatory_fields) and bool(self.criteria),
                'Incomplete policy')
        require(sum(c.maximum_score for c in self.criteria) == 100, 'Criteria must total 100')
        distinct(self.mandatory_fields)
        distinct([c.criterion_id for c in self.criteria])
        distinct(self.known_model_versions)


@dataclass(frozen=True)
class BudgetConfiguration(Contract):
    configuration_id: str
    currency: str
    precision: Nonnegative
    limit_minor_units: MinorUnits
    department: str
    active: bool


@dataclass(frozen=True)
class AuthoritySnapshot(Contract):
    snapshot_id: str
    currency: str
    auto_limit_minor_units: MinorUnits
    allowed_departments: tuple[str, ...]
    checker_id: str | None
    policy_owner_id: str | None
    budget_authority_id: str | None
    active: bool


@dataclass(frozen=True)
class ApprovalConfiguration(Contract):
    """Already effective configuration captured at submission, not a live selector."""
    policy: PolicySnapshot
    budgets: tuple[BudgetConfiguration, ...]
    authority: AuthoritySnapshot | None
    media_policy: MediaCompliancePolicy | None = None
    strategy_rubric: StrategyRubric | None = None
    media_model_snapshot: Any = None
    strategy_model_snapshot: Any = None

    def validate(self):
        if self.strategy_rubric is None:
            return
        configured = {criterion.criterion_id: criterion.weight
                      for criterion in self.strategy_rubric.criteria}
        policy_criteria = {criterion.criterion_id: criterion.maximum_score
                           for criterion in self.policy.criteria}
        require(configured == policy_criteria,
                "Approval policy and strategy rubric snapshots must use the same weights")

    @classmethod
    def from_dict(cls, value):
        # Policy snapshots persisted before Media/Strategy existed remain readable.
        if isinstance(value, Mapping) and set(value) == {"policy", "budgets", "authority"}:
            value = {**value, "media_policy": None, "strategy_rubric": None,
                     "media_model_snapshot": None, "strategy_model_snapshot": None}
        elif isinstance(value, Mapping) and set(value) == {
            "policy", "budgets", "authority", "media_policy", "strategy_rubric"
        }:
            value = {**value, "media_model_snapshot": None, "strategy_model_snapshot": None}
        return Contract.from_dict.__func__(cls, value)
