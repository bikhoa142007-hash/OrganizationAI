import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
import hashlib
import json
import threading

import httpx
import pytest

import src.ai_pipeline.authenticated_orchestrator as authenticated_orchestrator_module
from src.ai_pipeline.models import EvaluationRequest
from src.ai_pipeline.providers.base import ProviderNonRetryableError, ProviderTimeout
from src.ai_pipeline.task_evaluation import media_policy_from_json, strategy_rubric_from_json
from src.ai_pipeline.task_providers import TaskEvaluationRequest
from src.backend.domain.models import AttachmentManifest, MarketingPlan
from scripts.ai03_request_gate import (
    GatedTaskProvider,
    MAX_INPUT_BYTES,
    MAX_OUTPUT_TOKENS,
    MAX_RESPONSE_BYTES,
    RequestBudgetTransport,
    RequestGate,
    TASK_MODEL_ID,
    TASK_MODEL_VERSION,
    VLM_MODEL_ID,
    VLM_MODEL_VERSION,
    build_harness_orchestrator,
)


def test_request_gate_caps_six_http_requests_and_three_inference_posts():
    sent = []

    def responder(request):
        sent.append((request.method, request.url.path))
        return httpx.Response(200, json={"ok": True})

    gate = RequestGate(max_requests=6, max_inference_posts=3)
    transport = RequestBudgetTransport(gate, inner=httpx.MockTransport(responder))
    with httpx.Client(transport=transport) as client:
        for stage in ("VLM", "MEDIA", "STRATEGY"):
            with gate.provider_call(stage, timeout_seconds=1):
                client.get("http://127.0.0.1:11434/api/tags")
                client.post("http://127.0.0.1:11434/v1/chat/completions", json={})

        with pytest.raises(ProviderNonRetryableError) as error:
            with gate.provider_call("EXTRA", timeout_seconds=1):
                client.get("http://127.0.0.1:11434/api/tags")

    snapshot = gate.snapshot()
    assert error.value.code == "REQUEST_BUDGET_EXHAUSTED"
    assert len(sent) == 6
    assert snapshot["request_count"] == 6
    assert snapshot["inference_post_count"] == 3
    assert snapshot["blocked_requests"][-1]["reason"] == "REQUEST_BUDGET_EXHAUSTED"


def test_provider_timeout_latches_gate_and_suppresses_later_provider_requests():
    wire_requests = []

    def responder(request):
        wire_requests.append((request.method, request.url.path))
        if request.method == "POST":
            raise httpx.ReadTimeout("synthetic timeout", request=request)
        return httpx.Response(200, json={"ok": True})

    gate = RequestGate()
    transport = RequestBudgetTransport(gate, inner=httpx.MockTransport(responder))
    client = httpx.Client(transport=transport)

    class TimeoutProvider:
        settings = type("Settings", (), {"timeout_seconds": 1})()

        def evaluate(self, _request):
            client.post("http://127.0.0.1:11434/v1/chat/completions", json={})
            raise ProviderTimeout()

    class LaterProvider:
        settings = type("Settings", (), {"timeout_seconds": 1})()
        calls = 0

        def evaluate(self, _request):
            self.calls += 1
            client.post("http://127.0.0.1:11434/v1/chat/completions", json={})

    later = LaterProvider()
    try:
        first = GatedTaskProvider(TimeoutProvider(), gate, provider_name="MEDIA", timeout_seconds=1)
        second = GatedTaskProvider(later, gate, provider_name="STRATEGY", timeout_seconds=1)

        with pytest.raises(ProviderTimeout):
            first.evaluate(None)
        with pytest.raises(ProviderNonRetryableError) as error:
            second.evaluate(None)
    finally:
        client.close()

    snapshot = gate.snapshot()
    assert error.value.code == "PROVIDER_CALL_SUPPRESSED"
    assert wire_requests == [("POST", "/v1/chat/completions")]
    assert later.calls == 0
    assert snapshot["closed"] is True
    assert snapshot["close_reason"] == "PROVIDER_TIMEOUT"
    assert snapshot["request_count"] == 1
    assert snapshot["inference_post_count"] == 1
    assert snapshot["sent_requests"][0]["server_completion_known"] is False
    with pytest.raises(ProviderTimeout):
        first.evaluate(None)
    assert len(wire_requests) == 1


