"""Harness-only request ceiling and timeout circuit breaker for one synthetic case.

This module is deliberately outside the production AI pipeline. It wraps the
existing providers and their HTTPX transport only in the one-case harness.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import threading
import time

import httpx

APPROVED_OLLAMA_ORIGIN = "http://127.0.0.1:11434"
MAX_REQUESTS_PER_CASE = 6
MAX_INFERENCE_POSTS_PER_CASE = 3

from src.ai_pipeline.authenticated_orchestrator import AuthenticatedEvaluationOrchestrator
from src.ai_pipeline.providers.base import (
    ProviderNonRetryableError,
    ProviderTimeout,
)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class RequestGate:
    """Thread-safe per-case cap and permanent stop latch after a timeout."""

    def __init__(self, *, max_requests=6, max_inference_posts=3, clock=time.monotonic):
        if not 1 <= max_requests <= MAX_REQUESTS_PER_CASE:
            raise ValueError("Harness request limit cannot exceed six requests per case")
        if not 0 <= max_inference_posts <= MAX_INFERENCE_POSTS_PER_CASE:
            raise ValueError("Harness inference limit cannot exceed three POSTs per case")
        self.max_requests = max_requests
        self.max_inference_posts = max_inference_posts
        self._clock = clock
        self._lock = threading.RLock()
        self._next_call_id = 1
        self._next_request_id = 1
        self._active_call = None
        self._closed = False
        self._close_reason = None
        self._timed_out_provider = None
        self._sent = []
        self._blocked = []
        self._calls = []

    @contextmanager
    def provider_call(self, provider_name, *, timeout_seconds):
        if timeout_seconds <= 0:
            raise ValueError("Provider call deadline must be positive")
        with self._lock:
            self._expire_active_call_locked()
            if self._closed:
                self._record_blocked_call(provider_name, self._suppression_code_locked(provider_name))
                self._raise_closed_locked(provider_name)
            if self._active_call is not None:
                raise ProviderNonRetryableError(
                    "A provider call is already in flight; the case is sequential-only.",
                    code="PROVIDER_CALL_SUPPRESSED",
                )
            call_id = self._next_call_id
            self._next_call_id += 1
            started = self._clock()
            call = {
                "call_id": call_id,
                "provider": provider_name,
                "started_at": _now(),
                "completed_at": None,
                "deadline_monotonic": started + timeout_seconds,
                "status": "IN_PROGRESS",
                "error_code": None,
            }
            self._calls.append(call)
            self._active_call = call
            timer = threading.Timer(
                timeout_seconds, self._deadline_expired, args=(call_id, provider_name)
            )
            timer.daemon = True
            timer.start()

        try:
            yield call_id
            with self._lock:
                self._expire_active_call_locked()
                if self._closed and self._timed_out_provider == provider_name:
                    raise ProviderTimeout()
        except ProviderTimeout:
            self.latch_timeout(provider_name, "PROVIDER_TIMEOUT", call_id=call_id)
            with self._lock:
                call["status"] = "TIMED_OUT"
                call["error_code"] = "PROVIDER_TIMEOUT"
            raise
        except httpx.TimeoutException:
            self.latch_timeout(provider_name, "PROVIDER_TIMEOUT", call_id=call_id)
            with self._lock:
                call["status"] = "TIMED_OUT"
                call["error_code"] = "PROVIDER_TIMEOUT"
            raise ProviderTimeout() from None
        except ProviderNonRetryableError as exc:
            with self._lock:
                call["status"] = "FAILED"
                call["error_code"] = exc.code
            raise
        except Exception as exc:
            with self._lock:
                call["status"] = "FAILED"
                call["error_code"] = getattr(exc, "code", "PROVIDER_ERROR")
            raise
        else:
            with self._lock:
                call["status"] = "SUCCEEDED"
        finally:
            timer.cancel()
            with self._lock:
                call["completed_at"] = _now()
                if self._active_call is call:
                    self._active_call = None

    def _deadline_expired(self, call_id, provider_name):
        with self._lock:
            call = next((item for item in self._calls if item["call_id"] == call_id), None)
            if call is None or call["status"] != "IN_PROGRESS":
                return
            self._latch_locked("CALL_DEADLINE_EXCEEDED", provider_name)
            call["status"] = "TIMED_OUT"
            call["error_code"] = "PROVIDER_TIMEOUT"

    def _expire_active_call_locked(self):
        call = self._active_call
        if call is None or self._clock() < call["deadline_monotonic"]:
            return
        self._latch_locked("CALL_DEADLINE_EXCEEDED", call["provider"])
        call["status"] = "TIMED_OUT"
        call["error_code"] = "PROVIDER_TIMEOUT"

    def latch_timeout(self, provider_name, reason="PROVIDER_TIMEOUT", *, call_id=None):
        with self._lock:
            self._latch_locked(reason, provider_name)
            if call_id is not None:
                call = next((item for item in self._calls if item["call_id"] == call_id), None)
            else:
                call = next((
                    item for item in reversed(self._calls)
                    if item["status"] == "IN_PROGRESS"
                    and (provider_name is None or item["provider"] == provider_name)
                ), None)
            if call is not None:
                call["status"] = "TIMED_OUT"
                call["error_code"] = "PROVIDER_TIMEOUT"

    def close(self, reason, *, provider_name=None):
        """Close the case gate for a resource threshold or another harness stop."""
        with self._lock:
            self._latch_locked(reason, provider_name)

    def _latch_locked(self, reason, provider_name):
        if self._closed:
            return
        self._closed = True
        self._close_reason = reason
        self._timed_out_provider = provider_name
        for request in reversed(self._sent):
            if request["provider"] == provider_name and request["response_completed_at"] is None:
                request["error_code"] = "PROVIDER_TIMEOUT"
                request["server_completion_known"] = False
                break

    def _record_blocked_call(self, provider_name, reason):
        self._blocked.append({
            "provider": provider_name,
            "method": None,
            "route": None,
            "reason": reason,
            "blocked_at": _now(),
        })

    def _suppression_code_locked(self, provider_name):
        if self._close_reason in {"PROVIDER_TIMEOUT", "CALL_DEADLINE_EXCEEDED"}:
            if provider_name == self._timed_out_provider:
                return "PROVIDER_TIMEOUT"
            return "PROVIDER_CALL_SUPPRESSED"
        return self._close_reason or "PROVIDER_CALL_SUPPRESSED"

    def _raise_closed_locked(self, provider_name):
        code = self._suppression_code_locked(provider_name)
        if code == "PROVIDER_TIMEOUT":
            raise ProviderTimeout()
        raise ProviderNonRetryableError(
            "The synthetic pipeline request gate is closed; no provider request was sent.",
            code=code,
        )

    def admit(self, request):
        with self._lock:
            self._expire_active_call_locked()
            provider_name = (
                self._active_call["provider"] if self._active_call is not None else "UNKNOWN"
            )
            route = request.url.path
            reason = None
            if self._closed:
                reason = self._suppression_code_locked(provider_name)
            elif self._active_call is None:
                reason = "REQUEST_OUTSIDE_PROVIDER_CALL"
                self._latch_locked(reason, provider_name)
            elif (request.url.scheme != "http"
                  or request.url.host != "127.0.0.1"
                  or request.url.port != 11434
                  or request.url.username or request.url.password
                  or request.url.query or request.url.fragment):
                reason = "REQUEST_ORIGIN_NOT_ALLOWED"
                self._latch_locked(reason, provider_name)
            elif not self._allowed_route(request.method, route):
                reason = "REQUEST_ROUTE_NOT_ALLOWED"
                self._latch_locked(reason, provider_name)
            elif len(self._sent) >= self.max_requests:
                reason = "REQUEST_BUDGET_EXHAUSTED"
                self._latch_locked(reason, provider_name)
            elif request.method.upper() == "POST" and self._post_count_locked() >= self.max_inference_posts:
                reason = "INFERENCE_BUDGET_EXHAUSTED"
                self._latch_locked(reason, provider_name)

            if reason is not None:
                self._blocked.append({
                    "provider": provider_name,
                    "method": request.method.upper(),
                    "route": route,
                    "reason": reason,
                    "blocked_at": _now(),
                })
                self._raise_closed_locked(provider_name)

            request_id = self._next_request_id
            self._next_request_id += 1
            record = {
                "request_id": request_id,
                "provider": provider_name,
                "method": request.method.upper(),
                "route": route,
                "sent_at": _now(),
                "response_status": None,
                "response_headers_at": None,
                "response_completed_at": None,
                "server_completion_known": False,
                "error_code": None,
            }
            self._sent.append(record)
            return request_id

    @staticmethod
    def _allowed_route(method, route):
        method = method.upper()
        return (
            method == "GET" and route == "/api/tags"
        ) or (
            method == "POST" and route == "/v1/chat/completions"
        )

    def note_response_headers(self, request_id, status_code):
        with self._lock:
            record = self._request_record(request_id)
            record["response_status"] = status_code
            record["response_headers_at"] = _now()

    def note_response_complete(self, request_id):
        with self._lock:
            record = self._request_record(request_id)
            record["response_completed_at"] = _now()
            record["server_completion_known"] = True

    def note_request_error(self, request_id, error_code):
        with self._lock:
            record = self._request_record(request_id)
            record["error_code"] = error_code

    def _request_record(self, request_id):
        return next(item for item in self._sent if item["request_id"] == request_id)

    def _post_count_locked(self):
        return sum(item["method"] == "POST" for item in self._sent)

    def snapshot(self):
        with self._lock:
            self._expire_active_call_locked()
            return {
                "max_requests": self.max_requests,
                "max_inference_posts": self.max_inference_posts,
                "request_count": len(self._sent),
                "inference_post_count": self._post_count_locked(),
                "closed": self._closed,
                "close_reason": self._close_reason,
                "timed_out_provider": self._timed_out_provider,
                "provider_calls": [dict(item) for item in self._calls],
                "sent_requests": [dict(item) for item in self._sent],
                "blocked_requests": [dict(item) for item in self._blocked],
            }


class _ObservedResponseStream(httpx.SyncByteStream):
    def __init__(self, inner, gate, request_id):
        self._inner = inner
        self._gate = gate
        self._request_id = request_id

    def __iter__(self):
        try:
            yield from self._inner
        except httpx.TimeoutException:
            self._gate.note_request_error(self._request_id, "PROVIDER_TIMEOUT")
            raise
        except Exception:
            self._gate.note_request_error(self._request_id, "PROVIDER_ERROR")
            raise
        else:
            self._gate.note_response_complete(self._request_id)

    def close(self):
        self._inner.close()


class RequestBudgetTransport(httpx.BaseTransport):
    """Count only the approved local Ollama inventory and inference routes."""

    def __init__(self, gate, *, inner=None):
        self.gate = gate
        self.inner = inner or httpx.HTTPTransport()

    def handle_request(self, request):
        request_id = self.gate.admit(request)
        try:
            response = self.inner.handle_request(request)
        except httpx.TimeoutException:
            self.gate.note_request_error(request_id, "PROVIDER_TIMEOUT")
            raise
        except Exception:
            self.gate.note_request_error(request_id, "PROVIDER_ERROR")
            raise

        self.gate.note_response_headers(request_id, response.status_code)
        if response.is_stream_consumed:
            self.gate.note_response_complete(request_id)
        else:
            response.stream = _ObservedResponseStream(response.stream, self.gate, request_id)
        return response

    def close(self):
        self.inner.close()


class GatedVisualProvider:
    """Apply the harness deadline to the source VLM adapter without editing it."""

    def __init__(self, provider, gate, *, deadline_seconds=20):
        self.delegate = provider
        self.gate = gate
        self.timeout_seconds = getattr(provider, "timeout_seconds", 10)
        self.call_deadline_seconds = deadline_seconds

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def analyze_image(self, request):
        with self.gate.provider_call("VLM", timeout_seconds=self.call_deadline_seconds):
            return self.delegate.analyze_image(request)


class GatedTaskProvider:
    """Apply the harness deadline to one source Media or Strategy adapter."""

    def __init__(self, provider, gate, *, provider_name, timeout_seconds=20):
        if provider_name not in {"MEDIA", "STRATEGY"}:
            raise ValueError("Task provider name must be MEDIA or STRATEGY")
        self.delegate = provider
        self.gate = gate
        self.provider_name = provider_name
        self.timeout_seconds = timeout_seconds

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def evaluate(self, request):
        with self.gate.provider_call(
            self.provider_name, timeout_seconds=self.timeout_seconds
        ):
            return self.delegate.evaluate(request)


class HarnessAuthenticatedEvaluationOrchestrator(AuthenticatedEvaluationOrchestrator):
    """Latch the request gate when the source orchestrator times out a task future."""

    def __init__(self, *args, request_gate, **kwargs):
        super().__init__(*args, **kwargs)
        self._request_gate = request_gate

    def _run_step(self, task, *step_args, **step_kwargs):
        result = super()._run_step(task, *step_args, **step_kwargs)
        if result.get("status") == "TIMED_OUT":
            provider_name = "MEDIA" if task == "MEDIA_COMPLIANCE" else "STRATEGY"
            reason = result.get("error_code") or "PROVIDER_TIMEOUT"
            if reason in {"PROVIDER_TIMEOUT", "PIPELINE_TIMEOUT"}:
                self._request_gate.latch_timeout(provider_name, reason)
        return result

VLM_MODEL_ID = "qwen3-vl:4b"
VLM_MODEL_VERSION = "sha256:e8503d318d8df6622abc18a317c0e5eee044821322c87a16a6acddd62984da84"
TASK_MODEL_ID = "organizationai-qwen3:4b-ctx8192"
TASK_MODEL_VERSION = "sha256:b2ef2f414e31e4e10ef46366751464631a5fa4b5c1bf183b1e3b9076ab2116ef"
OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"
CALL_DEADLINE_SECONDS = 20
VLM_HTTP_TIMEOUT_SECONDS = 18
MAX_OUTPUT_TOKENS = 1536
MAX_RESPONSE_BYTES = 262_144
MAX_INPUT_BYTES = 1_048_576


def build_harness_orchestrator(gate, *, inner_transport=None):
    """Create a client that always routes through this case's request gate."""
    if not isinstance(gate, RequestGate):
        raise TypeError("A RequestGate instance is required for the synthetic harness")
    if inner_transport is not None and not isinstance(inner_transport, httpx.BaseTransport):
        raise TypeError("inner_transport must be an HTTPX BaseTransport")

    from src.ai_pipeline.providers.openai_provider import LocalVLMProvider
    from src.ai_pipeline.task_evaluation import (
        MEDIA_PROMPT_VERSION,
        MEDIA_SCHEMA_VERSION,
        STRATEGY_PROMPT_VERSION,
        STRATEGY_SCHEMA_VERSION,
    )
    from src.ai_pipeline.task_providers import (
        OpenAICompatibleTaskProvider,
        SUPPORTED_PROTOCOL,
        TaskModelSettings,
    )
    from src.ai_pipeline.providers.ollama_identity import OLLAMA_TAG_DIGEST

    client = httpx.Client(
        transport=RequestBudgetTransport(gate, inner=inner_transport),
        timeout=CALL_DEADLINE_SECONDS,
    )
    try:
        visual_source = LocalVLMProvider(
            model=VLM_MODEL_ID,
            model_version=VLM_MODEL_VERSION,
            base_url=OLLAMA_BASE_URL,
            api_key="",
            timeout_seconds=VLM_HTTP_TIMEOUT_SECONDS,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            max_response_bytes=MAX_RESPONSE_BYTES,
            max_input_bytes=MAX_INPUT_BYTES,
            allow_remote=False,
            identity_mode=OLLAMA_TAG_DIGEST,
            client=client,
        )
        media_settings = TaskModelSettings(
            task="MEDIA_COMPLIANCE",
            provider=SUPPORTED_PROTOCOL,
            base_url=OLLAMA_BASE_URL,
            model_id=TASK_MODEL_ID,
            model_version=TASK_MODEL_VERSION,
            api_key="",
            allow_remote=False,
            timeout_seconds=CALL_DEADLINE_SECONDS,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            max_response_bytes=MAX_RESPONSE_BYTES,
            max_input_bytes=MAX_INPUT_BYTES,
            max_retries=0,
            prompt_version=MEDIA_PROMPT_VERSION,
            schema_version=MEDIA_SCHEMA_VERSION,
            identity_mode=OLLAMA_TAG_DIGEST,
        )
        strategy_settings = TaskModelSettings(
            task="STRATEGY_EVALUATION",
            provider=SUPPORTED_PROTOCOL,
            base_url=OLLAMA_BASE_URL,
            model_id=TASK_MODEL_ID,
            model_version=TASK_MODEL_VERSION,
            api_key="",
            allow_remote=False,
            timeout_seconds=CALL_DEADLINE_SECONDS,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            max_response_bytes=MAX_RESPONSE_BYTES,
            max_input_bytes=MAX_INPUT_BYTES,
            max_retries=0,
            prompt_version=STRATEGY_PROMPT_VERSION,
            schema_version=STRATEGY_SCHEMA_VERSION,
            identity_mode=OLLAMA_TAG_DIGEST,
        )
        media_source = OpenAICompatibleTaskProvider(media_settings, client=client)
        strategy_source = OpenAICompatibleTaskProvider(strategy_settings, client=client)
        visual = GatedVisualProvider(
            visual_source, gate, deadline_seconds=CALL_DEADLINE_SECONDS
        )
        media = GatedTaskProvider(
            media_source, gate, provider_name="MEDIA",
            timeout_seconds=CALL_DEADLINE_SECONDS,
        )
        strategy = GatedTaskProvider(
            strategy_source, gate, provider_name="STRATEGY",
            timeout_seconds=CALL_DEADLINE_SECONDS,
        )
        orchestrator = HarnessAuthenticatedEvaluationOrchestrator(
            visual,
            media_provider=media,
            strategy_provider=strategy,
            timeout_seconds=100,
            visual_max_retries=0,
            request_gate=gate,
        )
    except Exception:
        client.close()
        raise
    return orchestrator, {
        "visual": visual,
        "media": media,
        "strategy": strategy,
        "media_settings": media_settings,
        "strategy_settings": strategy_settings,
        "client": client,
    }
