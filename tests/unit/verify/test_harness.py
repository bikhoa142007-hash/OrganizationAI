from src.verify.harness import VerifyHarness, default_verify_cases, VerifyCase


def test_verify_runs_five_cases_from_actual_workflow():
    rows = VerifyHarness().run_all()
    assert len(rows) == 5
    assert sum(row["actual_outcome"] == "AUTO_APPROVED" for row in rows) == 3
    assert sum(row["actual_outcome"] == "HUMAN_REVIEW_REQUIRED" for row in rows) == 2
    assert all(row["passed"] for row in rows)
    assert all(row["duration_ms"] >= 0 and row["timestamp"] for row in rows)


def test_verify_mismatch_is_fail_with_reason():
    case = default_verify_cases()[0]
    mismatch = VerifyCase(case.case_id, case.description, case.scenario, "HUMAN_REVIEW_REQUIRED", "FACT_UNCERTAIN")
    row = VerifyHarness(case_loader=lambda: (mismatch,)).run_all()[0]
    assert row["passed"] is False
    assert row["error"]
