import unittest
from dataclasses import replace

from fixtures import plan, config, evaluation, recommend_review, NOW
from src.backend.rules.decision import decide, DecisionContext


class DecisionTests(unittest.TestCase):
    def run_case(self, raw=None, cfg=None, p=None):
        p = p or plan()
        return decide(p, cfg or config(), raw if raw is not None else evaluation(p),
                      DecisionContext('synthetic-eval', 'synthetic-run', 'MOCK_VLM',
                                      'synthetic-trace', 'synthetic-intent', NOW,
                                      'PENDING_APPROVAL', 'ACTIVE', 0,
                                      p.input_hash, (('synthetic-image', 'a' * 64),),
                                      ('synthetic-checker',), False,
                                      ('synthetic-checker', 'synthetic-policy-owner', 'synthetic-budget-authority')))

    def assert_review(self, bundle, code, category):
        d = bundle.decision
        self.assertEqual(d.outcome, 'HUMAN_REVIEW_REQUIRED')
        self.assertIn(code, d.reason_codes)
        self.assertEqual(d.escalation_category, category)
        self.assertTrue(bundle.escalations)
        self.assertEqual(d.escalation_ids, tuple(q.escalation_id for q in bundle.escalations))

    def test_71_and_budget_equality_auto_approve(self):
        b = self.run_case()
        self.assertEqual(b.decision.outcome, 'AUTO_APPROVED')
        self.assertEqual(b.decision.reason_codes, ())
        self.assertIsNone(b.decision.escalation_category)
        self.assertEqual(b.audit.action, 'AUTO_APPROVED')

    def test_five_million_auto_limit_and_ten_million_budget_boundaries(self):
        cfg = config()
        cfg = replace(
            cfg,
            budgets=(replace(cfg.budgets[0], limit_minor_units='10000000'),),
            authority=replace(cfg.authority, auto_limit_minor_units='5000000'),
        )
        p = plan()

        at_auto_limit = replace(p, payload={**p.payload, 'budget_minor_units': '5000000'})
        self.assertEqual(self.run_case(cfg=cfg, p=at_auto_limit).decision.outcome, 'AUTO_APPROVED')

        over_auto_limit = replace(p, payload={**p.payload, 'budget_minor_units': '5000001'})
        over_auto_bundle = self.run_case(cfg=cfg, p=over_auto_limit)
        self.assertEqual(over_auto_bundle.decision.outcome, 'HUMAN_REVIEW_REQUIRED')
        self.assertEqual(over_auto_bundle.decision.budget_validation.result, 'PASS')
        self.assertIn('AUTHORITY_LIMIT', over_auto_bundle.decision.reason_codes)

        at_plan_limit = replace(p, payload={**p.payload, 'budget_minor_units': '10000000'})
        plan_limit_bundle = self.run_case(cfg=cfg, p=at_plan_limit)
        self.assertEqual(plan_limit_bundle.decision.budget_validation.result, 'PASS')
        self.assertEqual(plan_limit_bundle.decision.outcome, 'HUMAN_REVIEW_REQUIRED')

        above_plan_limit = replace(p, payload={**p.payload, 'budget_minor_units': '10000001'})
        above_plan_bundle = self.run_case(cfg=cfg, p=above_plan_limit)
        self.assertEqual(above_plan_bundle.decision.budget_validation.result, 'FAIL')
        self.assertEqual(above_plan_bundle.decision.outcome, 'HUMAN_REVIEW_REQUIRED')

    def test_score_70_requires_policy_review(self):
        e = recommend_review(evaluation(), 'POLICY_OUT_OF_SCOPE')
        e['feasibility_score'] = 70
        for criterion in e['criterion_scores']:
            criterion['score'] = 70
        self.assert_review(self.run_case(e), 'FEASIBILITY_SCORE', 'POLICY_OUT_OF_SCOPE')

    def test_budget_exceeded_is_authority_review(self):
        cfg = config()
        cfg = replace(cfg, budgets=(replace(cfg.budgets[0], limit_minor_units='9999'),))
        self.assert_review(self.run_case(cfg=cfg), 'BUDGET_LIMIT', 'AUTHORITY_EXCEEDED')

    def test_hard_violation_is_policy_review(self):
        e = recommend_review(evaluation(), 'POLICY_OUT_OF_SCOPE')
        e['media_findings'] = [dict(finding_id='f', severity='HARD_VIOLATION',
                                   description='Synthetic violation', rule_id='NO_HARD_VIOLATION',
                                   evidence_refs=['ev-image'])]
        self.assert_review(self.run_case(e), 'NO_HARD_VIOLATION', 'POLICY_OUT_OF_SCOPE')

    def test_conflict_requires_fact_review(self):
        e = recommend_review(evaluation())
        e['evidence_conflicts'] = [dict(conflict_id='c', description='Synthetic conflict',
                                       evidence_refs=['ev-image'])]
        self.assert_review(self.run_case(e), 'NO_EVIDENCE_CONFLICT', 'FACT_UNCERTAIN')

    def test_missing_collection_and_invalid_schema_fail_closed(self):
        for field in ('media_findings', 'agent_errors', 'evidence', 'criterion_scores'):
            e = evaluation()
            del e[field]
            with self.subTest(field=field):
                self.assert_review(self.run_case(e), 'EVAL_VALID', 'FACT_UNCERTAIN')

    def test_authority_exceeded(self):
        cfg = config()
        cfg = replace(cfg, authority=replace(cfg.authority, auto_limit_minor_units='9999'))
        self.assert_review(self.run_case(cfg=cfg), 'AUTHORITY_LIMIT', 'AUTHORITY_EXCEEDED')

    def test_missing_or_inactive_authority_actor_requires_review(self):
        p = plan()
        context = DecisionContext(
            'synthetic-eval', 'synthetic-run', 'MOCK_VLM', 'synthetic-trace',
            'synthetic-intent', NOW, 'PENDING_APPROVAL', 'ACTIVE', 0,
            p.input_hash, (('synthetic-image', 'a' * 64),), ('synthetic-checker',), False,
            ('synthetic-checker', 'synthetic-policy-owner'),
        )
        bundle = decide(p, config(), evaluation(p), context)
        self.assertEqual(bundle.decision.outcome, 'HUMAN_REVIEW_REQUIRED')
        self.assertIn('AUTHORITY_LIMIT', bundle.decision.reason_codes)

    def test_channel_outside_approved_scope_requires_review(self):
        p = plan()
        p = replace(p, payload={**p.payload, 'channels': ['email']})
        bundle = self.run_case(p=p)
        self.assertEqual(bundle.decision.outcome, 'HUMAN_REVIEW_REQUIRED')
        self.assertIn('DECISION_SCOPE', bundle.decision.reason_codes)

        p = plan()
        p = replace(p, payload={**p.payload, 'department': 'Sales'})
        bundle = self.run_case(p=p)
        self.assertEqual(bundle.decision.outcome, 'HUMAN_REVIEW_REQUIRED')
        self.assertIn('DECISION_SCOPE', bundle.decision.reason_codes)

    def test_missing_model_identity_requires_review(self):
        raw = evaluation()
        raw['model_version'] = None
        bundle = self.run_case(raw)
        self.assertEqual(bundle.decision.outcome, 'HUMAN_REVIEW_REQUIRED')
        self.assertIn('EVAL_VALID', bundle.decision.reason_codes)

    def test_same_inputs_produce_same_complete_bundle(self):
        self.assertEqual(self.run_case(), self.run_case())
