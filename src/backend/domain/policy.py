"""Internal configuration, not additions to WP1 wire schemas."""
from dataclasses import dataclass
from typing import Literal
from src.shared.validation import Contract, Positive, Nonnegative, MinorUnits, require, distinct

MANDATORY_FIELDS = ('title', 'maker_id', 'checker_id', 'department', 'objective',
                    'summary', 'start_date', 'end_date', 'budget_minor_units', 'currency')

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
