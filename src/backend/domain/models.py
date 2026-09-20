"""WP1 wire models. Required nullable fields deliberately have no defaults."""
from dataclasses import dataclass
from typing import Any, Literal
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from src.backend.domain.policy import RULE_IDS

from src.shared.validation import (
    Contract, Hash, Timestamp, MinorUnits, Positive, Nonnegative,
    require, distinct, paired, canonical_hash,
)

Outcome = Literal['AUTO_APPROVED', 'HUMAN_REVIEW_REQUIRED']
Category = Literal['FACT_UNCERTAIN', 'POLICY_OUT_OF_SCOPE', 'AUTHORITY_EXCEEDED']
CheckResult = Literal['PASS', 'FAIL', 'UNKNOWN']
PlanStatus = Literal['DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'REJECTED']
Stage = Literal['AI_PENDING', 'AI_PROCESSING', 'HUMAN_REVIEW_REQUIRED',
                'AI_AUTO_APPROVED', 'AI_PROCESSING_FAILED']


@dataclass(frozen=True)
class Actor(Contract):
    actor_type: Literal['HUMAN', 'SYSTEM']
    actor_id: str


@dataclass(frozen=True)
class AttachmentManifest(Contract):
    attachment_id: str
    content_hash: Hash
    media_type: str
    byte_size: Nonnegative


@dataclass(frozen=True)
class MarketingPlan(Contract):
    """Exact WP1 hash object; payload field names are configured by policy."""
    plan_id: str
    plan_version: Positive | None
    approval_round: Positive | None
    payload: Any
    attachments: tuple[AttachmentManifest, ...]

    def validate(self):
        paired(self.plan_version, self.approval_round)
        require(isinstance(self.payload, Mapping), 'Payload must be an object')
        distinct([a.attachment_id for a in self.attachments])
        object.__setattr__(self, 'attachments', tuple(sorted(
            self.attachments, key=lambda a: a.attachment_id)))
        canonical_hash(self)

    @property
    def input_hash(self):
        return canonical_hash(self)


@dataclass(frozen=True)
class Evidence(Contract):
    evidence_id: str
    source_type: Literal['ATTACHMENT', 'PLAN_FIELD', 'POLICY', 'BUDGET',
                         'AUTHORITY', 'PROVIDER_ERROR']
    source_ref: str
    observation: str
    content_hash: Hash | None

    def validate(self):
        require('://' not in self.source_ref, 'Evidence must use internal references')
        if self.source_type == 'ATTACHMENT':
            require(self.content_hash is not None, 'Attachment evidence needs hash')


@dataclass(frozen=True)
class MediaFinding(Contract):
    finding_id: str
    severity: Literal['HARD_VIOLATION', 'WARNING']
    description: str
    rule_id: str | None
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceConflict(Contract):
    conflict_id: str
    description: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class AgentError(Contract):
    component: str
    code: str
    message: str


@dataclass(frozen=True)
class CriterionScore(Contract):
    criterion_id: str
    score: float
    maximum_score: float
    rationale: str
    evidence_refs: tuple[str, ...]

    def validate(self):
        require(0 <= self.score <= self.maximum_score, 'Invalid criterion score')


@dataclass(frozen=True)
class EvaluationResult(Contract):
    evaluation_id: str
    plan_id: str
    plan_version: Positive
    approval_round: Positive
    run_id: str
    schema_version: Literal[1]
    input_hash: Hash
    policy_version: str
    provider: Literal['LOCAL_VLM', 'MOCK_VLM']
    model_version: str | None
    status: Literal['SUCCEEDED', 'FAILED', 'TIMED_OUT']
    media_result: Literal['PASS', 'REVIEW_REQUIRED'] | None
    media_findings: tuple[MediaFinding, ...]
    media_confidence: float | None
    feasibility_score: float | None
    feasibility_confidence: float | None
    missing_facts: tuple[str, ...]
    evidence_conflicts: tuple[EvidenceConflict, ...]
    evidence: tuple[Evidence, ...]
    proposed_action: Literal['RECOMMEND_AUTO_APPROVAL', 'RECOMMEND_HUMAN_REVIEW'] | None
    escalation_category: Category | None
    reason: str
    latency_ms: Nonnegative
    created_at: Timestamp
    started_at: Timestamp
    completed_at: Timestamp
    agent_errors: tuple[AgentError, ...]
    raw_output_hash: Hash | None
    reported_model_version: str | None
    correlation_id: str
    criterion_scores: tuple[CriterionScore, ...]
    assumptions: tuple[str, ...]

    def validate(self):
        require(datetime.fromisoformat(self.completed_at) >=
                datetime.fromisoformat(self.started_at), 'Invalid attempt times')
        for value, maximum in ((self.media_confidence, 1),
                               (self.feasibility_confidence, 1),
                               (self.feasibility_score, 100)):
            require(value is None or 0 <= value <= maximum, 'Score out of range')
        for collection, key in ((self.evidence, 'evidence_id'),
                                (self.media_findings, 'finding_id'),
                                (self.evidence_conflicts, 'conflict_id'),
                                (self.criterion_scores, 'criterion_id')):
            distinct([getattr(item, key) for item in collection])
        refs = {e.evidence_id for e in self.evidence}
        for item in (*self.media_findings, *self.evidence_conflicts, *self.criterion_scores):
            require(set(item.evidence_refs) <= refs, 'Unresolved evidence reference')
        measurements = (self.media_result, self.media_confidence,
                        self.feasibility_score, self.feasibility_confidence,
                        self.proposed_action)
        if self.status == 'SUCCEEDED':
            require(self.model_version is not None and not self.agent_errors and
                    all(x is not None for x in measurements), 'Invalid success envelope')
            if self.proposed_action == 'RECOMMEND_AUTO_APPROVAL':
                require(self.escalation_category is None and self.media_result == 'PASS'
                        and self.media_confidence >= .85 and self.feasibility_score > 70
                        and self.feasibility_confidence >= .80 and not self.missing_facts
                        and not self.evidence_conflicts
                        and not any(f.severity == 'HARD_VIOLATION' for f in self.media_findings),
                        'Invalid auto recommendation')
            else:
                require(self.escalation_category is not None, 'Review needs category')
        else:
            require(all(x is None for x in measurements) and bool(self.agent_errors)
                    and self.escalation_category == 'FACT_UNCERTAIN', 'Invalid failure envelope')


@dataclass(frozen=True)
class RuleCheck(Contract):
    rule_id: str
    result: CheckResult
    observed_value: Any
    applicable_rule_or_limit: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class BudgetValidation(Contract):
    configuration_id: str | None
    configuration_hash: Hash | None
    currency: str | None
    budget_minor_units: MinorUnits | None
    limit_minor_units: MinorUnits | None
    result: CheckResult

    def validate(self):
        paired(self.configuration_id, self.configuration_hash)
        if self.result != 'UNKNOWN':
            require(all(x is not None for x in (self.configuration_id, self.currency,
                    self.budget_minor_units, self.limit_minor_units)), 'Incomplete budget result')
            expected = 'PASS' if Decimal(self.budget_minor_units) <= Decimal(self.limit_minor_units) else 'FAIL'
            require(self.result == expected, 'Incorrect budget comparison')


@dataclass(frozen=True)
class DecisionResult(Contract):
    decision_id: str
    plan_id: str
    plan_version: Positive
    approval_round: Positive
    outcome: Outcome
    escalation_category: Category | None
    reason: str
    applied_rule_ids: tuple[str, ...]
    input_hash: Hash
    policy_version: str
    evaluation_id: str
    decided_by: Actor
    decided_at: Timestamp
    schema_version: Literal[1]
    rule_checks: tuple[RuleCheck, ...]
    evidence: tuple[Evidence, ...]
    escalation_ids: tuple[str, ...]
    policy_snapshot_id: str
    policy_snapshot_hash: Hash
    budget_validation: BudgetValidation
    authority_snapshot_id: str | None
    authority_snapshot_hash: Hash | None
    idempotency_key: str
    correlation_id: str
    round_revision: Nonnegative

    def validate(self):
        distinct(self.applied_rule_ids)
        require(set(RULE_IDS) <= set(self.applied_rule_ids), 'Missing required decision gates')
        distinct(self.escalation_ids)
        require(bool(self.applied_rule_ids) and self.applied_rule_ids ==
                tuple(c.rule_id for c in self.rule_checks), 'Rule trace mismatch')
        require(self.decided_by.actor_type == 'SYSTEM', 'Engine actor must be SYSTEM')
        paired(self.authority_snapshot_id, self.authority_snapshot_hash)
        auto = self.outcome == 'AUTO_APPROVED'
        require((self.escalation_category is None) == auto and
                bool(self.escalation_ids) != auto, 'Invalid escalation routing')
        if auto:
            require(all(c.result == 'PASS' for c in self.rule_checks) and
                    self.budget_validation.result == 'PASS' and
                    self.authority_snapshot_id is not None, 'Auto approval gates not satisfied')

    @property
    def reason_codes(self):
        """Derived view, not a new WP1 wire field."""
        return tuple(c.rule_id for c in self.rule_checks if c.result != 'PASS')


@dataclass(frozen=True)
class AnswerOption(Contract):
    option_id: str
    label: str


@dataclass(frozen=True)
class TargetAuthority(Contract):
    role: Literal['CHECKER', 'POLICY_OWNER', 'BUDGET_AUTHORITY']
    actor_id: str | None


@dataclass(frozen=True)
class Escalation(Contract):
    escalation_id: str
    category: Category
    disputed_or_missing_fact: str
    observed_value: Any
    applicable_rule_or_limit: str
    evidence_reference: tuple[str, ...]
    question: str
    answer_options: tuple[AnswerOption, ...]
    target_authority: TargetAuthority
    created_at: Timestamp
    schema_version: Literal[1]
    plan_id: str
    plan_version: Positive
    approval_round: Positive
    evaluation_id: str
    decision_id: str
    input_hash: Hash
    policy_version: str
    applied_rule_ids: tuple[str, ...]
    reason: str

    def validate(self):
        require(len(self.answer_options) >= 2 and bool(self.applied_rule_ids), 'Incomplete question')
        distinct([o.option_id for o in self.answer_options])
        distinct(self.applied_rule_ids)


@dataclass(frozen=True)
class State(Contract):
    plan_status: PlanStatus
    processing_stage: Stage | None
    approval_round_status: Literal['ACTIVE', 'CLOSED'] | None


@dataclass(frozen=True)
class HumanDecision(Contract):
    human_decision_id: str
    plan_id: str
    plan_version: Positive
    approval_round: Positive
    action: Literal['APPROVED', 'REJECTED']
    based_on_decision_id: str
    evaluation_id: str
    actor: Actor
    reason: str | None
    override_reason: str | None
    decided_at: Timestamp
    input_hash: Hash
    policy_version: str
    idempotency_key: str
    correlation_id: str
    round_revision: Nonnegative

    def validate(self):
        require(self.actor.actor_type == 'HUMAN', 'Human actor required')
        require(self.action != 'REJECTED' or self.reason is not None, 'Rejection needs reason')

    def validate_authorization(self, maker_id, checker_id, recommendation):
        require(self.actor.actor_id == checker_id and checker_id != maker_id, 'FORBIDDEN')
        expected = 'RECOMMEND_AUTO_APPROVAL' if self.action == 'APPROVED' else 'RECOMMEND_HUMAN_REVIEW'
        require(recommendation == expected or self.override_reason is not None, 'Override needs reason')


@dataclass(frozen=True)
class AuditEvent(Contract):
    event_id: str
    actor_type: Literal['HUMAN', 'SYSTEM']
    actor_id: str
    action: Literal['DRAFT_SAVED', 'ATTACHMENT_UPLOADED', 'PLAN_SUBMITTED',
                    'EVALUATION_STARTED', 'EVALUATION_COMPLETED', 'EVALUATION_FAILED',
                    'ENGINE_ROUTED', 'AUTO_APPROVED', 'HUMAN_APPROVED', 'HUMAN_REJECTED',
                    'ESCALATION_ANSWERED', 'PLAN_RESUBMITTED', 'ACCESS_DENIED', 'RETRY_REQUESTED']
    entity_id: str
    entity_version: Nonnegative
    input_hash: Hash | None
    policy_version: str | None
    model_version: str | None
    reason: str
    previous_state: State | None
    new_state: State | None
    timestamp: Timestamp
    schema_version: Literal[1]
    plan_id: str | None
    plan_version: Positive | None
    approval_round: Positive | None
    run_id: str | None
    evaluation_id: str | None
    decision_id: str | None
    human_decision_id: str | None
    correlation_id: str
    idempotency_key: str | None
    applied_rule_ids: tuple[str, ...]
    evidence_reference: tuple[str, ...]
    policy_snapshot_id: str | None
    policy_snapshot_hash: Hash | None
    budget_snapshot_id: str | None
    budget_snapshot_hash: Hash | None
    authority_snapshot_id: str | None
    authority_snapshot_hash: Hash | None
    outcome: Outcome | None
    human_action: Literal['APPROVED', 'REJECTED'] | None
    override_reason: str | None

    def validate(self):
        for prefix in ('policy', 'budget', 'authority'):
            paired(getattr(self, prefix + '_snapshot_id'), getattr(self, prefix + '_snapshot_hash'))
        distinct(self.applied_rule_ids)
        if self.action in ('ENGINE_ROUTED', 'AUTO_APPROVED', 'HUMAN_APPROVED', 'HUMAN_REJECTED'):
            require(all(x is not None for x in (self.plan_id, self.plan_version,
                    self.approval_round, self.input_hash, self.policy_version,
                    self.policy_snapshot_id, self.evaluation_id, self.decision_id,
                    self.idempotency_key)), 'Incomplete decision audit')
        if self.action in ('ENGINE_ROUTED', 'AUTO_APPROVED', 'HUMAN_APPROVED', 'HUMAN_REJECTED'):
            require(self.previous_state is not None and self.new_state is not None,
                    'Decision audit needs before/after states')
            require(self.previous_state.plan_status == 'PENDING_APPROVAL' and
                    self.previous_state.approval_round_status == 'ACTIVE', 'Invalid prior decision state')
            if self.action == 'ENGINE_ROUTED':
                require(self.new_state == State('PENDING_APPROVAL', 'HUMAN_REVIEW_REQUIRED', 'ACTIVE'),
                        'Invalid review routing state')
            elif self.action == 'AUTO_APPROVED':
                require(self.new_state == State('APPROVED', 'AI_AUTO_APPROVED', 'CLOSED'),
                        'Invalid auto approval state')
            else:
                require(self.new_state.plan_status == self.action.removeprefix('HUMAN_') and
                        self.new_state.approval_round_status == 'CLOSED', 'Invalid human final state')
        if self.action in ('ENGINE_ROUTED', 'AUTO_APPROVED'):
            expected = 'AUTO_APPROVED' if self.action == 'AUTO_APPROVED' else 'HUMAN_REVIEW_REQUIRED'
            require(self.actor_type == 'SYSTEM' and self.outcome == expected
                    and bool(self.applied_rule_ids), 'Invalid engine audit')
        if self.action == 'AUTO_APPROVED':
            require(self.budget_snapshot_id is not None and
                    self.authority_snapshot_id is not None, 'Missing auto approval configuration')
        if self.action in ('HUMAN_APPROVED', 'HUMAN_REJECTED'):
            require(self.actor_type == 'HUMAN' and self.human_decision_id is not None
                    and self.human_action == self.action.removeprefix('HUMAN_')
                    and self.outcome is None, 'Invalid human audit')
