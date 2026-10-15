"""Internal configuration, not additions to WP1 wire schemas."""
import math
import re
from dataclasses import dataclass
from collections.abc import Mapping
from typing import Any, Literal
from uuid import UUID
from datetime import datetime, timezone
from src.shared.validation import Contract, Positive, Nonnegative, MinorUnits, Timestamp, require, distinct, canonical_hash

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
    'INPUT_INTEGRITY', 'EVAL_VALID', 'DECISION_SCOPE', 'MEDIA_PASS', 'MEDIA_CONFIDENCE',
    'FEASIBILITY_SCORE', 'FEASIBILITY_CONFIDENCE', 'BUDGET_LIMIT', 'AUTHORITY_LIMIT',
    'NO_HARD_VIOLATION', 'NO_EVIDENCE_CONFLICT', 'POLICY_ENABLED', 'PLAN_PENDING', 'ROUND_ACTIVE',
)

AUTO_REJECT_REASON_PATTERN = re.compile(r"[A-Z][A-Z0-9_]{2,79}\Z")


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
class AutoRejectRule(Contract):
    """A deterministic evidence match. It never changes Media rule severity."""

    rule_id: str
    evidence_kind: Literal["OCR_TEXT"]
    forbidden_literals: tuple[str, ...]
    evidence_confidence_threshold: float
    media_confidence_threshold: float
    feasibility_confidence_threshold: float
    reason_code: str
    exceptions: tuple[str, ...]

    def validate(self):
        require(bool(self.forbidden_literals), "Auto-reject rules require an explicit forbidden literal.")
        distinct(self.forbidden_literals)
        distinct(self.exceptions)
        require(all(isinstance(value, str) and value.strip() for value in (*self.forbidden_literals, *self.exceptions)),
                "Auto-reject literals and exceptions must be non-blank strings.")
        for value in (self.evidence_confidence_threshold, self.media_confidence_threshold,
                      self.feasibility_confidence_threshold):
            require(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1,
                    "Auto-reject confidence thresholds must be in [0, 1].")
        require(bool(AUTO_REJECT_REASON_PATTERN.fullmatch(self.reason_code)),
                "Auto-reject reason code must be a stable uppercase identifier.")


@dataclass(frozen=True)
class AutoRejectPolicy(Contract):
    """Revisioned auto-reject authority captured into a submitted round."""

    configuration_id: str
    policy_version: str
    revision: Positive
    enabled: bool
    scope_departments: tuple[str, ...]
    scope_channels: tuple[str, ...]
    rules: tuple[AutoRejectRule, ...]
    configuration_hash: str | None
    signoff_source: Literal["SYNTHETIC_FIXTURE", "AUTHENTICATED_POLICY_OWNER"] | None
    signed_by: str | None
    signed_at: Timestamp | None
    environment: Literal["PRODUCTION", "SYNTHETIC_TEST"] = "PRODUCTION"

    def validate(self):
        require(bool(self.scope_departments) and bool(self.scope_channels),
                "Auto-reject policy requires explicit department and channel scope.")
        require(bool(self.rules), "Auto-reject policy requires at least one explicit rule.")
        distinct(self.scope_departments)
        distinct(self.scope_channels)
        distinct([rule.rule_id for rule in self.rules])
        require(all(value.strip() for value in (*self.scope_departments, *self.scope_channels)),
                "Auto-reject scope values must not be blank.")
        if self.enabled:
            require(self.configuration_hash == auto_reject_configuration_hash(self),
                    "Enabled auto-reject policy is not bound to its exact configuration hash.")
            require(self.signoff_source is not None and self.signed_by is not None and self.signed_at is not None,
                    "Enabled auto-reject policy needs a revision-specific sign-off.")
            if self.signoff_source == "SYNTHETIC_FIXTURE":
                require(self.environment == "SYNTHETIC_TEST"
                        and self.signed_by == "VERIFY_FIXTURE"
                        and self.configuration_id.startswith("VERIFY-"),
                        "Synthetic auto-reject sign-off is valid only for an unmistakable test fixture.")
            elif self.signoff_source == "AUTHENTICATED_POLICY_OWNER":
                require(self.environment == "PRODUCTION"
                        and not self.configuration_id.startswith("VERIFY-"),
                        "Authenticated Policy Owner sign-off is valid only for a production policy.")
                try:
                    UUID(self.signed_by)
                except (TypeError, ValueError, AttributeError) as exc:
                    raise ValueError("Authenticated Policy Owner sign-off must identify a user UUID.") from exc
            else:
                raise ValueError("Enabled auto-reject policy has an unsupported sign-off source.")
        else:
            require(self.configuration_hash is None,
                    "Disabled auto-reject policy must not carry an activation hash.")
            require(self.signoff_source is None and self.signed_by is None and self.signed_at is None,
                    "Disabled auto-reject policy must not carry an activation sign-off.")

    def applies_to(self, payload: Mapping[str, Any]) -> bool:
        channels = payload.get("channels")
        return (
            self.enabled
            and payload.get("department") in self.scope_departments
            and isinstance(channels, (tuple, list)) and bool(channels)
            and set(channels) <= set(self.scope_channels)
        )

    @classmethod
    def synthetic_fixture(cls, *, configuration_id, revision, enabled, scope_departments,
                          scope_channels, rules):
        """Create unmistakably test-only policy evidence; not a production sign-off."""
        signed_at = "2026-10-15T00:00:00Z"
        if not enabled:
            return cls(configuration_id, "VERIFY-AUTO-REJECT-1", revision, False,
                       tuple(scope_departments), tuple(scope_channels), tuple(rules), None,
                       None, None, None, "SYNTHETIC_TEST")
        unsigned = cls(configuration_id, "VERIFY-AUTO-REJECT-1", revision, False,
                       tuple(scope_departments), tuple(scope_channels), tuple(rules), None,
                       None, None, None, "SYNTHETIC_TEST")
        active_value = auto_reject_configuration_value(unsigned, enabled=True)
        digest = canonical_hash(active_value)
        return cls(configuration_id, "VERIFY-AUTO-REJECT-1", revision, True,
                   tuple(scope_departments), tuple(scope_channels), tuple(rules), digest,
                   "SYNTHETIC_FIXTURE", "VERIFY_FIXTURE", signed_at, "SYNTHETIC_TEST")


