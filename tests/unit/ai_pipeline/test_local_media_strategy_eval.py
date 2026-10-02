import json
from pathlib import Path

from scripts.evaluate_local_media_strategy import (
    DEFAULT_DATASET,
    build_task_request,
    load_dataset,
)
from src.ai_pipeline.task_evaluation import media_policy_from_json, strategy_rubric_from_json, task_messages


def test_local_eval_dataset_has_bounded_proposed_labels_and_independent_holdout():
    dataset, cases = load_dataset(DEFAULT_DATASET)

    assert len(cases) == 16
    assert dataset["label_status"] == "PROPOSED_NOT_HUMAN_APPROVED"
    assert sum(case["split"] == "tune" for case in cases) == 12
    assert sum(case["split"] == "holdout" for case in cases) == 4
    assert {case["task"] for case in cases} == {"MEDIA_COMPLIANCE", "STRATEGY_EVALUATION"}
    assert all("score" not in case["expected"] for case in cases)
    strategy_cases = [case for case in cases if case["task"] == "STRATEGY_EVALUATION"]
    assert all(len(case["expected"]["criterion_states"]) == 7 for case in strategy_cases)
    assert set(dataset["criterion_state_legend"]) == {
        "PRESENT", "PARTIAL", "MISSING", "UNSUPPORTED_TARGET", "NO_BENCHMARK", "CONFLICT",
    }


def test_expected_labels_and_case_identity_are_not_sent_to_the_model():
    dataset, cases = load_dataset(DEFAULT_DATASET)
    case = next(item for item in cases if item["case_id"] == "MEDIA-004")
    policy = media_policy_from_json(json.dumps(dataset["policy"], ensure_ascii=False))
    rubric = strategy_rubric_from_json(json.dumps(dataset["rubric"], ensure_ascii=False))
    request = build_task_request(case, policy, rubric)
    messages = task_messages(
        request.task, request.plan_payload, request.evidence,
        policy=request.policy, rubric=request.rubric,
    )
    prompt = "\n".join(message["content"] for message in messages)

    assert case["case_id"] not in prompt
    assert case["rationale"] not in prompt
    assert json.dumps(case["expected"], ensure_ascii=False) not in prompt


def test_strategy_request_contains_only_case_input_and_plan_evidence():
    dataset, cases = load_dataset(DEFAULT_DATASET)
    case = next(item for item in cases if item["case_id"] == "STRATEGY-007")
    policy = media_policy_from_json(json.dumps(dataset["policy"], ensure_ascii=False))
    rubric = strategy_rubric_from_json(json.dumps(dataset["rubric"], ensure_ascii=False))
    request = build_task_request(case, policy, rubric)

    assert request.plan_payload["budget_minor_units"] == "250000000"
    assert {item["evidence_id"] for item in request.evidence} >= {
        "plan-field:budget_minor_units", "strategy-007-quote",
    }
    assert not any("expected" in item for item in request.evidence)
