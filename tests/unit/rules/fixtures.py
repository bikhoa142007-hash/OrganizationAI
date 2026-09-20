"""Synthetic WP2 data only. No production limits or identities."""
from src.backend.domain.models import MarketingPlan, AttachmentManifest
from src.backend.domain.policy import (
    ApprovalConfiguration, PolicySnapshot, BudgetConfiguration, AuthoritySnapshot, Criterion,
)

NOW = '2026-09-20T00:00:00Z'


def plan():
    return MarketingPlan('SYNTHETIC-PLAN', 1, 1, {
        'title': 'Synthetic campaign', 'maker_id': 'synthetic-maker',
        'checker_id': 'synthetic-checker', 'department': 'synthetic-marketing',
        'objective': 'Demonstrate review', 'summary': 'Synthetic example',
        'start_date': '2026-10-01', 'end_date': '2026-10-31',
        'budget_minor_units': '10000', 'currency': 'VND',
    }, (AttachmentManifest('synthetic-image', 'a' * 64, 'image/png', 100),))


def config():
    return ApprovalConfiguration(
        PolicySnapshot('synthetic-policy-snapshot', 'SYNTHETIC-1', True,
                       ('title', 'maker_id', 'checker_id', 'department', 'objective',
                        'summary', 'start_date', 'end_date', 'budget_minor_units', 'currency'),
                       (Criterion('synthetic-total', 100),), ('synthetic-model-1',),
                       ('image/png',), 1000000),
        (BudgetConfiguration('synthetic-budget', 'VND', 0, '10000', 'synthetic-marketing', True),),
        AuthoritySnapshot('synthetic-authority', 'VND', '10000',
                          ('synthetic-marketing',), 'synthetic-checker',
                          'synthetic-policy-owner', 'synthetic-budget-authority', True),
    )


def evaluation(p=None):
    p = p or plan()
    return dict(
        evaluation_id='synthetic-eval', plan_id=p.plan_id, plan_version=p.plan_version,
        approval_round=p.approval_round, run_id='synthetic-run', schema_version=1,
        input_hash=p.input_hash, policy_version='SYNTHETIC-1', provider='MOCK_VLM',
        model_version='synthetic-model-1', status='SUCCEEDED', media_result='PASS',
        media_findings=[], media_confidence=.9, feasibility_score=71,
        feasibility_confidence=.9, missing_facts=[], evidence_conflicts=[],
        evidence=[dict(evidence_id='ev-image', source_type='ATTACHMENT',
                       source_ref='synthetic-image', observation='Synthetic image checked',
                       content_hash='a' * 64)],
        proposed_action='RECOMMEND_AUTO_APPROVAL', escalation_category=None,
        reason='Synthetic evaluation', latency_ms=1, created_at=NOW, started_at=NOW,
        completed_at=NOW, agent_errors=[], raw_output_hash=None,
        reported_model_version=None, correlation_id='synthetic-trace',
        criterion_scores=[dict(criterion_id='synthetic-total', score=71,
                               maximum_score=100, rationale='Synthetic score',
                               evidence_refs=['ev-image'])], assumptions=[],
    )


def recommend_review(e, category='FACT_UNCERTAIN'):
    e.update(proposed_action='RECOMMEND_HUMAN_REVIEW', escalation_category=category)
    return e
