"""Pure deterministic WP2 engine. No I/O, model calls or state mutation."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from src.shared.validation import (
    Contract, Hash, Timestamp, Nonnegative, ValidationError, require,
    canonical_hash, decode, MinorUnits,
)
from src.backend.domain.models import (
    Actor, AgentError, AuditEvent, AnswerOption, BudgetValidation, DecisionResult,
    Escalation, EvaluationResult, Evidence, MarketingPlan, RuleCheck, State, TargetAuthority,
)
from src.backend.domain.policy import ApprovalConfiguration, RULE_IDS


@dataclass(frozen=True)
class DecisionContext(Contract):
    """Server-owned observations; callers must not populate these from provider JSON."""
    evaluation_id: str
    run_id: str
    provider: Literal['LOCAL_VLM', 'MOCK_VLM']
    correlation_id: str
    idempotency_key: str
    decided_at: Timestamp
    plan_status: Literal['DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'REJECTED']
    approval_round_status: Literal['ACTIVE', 'CLOSED']
    round_revision: Nonnegative
    expected_input_hash: Hash
    verified_attachment_hashes: tuple[tuple[str, ...], ...]
    valid_checker_ids: tuple[str, ...]
    suspicious_input: bool

    def validate(self):
        require(all(len(x) == 2 for x in self.verified_attachment_hashes), 'Invalid verified manifest')
        require(len({x[0] for x in self.verified_attachment_hashes}) ==
                len(self.verified_attachment_hashes), 'Duplicate verified attachment')
        for _, digest in self.verified_attachment_hashes:
            decode(Hash, digest)


@dataclass(frozen=True)
class DecisionBundle:
    evaluation: EvaluationResult
    decision: DecisionResult
    escalations: tuple[Escalation, ...]
    audit: AuditEvent


def normalize_evaluation(raw, plan, config, ctx):
    """A boundary validator, not an orchestrator. Returns a persistable failure envelope."""
    error_code = 'INVALID_SCHEMA'
    try:
        result = EvaluationResult.from_dict(raw)
        expected = (ctx.evaluation_id, ctx.run_id, plan.plan_id, plan.plan_version,
                    plan.approval_round, plan.input_hash, config.policy.policy_version,
                    ctx.provider, ctx.correlation_id)
        actual = (result.evaluation_id, result.run_id, result.plan_id, result.plan_version,
                  result.approval_round, result.input_hash, result.policy_version,
                  result.provider, result.correlation_id)
        error_code = 'INPUT_MISMATCH'
        require(actual == expected, 'Evaluation identity mismatch')
        error_code = 'UNKNOWN_MODEL'
        require(result.model_version is None or result.model_version in
                config.policy.known_model_versions, 'Unknown model')
        error_code = 'INVALID_SCHEMA'
        if result.status == 'SUCCEEDED':
            maxima = {c.criterion_id: c.maximum_score for c in config.policy.criteria}
            require({c.criterion_id: c.maximum_score for c in result.criterion_scores} == maxima,
                    'Criterion set mismatch')
            require(sum(Decimal(str(c.score)) for c in result.criterion_scores) ==
                    Decimal(str(result.feasibility_score)), 'Criterion total mismatch')
        attachments = {a.attachment_id: a.content_hash for a in plan.attachments}
        for evidence in result.evidence:
            if evidence.source_type == 'ATTACHMENT':
                require(attachments.get(evidence.source_ref) == evidence.content_hash,
                        'Evidence from another attachment')
            elif evidence.source_type == 'PLAN_FIELD':
                require(evidence.source_ref in plan.payload, 'Unknown plan field')
            elif evidence.source_type in ('POLICY', 'BUDGET', 'AUTHORITY'):
                allowed = {config.policy.snapshot_id: canonical_hash(config.policy)}
                allowed.update({b.configuration_id: canonical_hash(b) for b in config.budgets})
                if config.authority:
                    allowed[config.authority.snapshot_id] = canonical_hash(config.authority)
                require(evidence.source_ref in allowed, 'Unknown configuration evidence')
                require(evidence.content_hash is None or
                        evidence.content_hash == allowed[evidence.source_ref], 'Evidence hash mismatch')
        return result
    except (ValidationError, TypeError, ValueError, OverflowError):
        try:
            raw_hash = canonical_hash(raw)
        except (ValidationError, TypeError, ValueError):
            raw_hash = None
        return EvaluationResult(
            ctx.evaluation_id, plan.plan_id, plan.plan_version, plan.approval_round,
            ctx.run_id, 1, plan.input_hash, config.policy.policy_version, ctx.provider,
            None, 'FAILED', None, (), None, None, None, (), (), (), None,
            'FACT_UNCERTAIN', 'Evaluation rejected by the WP1 boundary validator.',
            0, ctx.decided_at, ctx.decided_at, ctx.decided_at,
            (AgentError('schema-validator', error_code, 'Untrusted evaluation was not usable.'),),
            raw_hash, None, ctx.correlation_id, (), (),
        )


def _budget(plan, config):
    currency, amount = plan.payload.get('currency'), plan.payload.get('budget_minor_units')
    try:
        decode(MinorUnits, amount)
        decode(str, currency)
    except ValidationError:
        return BudgetValidation(None, None, None, None, None, 'UNKNOWN')
    matches = [b for b in config.budgets if b.active and b.currency == currency
               and b.department == plan.payload.get('department')]
    if len(matches) != 1:
        return BudgetValidation(None, None, currency, amount, None, 'UNKNOWN')
    b = matches[0]
    return BudgetValidation(b.configuration_id, canonical_hash(b), currency, amount,
                            b.limit_minor_units,
                            'PASS' if Decimal(amount) <= Decimal(b.limit_minor_units) else 'FAIL')


def _input_valid(plan, config, ctx, evaluation):
    payload, policy = plan.payload, config.policy
    if ctx.suspicious_input or plan.input_hash != ctx.expected_input_hash:
        return False
    if any(not isinstance(payload.get(k), str) or not payload[k].strip()
           for k in policy.mandatory_fields):
        return False
    if (payload.get('checker_id') not in ctx.valid_checker_ids or
            not isinstance(payload.get('maker_id'), str) or
            not payload['maker_id'].strip() or payload.get('maker_id') == payload.get('checker_id')):
        return False
    try:
        decode(MinorUnits, payload.get('budget_minor_units'))
        decode(str, payload.get('currency'))
        start, end = date.fromisoformat(payload['start_date']), date.fromisoformat(payload['end_date'])
        if start > end:
            return False
    except (KeyError, TypeError, ValueError):
        return False
    verified = dict(ctx.verified_attachment_hashes)
    if not plan.attachments or set(verified) != {a.attachment_id for a in plan.attachments}:
        return False
    if any(verified[a.attachment_id] != a.content_hash or
           a.media_type not in policy.allowed_media_types or
           not 0 < a.byte_size <= policy.max_attachment_bytes for a in plan.attachments):
        return False
    # Each submitted attachment needs evidence; an empty array is not sufficient proof.
    if evaluation.status == 'SUCCEEDED':
        observed = {e.source_ref for e in evaluation.evidence if e.source_type == 'ATTACHMENT'}
        return set(verified) <= observed
    return True


def decide(plan: MarketingPlan, config: ApprovalConfiguration, raw_evaluation,
           ctx: DecisionContext) -> DecisionBundle:
    """Compute a proposal bundle; persistence must atomically recheck state before commit."""
    require(plan.plan_version is not None and plan.approval_round is not None, 'CONFLICT: not submitted')
    require(ctx.plan_status == 'PENDING_APPROVAL' and ctx.approval_round_status == 'ACTIVE',
            'CONFLICT: round is no longer eligible')
    ev = normalize_evaluation(raw_evaluation, plan, config, ctx)
    policy, authority = config.policy, config.authority
    budget = _budget(plan, config)
    successful = ev.status == 'SUCCEEDED'
    checks, triggered, engine_evidence = [], {}, []
    ev_refs = tuple(e.evidence_id for e in ev.evidence)

    def check(rule, condition, observed, limit, category, refs=()):
        result = 'UNKNOWN' if condition is None else 'PASS' if condition else 'FAIL'
        checks.append(RuleCheck(rule, result, observed, limit, refs))
        if result != 'PASS':
            triggered.setdefault(category, []).append(checks[-1])

    check('INPUT_INTEGRITY', _input_valid(plan, config, ctx, ev),
          {'input_hash_matches': plan.input_hash == ctx.expected_input_hash,
           'attachment_count': len(plan.attachments)},
          'Complete required payload, verified snapshot and attachments, valid distinct Checker.',
          'FACT_UNCERTAIN', ev_refs)
    check('EVAL_VALID', successful, ev.status, 'Schema-valid success and known model.', 'FACT_UNCERTAIN')
    # Review caused only by unresolved facts is not a validated policy violation.
    # Keep independent policy/authority failures and existing category precedence.
    factual_media = bool(ev.missing_facts or ev.evidence_conflicts) and not any(
        f.severity == 'HARD_VIOLATION' or f.rule_id is not None for f in ev.media_findings)
    media_category = 'FACT_UNCERTAIN' if factual_media else 'POLICY_OUT_OF_SCOPE'
    for rule, value, passed, limit, category in (
        ('MEDIA_PASS', ev.media_result, ev.media_result == 'PASS', 'media_result = PASS', media_category),
        ('MEDIA_CONFIDENCE', ev.media_confidence, successful and ev.media_confidence >= .85,
         'media_confidence >= 0.85', 'FACT_UNCERTAIN'),
        ('FEASIBILITY_SCORE', ev.feasibility_score, successful and ev.feasibility_score > 70,
         'feasibility_score > 70', 'POLICY_OUT_OF_SCOPE'),
        ('FEASIBILITY_CONFIDENCE', ev.feasibility_confidence, successful and ev.feasibility_confidence >= .80,
         'feasibility_confidence >= 0.80', 'FACT_UNCERTAIN'),
    ):
        check(rule, passed if successful else None, value, limit,
              category if successful else 'FACT_UNCERTAIN', ev_refs)
    budget_ref = 'engine-budget-' + canonical_hash(budget)
    engine_evidence.append(Evidence(budget_ref, 'BUDGET', budget.configuration_id or policy.snapshot_id,
                                    'Deterministic comparison: ' + budget.result, budget.configuration_hash))
    check('BUDGET_LIMIT', None if budget.result == 'UNKNOWN' else budget.result == 'PASS',
          budget.to_dict(), 'budget <= uniquely applicable active same-currency limit',
          'POLICY_OUT_OF_SCOPE' if budget.result == 'UNKNOWN' else 'AUTHORITY_EXCEEDED', (budget_ref,))
    authority_known = (authority is not None and authority.active and
                       authority.currency == budget.currency and budget.budget_minor_units is not None)
    authority_pass = None
    if authority_known:
        authority_pass = (Decimal(budget.budget_minor_units) <= Decimal(authority.auto_limit_minor_units)
                          and plan.payload.get('department') in authority.allowed_departments
                          and authority.checker_id == plan.payload.get('checker_id'))
    authority_ref = 'engine-authority-' + canonical_hash(authority)
    engine_evidence.append(Evidence(authority_ref, 'AUTHORITY',
                                    authority.snapshot_id if authority else policy.snapshot_id,
                                    'Delegated authority checked deterministically.',
                                    canonical_hash(authority) if authority else None))
    check('AUTHORITY_LIMIT', authority_pass,
          authority.to_dict() if authority else None, 'Configured active automatic mandate and Checker.',
          'AUTHORITY_EXCEEDED' if authority_known else 'POLICY_OUT_OF_SCOPE', (authority_ref,))
    hard_count = sum(f.severity == 'HARD_VIOLATION' for f in ev.media_findings) if successful else None
    check('NO_HARD_VIOLATION', hard_count == 0 if successful else None, hard_count,
          'hard_violation_count = 0', 'POLICY_OUT_OF_SCOPE' if successful else 'FACT_UNCERTAIN', ev_refs)
    conflicts = len(ev.evidence_conflicts) + len(ev.missing_facts) if successful else None
    check('NO_EVIDENCE_CONFLICT', conflicts == 0 if successful else None, conflicts,
          'No unresolved conflicts or missing material facts.', 'FACT_UNCERTAIN', ev_refs)
    check('POLICY_ENABLED', policy.auto_approval_policy_enabled, policy.auto_approval_policy_enabled,
          'auto_approval_policy_enabled = true', 'POLICY_OUT_OF_SCOPE')
    check('PLAN_PENDING', True, ctx.plan_status, 'plan_status = PENDING_APPROVAL', 'FACT_UNCERTAIN')
    check('ROUND_ACTIVE', True, ctx.approval_round_status, 'approval_round_status = ACTIVE', 'FACT_UNCERTAIN')
    require(tuple(c.rule_id for c in checks) == RULE_IDS, 'Incomplete engine checks')
    categories = [c for c in ('AUTHORITY_EXCEEDED', 'POLICY_OUT_OF_SCOPE', 'FACT_UNCERTAIN') if c in triggered]
    outcome = 'HUMAN_REVIEW_REQUIRED' if categories else 'AUTO_APPROVED'
    evaluation_identity = ev.to_dict()
    context_identity = ctx.to_dict()
    for field in ('created_at', 'started_at', 'completed_at', 'latency_ms', 'correlation_id'):
        evaluation_identity.pop(field)
    for field in ('decided_at', 'idempotency_key', 'correlation_id'):
        context_identity.pop(field)
    decision_id = 'decision-' + canonical_hash({
        'plan': plan, 'configuration': config, 'evaluation': evaluation_identity,
        'context': context_identity,
    })
    questions = []
    for category in categories:
        issues = triggered[category]
        role = {'FACT_UNCERTAIN': 'CHECKER', 'POLICY_OUT_OF_SCOPE': 'POLICY_OWNER',
                'AUTHORITY_EXCEEDED': 'BUDGET_AUTHORITY'}[category]
        actor_id = ({'CHECKER': authority.checker_id, 'POLICY_OWNER': authority.policy_owner_id,
                     'BUDGET_AUTHORITY': authority.budget_authority_id}[role] if authority else None)
        codes = tuple(c.rule_id for c in issues)
        refs = tuple(dict.fromkeys(r for c in issues for r in c.evidence_refs))
        limits = '; '.join(c.applicable_rule_or_limit for c in issues)
        reason = 'Review required for ' + ', '.join(codes) + '.'
        if not refs:
            reason += ' No trustworthy evidence is available for these checks.'
        questions.append(Escalation(
            decision_id + '-' + category, category, ', '.join(codes),
            {c.rule_id: c.observed_value for c in issues}, limits, refs,
            'For plan ' + plan.plan_id + ', inspect ' + ', '.join(codes) +
            ' against ' + limits + ' Can the configured authority resolve these issues or defer?',
            (AnswerOption('REVIEW', 'Record an authorized assessment'),
             AnswerOption('DEFER', 'Defer and request clarification')),
            TargetAuthority(role, actor_id), ctx.decided_at, 1, plan.plan_id,
            plan.plan_version, plan.approval_round, ev.evaluation_id, decision_id,
            plan.input_hash, policy.policy_version, codes, reason,
        ))
    reason = ('All mandatory auto-approval gates passed.' if not categories else
              'Human Review required: ' + ', '.join(c.rule_id for c in checks if c.result != 'PASS') + '.')
    decision = DecisionResult(
        decision_id, plan.plan_id, plan.plan_version, plan.approval_round, outcome,
        categories[0] if categories else None, reason, RULE_IDS, plan.input_hash,
        policy.policy_version, ev.evaluation_id, Actor('SYSTEM', 'decision-engine'),
        ctx.decided_at, 1, tuple(checks), tuple(engine_evidence),
        tuple(q.escalation_id for q in questions), policy.snapshot_id, canonical_hash(policy),
        budget, authority.snapshot_id if authority else None,
        canonical_hash(authority) if authority else None, ctx.idempotency_key,
        ctx.correlation_id, ctx.round_revision,
    )
    auto = outcome == 'AUTO_APPROVED'
    audit = AuditEvent(
        'audit-' + decision_id, 'SYSTEM', 'decision-engine',
        'AUTO_APPROVED' if auto else 'ENGINE_ROUTED', plan.plan_id, ctx.round_revision,
        plan.input_hash, policy.policy_version, ev.model_version, reason,
        State('PENDING_APPROVAL', 'AI_PROCESSING', 'ACTIVE'),
        State('APPROVED', 'AI_AUTO_APPROVED', 'CLOSED') if auto else
        State('PENDING_APPROVAL', 'HUMAN_REVIEW_REQUIRED', 'ACTIVE'),
        ctx.decided_at, 1, plan.plan_id, plan.plan_version, plan.approval_round,
        ev.run_id, ev.evaluation_id, decision_id, None, ctx.correlation_id,
        ctx.idempotency_key, RULE_IDS, tuple(e.evidence_id for e in engine_evidence),
        policy.snapshot_id, canonical_hash(policy), budget.configuration_id, budget.configuration_hash,
        decision.authority_snapshot_id, decision.authority_snapshot_hash,
        outcome, None, None,
    )
    return DecisionBundle(ev, decision, tuple(questions), audit)
