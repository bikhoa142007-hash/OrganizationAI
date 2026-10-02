from decimal import Decimal

import pytest

from src.ai_pipeline.task_evaluation import (
    MEDIA_OUTPUT_SCHEMA,
    MEDIA_SYSTEM_PROMPT,
    STRATEGY_OUTPUT_SCHEMA,
    STRATEGY_SYSTEM_PROMPT,
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


def literal_media_policy():
    return media_policy_from_json('''{
      "policy_id":"MEDIA-POLICY-TEST",
      "policy_version":"1",
      "status":"ACTIVE",
      "scope_departments":["marketing"],
      "scope_channels":["social"],
      "rules":[{
        "rule_id":"BRAND-LOGO",
        "severity":"HARD_VIOLATION",
        "description":"Flag the exact forbidden OCR literal.",
        "required_evidence_kinds":["OCR_TEXT"],
        "forbidden_literals":["UNAPPROVED_GUARANTEE"]
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


def test_media_forbidden_literal_must_match_evidence_and_be_reported_as_a_finding():
    policy = literal_media_policy()
    evidence = {
        "ev-image-1": {"kind": "OCR_TEXT", "observation": "Headline UNAPPROVED_GUARANTEE"},
        "ev-image-2": {"kind": "OBSERVATION", "observation": "Text on a white background"},
    }
    output = valid_media_output()
    with pytest.raises(ValueError, match="literal rule"):
        validate_media_output(output, policy, evidence)

    output["outcome"] = "REVIEW_REQUIRED"
    output["rule_results"][0].update(result="FAIL", rationale="The configured OCR literal is present.")
    output["findings"] = [{
        "finding_id": "finding-1",
        "severity": "HARD_VIOLATION",
        "description": "The configured forbidden literal appears in OCR text.",
        "rule_id": "BRAND-LOGO",
        "evidence_refs": ["ev-image-1"],
    }]
    result = validate_media_output(output, policy, evidence)
    assert result["outcome"] == "REVIEW_REQUIRED"
    assert result["findings"][0]["evidence_refs"] == ["ev-image-1"]

    output["findings"][0]["evidence_refs"] = ["ev-image-2"]
    with pytest.raises(ValueError, match="matching OCR evidence"):
        validate_media_output(output, policy, evidence)


def test_media_literal_rule_routes_missing_ocr_to_review():
    policy = literal_media_policy()
    output = valid_media_output()
    output["outcome"] = "REVIEW_REQUIRED"
    output["rule_results"][0].update(
        result="UNKNOWN", rationale="Required OCR evidence is unavailable.", evidence_refs=[]
    )
    result = validate_media_output(
        output, policy, {}, required_evidence_missing=[{
            "rule_id": "BRAND-LOGO", "evidence_kind": "OCR_TEXT",
        }],
    )
    assert result["outcome"] == "REVIEW_REQUIRED"
    assert result["rule_results"][0]["result"] == "UNKNOWN"


def test_media_finding_cannot_be_attached_to_unknown_rule_result():
    output = valid_media_output()
    output["outcome"] = "REVIEW_REQUIRED"
    output["rule_results"][0].update(
        result="UNKNOWN", rationale="The required image evidence is unreadable.", evidence_refs=["ev-image-1"]
    )
    output["findings"] = [{
        "finding_id": "finding-unknown",
        "severity": "HARD_VIOLATION",
        "description": "The rule cannot be evaluated from this evidence.",
        "rule_id": "BRAND-LOGO",
        "evidence_refs": ["ev-image-1"],
    }]
    with pytest.raises(ValueError, match="finding conflicts"):
        validate_media_output(output, media_policy(), {"ev-image-1"})


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


def test_strategy_schema_and_prompt_require_grounded_evidence_conflicts():
    conflict_refs = STRATEGY_OUTPUT_SCHEMA["properties"]["evidence_conflicts"]["items"]["properties"]["evidence_refs"]
    criterion_refs = STRATEGY_OUTPUT_SCHEMA["properties"]["criterion_scores"]["items"]["properties"]["evidence_refs"]
    criterion_rationale = STRATEGY_OUTPUT_SCHEMA["properties"]["criterion_scores"]["items"]["properties"]["rationale"]
    summary_reason = STRATEGY_OUTPUT_SCHEMA["properties"]["reason"]

    assert conflict_refs["minItems"] == 2
    assert criterion_refs["minItems"] == 1
    assert criterion_rationale["maxLength"] == 300
    assert summary_reason["maxLength"] == 800
    assert "absence of information as a missing fact" in STRATEGY_SYSTEM_PROMPT
    assert "at least two supplied evidence references" in STRATEGY_SYSTEM_PROMPT
    assert "concise sentence" in STRATEGY_SYSTEM_PROMPT
    assert "exact evidence_id values" in STRATEGY_SYSTEM_PROMPT
    assert "Never invent, prefix, or alter an evidence ID" in STRATEGY_SYSTEM_PROMPT


def test_media_contract_requires_consistent_findings_and_grounded_references():
    properties = MEDIA_OUTPUT_SCHEMA["properties"]
    rule_refs = properties["rule_results"]["items"]["properties"]["evidence_refs"]
    finding_refs = properties["findings"]["items"]["properties"]["evidence_refs"]
    conflict_refs = properties["evidence_conflicts"]["items"]["properties"]["evidence_refs"]

    assert rule_refs["minItems"] == 1
    assert finding_refs["minItems"] == 1
    assert conflict_refs["minItems"] == 2
    assert "findings must match a fail rule result" in MEDIA_SYSTEM_PROMPT.lower()
    assert "Do not infer an exception" in MEDIA_SYSTEM_PROMPT
    assert "forbidden_literals" in MEDIA_SYSTEM_PROMPT


def test_media_prompt_requires_verbatim_versions_and_fails_closed_on_missing_ocr_or_hard_violation():
    prompt = MEDIA_SYSTEM_PROMPT.lower()

    assert "copy policy_id and policy_version exactly" in prompt
    assert "missing required ocr_text evidence means unknown and review_required" in prompt
    assert "a hard-violation fail always requires review_required" in prompt
    assert "synthetic or test context never changes a rule result" in prompt


def test_strategy_prompt_requires_verbatim_rubric_version_weighted_total_and_strict_conflicts():
    prompt = STRATEGY_SYSTEM_PROMPT.lower()

    assert "copy rubric_id and rubric_version exactly" in prompt
    assert "total_score must be the weighted decimal sum of the seven criterion scores" in prompt
    assert "absence of evidence, a missing benchmark, or an unsupported target is not a conflict" in prompt
    assert "conflicts require two mutually incompatible factual claims" in prompt