def test_absolute_call_deadline_latches_gate_before_slow_provider_can_send():
    wire_requests = []

    def responder(request):
        wire_requests.append((request.method, request.url.path))
        return httpx.Response(200, json={"ok": True})

    gate = RequestGate()
    transport = RequestBudgetTransport(gate, inner=httpx.MockTransport(responder))
    client = httpx.Client(transport=transport)

    class SlowProvider:
        settings = type("Settings", (), {"timeout_seconds": 0.04})()

        def evaluate(self, _request):
            time.sleep(0.08)
            return client.post("http://127.0.0.1:11434/v1/chat/completions", json={})

    provider = GatedTaskProvider(SlowProvider(), gate, provider_name="MEDIA", timeout_seconds=0.04)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(provider.evaluate, None)
            with pytest.raises(FutureTimeout):
                future.result(timeout=0.02)
            time.sleep(0.05)
            with pytest.raises(ProviderTimeout) as error:
                future.result()
    finally:
        client.close()

    snapshot = gate.snapshot()
    assert isinstance(error.value, ProviderTimeout)
    assert wire_requests == []
    assert snapshot["closed"] is True
    assert snapshot["close_reason"] == "CALL_DEADLINE_EXCEEDED"
    assert snapshot["request_count"] == 0
    assert snapshot["blocked_requests"][-1]["reason"] == "PROVIDER_TIMEOUT"

from scripts.ai03_request_gate import GatedVisualProvider


def test_visual_wrapper_keeps_source_outer_timeout_and_separate_20_second_gate():
    class SourceVisualProvider:
        timeout_seconds = 18

        def analyze_image(self, _request):
            return "synthetic"

    gate = RequestGate()
    provider = GatedVisualProvider(SourceVisualProvider(), gate, deadline_seconds=20)

    assert provider.timeout_seconds == 18
    assert provider.call_deadline_seconds == 20
    assert provider.analyze_image(None) == "synthetic"
    assert gate.snapshot()["provider_calls"][0]["status"] == "SUCCEEDED"
def test_request_gate_pins_approved_origin_routes_and_hard_ceiling():
    with pytest.raises(ValueError):
        RequestGate(max_requests=7)
    with pytest.raises(ValueError):
        RequestGate(max_inference_posts=4)

    wire_requests = []
    gate = RequestGate()
    transport = RequestBudgetTransport(
        gate,
        inner=httpx.MockTransport(lambda request: wire_requests.append(request) or httpx.Response(200)),
    )
    with httpx.Client(transport=transport) as client:
        with pytest.raises(ProviderNonRetryableError) as error:
            with gate.provider_call("VLM", timeout_seconds=1):
                client.post("http://example.invalid/v1/chat/completions", json={})

    assert error.value.code == "REQUEST_ORIGIN_NOT_ALLOWED"
    assert wire_requests == []
    assert gate.snapshot()["request_count"] == 0


SYNTHETIC_MEDIA_POLICY = media_policy_from_json('''{
  "policy_id":"SYNTHETIC-POLICY","policy_version":"1","status":"ACTIVE",
  "scope_departments":["marketing"],"scope_channels":["social"],
  "rules":[{"rule_id":"SYNTHETIC-RULE","severity":"WARNING",
    "description":"Synthetic only","required_evidence_kinds":["OBSERVATION"]}]
}''')
SYNTHETIC_STRATEGY_RUBRIC = strategy_rubric_from_json('''{
  "rubric_id":"SYNTHETIC-RUBRIC","rubric_version":"1","status":"ACTIVE",
  "criteria":[
    {"criterion_id":"objective","label":"Objective","weight":15},
    {"criterion_id":"audience","label":"Audience","weight":15},
    {"criterion_id":"channel","label":"Channel","weight":15},
    {"criterion_id":"timeline","label":"Timeline","weight":15},
    {"criterion_id":"kpi","label":"KPI","weight":15},
    {"criterion_id":"budget_efficiency","label":"Budget efficiency","weight":15},
    {"criterion_id":"risk_control","label":"Risk control","weight":10}
  ]
}''')
SYNTHETIC_EVIDENCE = [{
    "evidence_id": "synthetic-observation-1",
    "kind": "OBSERVATION",
    "text": "Synthetic observation only.",
}]


