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
                                      ('synthetic-checker',), False))

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

    def test_score_70_requires_policy_review(self):
        e = recommend_review(evaluation(), 'POLICY_OUT_OF_SCOPE')
        e['feasibility_score'] = e['criterion_scores'][0]['score'] = 70
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

    def test_same_inputs_produce_same_complete_bundle(self):
        self.assertEqual(self.run_case(), self.run_case())
