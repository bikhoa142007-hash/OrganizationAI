from src.verify.competition import CASE_IDS, run_competition_suite


def test_competition_suite_executes_four_required_cases_through_workflow():
    run = run_competition_suite()

    assert [row["case_id"] for row in run["rows"]] == list(CASE_IDS)
    assert len(run["rows"]) == 4
    assert all(row["status"] == "PASS" for row in run["rows"])
    assert run["environment"] == "SYNTHETIC_TEST"
    assert run["provider_mode"] == "MOCK_VLM (external calls disabled)"
    assert [row["actual"]["decision"]["outcome"] for row in run["rows"]] == [
        "AUTO_APPROVED",
        "HUMAN_REVIEW_REQUIRED",
        "HUMAN_REVIEW_REQUIRED",
        "HUMAN_REVIEW_REQUIRED",
    ]


def test_budget_case_keeps_plan_within_maximum_but_routes_over_auto_limit():
    run = run_competition_suite()
    row = next(item for item in run["rows"] if item["case_id"] == "TC02")

    assert row["input"]["plan"]["budget_minor_units"] == "6000000"
    assert run["configuration"]["auto_approval_limit_minor_units"] == "5000000"
    assert run["configuration"]["budget_limit_minor_units"] == "10000000"
    assert row["actual"]["plan"]["state"]["plan_status"] == "PENDING_APPROVAL"
    decision = row["actual"]["decision"]
    assert decision["escalation_category"] == "AUTHORITY_EXCEEDED"
    assert any(
        check["rule_id"] == "AUTHORITY_LIMIT" and check["result"] != "PASS"
        for check in decision["rule_checks"]
    )


def test_missing_media_evidence_is_not_inferred_as_pass():
    run = run_competition_suite()
    row = next(item for item in run["rows"] if item["case_id"] == "TC03")

    assert row["input"]["plan"]["attachments"]
    assert row["actual"]["evaluation"]["status"] == "FAILED"
    assert row["actual"]["evaluation"]["media_result"] is None
    assert row["actual"]["evaluation"]["evidence"] == []
    assert "INVALID_SCHEMA" in {
        item["code"] for item in row["actual"]["evaluation"]["agent_errors"]
    }
    assert row["actual"]["decision"]["outcome"] == "HUMAN_REVIEW_REQUIRED"


def test_controlled_provider_timeout_preserves_submission_and_audit():
    run = run_competition_suite()
    row = next(item for item in run["rows"] if item["case_id"] == "TC04")
    audit_actions = {event["action"] for event in row["actual"]["audit"]}

    assert row["actual"]["plan"]["state"]["plan_status"] == "PENDING_APPROVAL"
    assert row["actual"]["evaluation"]["status"] == "TIMED_OUT"
    assert row["actual"]["decision"]["outcome"] == "HUMAN_REVIEW_REQUIRED"
    assert {"PLAN_SUBMITTED", "ENGINE_ROUTED"} <= audit_actions
    assert row["status"] == "PASS"
