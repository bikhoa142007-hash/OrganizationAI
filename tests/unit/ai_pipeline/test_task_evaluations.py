from decimal import Decimal

import pytest

from src.ai_pipeline.task_evaluation import (
    STRATEGY_CRITERIA,
    media_policy_from_json,
    strategy_rubric_from_json,
    validate_media_output,
    validate_strategy_output,
)


def media_policy():
    return media_policy_from_json('''{
      "policy_id":"MEDIA-POLICY-TEST",
      "policy_version":"1",
      "status":"ACTIVE",
      "scope_departments":["marketing"],
      "scope_channels":["social"],
      "rules":[{
        "rule_id":"BRAND-LOGO",
        "severity":"HARD_VIOLATION",
        "description":"Check the supplied organization brand mark rule.",
        "required_evidence_kinds":["OBSERVATION"]
      }]
    }''')


def strategy_rubric():
    return strategy_rubric_from_json('''{
      "rubric_id":"BA-STRATEGY-TEST",
      "rubric_version":"1",
      "status":"ACTIVE",
      "criteria":[
        {"criterion_id":"objective","label":"Mục tiêu","weight":15},
        {"criterion_id":"audience","label":"Đối tượng","weight":15},
        {"criterion_id":"channel","label":"Kênh","weight":15},
        {"criterion_id":"timeline","label":"Thời gian","weight":15},
        {"criterion_id":"kpi","label":"KPI","weight":15},
        {"criterion_id":"budget_efficiency","label":"Hiệu quả ngân sách","weight":15},
        {"criterion_id":"risk_control","label":"Kiểm soát rủi ro","weight":10}
      ]
    }''')


def valid_media_output():
    return {
        "policy_id": "MEDIA-POLICY-TEST",
        "policy_version": "1",
        "outcome": "PASS",
        "confidence": 0.91,
        "reason": "The configured rule was checked against the supplied observation.",
        "rule_results": [{
            "rule_id": "BRAND-LOGO",
            "result": "PASS",
            "rationale": "The cited observation supports this check.",
            "evidence_refs": ["ev-image-1"],
        }],
        "findings": [],
        "evidence_conflicts": [],
    }


def valid_strategy_output(score=71):
    return {
        "rubric_id": "BA-STRATEGY-TEST",
        "rubric_version": "1",
        "total_score": score,
        "confidence": 0.82,
        "criterion_scores": [{
            "criterion_id": criterion_id,
            "score": score,
            "rationale": "Grounded in the referenced plan field.",
            "evidence_refs": ["ev-plan-objective"],
        } for criterion_id, _label, _weight in STRATEGY_CRITERIA],
        "assumptions": [],
        "missing_facts": [],
        "critical_gaps": [],
        "evidence_conflicts": [],
        "reason": "Scores are advisory and use only the submitted plan evidence.",
    }


def test_media_result_requires_configured_policy_and_resolvable_evidence():
    policy = media_policy()
    result = validate_media_output(valid_media_output(), policy, {"ev-image-1"})

    assert result["outcome"] == "PASS"
    assert result["findings"] == []

    invalid = valid_media_output()
    invalid["rule_results"][0]["rule_id"] = "MADE-UP-RULE"
    with pytest.raises(ValueError, match="policy"):
        validate_media_output(invalid, policy, {"ev-image-1"})

    invalid = valid_media_output()
    invalid["rule_results"][0]["evidence_refs"] = ["other-plan-evidence"]
    with pytest.raises(ValueError, match="evidence"):
        validate_media_output(invalid, policy, {"ev-image-1"})


def test_media_hard_violation_cannot_be_reported_as_pass():
    policy = media_policy()
    output = valid_media_output()
    output["rule_results"][0].update(result="FAIL", rationale="A configured hard rule failed.")
    output["findings"] = [{
        "finding_id": "finding-1",
        "severity": "HARD_VIOLATION",
        "description": "Evidence conflicts with the configured brand rule.",
        "rule_id": "BRAND-LOGO",
        "evidence_refs": ["ev-image-1"],
    }]

    with pytest.raises(ValueError, match="outcome"):
        validate_media_output(output, policy, {"ev-image-1"})

    output["outcome"] = "REVIEW_REQUIRED"
    assert validate_media_output(output, policy, {"ev-image-1"})["outcome"] == "REVIEW_REQUIRED"


def test_media_policy_must_have_an_explicit_scope_and_version():
    assert media_policy_from_json("") is None
    with pytest.raises(ValueError):
        media_policy_from_json('{"policy_id":"P","policy_version":"1","status":"ACTIVE","scope_departments":[],"scope_channels":["social"],"rules":[]}')


def test_strategy_rubric_has_seven_authoritative_weights_summing_to_100():
    rubric = strategy_rubric()
    assert sum(item.weight for item in rubric.criteria) == 100
    assert strategy_rubric_from_json("") is None

    malformed = valid_strategy_output()
    malformed["criterion_scores"] = malformed["criterion_scores"][:-1]
    with pytest.raises(ValueError, match="criterion"):
        validate_strategy_output(malformed, rubric, {"ev-plan-objective"})


def test_strategy_backend_weighted_total_is_decimal_and_exactly_checked():
    rubric = strategy_rubric()
    result = validate_strategy_output(valid_strategy_output(71), rubric, {"ev-plan-objective"})
    assert Decimal(str(result["feasibility_score"])) == Decimal("71")
    assert [item["weight"] for item in result["criterion_scores"]] == [15, 15, 15, 15, 15, 15, 10]

    exact_threshold = valid_strategy_output(70)
    assert validate_strategy_output(exact_threshold, rubric, {"ev-plan-objective"})["feasibility_score"] == 70

    mismatched_total = valid_strategy_output(71)
    mismatched_total["total_score"] = 71.01
    with pytest.raises(ValueError, match="total"):
        validate_strategy_output(mismatched_total, rubric, {"ev-plan-objective"})

    wrong_evidence = valid_strategy_output()
    wrong_evidence["criterion_scores"][0]["evidence_refs"] = ["foreign-evidence"]
    with pytest.raises(ValueError, match="evidence"):
        validate_strategy_output(wrong_evidence, rubric, {"ev-plan-objective"})
