import unittest
from collections import Counter
from src.backend.domain.store import SnapshotStore
from src.backend.rules.decision import decide
from tests.unit.rules.synthetic_cases import cases, seed


class SyntheticCasesTests(unittest.TestCase):
    def test_15_cases_match_independent_ground_truth_and_question_requirements(self):
        dataset = cases()
        self.assertEqual(len(dataset), 15)
        self.assertEqual(Counter(c.group for c in dataset), {
            'routine': 6, 'fact-uncertain': 3, 'policy-out-of-scope': 2,
            'authority-exceeded': 2, 'deterministic-policy-violation': 2,
        })
        for case in dataset:
            with self.subTest(case=case.case_id):
                self.assertTrue(case.synthetic)
                b = decide(case.plan, case.configuration, case.evaluation, case.context)
                self.assertEqual(b.decision.outcome, case.expected_outcome)
                self.assertEqual(b.decision.escalation_category, case.expected_category)
                self.assertEqual(b.decision.reason_codes, case.expected_reason_codes)
                self.assertEqual(tuple(q.category for q in b.escalations), case.expected_question_categories)
                for q in b.escalations:
                    self.assertIn('DEFER', [o.option_id for o in q.answer_options])
                    self.assertTrue(q.applied_rule_ids)
                    self.assertIn(case.plan.plan_id, q.question)

    def test_repeatable_15_case_seed_retains_inspectable_inputs_and_expectations(self):
        with SnapshotStore(':memory:') as store:
            store.migrate()
            self.assertEqual(seed(store), 15)
            self.assertEqual(seed(store), 15)
            for case in cases():
                saved = store.read('synthetic-case', case.case_id)
                self.assertTrue(saved['synthetic'])
                self.assertEqual(saved['expected_outcome'], case.expected_outcome)
                self.assertIn('input_hash', saved['evaluation'])
                self.assertIn('policy_version', saved['configuration']['policy'])
