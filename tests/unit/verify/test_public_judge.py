import hashlib
import json
from threading import Barrier, Event, Lock, Thread
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.backend.api.public_judge import PublicJudgeActionStore, PublicJudgeActionError, router


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


def test_new_input_review_can_be_stopped_with_hash_and_reason_audit():
    client = _client()
    run = client.post("/api/public/judge/input-runs", json=_input(source_budget_vnd=42_000_000)).json()

    response = client.post(
        f"/api/public/judge/runs/{run['run_id']}/cases/NEW_INPUT/action",
        json={"action": "STOP", "reason": "Stop the synthetic case pending source verification."},
        headers={"Idempotency-Key": str(uuid4())},
    )

    assert response.status_code == 200
    result = response.json()
    assert run["human_action_available"] is True
    assert run["human_action_status"] == "PENDING"
    assert result["status"] == "STOPPED"
    assert result["is_override"] is False
    assert result["input_sha256"] == run["audit"]["input_sha256"]
    assert result["audit"][-1]["action"] == "HUMAN_STOPPED"
    assert result["audit"][-1]["reason"] == "Stop the synthetic case pending source verification."


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


def test_health_remains_responsive_while_public_suite_is_paused(monkeypatch):
    from fastapi import FastAPI
    from src.verify import runner

    entered = Event()
    release = Event()

    def paused_suite(_suite):
        entered.set()
        if not release.wait(timeout=5):
            raise TimeoutError("synthetic paused suite was not released")
        return []

    monkeypatch.setattr(runner, "run_suite", paused_suite)
    app = FastAPI()
    app.include_router(router)

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    suite_results = []
    health_results = []
    health_done = Event()

    with TestClient(app) as client:
        def run_judge_suite():
            suite_results.append(client.post("/api/public/judge/runs", json={"suite": "general"}))

        suite_thread = Thread(target=run_judge_suite, daemon=True)
        suite_thread.start()
        assert entered.wait(timeout=2), "suite did not reach the synthetic pause"

        def request_health():
            try:
                health_results.append(client.get("/api/health"))
            finally:
                health_done.set()

        health_thread = Thread(target=request_health, daemon=True)
        health_thread.start()
        responsive_while_paused = health_done.wait(timeout=1)
        release.set()
        suite_thread.join(timeout=2)
        health_thread.join(timeout=2)

    assert responsive_while_paused, "a paused public suite blocked the shared ASGI event loop"
    assert suite_results and suite_results[0].status_code == 200
    assert health_results and health_results[0].status_code == 200


def test_public_router_has_only_the_two_post_run_routes():
    routes = {(route.path, tuple(sorted(route.methods))) for route in router.routes}

    assert routes == {
        ("/api/public/judge/runs", ("POST",)),
        ("/api/public/judge/input-runs", ("POST",)),
        ("/api/public/judge/runs/{run_id}/cases/{case_id}/action", ("POST",)),
    }


def test_public_judge_action_store_keeps_only_hash_and_audit_metadata():
    store = PublicJudgeActionStore()
    raw_input = {"title": "Synthetic title must not be retained", "budget_vnd": 123}

    input_hash = hashlib.sha256(json.dumps(raw_input, sort_keys=True).encode()).hexdigest()
    assert store.register_run("RUN-1", [{
        "case_id": "CASE-1",
        "recommendation": "HUMAN_REVIEW_REQUIRED",
        "input_sha256": input_hash,
        "reason": "Synthetic conflict needs human review.",
        "audit": [],
    }])

    result = store.perform_action(
        "RUN-1", "CASE-1", "APPROVE", "Checker verifies source authority.", str(uuid4()),
    )

    assert result["status"] == "HUMAN_APPROVED"
    assert result["is_override"] is False
    assert result["input_sha256"] == input_hash
    assert result["audit"][-1]["action"] == "HUMAN_APPROVED"
    assert result["audit"][-1]["timestamp"]
    assert result["audit"][-1]["reason"] == "Checker verifies source authority."
    assert "Synthetic title must not be retained" not in repr(store._records)
    assert "raw_input" not in repr(store._records)


