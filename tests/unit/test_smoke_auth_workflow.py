import json

import httpx
import pytest

from scripts import smoke_auth_workflow as smoke


def _response_plan(request, plan_id="plan-1"):
    body = json.loads(request.content)
    return {
        "id": plan_id,
        "payload": body["payload"],
        "status": "DRAFT",
        "revision": 0,
        "attachments": [],
    }


def test_create_saves_plan_id_and_uses_payload_title(tmp_path):
    requests = []

    def handle(request):
        requests.append(request)
        assert request.method == "POST"
        assert request.url.path == "/api/workflow/plans"
        return httpx.Response(201, json=_response_plan(request))

    state = smoke.SmokeRunState(tmp_path / "state.json")
    with httpx.Client(transport=httpx.MockTransport(handle), base_url="http://local/api/") as client:
        draft = smoke.create_or_recover_draft(client, "checker-1", "Smoke plan title", state, "approval")

    assert draft["payload"]["title"] == "Smoke plan title"
    assert state.plan_id("approval") == "plan-1"
    saved = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert saved["plan_ids"]["approval"] == "plan-1"
    assert len(requests) == 1


def test_timeout_recovers_created_plan_before_any_retry(tmp_path, monkeypatch):
    post_count = 0
    stored = {}

    def handle(request):
        nonlocal post_count
        if request.method == "POST":
            post_count += 1
            stored["plan"] = _response_plan(request)
            raise httpx.ReadTimeout("response lost after server accepted create", request=request)
        if request.method == "GET" and request.url.path == "/api/workflow/plans/plan-1":
            return httpx.Response(200, json=stored["plan"])
        raise AssertionError(f"Unexpected fixture request: {request.method} {request.url}")

    monkeypatch.setattr(
        smoke,
        "find_plans_by_run_marker",
        lambda marker: [{"id": "plan-1", "payload": stored["plan"]["payload"]}],
    )
    state = smoke.SmokeRunState(tmp_path / "state.json")
    with httpx.Client(transport=httpx.MockTransport(handle), base_url="http://local/api/") as client:
        draft = smoke.create_or_recover_draft(client, "checker-1", "Smoke plan title", state, "approval")

    assert draft["id"] == "plan-1"
    assert post_count == 1
    assert state.plan_id("approval") == "plan-1"


def test_timeout_without_match_stops_without_retrying_create(tmp_path, monkeypatch):
    post_count = 0
    lookup_count = 0

    def handle(request):
        nonlocal post_count
        if request.method != "POST":
            raise AssertionError(f"Unexpected fixture request: {request.method} {request.url}")
        post_count += 1
        if post_count == 1:
            raise httpx.ReadTimeout("create response timed out", request=request)
        return httpx.Response(201, json=_response_plan(request, "plan-2"))

    def no_candidates(marker):
        nonlocal lookup_count
        lookup_count += 1
        return []

    monkeypatch.setattr(smoke, "find_plans_by_run_marker", no_candidates)
    state = smoke.SmokeRunState(tmp_path / "state.json")
    with httpx.Client(transport=httpx.MockTransport(handle), base_url="http://local/api/") as client:
        with pytest.raises(RuntimeError, match="stopped without retrying"):
            smoke.create_or_recover_draft(client, "checker-1", "Smoke plan title", state, "approval")
        with pytest.raises(RuntimeError, match="no matching plan is visible"):
            smoke.create_or_recover_draft(client, "checker-1", "Smoke plan title", state, "approval")

    assert post_count == 1
    assert lookup_count == 2
    assert state.plan_id("approval") is None


def test_smoke_state_refuses_a_second_plan_and_preserves_completed_id(tmp_path):
    state_path = tmp_path / "state.json"
    state = smoke.SmokeRunState(state_path)
    state.save_plan_id("maker-checker-cycle", "plan-1")
    with pytest.raises(RuntimeError, match="only one plan"):
        state.assert_single_plan_scenario("second-plan")
    state.mark_complete()

    reloaded = smoke.SmokeRunState(state_path)

    assert reloaded.completed is True
    assert reloaded.plan_id("maker-checker-cycle") == "plan-1"


def test_wait_for_checker_review_polls_persisted_state_without_restarting_ai(monkeypatch):
    processing = {
        "id": "plan-1", "status": "PENDING_APPROVAL", "current_version": 1,
        "current_round": 1, "processing_stage": "AI_PROCESSING",
        "ai_evaluations": [], "engine_decisions": [],
    }
    ready = {
        **processing,
        "processing_stage": "HUMAN_REVIEW_REQUIRED",
        "ai_evaluations": [{"version_number": 1, "round_number": 1}],
        "engine_decisions": [{
            "version_number": 1, "round_number": 1,
            "outcome": "HUMAN_REVIEW_REQUIRED",
        }],
    }
    requests = []

    def handle(request):
        requests.append(request)
        assert request.method == "GET"
        return httpx.Response(200, json=ready)

    monkeypatch.setattr(smoke, "sleep", lambda _seconds: None)
    with httpx.Client(transport=httpx.MockTransport(handle), base_url="http://local/api/") as client:
        result = smoke.wait_for_checker_review(client, processing, timeout_seconds=30)

    assert result["processing_stage"] == "HUMAN_REVIEW_REQUIRED"
    assert len(requests) == 1


def test_multiple_run_marker_candidates_stop_without_selecting_or_deleting(tmp_path, monkeypatch):
    post_count = 0

    def handle(request):
        nonlocal post_count
        post_count += 1
        raise httpx.ReadTimeout("create response timed out", request=request)

    monkeypatch.setattr(smoke, "find_plans_by_run_marker", lambda marker: [
        {"id": "plan-a", "payload": {"notes": marker}},
        {"id": "plan-b", "payload": {"notes": marker}},
    ])
    state = smoke.SmokeRunState(tmp_path / "state.json")
    with httpx.Client(transport=httpx.MockTransport(handle), base_url="http://local/api/") as client:
        with pytest.raises(RuntimeError, match="plan-a, plan-b"):
            smoke.create_or_recover_draft(client, "checker-1", "Smoke plan title", state, "approval")

    assert post_count == 1
    assert state.plan_id("approval") is None
