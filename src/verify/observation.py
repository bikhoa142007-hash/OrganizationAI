"""Validate persisted cross-record integrity without recomputing decision rules."""
from src.backend.domain.models import AuditEvent, DecisionResult, EvaluationResult, Escalation, MarketingPlan
from src.shared.validation import require


def validate_observation(actual):
    decision = DecisionResult.from_dict(actual['decision'])
    evaluation = EvaluationResult.from_dict(actual['evaluation'])
    version = MarketingPlan.from_dict(actual['versions'][0])
    require(actual['application_reference'] == 'ApprovalWorkflow.get_verify_observation', 'Application path missing')
    require(decision.input_hash == evaluation.input_hash == version.input_hash, 'Snapshot hash mismatch')
    require(decision.evaluation_id == evaluation.evaluation_id and decision.policy_version == evaluation.policy_version,
            'Evaluation linkage mismatch')
    for record in (decision, evaluation):
        require((record.plan_id, record.plan_version, record.approval_round) ==
                (version.plan_id, version.plan_version, version.approval_round), 'Record identity mismatch')
    questions = [Escalation.from_dict(q) for q in actual['questions']]
    require({q.escalation_id for q in questions} == set(decision.escalation_ids), 'Question set mismatch')
    for q in questions:
        require(q.decision_id == decision.decision_id and q.evaluation_id == evaluation.evaluation_id
                and q.input_hash == version.input_hash, 'Question provenance mismatch')
    if decision.outcome == 'HUMAN_REVIEW_REQUIRED':
        require(any(q.category == decision.escalation_category for q in questions), 'Primary category question missing')
    events = [AuditEvent.from_dict(e) for e in actual['audit']]
    require(any(e.decision_id == decision.decision_id and e.input_hash == version.input_hash
                and e.action in ('AUTO_APPROVED', 'ENGINE_ROUTED') for e in events), 'Decision audit missing')
    require(any(e.action == 'PLAN_SUBMITTED' and e.input_hash == version.input_hash for e in events), 'Submission audit missing')


def contract_result(row):
    """WP1 Verify view for cases with fully specified expected categories.

The BA hard-violation GT cases intentionally have no expected category, and
remain detailed GT regression reports rather than fabricated WP1 Verify rows.
"""
    expected, actual = row['expected'], row['actual']
    if expected['route'] == 'HUMAN_REVIEW_REQUIRED' and expected['primary_category'] is None:
        return None
    ids = ('APPLICATION_PATH', 'SCHEMA_VALID', 'OUTCOME_MATCH', 'CATEGORY_MATCH',
           'QUESTION_VALID', 'RULE_TRACE', 'AUDIT_TRACE', 'SNAPSHOT_MATCH')
    valid = False
    if actual:
        try:
            validate_observation(actual)
            valid = True
        except ValueError:
            pass
    assertions = [dict(assertion_id=key, passed=valid and not row['differences'],
                       detail='Persisted workflow records validated and oracle assertions checked.' if valid and not row['differences']
                       else '; '.join(row['differences']) or 'Observation validation failed.') for key in ids]
    d = actual['decision'] if actual else {}
    return dict(case_id=row['case_id'], expected_action=expected['route'], actual_action=d.get('outcome'),
                expected_category=expected['primary_category'], actual_category=d.get('escalation_category'),
                generated_question=actual['questions'] if actual else [], applied_rule_ids=d.get('applied_rule_ids', []),
                started_at=row['started_at'], completed_at=row['completed_at'], duration_ms=row['duration_ms'],
                schema_version=1, evaluation_id=d.get('evaluation_id'), decision_id=d.get('decision_id'),
                plan_id=d.get('plan_id'), plan_version=d.get('plan_version'), approval_round=d.get('approval_round'),
                input_hash=d.get('input_hash'), policy_version=d.get('policy_version'), application_invoked=actual is not None,
                application_reference=actual['application_reference'] if actual else None,
                correlation_id=d.get('correlation_id', 'ba-run'), assertions=assertions,
                error={'code': 'VERIFY_FAILED', 'message': row['error']} if row['error'] else None,
                **{'pass': bool(valid and row['passed'])})