def test_public_judge_action_store_marks_auto_decision_as_override_and_replays_idempotently():
    store = PublicJudgeActionStore()
    store.register_run("RUN-2", [{
        "case_id": "CASE-2",
        "recommendation": "AUTO_APPROVED",
        "input_sha256": "a" * 64,
        "reason": "Synthetic automatic result.",
        "audit": [{"action": "AUTO_APPROVED", "timestamp": "2026-10-15T00:00:00Z",
                   "input_sha256": "a" * 64, "reason": "Synthetic automatic result."}],
    }])
    idempotency_key = str(uuid4())

    result = store.perform_action("RUN-2", "CASE-2", "REJECT", "Human stops this simulation.", idempotency_key)
    replay = store.perform_action("RUN-2", "CASE-2", "REJECT", "Human stops this simulation.", idempotency_key)

    assert result["status"] == "HUMAN_REJECTED"
    assert result["is_override"] is True
    assert replay["idempotent_replay"] is True
    assert replay["audit"] == result["audit"]
    assert replay["audit"][-1]["action"] == "HUMAN_OVERRIDE_REJECTED"
    assert replay["audit"][-1]["input_sha256"] == "a" * 64


def test_public_judge_action_store_rejects_a_second_final_action():
    store = PublicJudgeActionStore()
    store.register_run("RUN-3", [{
        "case_id": "CASE-3", "recommendation": "HUMAN_REVIEW_REQUIRED",
        "input_sha256": "b" * 64, "reason": "Needs decision.", "audit": [],
    }])
    store.perform_action("RUN-3", "CASE-3", "STOP", "Stop the simulation.", str(uuid4()))

    try:
        store.perform_action("RUN-3", "CASE-3", "APPROVE", "Different final action.", str(uuid4()))
    except PublicJudgeActionError as exc:
        assert exc.code == "ACTION_ALREADY_FINAL"
        assert exc.status_code == 409
    else:
        raise AssertionError("a case must have at most one final human action")


def test_public_judge_action_store_expires_sessions_and_bounds_pending_cases():
    now = [0.0]
    store = PublicJudgeActionStore(clock=lambda: now[0], max_cases=1, ttl_seconds=10)
    case = [{
        "case_id": "CASE",
        "recommendation": "HUMAN_REVIEW_REQUIRED",
        "input_sha256": "e" * 64,
        "reason": "Synthetic review.",
        "audit": [],
    }]

    assert store.register_run("RUN-1", case)
    assert not store.register_run("RUN-2", case)
    now[0] = 11.0
    assert store.register_run("RUN-2", case)


def test_public_judge_action_store_serializes_concurrent_final_actions():
    store = PublicJudgeActionStore()
    store.register_run("RUN-4", [{
        "case_id": "CASE-4", "recommendation": "HUMAN_REVIEW_REQUIRED",
        "input_sha256": "c" * 64, "reason": "Needs decision.", "audit": [],
    }])
    barrier = Barrier(3)
    results = []
    result_lock = Lock()

    def decide(action):
        barrier.wait(timeout=2)
        try:
            value = store.perform_action("RUN-4", "CASE-4", action, f"Synthetic {action}.", str(uuid4()))
            outcome = ("OK", value["status"])
        except PublicJudgeActionError as exc:
            outcome = ("ERROR", exc.code)
        with result_lock:
            results.append(outcome)

    threads = [Thread(target=decide, args=(action,)) for action in ("APPROVE", "STOP")]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=2)
    for thread in threads:
        thread.join(timeout=2)

    assert all(not thread.is_alive() for thread in threads)
    assert sorted(result[0] for result in results) == ["ERROR", "OK"]
    assert [result[1] for result in results if result[0] == "ERROR"] == ["ACTION_ALREADY_FINAL"]