def _source_visual_request(image=b"synthetic-image-bytes"):
    manifest = AttachmentManifest(
        "synthetic-attachment",
        hashlib.sha256(image).hexdigest(),
        "image/png",
        len(image),
    )
    plan = MarketingPlan(
        "synthetic-plan", 1, 1, {"title": "Synthetic only"}, (manifest,)
    )
    return EvaluationRequest(
        plan=plan,
        policy_version="SYNTHETIC-POLICY-1",
        evaluation_id="synthetic-evaluation",
        run_id="synthetic-run",
        correlation_id="synthetic-correlation",
        provider="LOCAL_VLM",
        model_version=VLM_MODEL_VERSION,
        metadata={"attachment_contents": {manifest.attachment_id: image}},
    )


def _source_task_request(task, *, title="Synthetic campaign"):
    values = {
        "title": title,
        "objective": "Synthetic objective",
        "department": "marketing",
        "channels": ["social"],
    }
    return TaskEvaluationRequest(
        task=task,
        input_hash="a" * 64,
        plan_payload=values,
        evidence=list(SYNTHETIC_EVIDENCE),
        policy=SYNTHETIC_MEDIA_POLICY if task == "MEDIA_COMPLIANCE" else None,
        rubric=SYNTHETIC_STRATEGY_RUBRIC if task == "STRATEGY_EVALUATION" else None,
    )


def _identity_response():
    return httpx.Response(200, json={"models": [
        {"name": VLM_MODEL_ID, "digest": VLM_MODEL_VERSION.removeprefix("sha256:")},
        {"name": TASK_MODEL_ID, "digest": TASK_MODEL_VERSION.removeprefix("sha256:")},
    ]})


def _completion_response(model_id, *, finish_reason="length", content=""):
    return httpx.Response(200, json={
        "model": model_id,
        "choices": [{
            "finish_reason": finish_reason,
            "message": {"content": content, "refusal": None},
        }],
    })


def _call_source_provider(kind, providers, *, visual_request=None, task_request=None):
    if kind == "VLM":
        return providers["visual"].analyze_image(visual_request or _source_visual_request())
    if kind == "MEDIA":
        return providers["media"].evaluate(
            task_request or _source_task_request("MEDIA_COMPLIANCE")
        )
    return providers["strategy"].evaluate(
        task_request or _source_task_request("STRATEGY_EVALUATION")
    )


def test_builder_owns_a_client_with_the_same_hard_gate():
    gate = RequestGate()
    orchestrator, providers = build_harness_orchestrator(
        gate, inner_transport=httpx.MockTransport(lambda _request: _identity_response())
    )
    client = providers["client"]
    try:
        assert orchestrator is not None
        assert isinstance(client._transport, RequestBudgetTransport)
        assert client._transport.gate is gate
        with pytest.raises(TypeError):
            build_harness_orchestrator(gate, object())
    finally:
        client.close()


def test_fourth_inference_post_is_blocked_while_total_request_budget_remains():
    wire_requests = []
    gate = RequestGate()
    transport = RequestBudgetTransport(
        gate,
        inner=httpx.MockTransport(
            lambda request: wire_requests.append((request.method, request.url.path))
            or httpx.Response(200)
        ),
    )
    with httpx.Client(transport=transport) as client:
        for provider in ("VLM", "MEDIA", "STRATEGY"):
            with gate.provider_call(provider, timeout_seconds=1):
                client.post("http://127.0.0.1:11434/v1/chat/completions", json={})
        with pytest.raises(ProviderNonRetryableError) as error:
            with gate.provider_call("EXTRA", timeout_seconds=1):
                client.post("http://127.0.0.1:11434/v1/chat/completions", json={})

    snapshot = gate.snapshot()
    assert error.value.code == "INFERENCE_BUDGET_EXHAUSTED"
    assert len(wire_requests) == 3
    assert snapshot["request_count"] == 3 < snapshot["max_requests"]
    assert snapshot["inference_post_count"] == 3
    assert snapshot["blocked_requests"][-1]["reason"] == "INFERENCE_BUDGET_EXHAUSTED"


