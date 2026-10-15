from dataclasses import replace
import pytest

from fixtures import NOW, config, evaluation, plan, recommend_review
from src.backend.domain.models import DecisionResult
from src.backend.domain.policy import (
    AutoRejectPolicy, AutoRejectRule, auto_reject_configuration_hash,
)
from src.backend.rules.decision import DecisionContext, decide
from src.shared.validation import ValidationError, canonical_hash


def _fixture_policy(*, enabled=True, scope_departments=("synthetic-marketing",), rules=None):
    rules = rules or (AutoRejectRule(
        rule_id="SYNTHETIC-FORBIDDEN-LITERAL",
        evidence_kind="OCR_TEXT",
        forbidden_literals=("DEMO-CONTENT-V2",),
        evidence_confidence_threshold=0.85,
        media_confidence_threshold=0.85,
        feasibility_confidence_threshold=0.80,
        reason_code="SYNTHETIC_FORBIDDEN_LITERAL",
        exceptions=(),
    ),)
    return AutoRejectPolicy.synthetic_fixture(
        configuration_id="VERIFY-AUTO-REJECT",
        revision=1,
        enabled=enabled,
        scope_departments=scope_departments,
        scope_channels=("social",),
        rules=rules,
    )


def _evaluate(*, policy=None, raw=None, p=None, cfg=None):
    p = p or plan()
    cfg = replace(cfg or config(), auto_reject_policy=policy)
    raw = raw or evaluation(p)
    ctx = DecisionContext(
        "synthetic-eval", "synthetic-run", "MOCK_VLM", "synthetic-trace",
        "synthetic-intent", NOW, "PENDING_APPROVAL", "ACTIVE", 0, p.input_hash,
        ((p.attachments[0].attachment_id, p.attachments[0].content_hash),),
        ("synthetic-checker",), False,
        ("synthetic-checker", "synthetic-policy-owner", "synthetic-budget-authority"),
    )
    return decide(p, cfg, raw, ctx)


def _ocr_evidence(p, text="DEMO-CONTENT-V2"):
    attachment = p.attachments[0]
    return [{
        # Keep the existing criterion reference valid while changing the
        # attachment observation from a generic visual result to OCR text.
        "evidence_id": "ev-image",
        "source_type": "ATTACHMENT",
        "source_ref": attachment.attachment_id,
        "observation": text,
        "content_hash": attachment.content_hash,
        "evidence_kind": "OCR_TEXT",
        "confidence": 0.95,
    }]


def test_only_approved_scoped_rule_with_hash_bound_ocr_can_auto_reject():
    p = plan()
    raw = evaluation(p)
    raw["evidence"] = _ocr_evidence(p)

    bundle = _evaluate(policy=_fixture_policy(), raw=raw, p=p)
    decision = bundle.decision

    assert bundle.evaluation.status == "SUCCEEDED"
    assert bundle.evaluation.evidence[0].evidence_id == "ev-image"
    assert decision.outcome == "AUTO_REJECTED"
    assert decision.auto_reject_rule_id == "SYNTHETIC-FORBIDDEN-LITERAL"
    assert decision.reason_code == "SYNTHETIC_FORBIDDEN_LITERAL"
    assert decision.escalation_ids == ()

    for field, value in (
        ("auto_reject_rule_id", "A-DIFFERENT-RULE"),
        ("reason_code", "A_DIFFERENT_REASON"),
    ):
        tampered = decision.to_dict()
        tampered[field] = value
        with pytest.raises(ValidationError, match="matched rule check with evidence"):
            DecisionResult.from_dict(tampered)

    tampered_trace = decision.to_dict()
    matched_check = next(
        check for check in tampered_trace["rule_checks"]
        if check["rule_id"] == "AUTO_REJECT_MATCH"
    )
    matched_check["observed_value"]["literal_matched"] = False
    with pytest.raises(ValidationError, match="matched rule check with evidence"):
        DecisionResult.from_dict(tampered_trace)


