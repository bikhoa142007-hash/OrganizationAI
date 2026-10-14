import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

import httpx
import pytest

from src.ai_pipeline.providers.base import ProviderNonRetryableError, ProviderTimeout
from scripts.ai03_request_gate import (
    GatedTaskProvider,
    RequestBudgetTransport,
    RequestGate,
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