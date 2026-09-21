from src.frontend.service import FrontendService, audit_rows, validate_plan_form


def valid_payload():
    return {"title": "Campaign", "maker_id": "maker", "checker_id": "checker",
            "department": "marketing", "objective": "Reach users", "summary": "Summary",
            "start_date": "2026-10-01", "end_date": "2026-10-31",
            "budget_minor_units": "100", "currency": "VND"}


def test_form_validation_requires_fields_and_attachment():
    result = validate_plan_form({}, 0)
    assert not result["valid"]
    assert "title" in result["errors"]
    assert "attachments" in result["errors"]


def test_form_accepts_new_input_without_case_id_logic():
    assert validate_plan_form(valid_payload(), 1) == {"valid": True, "errors": {}}


def test_result_view_supports_auto_and_human_review():
    service = object.__new__(FrontendService)
    auto = service.result_view({"decision": {"outcome": "AUTO_APPROVED", "reason": "All gates passed", "rule_checks": []},
                                "evaluation": {"plan_id": "p", "plan_version": 1, "approval_round": 1,
                                               "provider": "MOCK_VLM", "evidence": [], "media_confidence": .9,
                                               "feasibility_confidence": .9, "completed_at": "2026-01-01T00:00:00Z"}, "questions": []})
    review = service.result_view({"decision": {"outcome": "HUMAN_REVIEW_REQUIRED", "escalation_category": "FACT_UNCERTAIN", "reason": "Review"},
                                  "evaluation": {"evidence": []}, "questions": [{"question": "Can a Checker resolve this?"}]})
    assert auto["outcome"] == "AUTO_APPROVED"
    assert review["escalation_questions"] == ["Can a Checker resolve this?"]


def test_audit_rows_map_required_columns():
    rows = audit_rows({"audit": [{"body": {"action": "PLAN_SUBMITTED", "actor_id": "maker", "timestamp": "t",
                                             "entity_id": "p", "reason": "submitted", "correlation_id": "c",
                                             "previous_state": {}, "new_state": {"plan_status": "PENDING_APPROVAL"}}}]})
    assert rows[0]["action"] == "PLAN_SUBMITTED"
    assert rows[0]["resulting_state"] == "PENDING_APPROVAL"
