import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.backend.api.public_judge import router


def _client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _input(**overrides):
    value = {
        "title": "Synthetic campaign",
        "department": "DEMO-DEPT-01",
        "objective": "Reach a defined demo audience",
        "summary": "A short synthetic plan for checking the Judge input path.",
        "target_audience": "Synthetic audience",
        "channel": "DEMO_SOCIAL",
        "currency": "VND",
        "budget_vnd": 50_000_000,
        "source_budget_vnd": 50_000_000,
    }
    value.update(overrides)
    return value


def test_server_ground_truth_catalog_has_at_least_fifteen_cases():
    fixture = Path(__file__).resolve().parents[2] / "fixtures" / "ba" / "v2.1" / "ground-truth-cases.json"
    cases = json.loads(fixture.read_text(encoding="utf-8"))

    assert len(cases) >= 15
    assert len({case["id"] for case in cases}) == len(cases)


def test_custom_input_varies_by_facts_scope_and_authority_without_claiming_quality():
    client = _client()

    matched = client.post("/api/public/judge/input-runs", json=_input())
    conflict = client.post("/api/public/judge/input-runs", json=_input(source_budget_vnd=42_000_000))
    out_of_scope = client.post("/api/public/judge/input-runs", json=_input(channel="UNLISTED_CHANNEL"))
    over_limit = client.post("/api/public/judge/input-runs", json=_input(budget_vnd=100_000_001, source_budget_vnd=100_000_001))

    assert [response.status_code for response in (matched, conflict, out_of_scope, over_limit)] == [200] * 4
    results = [response.json() for response in (matched, conflict, out_of_scope, over_limit)]
    assert [result["outcome"] for result in results] == [
        "SIMULATED_AUTO_APPROVE", "HUMAN_REVIEW_REQUIRED", "HUMAN_REVIEW_REQUIRED", "HUMAN_REVIEW_REQUIRED"
    ]
    assert [result["category"] for result in results] == [
        None, "FACT_UNCERTAIN", "POLICY_OUT_OF_SCOPE", "AUTHORITY_EXCEEDED"
    ]
    assert all(result["data_classification"] == "USER_SUPPLIED_UNVERIFIED" for result in results)
    assert all(result["quality_status"] == "NOT_MEASURED" for result in results)
    assert all(result["mode"] == "MOCK" for result in results)
    assert all(result["audit"]["action"] == "INPUT_EVALUATED" for result in results)
    assert all(result["audit"]["input_sha256"] for result in results)
    assert all(result["audit"]["timestamp"] and result["audit"]["reason"] for result in results)
    assert "Synthetic campaign" not in json.dumps(results)
    assert "không xác nhận" in results[1]["reason"].lower()
    assert "nguồn có thẩm quyền" in results[1]["handoff_question"].lower()
    assert "UNLISTED_CHANNEL" in results[2]["handoff_question"]
    assert "100,000,000 VND" in results[3]["handoff_question"]


def test_input_rejects_unknown_fields_and_enforces_small_body_limit():
    client = _client()

    unknown = client.post("/api/public/judge/input-runs", json=_input(expected_action="AUTO_APPROVED"))
    large = client.post("/api/public/judge/input-runs", content=b" " * (16 * 1024 + 1),
                        headers={"Content-Type": "application/json"})

    assert unknown.status_code == 422
    assert unknown.json()["code"] == "VALIDATION_ERROR"
    assert "expected_action" not in unknown.text
    assert large.status_code == 413
    assert large.json()["code"] == "INPUT_TOO_LARGE"


def test_fixed_suite_uses_server_oracle_and_needs_no_actor_or_cookie(monkeypatch):
    from src.verify import runner

    monkeypatch.setattr(runner, "run_suite", lambda suite: [
        {
            "case_id": "FIXTURE-ONLY-CASE",
            "case_name": "Synthetic fixture",
            "started_at": "2026-10-14T00:00:00.000Z",
            "completed_at": "2026-10-14T00:00:00.010Z",
            "duration_ms": 10,
            "expected": {"route": "AUTO_APPROVED", "primary_category": None},
            "actual": {
                "decision": {"outcome": "AUTO_APPROVED", "reason": "Fixture workflow result.", "applied_rule_ids": ["BUDGET_LIMIT"]},
                "evaluation": {"model_version": "mock-fixture-v1", "evidence": []},
                "plan": {"payload": {"title": "Synthetic fixture"}},
                "audit": [{"action": "AUTO_APPROVED", "input_hash": "sha256-demo", "timestamp": "2026-10-14T00:00:00.010Z", "reason": "Fixture workflow result."}],
                "questions": [],
            },
            "differences": [],
            "error": None,
        }
    ])

    response = _client().post("/api/public/judge/runs", json={"suite": "general"})

    assert response.status_code == 200
    result = response.json()
    assert result["suite"] == "general"
    assert result["mode"] == "MOCK"
    assert result["data_classification"] == "SYNTHETIC"
    assert result["rows"][0]["status"] == "PASS"
    assert result["rows"][0]["expected_action"] == "AUTO_APPROVED"
    assert result["rows"][0]["actual_action"] == "AUTO_APPROVED"
    assert result["rows"][0]["audit"][0]["action"] == "AUTO_APPROVED"


def test_public_mock_suites_execute_the_required_case_counts_and_routes():
    client = _client()
    general = client.post("/api/public/judge/runs", json={"suite": "general"}).json()
    escalation = client.post("/api/public/judge/runs", json={"suite": "escalation"}).json()

    assert len(general["rows"]) == 4
    assert sum(row["actual_action"] == "AUTO_APPROVED" for row in general["rows"]) == 3
    assert sum(row["actual_action"] == "HUMAN_REVIEW_REQUIRED" for row in general["rows"]) == 1
    assert len(escalation["rows"]) == 5
    assert sum(row["actual_action"] == "AUTO_APPROVED" for row in escalation["rows"]) == 3
    assert sum(row["actual_action"] == "HUMAN_REVIEW_REQUIRED" for row in escalation["rows"]) == 2
    assert {row["actual_category"] for row in escalation["rows"] if row["actual_category"]} == {
        "FACT_UNCERTAIN", "AUTHORITY_EXCEEDED"
    }
    assert all(row["status"] == "PASS" for row in [*general["rows"], *escalation["rows"]])
    assert all(row["started_at"] and row["completed_at"] and row["duration_ms"] >= 0
               for row in [*general["rows"], *escalation["rows"]])
    assert all(any(event["action"] and event["timestamp"] and event["input_sha256"] and event["reason"]
                   for event in row["audit"])
               for row in [*general["rows"], *escalation["rows"]])


def test_errors_follow_the_public_envelope_and_never_echo_arbitrary_body():
    client = _client()
    response = client.post("/api/public/judge/runs", json={"suite": "secret-suite", "provider": "local-vlm"})

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert response.json()["http_status"] == 422
    assert response.json()["correlation_id"]
    assert "secret-suite" not in response.text


def test_public_router_has_only_the_two_post_run_routes():
    routes = {(route.path, tuple(sorted(route.methods))) for route in router.routes}

    assert routes == {
        ("/api/public/judge/runs", ("POST",)),
        ("/api/public/judge/input-runs", ("POST",)),
    }
