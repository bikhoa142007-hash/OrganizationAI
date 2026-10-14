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
    monkeypatch.setattr(runner, "run_suite", lambda suite: [])

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
    }

    with TestClient(app) as client:
        allowed = client.options("/api/public/judge/runs", headers={
            "Origin": "https://judge.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        })
        denied = client.options("/api/public/judge/runs", headers={
            "Origin": "https://unlisted.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        })

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://judge.example"
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
