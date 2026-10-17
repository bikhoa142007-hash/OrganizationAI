import unittest
from dataclasses import replace
from decimal import Decimal

from fixtures import plan, config, evaluation, recommend_review, NOW
from src.backend.rules.decision import decide, DecisionContext
from src.backend.domain.policy import Criterion, StrategyRubric, STRATEGY_CRITERIA, STRATEGY_RUBRIC_V2_VERSION


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

    def strategy_v2_case(self, scores, *, critical_gaps=()):
        p = plan()
        base = config()
        rubric = StrategyRubric.from_dict({
            "rubric_id": "BA-STRATEGY-7",
            "rubric_version": STRATEGY_RUBRIC_V2_VERSION,
            "status": "ACTIVE",
            "criteria": [
                {"criterion_id": criterion_id, "label": label, "weight": weight}
                for criterion_id, label, weight in STRATEGY_CRITERIA
            ],
        })
        configured_policy = replace(
            base.policy,
            criteria=tuple(Criterion(criterion_id, weight)
                           for criterion_id, _label, weight in STRATEGY_CRITERIA),
        )
        cfg = replace(base, policy=configured_policy, strategy_rubric=rubric)
        weighted_score = sum(
            Decimal(str(score)) * Decimal(weight) / Decimal(100)
            for score, (_criterion_id, _label, weight) in zip(scores, STRATEGY_CRITERIA)
        )
        raw = evaluation(p)
        raw.update(
            schema_version=2,
            strategy_rubric_version=STRATEGY_RUBRIC_V2_VERSION,
            strategy_critical_gaps=list(critical_gaps),
            feasibility_score=float(weighted_score),
            criterion_scores=[
                {"criterion_id": criterion_id, "score": score, "maximum_score": 100,
                 "rationale": "Synthetic rubric-gate case.", "evidence_refs": ["ev-image"]}
                for score, (criterion_id, _label, _weight) in zip(scores, STRATEGY_CRITERIA)
            ],
        )
        if critical_gaps or any(
            (criterion_id in ("objective", "audience", "channel", "timeline") and score == 0)
            or (criterion_id in ("kpi", "budget_efficiency", "risk_control") and score < 50)
            for score, (criterion_id, _label, _weight) in zip(scores, STRATEGY_CRITERIA)
        ):
            recommend_review(raw)
        return cfg, p, raw

    def test_v2_zero_core_criterion_routes_checker_even_when_weighted_total_passes(self):
        scores = [0, 100, 100, 100, 100, 100, 100]
        cfg, p, raw = self.strategy_v2_case(scores)

        bundle = self.run_case(raw, cfg, p)

        self.assertEqual(raw["feasibility_score"], 85)
        self.assert_review(bundle, "STRATEGY_REVIEW_GATES", "FACT_UNCERTAIN")

    def test_v2_kpi_budget_and_risk_scores_below_50_route_checker(self):
        for criterion_id in ("kpi", "budget_efficiency", "risk_control"):
            scores = [100] * 7
            scores[next(index for index, row in enumerate(STRATEGY_CRITERIA)
                        if row[0] == criterion_id)] = 25
            cfg, p, raw = self.strategy_v2_case(scores)
            with self.subTest(criterion=criterion_id):
                self.assert_review(self.run_case(raw, cfg, p), "STRATEGY_REVIEW_GATES", "FACT_UNCERTAIN")

    def test_v2_fifty_points_passes_individual_checker_gate_and_critical_gaps_do_not(self):
        scores = [100] * 7
        scores[-1] = 50
        cfg, p, raw = self.strategy_v2_case(scores)
        self.assertEqual(self.run_case(raw, cfg, p).decision.outcome, "AUTO_APPROVED")

        cfg, p, raw = self.strategy_v2_case([75, 75, 75, 75, 75, 75, 50],
                                             critical_gaps=("A material assumption is unverified.",))
        self.assert_review(self.run_case(raw, cfg, p), "STRATEGY_REVIEW_GATES", "FACT_UNCERTAIN")

    def test_v2_rubric_version_mismatch_and_non_anchor_score_fail_closed(self):
        cfg, p, raw = self.strategy_v2_case([75, 75, 75, 75, 75, 75, 50])
        wrong_version = dict(raw, strategy_rubric_version="BA-STRATEGY-7-1.0")
        self.assert_review(self.run_case(wrong_version, cfg, p), "EVAL_VALID", "FACT_UNCERTAIN")

        wrong_score = dict(raw)
        wrong_score["criterion_scores"] = [dict(item) for item in raw["criterion_scores"]]
        wrong_score["criterion_scores"][0]["score"] = 74
        wrong_score["feasibility_score"] = 72.35
        self.assert_review(self.run_case(wrong_score, cfg, p), "EVAL_VALID", "FACT_UNCERTAIN")
