"""15 independently named synthetic ground-truth inputs; expectations never call the engine.

Run as a module with --database PATH to repeatably seed the WP2 snapshot adapter.
"""
import argparse
from dataclasses import dataclass, replace

from tests.unit.rules.fixtures import plan, config, evaluation, recommend_review, NOW
from src.backend.domain.models import MarketingPlan
from src.backend.domain.policy import ApprovalConfiguration
from src.backend.rules.decision import DecisionContext
from src.backend.domain.store import SnapshotStore


@dataclass(frozen=True)
class SyntheticCase:
    case_id: str
    group: str
    description: str
    plan: MarketingPlan
    configuration: ApprovalConfiguration
    evaluation: dict
    context: DecisionContext
    expected_outcome: str
    expected_category: str | None
    expected_reason_codes: tuple[str, ...]
    expected_question_categories: tuple[str, ...]
    synthetic: bool = True


def cases():
    result = []

    def add(case_id, group, description, *, p=None, cfg=None, raw=None,
            category=None, codes=()):
        p, cfg = p or plan(), cfg or config()
        ctx = DecisionContext('synthetic-eval', 'synthetic-run', 'MOCK_VLM',
                              'synthetic-trace', 'synthetic-intent', NOW,
                              'PENDING_APPROVAL', 'ACTIVE', 0, p.input_hash,
                              (('synthetic-image', 'a' * 64),), ('synthetic-checker',), False)
        result.append(SyntheticCase(
            case_id, group, description, p, cfg, evaluation(p) if raw is None else raw, ctx,
            'AUTO_APPROVED' if category is None else 'HUMAN_REVIEW_REQUIRED', category,
            codes, () if category is None else (category,),
        ))

    add('routine-01', 'routine', 'Score 71, cost exactly at budget and authority limits.')
    p = plan()
    add('routine-02', 'routine', 'Cost below limits.',
        p=replace(p, payload={**p.payload, 'budget_minor_units': '9999'}))
    add('routine-03', 'routine', 'Zero cost is valid.',
        p=replace(p, payload={**p.payload, 'budget_minor_units': '0'}))
    e = evaluation()
    e['media_confidence'] = .85
    add('routine-04', 'routine', 'Media confidence exactly 0.85.', raw=e)
    e = evaluation()
    e['feasibility_confidence'] = .80
    add('routine-05', 'routine', 'Feasibility confidence exactly 0.80.', raw=e)
    e = evaluation()
    e['media_findings'] = [dict(finding_id='synthetic-warning', severity='WARNING',
                               description='Optional cosmetic note.', rule_id=None,
                               evidence_refs=['ev-image'])]
    add('routine-06', 'routine', 'Optional warning alone is not a failed gate.', raw=e)

    e = recommend_review(evaluation())
    e['media_confidence'] = .849
    add('fact-01', 'fact-uncertain', 'Low media confidence.', raw=e,
        category='FACT_UNCERTAIN', codes=('MEDIA_CONFIDENCE',))
    e = recommend_review(evaluation())
    e['evidence_conflicts'] = [dict(conflict_id='synthetic-conflict',
                                   description='Conflicting synthetic image evidence.',
                                   evidence_refs=['ev-image'])]
    add('fact-02', 'fact-uncertain', 'Unresolved evidence conflict.', raw=e,
        category='FACT_UNCERTAIN', codes=('NO_EVIDENCE_CONFLICT',))
    e = evaluation()
    e.update(status='TIMED_OUT', media_result=None, media_confidence=None,
             feasibility_score=None, feasibility_confidence=None, proposed_action=None,
             escalation_category='FACT_UNCERTAIN',
             agent_errors=[dict(component='vlm', code='PROVIDER_TIMEOUT', message='Synthetic timeout')])
    add('fact-03', 'fact-uncertain', 'Provider timeout preserves submission.', raw=e,
        category='FACT_UNCERTAIN', codes=('EVAL_VALID', 'MEDIA_PASS', 'MEDIA_CONFIDENCE',
            'FEASIBILITY_SCORE', 'FEASIBILITY_CONFIDENCE', 'NO_HARD_VIOLATION', 'NO_EVIDENCE_CONFLICT'))

    cfg = config()
    add('policy-01', 'policy-out-of-scope', 'No applicable budget configuration.',
        cfg=replace(cfg, budgets=()), category='POLICY_OUT_OF_SCOPE', codes=('BUDGET_LIMIT',))
    add('policy-02', 'policy-out-of-scope', 'Auto approval disabled.',
        cfg=replace(cfg, policy=replace(cfg.policy, auto_approval_policy_enabled=False)),
        category='POLICY_OUT_OF_SCOPE', codes=('POLICY_ENABLED',))
    add('authority-01', 'authority-exceeded', 'Cost exceeds allowed budget.',
        cfg=replace(cfg, budgets=(replace(cfg.budgets[0], limit_minor_units='9999'),)),
        category='AUTHORITY_EXCEEDED', codes=('BUDGET_LIMIT',))
    add('authority-02', 'authority-exceeded', 'Cost exceeds delegated automatic mandate.',
        cfg=replace(cfg, authority=replace(cfg.authority, auto_limit_minor_units='9999')),
        category='AUTHORITY_EXCEEDED', codes=('AUTHORITY_LIMIT',))

    add('violation-01', 'deterministic-policy-violation', 'Submitted end date precedes start date.',
        p=replace(p, payload={**p.payload, 'end_date': '2026-09-01'}),
        category='FACT_UNCERTAIN', codes=('INPUT_INTEGRITY',))
    add('violation-02', 'deterministic-policy-violation', 'Attachment exceeds configured file size.',
        p=replace(p, attachments=(replace(p.attachments[0], byte_size=1000001),)),
        category='FACT_UNCERTAIN', codes=('INPUT_INTEGRITY',))
    return tuple(result)


def seed(store):
    records = tuple(('synthetic-case', case.case_id, case) for case in cases())
    store.append_many(records)
    return len(records)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    args = parser.parse_args()
    with SnapshotStore(args.database) as store:
        store.migrate()
        print(f'Seeded {seed(store)} labelled synthetic WP2 cases.')