def test_confidence_floor_is_inclusive_at_each_approved_threshold():
    p = plan()
    raw = evaluation(p)
    raw["media_confidence"] = 0.85
    raw["feasibility_confidence"] = 0.80
    raw["evidence"] = _ocr_evidence(p)
    raw["evidence"][0]["confidence"] = 0.85

    decision = _evaluate(policy=_fixture_policy(), raw=raw, p=p).decision

    assert decision.outcome == "AUTO_REJECTED"


def test_budget_mandate_and_plan_cap_boundaries_still_override_fixture_reject():
    p = plan()
    base = config()
    cfg = replace(
        base,
        budgets=(replace(base.budgets[0], limit_minor_units="10000000"),),
        authority=replace(base.authority, auto_limit_minor_units="5000000"),
    )

    def decide_at(amount):
        current = replace(p, payload={**p.payload, "budget_minor_units": amount})
        raw = evaluation(current)
        raw["evidence"] = _ocr_evidence(current)
        return _evaluate(policy=_fixture_policy(), raw=raw, p=current, cfg=cfg).decision

    assert decide_at("5000000").outcome == "AUTO_REJECTED"
    assert decide_at("5000001").outcome == "HUMAN_REVIEW_REQUIRED"
    assert decide_at("10000000").outcome == "HUMAN_REVIEW_REQUIRED"
    assert decide_at("10000001").outcome == "HUMAN_REVIEW_REQUIRED"


def test_production_auto_reject_cannot_be_enabled_without_implemented_signoff_registry():
    rule = _fixture_policy().rules[0]
    unsigned = AutoRejectPolicy(
        "PRODUCTION-AUTO-REJECT", "PRODUCTION-1", 1, False, ("Marketing",), ("social",),
        (rule,), None, None, None, None, "PRODUCTION",
    )
    from src.backend.domain.policy import auto_reject_configuration_value
    signed_value = auto_reject_configuration_value(unsigned, enabled=True)
    with pytest.raises(ValidationError, match="disabled in production"):
        AutoRejectPolicy(
            "PRODUCTION-AUTO-REJECT", "PRODUCTION-1", 1, True, ("Marketing",), ("social",),
            (rule,), canonical_hash(signed_value), "SYNTHETIC_FIXTURE", "VERIFY_FIXTURE",
            "2026-10-15T00:00:00Z", "PRODUCTION",
        )


def test_fixture_policy_hash_binds_its_exact_revision():
    first = _fixture_policy()
    second = AutoRejectPolicy.synthetic_fixture(
        configuration_id=first.configuration_id,
        revision=2,
        enabled=True,
        scope_departments=first.scope_departments,
        scope_channels=first.scope_channels,
        rules=first.rules,
    )

    assert auto_reject_configuration_hash(first) != auto_reject_configuration_hash(second)


def test_match_does_not_reject_when_policy_is_disabled_or_scope_does_not_match():
    p = plan()
    raw = evaluation(p)
    raw["evidence"] = _ocr_evidence(p)

    disabled = _evaluate(policy=_fixture_policy(enabled=False), raw=raw, p=p).decision
    wrong_scope = _evaluate(
        policy=_fixture_policy(scope_departments=("Marketing",)), raw=raw, p=p,
    ).decision

    assert disabled.outcome == "AUTO_APPROVED"
    assert wrong_scope.outcome == "AUTO_APPROVED"
    assert disabled.auto_reject_rule_id is None
    assert wrong_scope.auto_reject_rule_id is None


