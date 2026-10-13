from types import SimpleNamespace
from decimal import Decimal

import pytest

from src.ai_pipeline.task_evaluation import (
    PolicyOutputConflictError,
    EvaluatorRubricUnsupportedError,
    STRATEGY_CRITERIA,
    strategy_rubric_weights,
    validate_media_output,
    validate_strategy_output,
)
from src.backend.domain.policy import (
    MediaCompliancePolicy,
    MediaPolicyRule,
    StrategyCriterion,
    StrategyRubric,
)


POLICY = MediaCompliancePolicy(
    policy_id="SYNTH-POLICY", policy_version="1", status="ACTIVE",
    scope_departments=("Synthetic Lab",), scope_channels=("social",),
    rules=(MediaPolicyRule(
        rule_id="NO-GUARANTEED-RESULT", severity="HARD_VIOLATION",
        description="Do not make a guaranteed result claim.",
        required_evidence_kinds=("OCR_TEXT",),
        forbidden_literals=("GUARANTEED RESULT",),
    ),),
)
RUBRIC = StrategyRubric(
    rubric_id="SYNTH-RUBRIC", rubric_version="1", status="ACTIVE",
    criteria=tuple(StrategyCriterion(
        criterion_id=criterion_id, label=label, weight=weight,
    ) for criterion_id, label, weight in STRATEGY_CRITERIA),
)


def valid_media_output():
    return {
        "policy_id": "SYNTH-POLICY", "policy_version": "1",
        "outcome": "PASS", "confidence": 0.9, "reason": "Rule checked.",
        "rule_results": [{
            "rule_id": "NO-GUARANTEED-RESULT", "result": "PASS",
            "rationale": "The exact literal is absent.", "evidence_refs": ["ev-ocr"],
        }],
        "findings": [], "evidence_conflicts": [],
    }


def test_policy_output_conflict_is_distinct_from_schema_error():
    conflict = valid_media_output()
    evidence = {"ev-ocr": {
        "kind": "OCR_TEXT", "observation": "GUARANTEED RESULT from this fictional product",
    }}

    with pytest.raises(PolicyOutputConflictError) as error:
        validate_media_output(conflict, POLICY, evidence)
    assert error.value.code == "POLICY_OUTPUT_CONFLICT"

    malformed = valid_media_output()
    del malformed["reason"]
    with pytest.raises(ValueError) as schema_error:
        validate_media_output(malformed, POLICY, evidence)
    assert not isinstance(schema_error.value, PolicyOutputConflictError)


def test_strategy_weighted_total_conflict_is_not_relabelled_as_schema_error():
    output = {
        "rubric_id": "SYNTH-RUBRIC", "rubric_version": "1",
        "total_score": 71, "confidence": 0.82,
        "criterion_scores": [{
            "criterion_id": criterion_id, "score": 70,
            "rationale": "Supported by synthetic evidence.", "evidence_refs": ["ev-plan"],
        } for criterion_id, _label, _weight in STRATEGY_CRITERIA],
        "assumptions": [], "missing_facts": [], "critical_gaps": [],
        "evidence_conflicts": [], "reason": "The weighted score is advisory.",
    }

    with pytest.raises(PolicyOutputConflictError) as error:
        validate_strategy_output(output, RUBRIC, ["ev-plan"])

    assert error.value.code == "POLICY_OUTPUT_CONFLICT"
    assert str(error.value.reported_total) == "71"
    assert error.value.computed_total == Decimal("70")


def test_custom_strategy_weights_fail_closed_as_unsupported_rubric():
    custom_weights = [20, 10, 15, 15, 15, 15, 10]
    rubric = SimpleNamespace(
        rubric_id="CUSTOM-RUBRIC",
        rubric_version="1",
        criteria=tuple(
            SimpleNamespace(criterion_id=criterion_id, weight=weight)
            for (criterion_id, _label, _baseline_weight), weight
            in zip(STRATEGY_CRITERIA, custom_weights, strict=True)
        ),
    )

    with pytest.raises(EvaluatorRubricUnsupportedError) as error:
        strategy_rubric_weights(rubric)

    assert error.value.code == "EVALUATOR_RUBRIC_UNSUPPORTED"