@pytest.mark.parametrize("kind", ["VLM", "MEDIA", "STRATEGY"])
def test_real_source_providers_reject_inputs_over_the_approved_limit(kind):
    wire_requests = []

    def respond(request):
        wire_requests.append((request.method, request.url.path))
        return _identity_response()

    gate = RequestGate()
    orchestrator, providers = build_harness_orchestrator(
        gate, inner_transport=httpx.MockTransport(respond)
    )
    del orchestrator
    client = providers["client"]
    try:
        if kind == "VLM":
            request = _source_visual_request(b"x" * (MAX_INPUT_BYTES + 1))
            with pytest.raises(ProviderNonRetryableError) as error:
                _call_source_provider(kind, providers, visual_request=request)
        else:
            task = "MEDIA_COMPLIANCE" if kind == "MEDIA" else "STRATEGY_EVALUATION"
            request = _source_task_request(task, title="x" * (MAX_INPUT_BYTES + 1))
            with pytest.raises(ProviderNonRetryableError) as error:
                _call_source_provider(kind, providers, task_request=request)
    finally:
        client.close()

    assert error.value.code == "INPUT_TOO_LARGE"
    assert wire_requests == [("GET", "/api/tags")]
    assert gate.snapshot()["inference_post_count"] == 0


@pytest.mark.parametrize("kind", ["VLM", "MEDIA", "STRATEGY"])
def test_real_source_providers_reject_responses_over_the_approved_limit(kind):
    wire_requests = []

    def respond(request):
        wire_requests.append((request.method, request.url.path))
        if request.method == "GET":
            return _identity_response()
        return httpx.Response(200, content=b"x" * (MAX_RESPONSE_BYTES + 1))

    gate = RequestGate()
    orchestrator, providers = build_harness_orchestrator(
        gate, inner_transport=httpx.MockTransport(respond)
    )
    del orchestrator
    client = providers["client"]
    try:
        with pytest.raises(ProviderNonRetryableError) as error:
            _call_source_provider(kind, providers)
    finally:
        client.close()

    assert error.value.code == "RESOURCE_EXHAUSTED"
    assert wire_requests == [
        ("GET", "/api/tags"),
        ("POST", "/v1/chat/completions"),
    ]


def test_all_three_real_source_providers_send_the_approved_output_token_cap():
    inference_bodies = []

    def respond(request):
        if request.method == "GET":
            return _identity_response()
        body = json.loads(request.content)
        inference_bodies.append(body)
        return _completion_response(body["model"])

    gate = RequestGate()
    orchestrator, providers = build_harness_orchestrator(
        gate, inner_transport=httpx.MockTransport(respond)
    )
    del orchestrator
    client = providers["client"]
    try:
        for kind in ("VLM", "MEDIA", "STRATEGY"):
            with pytest.raises(ProviderNonRetryableError) as error:
                _call_source_provider(kind, providers)
            assert error.value.code == "TRUNCATED_OUTPUT"
    finally:
        client.close()

    assert [item["model"] for item in inference_bodies] == [
        VLM_MODEL_ID, TASK_MODEL_ID, TASK_MODEL_ID,
    ]
    assert [item["max_tokens"] for item in inference_bodies] == [
        MAX_OUTPUT_TOKENS, MAX_OUTPUT_TOKENS, MAX_OUTPUT_TOKENS,
    ]
    assert gate.snapshot()["inference_post_count"] == 3


@pytest.mark.parametrize(("url", "method", "expected_code"), [
    ("http://127.0.0.1:11434/v1/chat/completions", "GET", "REQUEST_ROUTE_NOT_ALLOWED"),
    ("http://127.0.0.1:11434/api/tags", "POST", "REQUEST_ROUTE_NOT_ALLOWED"),
    ("http://127.0.0.1:11434/api/show", "GET", "REQUEST_ROUTE_NOT_ALLOWED"),
    ("http://localhost:11434/api/tags", "GET", "REQUEST_ORIGIN_NOT_ALLOWED"),
    ("https://127.0.0.1:11434/api/tags", "GET", "REQUEST_ORIGIN_NOT_ALLOWED"),
    ("http://127.0.0.1:11435/api/tags", "GET", "REQUEST_ORIGIN_NOT_ALLOWED"),
])
def test_disallowed_method_path_or_origin_is_rejected_before_inner_transport(
    url, method, expected_code,
):
    inner_calls = []
    gate = RequestGate()
    transport = RequestBudgetTransport(
        gate,
        inner=httpx.MockTransport(
            lambda request: inner_calls.append(request) or httpx.Response(200)
        ),
    )
    with httpx.Client(transport=transport) as client:
        with pytest.raises(ProviderNonRetryableError) as error:
            client.request(method, url)

    assert error.value.code == expected_code
    assert inner_calls == []
    assert gate.snapshot()["request_count"] == 0