def test_low_confidence_missing_conflicting_or_unbound_evidence_never_auto_rejects():
    p = plan()
    raw = evaluation(p)
    raw["evidence"] = _ocr_evidence(p, "DEMO-CONTENT-V3")
    raw["media_confidence"] = 0.84
    raw = recommend_review(raw)
    low_confidence = _evaluate(policy=_fixture_policy(), raw=raw, p=p).decision

    raw = evaluation(p)
    raw["evidence"] = []
    raw = recommend_review(raw)
    missing = _evaluate(policy=_fixture_policy(), raw=raw, p=p).decision

    raw = evaluation(p)
    raw["evidence"] = _ocr_evidence(p)
    raw["evidence_conflicts"] = [{
        "conflict_id": "conflict-1", "description": "Conflicting synthetic evidence.",
        "evidence_refs": ["ev-ocr"],
    }]
    raw = recommend_review(raw)
    conflicting = _evaluate(policy=_fixture_policy(), raw=raw, p=p).decision

    raw = evaluation(p)
    raw["evidence"] = _ocr_evidence(p)
    raw["evidence"][0]["content_hash"] = "b" * 64
    unbound = _evaluate(policy=_fixture_policy(), raw=raw, p=p).decision

    for decision in (low_confidence, missing, conflicting, unbound):
        assert decision.outcome != "AUTO_REJECTED"
        assert decision.auto_reject_rule_id is None


def test_literal_near_miss_warning_and_provider_failure_do_not_auto_reject():
    p = plan()
    raw = evaluation(p)
    raw["evidence"] = _ocr_evidence(p, "DEMO-CONTENT-V3")
    near_miss = _evaluate(policy=_fixture_policy(), raw=raw, p=p).decision

    raw = evaluation(p)
    raw["evidence"] = _ocr_evidence(p, "DEMO-CONTENT-V3")
    raw["media_findings"] = [{
        "finding_id": "warning-1", "severity": "WARNING",
        "description": "Synthetic warning only.", "rule_id": "WARNING-ONLY",
        "evidence_refs": [raw["evidence"][0]["evidence_id"]],
    }]
    warning_bundle = _evaluate(policy=_fixture_policy(), raw=raw, p=p)
    warning = warning_bundle.decision

    raw = evaluation(p)
    raw.update(
        status="TIMED_OUT", media_result=None, media_confidence=None,
        feasibility_score=None, feasibility_confidence=None, proposed_action=None,
        escalation_category="FACT_UNCERTAIN",
        agent_errors=[{"component": "visual_extraction", "code": "PROVIDER_TIMEOUT", "message": "Synthetic timeout."}],
        evidence=_ocr_evidence(p),
    )
    timeout = _evaluate(policy=_fixture_policy(), raw=raw, p=p).decision

    assert near_miss.outcome == "AUTO_APPROVED"
    assert warning_bundle.evaluation.status == "SUCCEEDED"
    assert warning.outcome == "AUTO_APPROVED"  # a WARNING alone is not a rejection rule
    assert timeout.outcome == "HUMAN_REVIEW_REQUIRED"
    assert timeout.auto_reject_rule_id is None


def test_strategy_score_seventy_and_budget_routes_are_not_auto_reject_triggers():
    p = plan()
    raw = evaluation(p)
    raw["feasibility_score"] = 70
    raw["criterion_scores"] = [
        {**item, "score": 70} for item in raw["criterion_scores"]
    ]
    raw["evidence"] = _ocr_evidence(p)
    score_70 = _evaluate(policy=_fixture_policy(), raw=recommend_review(raw), p=p).decision

    p_over_budget = plan()
    p_over_budget = replace(p_over_budget, payload={**p_over_budget.payload, "budget_minor_units": "10001"})
    raw = evaluation(p_over_budget)
    raw["evidence"] = _ocr_evidence(p_over_budget)
    over_budget = _evaluate(policy=_fixture_policy(), raw=raw, p=p_over_budget).decision

    assert score_70.outcome == "HUMAN_REVIEW_REQUIRED"
    assert score_70.auto_reject_rule_id is None
    assert over_budget.outcome == "HUMAN_REVIEW_REQUIRED"
    assert over_budget.auto_reject_rule_id is None
