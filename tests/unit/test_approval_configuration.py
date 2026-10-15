from __future__ import annotations

from uuid import uuid4
import pytest

from src.backend.application.approval_configuration import (
    ConfigurationValidationError,
    budget_decision,
    canonical_configuration_hash,
    feasibility_score_passes,
    validate_configuration_value,
)


def test_budget_equal_to_limit_passes_and_over_limit_requires_review():
    config = validate_configuration_value("budget", {
        "currency": "VND",
        "limits": [{"department": "Marketing", "limit_minor_units": "1000000", "active": True}],
    })

    assert budget_decision(config, "Marketing", "1000000").result == "PASS"
    assert budget_decision(config, "Marketing", "1000001").result == "HUMAN_REVIEW_REQUIRED"


def test_missing_or_ambiguous_budget_is_unknown():
    empty = validate_configuration_value("budget", {"currency": "VND", "limits": []})
    missing = budget_decision(empty, "Marketing", "1")
    assert missing.result == "HUMAN_REVIEW_REQUIRED"
    assert missing.status == "UNCONFIGURED"

    with pytest.raises(ConfigurationValidationError):
        validate_configuration_value("budget", {
            "currency": "VND",
            "limits": [
                {"department": "Marketing", "limit_minor_units": "10", "active": True},
                {"department": "Marketing", "limit_minor_units": "20", "active": True},
            ],
        })


def test_checker_assignment_requires_boolean_toggle_and_unique_department_defaults():
    with pytest.raises(ConfigurationValidationError, match="must be a boolean"):
        validate_configuration_value("checker_assignment", {
            "maker_may_select_other": 1,
            "defaults": [],
        })

    with pytest.raises(ConfigurationValidationError, match="more than one default Checker"):
        validate_configuration_value("checker_assignment", {
            "maker_may_select_other": False,
            "defaults": [
                {"department": "Marketing", "checker_id": str(uuid4())},
                {"department": "Marketing", "checker_id": str(uuid4())},
            ],
        })


def test_malformed_budget_snapshot_fails_closed():
    decision = budget_decision({"currency": "VND", "limits": [None]}, "Marketing", "1")
    assert decision.result == "HUMAN_REVIEW_REQUIRED"
    assert decision.status == "INVALID_INPUT"


def test_strategy_rubric_requires_known_criteria_and_total_weight_100():
    valid = {
        "rubric_id": "SYNTHETIC-RUBRIC",
        "rubric_version": "SYNTHETIC-1",
        "status": "ACTIVE",
        "criteria": [
            {"criterion_id": "objective", "label": "Mục tiêu", "weight": 15},
            {"criterion_id": "audience", "label": "Đối tượng", "weight": 15},
            {"criterion_id": "channel", "label": "Kênh", "weight": 15},
            {"criterion_id": "timeline", "label": "Thời gian", "weight": 15},
            {"criterion_id": "kpi", "label": "KPI", "weight": 15},
            {"criterion_id": "budget_efficiency", "label": "Hiệu quả ngân sách", "weight": 15},
            {"criterion_id": "risk_control", "label": "Kiểm soát rủi ro", "weight": 10},
        ],
    }
    assert validate_configuration_value("strategy_rubric", valid)["status"] == "ACTIVE"

    valid["criteria"][0]["weight"] = 14
    with pytest.raises(ConfigurationValidationError):
        validate_configuration_value("strategy_rubric", valid)


def test_strategy_rubric_normalizes_criterion_order_before_hashing():
    criteria = [
        {"criterion_id": "risk_control", "label": "Rủi ro", "weight": 10},
        {"criterion_id": "budget_efficiency", "label": "Ngân sách", "weight": 25},
        {"criterion_id": "kpi", "label": "KPI", "weight": 15},
        {"criterion_id": "timeline", "label": "Thời gian", "weight": 10},
        {"criterion_id": "channel", "label": "Kênh", "weight": 10},
        {"criterion_id": "audience", "label": "Đối tượng", "weight": 10},
        {"criterion_id": "objective", "label": "Mục tiêu", "weight": 20},
    ]
    first = validate_configuration_value("strategy_rubric", {
        "rubric_id": "SYNTHETIC-RUBRIC",
        "rubric_version": "SYNTHETIC-2",
        "status": "DISABLED",
        "criteria": criteria,
    })
    second = validate_configuration_value("strategy_rubric", {
        "rubric_id": "SYNTHETIC-RUBRIC",
        "rubric_version": "SYNTHETIC-2",
        "status": "DISABLED",
        "criteria": list(reversed(criteria)),
    })

    expected_order = ["objective", "audience", "channel", "timeline", "kpi", "budget_efficiency", "risk_control"]
    assert [item["criterion_id"] for item in first["criteria"]] == expected_order
    assert first == second
    assert canonical_configuration_hash(first) == canonical_configuration_hash(second)


def test_threshold_number_overflow_is_a_validation_error():
    value = {
        "enabled": False,
        "media_confidence_threshold": 10**10000,
        "feasibility_score_threshold_exclusive": 70,
        "feasibility_confidence_threshold": 0.80,
    }
    with pytest.raises(ConfigurationValidationError):
        validate_configuration_value("approval_policy", value)


def test_auto_approval_configuration_cannot_be_enabled_by_admin_revision():
    value = {
        "enabled": True,
        "media_confidence_threshold": 0.85,
        "feasibility_score_threshold_exclusive": 70,
        "feasibility_confidence_threshold": 0.80,
    }
    with pytest.raises(ConfigurationValidationError, match="PO sign-off"):
        validate_configuration_value("approval_policy", value)


def test_feasibility_threshold_is_strictly_greater_than_configured_score():
    assert feasibility_score_passes(70, 70) is False
    assert feasibility_score_passes(71, 70) is True


def test_canonical_configuration_hash_uses_canonical_json():
    first = canonical_configuration_hash({"a": 1, "b": {"x": True}})
    second = canonical_configuration_hash({"b": {"x": True}, "a": 1})
    assert first == second