def test_orchestrator_future_timeout_cancels_and_closes_gate_before_next_request(monkeypatch):
    post_started = threading.Event()
    release_post = threading.Event()
    post_finished = threading.Event()
    wire_requests = []
    observed_executors = []
    real_executor_type = ThreadPoolExecutor

    def respond(request):
        wire_requests.append((request.method, request.url.path))
        if request.method == "GET":
            return _identity_response()
        post_started.set()
        try:
            if not release_post.wait(timeout=5):
                raise AssertionError("Test did not release the synthetic POST.")
            model_id = json.loads(request.content)["model"]
            return _completion_response(model_id, finish_reason="stop", content="{}")
        finally:
            post_finished.set()

    class ObservedFuture:
        def __init__(self, future):
            self.future = future
            self.cancel_called = False
            self.cancel_result = None
            self.result_timeout = None

        def result(self, timeout=None):
            self.result_timeout = timeout
            assert post_started.wait(timeout=2), "Synthetic POST did not start before FutureTimeout."
            # Keep the approved 20-second source timeout; virtualize only the
            # elapsed wait so the deterministic test does not wait 20 seconds.
            return self.future.result(timeout=0.05)

        def cancel(self):
            self.cancel_called = True
            self.cancel_result = self.future.cancel()
            return self.cancel_result

    class ObservedExecutor:
        def __init__(self, *args, **kwargs):
            self.executor = real_executor_type(*args, **kwargs)
            self.future = None
            observed_executors.append(self)

        def submit(self, *args, **kwargs):
            self.future = ObservedFuture(self.executor.submit(*args, **kwargs))
            return self.future

        def shutdown(self, *, wait=True, cancel_futures=False):
            return self.executor.shutdown(wait=wait, cancel_futures=cancel_futures)

    monkeypatch.setattr(
        authenticated_orchestrator_module, "ThreadPoolExecutor", ObservedExecutor
    )
    gate = RequestGate()
    orchestrator, providers = build_harness_orchestrator(
        gate, inner_transport=httpx.MockTransport(respond)
    )
    client = providers["client"]
    media_request = _source_task_request("MEDIA_COMPLIANCE")
    step = {"status": "PENDING", "attempt_history": [], "attempts": 0, "retried": False}
    try:
        result = orchestrator._run_step(
            "MEDIA_COMPLIANCE",
            providers["media"],
            media_request,
            step,
            time.monotonic() + 100,
            lambda _output, _evidence: {},
            [],
            None,
        )

        assert result["status"] == "TIMED_OUT"
        assert result["error_code"] == "PROVIDER_TIMEOUT"
        assert len(observed_executors) == 1
        observed_future = observed_executors[0].future
        assert observed_future.result_timeout == 20
        assert observed_future.cancel_called is True
        assert observed_future.cancel_result is False
        assert observed_future.future.done() is False
        assert post_started.is_set()

        with pytest.raises(ProviderNonRetryableError) as error:
            providers["strategy"].evaluate(_source_task_request("STRATEGY_EVALUATION"))
        assert error.value.code == "PROVIDER_CALL_SUPPRESSED"
        with pytest.raises(ProviderTimeout):
            client.post("http://127.0.0.1:11434/v1/chat/completions", json={})

        timeout_evidence = gate.snapshot()
        assert timeout_evidence["closed"] is True
        assert timeout_evidence["close_reason"] == "PROVIDER_TIMEOUT"
        assert timeout_evidence["request_count"] == 2
        assert timeout_evidence["inference_post_count"] == 1
        assert timeout_evidence["provider_calls"][-1]["status"] == "TIMED_OUT"
        assert timeout_evidence["provider_calls"][-1]["error_code"] == "PROVIDER_TIMEOUT"
        assert timeout_evidence["sent_requests"][-1]["server_completion_known"] is False
        assert timeout_evidence["sent_requests"][-1]["response_completed_at"] is None
        assert wire_requests == [
            ("GET", "/api/tags"),
            ("POST", "/v1/chat/completions"),
        ]
    finally:
        release_post.set()
        for observed in observed_executors:
            observed.shutdown(wait=True, cancel_futures=True)
        assert post_finished.wait(timeout=2)
        client.close()