def auto_reject_configuration_value(policy: AutoRejectPolicy, *, enabled: bool | None = None) -> dict[str, Any]:
    return {
        "configuration_id": policy.configuration_id,
        "policy_version": policy.policy_version,
        "revision": policy.revision,
        "environment": policy.environment,
        "enabled": policy.enabled if enabled is None else enabled,
        "scope_departments": list(policy.scope_departments),
        "scope_channels": list(policy.scope_channels),
        "rules": [rule.to_dict() for rule in policy.rules],
    }


def auto_reject_configuration_hash(policy: AutoRejectPolicy) -> str:
    return canonical_hash(auto_reject_configuration_value(policy))


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
    feasibility_threshold: int = 70
    media_confidence_threshold: float = .85
    feasibility_confidence_threshold: float = .80

    def validate(self):
        require(self.rule_ids == RULE_IDS, 'Required rules cannot be disabled')
        require(set(MANDATORY_FIELDS) <= set(self.mandatory_fields) and bool(self.criteria),
                'Incomplete policy')
        require(sum(c.maximum_score for c in self.criteria) == 100, 'Criteria must total 100')
        require(type(self.feasibility_threshold) is int and 0 <= self.feasibility_threshold < 100,
                'Exclusive feasibility threshold must be an integer from 0 to 99')
        require(type(self.media_confidence_threshold) in (int, float)
                and math.isfinite(self.media_confidence_threshold)
                and 0 <= self.media_confidence_threshold <= 1,
                'Media confidence threshold must be in [0, 1]')
        require(type(self.feasibility_confidence_threshold) in (int, float)
                and math.isfinite(self.feasibility_confidence_threshold)
                and 0 <= self.feasibility_confidence_threshold <= 1,
                'Feasibility confidence threshold must be in [0, 1]')
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
    auto_reject_policy: AutoRejectPolicy | None = None
    media_model_snapshot: Any = None
    strategy_model_snapshot: Any = None
    visual_model_snapshot: Any = None

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
        # Older immutable round snapshots predate one or more AI model snapshots.
        if isinstance(value, Mapping):
            defaults = {
                "media_policy": None,
                "strategy_rubric": None,
                "auto_reject_policy": None,
                "media_model_snapshot": None,
                "strategy_model_snapshot": None,
                "visual_model_snapshot": None,
            }
            value = {**defaults, **value}
        return Contract.from_dict.__func__(cls, value)
