from importlib import import_module

from fastapi.testclient import TestClient

from src.backend.api.auth import get_auth_db
from src.backend.api.dependencies import Settings


app_module = import_module("src.backend.api.app")


def _app(app_env="production"):
    base = app_module.app
    return app_module.create_app(
        settings=Settings(
            app_env=app_env,
            database="unused-public-judge-test.sqlite3",
            cors_origins=("https://judge.example",),
            mock_mode="pass",
        ),
        auth_workflow_provider=base.state.auth_workflow_provider,
        auth_workflow_media_provider=base.state.auth_workflow_media_provider,
        auth_workflow_strategy_provider=base.state.auth_workflow_strategy_provider,
        auth_workflow_configuration=base.state.auth_workflow_configuration,
    )


def _input():
    return {
        "title": "Synthetic public Judge input",
        "department": "DEMO-DEPT-01",
        "objective": "Reach a defined demo audience",
        "summary": "A bounded, synthetic input for route-composition tests.",
        "target_audience": "Synthetic audience",
        "channel": "DEMO_SOCIAL",
        "currency": "VND",
        "budget_vnd": 50_000_000,
        "source_budget_vnd": 50_000_000,
    }


def test_public_judge_is_mounted_without_auth_database_or_demo_workflow(monkeypatch):
    from src.verify import runner

    app = _app(app_env="demo")

    def forbidden_database_access(*args, **kwargs):
        raise AssertionError("public Judge must not access Auth DB or demo workflow")

    app.dependency_overrides[get_auth_db] = forbidden_database_access
    monkeypatch.setattr(app_module, "open_workflow", forbidden_database_access)
    monkeypatch.setattr(runner, "run_suite", lambda _suite: [{
        "case_id": "SYNTHETIC-ISOLATION-CASE",
        "case_name": "Synthetic human-review case",
        "started_at": "2026-10-15T00:00:00.000Z",
        "completed_at": "2026-10-15T00:00:00.010Z",
        "duration_ms": 10,
        "expected": {"route": "HUMAN_REVIEW_REQUIRED", "primary_category": "FACT_UNCERTAIN"},
        "actual": {
            "decision": {"outcome": "HUMAN_REVIEW_REQUIRED", "reason": "A source is needed."},
            "evaluation": {"model_version": "mock-fixture-v1", "evidence": []},
            "plan": {"payload": {"title": "Synthetic isolation case"}},
            "audit": [{"action": "ENGINE_ROUTED", "input_hash": "f" * 64,
                        "timestamp": "2026-10-15T00:00:00.010Z", "reason": "A source is needed."}],
            "questions": [],
        },
        "differences": [],
        "error": None,
    }])

    with TestClient(app) as client:
        suite = client.post("/api/public/judge/runs", json={"suite": "general"})
        custom = client.post("/api/public/judge/input-runs", json=_input())

    assert suite.status_code == 200
    assert suite.json()["mode"] == "MOCK"
    assert suite.json()["data_classification"] == "SYNTHETIC"
    assert custom.status_code == 200
    assert custom.json()["processing_mode"] == "DETERMINISTIC_INPUT_SIMULATION"
    assert custom.json()["data_classification"] == "USER_SUPPLIED_UNVERIFIED"


