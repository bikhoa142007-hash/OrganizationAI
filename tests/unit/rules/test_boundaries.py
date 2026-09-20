import copy
import unittest
from dataclasses import replace

from fixtures import plan, config, evaluation, recommend_review, NOW
from src.backend.rules.decision import decide, DecisionContext
from src.backend.domain.models import EvaluationResult, DecisionResult, AuditEvent, HumanDecision, Actor
from src.shared.validation import ValidationError


def context(p=None, **changes):
    p = p or plan()
    return replace(DecisionContext('synthetic-eval', 'synthetic-run', 'MOCK_VLM',
                   'synthetic-trace', 'synthetic-intent', NOW, 'PENDING_APPROVAL', 'ACTIVE', 0,
                   p.input_hash, (('synthetic-image', 'a' * 64),), ('synthetic-checker',), False), **changes)


def run(raw=None, p=None, cfg=None, ctx=None):
    p = p or plan()
    return decide(p, cfg or config(), evaluation(p) if raw is None else raw, ctx or context(p))


class BoundaryTests(unittest.TestCase):
    def assert_fact(self, raw):
        result = run(raw)
        self.assertEqual(result.decision.outcome, 'HUMAN_REVIEW_REQUIRED')
        self.assertEqual(result.decision.escalation_category, 'FACT_UNCERTAIN')
        return result

    def test_all_required_evaluation_properties_and_unknown_fields(self):
        for field in evaluation():
            e = evaluation()
            del e[field]
            with self.subTest(field=field):
                b = self.assert_fact(e)
                self.assertIn('EVAL_VALID', b.decision.reason_codes)
        e = evaluation()
        e['outcome'] = 'REJECTED_BY_DETERMINISTIC_POLICY'
        self.assert_fact(e)

    def test_agent_error_and_timeout_preserve_failure_envelope(self):
        for status, code in (('FAILED', 'PROVIDER_ERROR'), ('TIMED_OUT', 'PROVIDER_TIMEOUT')):
            e = evaluation()
            e.update(status=status, media_result=None, media_confidence=None, feasibility_score=None,
                     feasibility_confidence=None, proposed_action=None, escalation_category='FACT_UNCERTAIN',
                     agent_errors=[dict(component='vlm', code=code, message='Synthetic failure')])
            b = self.assert_fact(e)
            self.assertEqual(b.evaluation.status, status)
            self.assertEqual(b.evaluation.agent_errors[0].code, code)

    def test_invalid_numbers_enums_models_timestamps_and_identity(self):
        invalid = [('feasibility_score', float('nan')), ('media_confidence', float('inf')),
                   ('media_confidence', True), ('media_confidence', -1), ('status', 'OK'),
                   ('model_version', 'unknown'), ('plan_id', 'other'), ('input_hash', 'b' * 64),
                   ('plan_version', True), ('created_at', 'yesterday'),
                   ('completed_at', '2026-09-19T00:00:00Z')]
        for field, value in invalid:
            e = evaluation()
            e[field] = value
            with self.subTest(field=field, value=value):
                self.assertIn('EVAL_VALID', self.assert_fact(e).decision.reason_codes)

    def test_low_confidence_boundaries(self):
        for field, boundary in (('media_confidence', .85), ('feasibility_confidence', .80)):
            e = evaluation()
            e[field] = boundary
            self.assertEqual(run(e).decision.outcome, 'AUTO_APPROVED')
            recommend_review(e)
            e[field] -= .001
            self.assert_fact(e)

    def test_missing_facts_and_wrong_evidence(self):
        e = recommend_review(evaluation())
        e['missing_facts'] = ['Synthetic uncertain fact']
        self.assertIn('NO_EVIDENCE_CONFLICT', self.assert_fact(e).decision.reason_codes)
        for source_ref, digest in (('another-image', 'a' * 64), ('synthetic-image', 'b' * 64)):
            e = evaluation()
            e['evidence'][0].update(source_ref=source_ref, content_hash=digest)
            self.assertIn('EVAL_VALID', self.assert_fact(e).decision.reason_codes)

    def test_empty_evidence_and_incorrect_criterion_total(self):
        e = evaluation()
        e['evidence'] = []
        e['criterion_scores'][0]['evidence_refs'] = []
        self.assertIn('INPUT_INTEGRITY', self.assert_fact(e).decision.reason_codes)
        e = evaluation()
        e['criterion_scores'][0]['score'] = 72
        self.assertIn('EVAL_VALID', self.assert_fact(e).decision.reason_codes)

    def test_disabled_missing_ambiguous_and_inactive_configuration(self):
        cfg = config()
        variants = [replace(cfg, policy=replace(cfg.policy, auto_approval_policy_enabled=False)),
                    replace(cfg, budgets=()), replace(cfg, budgets=cfg.budgets * 2),
                    replace(cfg, budgets=(replace(cfg.budgets[0], active=False),)),
                    replace(cfg, authority=None)]
        for variant in variants:
            b = run(cfg=variant)
            self.assertEqual(b.decision.outcome, 'HUMAN_REVIEW_REQUIRED')
            self.assertEqual(b.decision.escalation_category, 'POLICY_OUT_OF_SCOPE')

    def test_invalid_submission_and_tamper_checks(self):
        p = plan()
        for field, value in (('title', ' '), ('checker_id', 'synthetic-maker'),
                             ('checker_id', 'unknown'), ('start_date', '2026-11-01'),
                             ('budget_minor_units', '-1'), ('budget_minor_units', 10000)):
            changed = replace(p, payload={**p.payload, field: value})
            b = run(p=changed)
            self.assertEqual(b.decision.outcome, 'HUMAN_REVIEW_REQUIRED')
            self.assertIn('INPUT_INTEGRITY', b.decision.reason_codes)
        for ctx in (context(suspicious_input=True), context(expected_input_hash='b' * 64),
                    context(verified_attachment_hashes=())):
            self.assertIn('INPUT_INTEGRITY', run(ctx=ctx).decision.reason_codes)

    def test_closed_round_never_routes_or_reopens(self):
        for ctx in (context(plan_status='APPROVED'), context(approval_round_status='CLOSED')):
            with self.assertRaisesRegex(ValidationError, 'CONFLICT'):
                run(ctx=ctx)

    def test_precedence_retains_all_categories_and_ignores_untrusted_claims(self):
        cfg = config()
        cfg = replace(cfg, authority=replace(cfg.authority, auto_limit_minor_units='9999'),
                      policy=replace(cfg.policy, auto_approval_policy_enabled=False))
        b = run({}, cfg=cfg)
        self.assertEqual(b.decision.escalation_category, 'AUTHORITY_EXCEEDED')
        self.assertEqual({q.category for q in b.escalations},
                         {'AUTHORITY_EXCEEDED', 'POLICY_OUT_OF_SCOPE', 'FACT_UNCERTAIN'})
        e = evaluation()
        e['escalation_category'] = 'AUTHORITY_EXCEEDED'
        self.assert_fact(e)

    def test_wire_roundtrip_and_reserved_outcome_rejection(self):
        b = run()
        for record in (b.evaluation, b.decision, b.audit):
            self.assertEqual(type(record).from_dict(record.to_dict()), record)
        for record in (b.decision, b.audit):
            data = record.to_dict()
            data['outcome'] = 'REJECTED_BY_DETERMINISTIC_POLICY'
            with self.assertRaises(ValidationError):
                type(record).from_dict(data)

    def test_provider_inputs_and_previous_results_are_unchanged(self):
        raw = evaluation()
        before = copy.deepcopy(raw)
        first = run(raw)
        run(recommend_review(evaluation()))
        self.assertEqual(raw, before)
        self.assertEqual(first, run(raw))

    def test_human_rejection_self_approval_and_override(self):
        d = HumanDecision('h', 'p', 1, 1, 'APPROVED', 'd', 'e', Actor('HUMAN', 'checker'),
                          None, None, NOW, 'a' * 64, 'v1', 'key', 'trace', 0)
        with self.assertRaises(ValidationError):
            replace(d, action='REJECTED')
        with self.assertRaises(ValidationError):
            replace(d, action='REJECTED', reason=' ')
        with self.assertRaises(ValidationError):
            d.validate_authorization('checker', 'checker', 'RECOMMEND_AUTO_APPROVAL')
        with self.assertRaises(ValidationError):
            d.validate_authorization('maker', 'checker', 'RECOMMEND_HUMAN_REVIEW')
        replace(d, override_reason='Synthetic manual verification').validate_authorization(
            'maker', 'checker', 'RECOMMEND_HUMAN_REVIEW')

    def test_non_text_mandatory_content_cannot_auto_approve(self):
        p = plan()
        for field in ('title', 'objective', 'summary', 'department'):
            for value in ([], {}, False, 12):
                changed = replace(p, payload={**p.payload, field: value})
                with self.subTest(field=field, value=value):
                    b = run(p=changed)
                    self.assertEqual(b.decision.outcome, 'HUMAN_REVIEW_REQUIRED')
                    self.assertIn('INPUT_INTEGRITY', b.decision.reason_codes)

    def test_decision_cannot_omit_required_gates(self):
        b = run()
        d = b.decision.to_dict()
        d['applied_rule_ids'] = ['PLAN_PENDING']
        d['rule_checks'] = [c for c in d['rule_checks'] if c['rule_id'] == 'PLAN_PENDING']
        with self.assertRaises(ValidationError):
            DecisionResult.from_dict(d)

    def test_large_integer_money_comparison_is_exact(self):
        p, cfg = plan(), config()
        amount = '1' + '0' * 4400
        p = replace(p, payload={**p.payload, 'budget_minor_units': amount})
        cfg = replace(cfg, budgets=(replace(cfg.budgets[0], limit_minor_units=amount),),
                      authority=replace(cfg.authority, auto_limit_minor_units=amount))
        self.assertEqual(run(p=p, cfg=cfg).decision.outcome, 'AUTO_APPROVED')

    def test_retry_metadata_does_not_change_semantic_decision_identity(self):
        first = run()
        retry = run(ctx=context(decided_at='2026-09-20T01:00:00Z', idempotency_key='retry-key'))
        self.assertEqual(first.decision.decision_id, retry.decision.decision_id)
        self.assertEqual(first.decision.outcome, retry.decision.outcome)
        self.assertEqual(first.decision.rule_checks, retry.decision.rule_checks)

    def test_policy_cannot_remove_mandatory_submission_fields(self):
        with self.assertRaises(ValidationError):
            replace(config().policy, mandatory_fields=('currency',))

    def test_fresh_evaluation_attempt_keeps_rule_decision_but_has_own_trace(self):
        first = run()
        e = evaluation()
        e.update(evaluation_id='synthetic-eval-2', run_id='synthetic-run-2', latency_ms=50,
                 created_at='2026-09-20T01:00:00Z', started_at='2026-09-20T01:00:00Z',
                 completed_at='2026-09-20T01:00:00Z')
        retry = run(e, ctx=context(evaluation_id='synthetic-eval-2', run_id='synthetic-run-2',
                                  decided_at='2026-09-20T01:00:00Z'))
        self.assertEqual(first.decision.outcome, retry.decision.outcome)
        self.assertEqual(first.decision.rule_checks, retry.decision.rule_checks)
        self.assertEqual(retry.decision.evaluation_id, 'synthetic-eval-2')
        self.assertNotEqual(first.decision.decision_id, retry.decision.decision_id)

    def test_final_audit_cannot_assert_an_impossible_state(self):
        b = run()
        for field, state in (('new_state', None), ('previous_state', None),
                             ('new_state', {'plan_status': 'PENDING_APPROVAL',
                                            'processing_stage': 'AI_AUTO_APPROVED',
                                            'approval_round_status': 'ACTIVE'})):
            data = b.audit.to_dict()
            data[field] = state
            with self.subTest(field=field, state=state), self.assertRaises(ValidationError):
                AuditEvent.from_dict(data)