def test_public_judge_keeps_existing_cors_allowlist_and_only_two_post_routes(monkeypatch):
    from src.verify import runner

    app = _app(app_env="demo")
    monkeypatch.setattr(runner, "run_suite", lambda suite: [])
    judge_routes = {
        (path, tuple(sorted(method.upper() for method in methods)))
        for path, methods in app.openapi()["paths"].items()
        if path.startswith("/api/public/judge")
    }

    assert judge_routes == {
        ("/api/public/judge/runs", ("POST",)),
        ("/api/public/judge/input-runs", ("POST",)),
        ("/api/public/judge/runs/{run_id}/cases/{case_id}/action", ("POST",)),
    }

    with TestClient(app) as client:
        allowed = client.options("/api/public/judge/runs", headers={
            "Origin": "https://judge.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,idempotency-key",
        })
        denied = client.options("/api/public/judge/runs", headers={
            "Origin": "https://unlisted.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        })

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://judge.example"
    assert "idempotency-key" in allowed.headers["access-control-allow-headers"].lower()
    assert denied.headers.get("access-control-allow-origin") is None


def test_public_judge_quota_is_bounded_and_does_not_affect_other_routes(monkeypatch):
    from src.verify import runner

    app = _app(app_env="demo")
    app.state.public_judge_request_gate = app_module._PublicJudgeRequestGate(
        max_requests=1,
        window_seconds=60,
        max_concurrent=1,
        clock=lambda: 10.0,
    )
    monkeypatch.setattr(runner, "run_suite", lambda suite: [])

    with TestClient(app) as client:
        first = client.post("/api/public/judge/input-runs", json=_input())
        limited = client.post("/api/public/judge/input-runs", json=_input())
        health = client.get("/api/health")

    assert first.status_code == 200
    assert limited.status_code == 429
    assert limited.json()["code"] == "RATE_LIMITED"
    assert limited.headers["retry-after"] == "60"
    assert "Synthetic public Judge input" not in limited.text
    assert health.status_code == 200


def test_public_judge_is_unavailable_in_production():
    app = _app(app_env="production")
    assert not any(path.startswith("/api/public/judge") for path in app.openapi()["paths"])

    with TestClient(app) as client:
        response = client.post("/api/public/judge/input-runs", json=_input())

    assert response.status_code == 404


def test_public_judge_only_profile_does_not_mount_auth_or_shared_demo_routes(monkeypatch):
    from src.verify import runner

    app = app_module.create_app(
        settings=Settings(
            app_env="demo",
            database="unused-public-judge-test.sqlite3",
            cors_origins=("https://judge.example",),
            mock_mode="pass",
            public_judge_only=True,
        ),
        auth_workflow_provider=app_module.app.state.auth_workflow_provider,
        auth_workflow_media_provider=app_module.app.state.auth_workflow_media_provider,
        auth_workflow_strategy_provider=app_module.app.state.auth_workflow_strategy_provider,
        auth_workflow_configuration=app_module.app.state.auth_workflow_configuration,
    )

    def forbidden_database_access(*args, **kwargs):
        raise AssertionError("public Judge-only profile must not access shared databases")

    app.dependency_overrides[get_auth_db] = forbidden_database_access
    monkeypatch.setattr(app_module, "open_workflow", forbidden_database_access)
    monkeypatch.setattr(runner, "run_suite", lambda _suite: [{
        "case_id": "SYNTHETIC-ISOLATION-CASE",
        "case_name": "Synthetic human-review case",
        "started_at": "2026-10-15T00:00:00.000Z",
        "completed_at": "2026-10-15T00:00:00.010Z",
        "duration_ms": 10,
        "expected": {"route": "HUMAN_REVIEW_REQUIRED", "primary_category": "FACT_UNCERTAIN"},
        "actual": {
            "decision": {"outcome": "HUMAN_REVIEW_REQUIRED", "reason": "A source is needed."},
            "evaluation": {"model_version": "mock-fixture-v1", "evidence": []},
            "plan": {"payload": {"title": "Synthetic isolation case"}},
            "audit": [{"action": "ENGINE_ROUTED", "input_hash": "f" * 64,
                        "timestamp": "2026-10-15T00:00:00.010Z", "reason": "A source is needed."}],
            "questions": [],
        },
        "differences": [],
        "error": None,
    }])

    paths = set(app.openapi()["paths"])
    assert "/api/health" in paths
    assert "/api/public/judge/runs" in paths
    assert "/api/public/judge/input-runs" in paths
    assert "/api/public/judge/runs/{run_id}/cases/{case_id}/action" in paths
    assert "/api/config" not in paths
    assert "/api/plans" not in paths
    assert "/api/auth/login" not in paths

    with TestClient(app) as client:
        health = client.get("/api/health")
        anonymous = client.get("/api/config", headers={"X-Demo-Actor": "MAKER"})
        workflow = client.get("/api/plans", headers={"X-Demo-Actor": "MAKER"})
        auth = client.post("/api/auth/login", json={})
        suite = client.post("/api/public/judge/runs", json={"suite": "general"})
        custom = client.post("/api/public/judge/input-runs", json=_input())
        preflight = client.options("/api/public/judge/runs/SYNTHETIC/cases/CASE/action", headers={
            "Origin": "https://judge.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,idempotency-key",
        })
        openapi = client.get("/openapi.json")
        case = suite.json()["rows"][0]
        action = client.post(
            f"/api/public/judge/runs/{suite.json()['run_id']}/cases/{case['case_id']}/action",
            json={"action": "APPROVE", "reason": "Synthetic source checked by the judge."},
            headers={"Idempotency-Key": "a8fdb708-4a7c-4ef4-a64f-a9221f50cb4e"},
        )

    assert health.status_code == 200
    assert anonymous.status_code == workflow.status_code == auth.status_code == 404
    assert suite.status_code == custom.status_code == action.status_code == 200
    assert case["human_action_available"] is True
    assert action.json()["status"] == "HUMAN_APPROVED"
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "https://judge.example"
    assert "idempotency-key" in preflight.headers["access-control-allow-headers"].lower()
    assert preflight.headers.get("access-control-allow-credentials") is None
    assert openapi.status_code == 404


def test_public_judge_only_profile_is_invalid_outside_demo():
    settings = Settings(
        app_env="production",
        database="unused-public-judge-test.sqlite3",
        cors_origins=("https://judge.example",),
        mock_mode="pass",
        public_judge_only=True,
    )

    try:
        settings.validate()
    except ValueError as exc:
        assert str(exc) == "PUBLIC_JUDGE_ONLY requires APP_ENV=demo."
    else:
        raise AssertionError("public Judge-only profile must require the isolated demo environment")


def test_public_judge_only_profile_does_not_initialize_auth_ai_configuration(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("public Judge-only profile must not initialize Auth AI configuration")

    monkeypatch.setattr(app_module, "create_authenticated_provider", forbidden)
    monkeypatch.setattr(app_module, "configured_task_components", forbidden)
    monkeypatch.setattr(app_module, "unconfigured_approval_configuration", forbidden)

    app = app_module.create_app(settings=Settings(
        app_env="demo",
        database="unused-public-judge-test.sqlite3",
        cors_origins=("https://judge.example",),
        mock_mode="pass",
        public_judge_only=True,
    ))

    assert app.state.auth_workflow_provider is None
    assert app.state.auth_workflow_media_provider is None
    assert app.state.auth_workflow_strategy_provider is None
    assert app.state.auth_workflow_configuration is None


def test_public_judge_human_action_is_audited_idempotent_and_single_final(monkeypatch):
    from src.verify import runner

    app = _app(app_env="demo")
    monkeypatch.setattr(runner, "run_suite", lambda _suite: [{
        "case_id": "SYNTHETIC-REVIEW-1",
        "case_name": "Synthetic fact conflict",
        "started_at": "2026-10-15T00:00:00.000Z",
        "completed_at": "2026-10-15T00:00:00.010Z",
        "duration_ms": 10,
        "expected": {"route": "HUMAN_REVIEW_REQUIRED", "primary_category": "FACT_UNCERTAIN"},
        "actual": {
            "decision": {"outcome": "HUMAN_REVIEW_REQUIRED", "reason": "Source authority is missing."},
            "evaluation": {"model_version": "mock-fixture-v1", "evidence": []},
            "plan": {"payload": {"title": "Synthetic private title"}},
            "audit": [{"action": "ENGINE_ROUTED", "input_hash": "d" * 64,
                        "timestamp": "2026-10-15T00:00:00.010Z",
                        "reason": "Source authority is missing."}],
            "questions": [],
        },
        "differences": [],
        "error": None,
    }])

    with TestClient(app) as client:
        run_response = client.post("/api/public/judge/runs", json={"suite": "general"})
        run = run_response.json()
        case = run["rows"][0]
        missing_key = client.post(
            f"/api/public/judge/runs/{run['run_id']}/cases/{case['case_id']}/action",
            json={"action": "STOP", "reason": "Stop this synthetic flow."},
        )
        blank_reason = client.post(
            f"/api/public/judge/runs/{run['run_id']}/cases/{case['case_id']}/action",
            json={"action": "STOP", "reason": "   "},
            headers={"Idempotency-Key": "2dfe7550-f4f8-42b4-9c73-cda69ed72e8d"},
        )
        invalid_key = client.post(
            f"/api/public/judge/runs/{run['run_id']}/cases/{case['case_id']}/action",
            json={"action": "STOP", "reason": "Stop this synthetic flow."},
            headers={"Idempotency-Key": "not-a-uuid"},
        )
        key = "fd2c54b9-7f8a-4b1f-90d1-2ad56cb6afe1"
        endpoint = f"/api/public/judge/runs/{run['run_id']}/cases/{case['case_id']}/action"
        payload = {"action": "STOP", "reason": "Stop before the synthetic workflow continues."}
        first = client.post(endpoint, json=payload, headers={"Idempotency-Key": key})
        replay = client.post(endpoint, json=payload, headers={"Idempotency-Key": key})
        mismatched_replay = client.post(endpoint, json={
            "action": "APPROVE", "reason": "Same idempotency key, different action.",
        }, headers={"Idempotency-Key": key})
        different_action = client.post(endpoint, json={
            "action": "APPROVE", "reason": "A second result must conflict.",
        }, headers={"Idempotency-Key": "fd2c54b9-7f8a-4b1f-90d1-2ad56cb6afe2"})

    assert run_response.status_code == 200
    assert case["human_action_available"] is True
    assert case["human_action_status"] == "PENDING"
    assert missing_key.status_code == 422
    assert missing_key.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    assert blank_reason.status_code == 422
    assert blank_reason.json()["code"] == "VALIDATION_ERROR"
    assert "   " not in blank_reason.text
    assert invalid_key.status_code == 422
    assert invalid_key.json()["code"] == "IDEMPOTENCY_KEY_INVALID"
    assert first.status_code == 200
    result = first.json()
    assert result["status"] == "STOPPED"
    assert result["is_override"] is False
    assert result["idempotent_replay"] is False
    assert result["input_sha256"] == case["audit"][0]["input_sha256"]
    assert result["audit"][-1]["action"] == "HUMAN_STOPPED"
    assert result["audit"][-1]["timestamp"]
    assert result["audit"][-1]["reason"] == payload["reason"]
    assert result["audit"][-1]["actor"] == "ANONYMOUS_PUBLIC_JUDGE"
    assert replay.status_code == 200
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["audit"] == result["audit"]
    assert mismatched_replay.status_code == 409
    assert mismatched_replay.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert different_action.status_code == 409
    assert different_action.json()["code"] == "ACTION_ALREADY_FINAL"
    assert "Synthetic private title" not in first.text


def test_public_judge_concurrency_gate_rejects_without_blocking(monkeypatch):
    gate = app_module._PublicJudgeRequestGate(
        max_requests=10,
        window_seconds=60,
        max_concurrent=1,
        clock=lambda: 20.0,
    )

    assert gate.try_acquire() is None
    assert gate.try_acquire() == 1
    gate.release()
    assert gate.try_acquire() is None
    gate.release()
