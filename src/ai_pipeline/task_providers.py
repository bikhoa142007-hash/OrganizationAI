"""Isolated, secret-safe model adapters for Media Compliance and Strategy Evaluation."""

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json
import os
from typing import Any, Literal, Mapping

import httpx

from src.ai_pipeline.providers.base import (
    ProviderAnalysis,
    ProviderConfigurationError,
    ProviderError,
    ProviderNonRetryableError,
    ProviderTimeout,
)
from src.ai_pipeline.task_evaluation import (
    MEDIA_OUTPUT_SCHEMA,
    MEDIA_PROMPT_VERSION,
    MEDIA_SCHEMA_VERSION,
    STRATEGY_OUTPUT_SCHEMA,
    STRATEGY_PROMPT_VERSION,
    STRATEGY_SCHEMA_VERSION,
    task_messages,
)
from src.shared.validation import canonical_hash


SUPPORTED_PROTOCOL = "OPENAI_COMPATIBLE_CHAT_COMPLETIONS"
TaskName = Literal["MEDIA_COMPLIANCE", "STRATEGY_EVALUATION"]


@dataclass(frozen=True)
class TaskModelSettings:
    task: TaskName
    provider: str | None
    base_url: str
    model_id: str
    model_version: str
    api_key: str = field(default="", repr=False, compare=False)
    reasoning_effort: str | None = None
    allow_remote: bool = False
    timeout_seconds: int = 20
    max_output_tokens: int = 2048
    max_response_bytes: int = 262_144
    max_input_bytes: int = 1_048_576
    max_retries: int = 1
    prompt_version: str = ""
    schema_version: str = ""
    configuration_error: str | None = None

    @classmethod
    def from_environment(cls, task: TaskName, environ=None):
        environ = os.environ if environ is None else environ
        prefix = "AUTH_WORKFLOW_MEDIA" if task == "MEDIA_COMPLIANCE" else "AUTH_WORKFLOW_STRATEGY"
        expected_prompt, expected_schema = _versions(task)
        provider = _optional(environ.get(prefix + "_PROVIDER"))
        base_url = _optional(environ.get(prefix + "_BASE_URL")) or ""
        model_id = _optional(environ.get(prefix + "_MODEL")) or ""
        model_version = _optional(environ.get(prefix + "_MODEL_VERSION")) or ""
        api_key = environ.get(prefix + "_API_KEY", "")
        reasoning_effort = _optional(environ.get(prefix + "_REASONING_EFFORT"))
        if reasoning_effort is not None:
            reasoning_effort = reasoning_effort.lower()
        reasoning_invalid = reasoning_effort not in {None, "none", "low", "medium", "high", "max"}
        if reasoning_invalid:
            reasoning_effort = None
        prompt_version = _optional(environ.get(prefix + "_PROMPT_VERSION")) or expected_prompt
        schema_version = _optional(environ.get(prefix + "_SCHEMA_VERSION")) or expected_schema
        allow_remote, remote_invalid = _boolean(environ.get(prefix + "_ALLOW_REMOTE"), default=False)
        error = None
        defaults = {
            "timeout_seconds": 20,
            "max_output_tokens": 2048,
            "max_response_bytes": 262_144,
            "max_input_bytes": 1_048_576,
            "max_retries": 1,
        }
        bounds = {
            "timeout_seconds": (1, 45),
            "max_output_tokens": (128, 8192),
            "max_response_bytes": (1024, 1_048_576),
            "max_input_bytes": (1024, 2_097_152),
            "max_retries": (0, 2),
        }
        try:
            parsed = {
                key: _bounded_int(environ, prefix + "_" + key.upper(), default, *bounds[key])
                for key, default in defaults.items()
            }
        except ValueError:
            # Malformed optional provider settings must route this task to review,
            # not prevent the authenticated workflow API from starting.
            error = "INVALID_PROVIDER_CONFIGURATION"
            parsed = defaults
        if reasoning_invalid:
            error = "INVALID_PROVIDER_CONFIGURATION"
        elif provider and provider != SUPPORTED_PROTOCOL:
            error = "UNSUPPORTED_PROVIDER_PROTOCOL"
        elif provider and prompt_version != expected_prompt:
            error = "UNSUPPORTED_PROMPT_VERSION"
        elif provider and schema_version != expected_schema:
            error = "UNSUPPORTED_SCHEMA_VERSION"
        elif remote_invalid:
            error = "INVALID_PROVIDER_CONFIGURATION"
        elif provider and model_id and model_version and base_url:
            from src.ai_pipeline.providers.openai_provider import _validate_base_url
            error = _validate_base_url(base_url, allow_remote=allow_remote)
            if not error and (len(model_id) > 160 or len(model_version) > 160 or len(base_url) > 512):
                error = "INVALID_PROVIDER_CONFIGURATION"
        return cls(
            task=task,
            provider=provider,
            base_url=base_url.rstrip("/"),
            model_id=model_id,
            model_version=model_version,
            api_key=api_key,
            reasoning_effort=reasoning_effort,
            allow_remote=allow_remote,
            prompt_version=prompt_version,
            schema_version=schema_version,
            configuration_error=error,
            **parsed,
        )

    @property
    def is_configured(self):
        return bool(
            self.provider == SUPPORTED_PROTOCOL and self.base_url and self.model_id
            and self.model_version and not self.configuration_error
        )

    def public_snapshot(self):
        """Describe a pinned task model without persisting credentials or raw endpoints."""
        safe = {
            "task": self.task,
            "provider": self.provider,
            "model_id": self.model_id or None,
            "model_version": self.model_version or None,
            "reasoning_effort": self.reasoning_effort,
            "endpoint_fingerprint": hashlib.sha256(self.base_url.encode("utf-8")).hexdigest()
            if self.base_url else None,
            "timeout_seconds": self.timeout_seconds,
            "max_output_tokens": self.max_output_tokens,
            "max_response_bytes": self.max_response_bytes,
            "max_input_bytes": self.max_input_bytes,
            "max_retries": self.max_retries,
            "prompt_version": self.prompt_version,
            "schema_version": self.schema_version,
            "configuration_error": self.configuration_error,
        }
        return {**safe, "configuration_hash": canonical_hash(safe)}


@dataclass(frozen=True)
class TaskEvaluationRequest:
    task: TaskName
    input_hash: str
    plan_payload: Mapping[str, Any]
    evidence: list[dict[str, Any]]
    policy: Any = None
    rubric: Any = None


class OpenAICompatibleTaskProvider:
    """A text-only Chat Completions adapter; compatibility must be verified per runtime."""

    def __init__(self, settings: TaskModelSettings, *, client=None):
        self.settings = settings
        self._client = client

    def get_model_metadata(self):
        return {
            "provider": self.settings.provider,
            "model_id": self.settings.model_id or None,
            "model_version": self.settings.model_version or None,
            "protocol": SUPPORTED_PROTOCOL,
        }

    def evaluate(self, request: TaskEvaluationRequest) -> ProviderAnalysis:
        settings = self.settings
        if request.task != settings.task:
            raise ProviderConfigurationError(code="TASK_PROVIDER_MISMATCH")
        if settings.configuration_error:
            raise ProviderConfigurationError(code=settings.configuration_error)
        if not settings.is_configured:
            raise ProviderConfigurationError()
        try:
            messages = task_messages(
                request.task, request.plan_payload, request.evidence,
                policy=request.policy, rubric=request.rubric,
            )
        except (TypeError, ValueError):
            raise ProviderNonRetryableError("Task input was invalid.", code="INVALID_TASK_INPUT") from None
        input_bytes = sum(len(item["content"].encode("utf-8")) for item in messages)
        if input_bytes > settings.max_input_bytes:
            raise ProviderNonRetryableError("Task input exceeds the configured limit.", code="INPUT_TOO_LARGE")
        schema_name, schema = _schema_for(request)
        body = {
            "model": settings.model_id,
            "messages": messages,
            "temperature": 0,
            "max_tokens": settings.max_output_tokens,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
        }
        if settings.reasoning_effort is not None:
            body["reasoning_effort"] = settings.reasoning_effort
        response_bytes = self._post(body)
        try:
            response = json.loads(response_bytes)
            reported_model_id = response["model"]
            choice = response["choices"][0]
            finish_reason = choice["finish_reason"]
            message = choice["message"]
            if finish_reason == "length":
                raise ProviderNonRetryableError("Provider output was truncated.", code="TRUNCATED_OUTPUT")
            if finish_reason != "stop" or message.get("refusal"):
                raise ProviderNonRetryableError("Provider did not return a usable evaluation.", code="PROVIDER_REFUSAL")
            content = message["content"]
            if not isinstance(content, str):
                raise ValueError("Output content is not text")
            output = json.loads(content)
        except ProviderNonRetryableError:
            raise
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
            raise ProviderNonRetryableError(
                "Provider returned an invalid response.", code="INVALID_PROVIDER_RESPONSE"
            ) from None
        if reported_model_id != settings.model_id:
            raise ProviderNonRetryableError("Provider model identity did not match the pinned model.", code="UNKNOWN_MODEL")
        if not isinstance(output, dict):
            raise ProviderNonRetryableError("Provider output must be a JSON object.", code="INVALID_SCHEMA")
        return ProviderAnalysis(
            output=output,
            raw_output_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            model_revision=settings.model_version,
            reported_model_id=_safe_model_id(reported_model_id),
        )

    @contextmanager
    def _client_context(self):
        if self._client is not None:
            yield self._client
        else:
            with httpx.Client(timeout=self.settings.timeout_seconds) as client:
                yield client

    def _post(self, body):
        raw = bytearray()
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.settings.api_key.strip():
            headers["Authorization"] = "Bearer " + self.settings.api_key.strip()
        try:
            with self._client_context() as client:
                with client.stream(
                    "POST", self.settings.base_url + "/chat/completions",
                    headers=headers, json=body, timeout=self.settings.timeout_seconds,
                ) as response:
                    if response.status_code >= 400:
                        code = _status_error_code(response.status_code)
                        if code in {"AUTHENTICATION_FAILED", "REQUEST_UNSUPPORTED", "STRUCTURED_OUTPUT_UNSUPPORTED"}:
                            raise ProviderNonRetryableError(
                                "Configured task provider rejected the request.", code=code
                            )
                        raise ProviderError("Task provider request failed.", code=code)
                    for chunk in response.iter_bytes(chunk_size=64 * 1024):
                        if len(raw) + len(chunk) > self.settings.max_response_bytes:
                            raise ProviderNonRetryableError(
                                "Provider response exceeded the configured limit.", code="RESOURCE_EXHAUSTED"
                            )
                        raw.extend(chunk)
        except ProviderError:
            raise
        except httpx.TimeoutException:
            raise ProviderTimeout() from None
        except httpx.ConnectError:
            raise ProviderError("Configured task provider is unavailable.", code="PROVIDER_UNAVAILABLE") from None
        except httpx.HTTPError:
            raise ProviderError("Task provider request failed.", code="PROVIDER_ERROR") from None
        return bytes(raw)


def _versions(task):
    if task == "MEDIA_COMPLIANCE":
        return MEDIA_PROMPT_VERSION, MEDIA_SCHEMA_VERSION
    return STRATEGY_PROMPT_VERSION, STRATEGY_SCHEMA_VERSION


def _schema_for(request):
    """Constrain identifiers to this immutable evaluation input snapshot."""
    if request.task == "MEDIA_COMPLIANCE":
        name, source = "media_compliance", MEDIA_OUTPUT_SCHEMA
    else:
        name, source = "strategy_feasibility", STRATEGY_OUTPUT_SCHEMA
    schema = deepcopy(source)

    def set_enum(node, values):
        if values:
            node["enum"] = values

    evidence_ids = _unique_text_values(
        item.get("evidence_id") for item in request.evidence if isinstance(item, Mapping)
    )
    if request.task == "MEDIA_COMPLIANCE":
        if request.policy is not None:
            properties = schema["properties"]
            set_enum(properties["policy_id"], [request.policy.policy_id])
            set_enum(properties["policy_version"], [request.policy.policy_version])
            rule_ids = [rule.rule_id for rule in request.policy.rules]
            set_enum(properties["rule_results"]["items"]["properties"]["rule_id"], rule_ids)
            set_enum(properties["findings"]["items"]["properties"]["rule_id"], rule_ids)
        for key in ("rule_results", "findings", "evidence_conflicts"):
            refs = schema["properties"][key]["items"]["properties"]["evidence_refs"]
            set_enum(refs["items"], evidence_ids)
    elif request.rubric is not None:
        properties = schema["properties"]
        set_enum(properties["rubric_id"], [request.rubric.rubric_id])
        set_enum(properties["rubric_version"], [request.rubric.rubric_version])
        criterion_ids = [criterion.criterion_id for criterion in request.rubric.criteria]
        set_enum(
            properties["criterion_scores"]["items"]["properties"]["criterion_id"],
            criterion_ids,
        )
        for key in ("criterion_scores", "evidence_conflicts"):
            refs = schema["properties"][key]["items"]["properties"]["evidence_refs"]
            set_enum(refs["items"], evidence_ids)
    return name, schema


def _unique_text_values(values):
    return list(dict.fromkeys(
        value for value in values if isinstance(value, str) and value.strip()
    ))


def _bounded_int(environ, name, default, minimum, maximum):
    value = environ.get(name)
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer.") from None
    if not minimum <= parsed <= maximum:
        raise ValueError(f"{name} is outside its allowed range.")
    return parsed


def _boolean(value, *, default):
    if value is None or value == "":
        return default, False
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True, False
    if normalized in {"false", "0", "no", "off"}:
        return False, False
    return default, True


def _optional(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


def _safe_model_id(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 160:
        return None
    if any(ord(char) < 32 for char in value):
        return None
    return value.strip()


def _status_error_code(status_code):
    return {
        401: "AUTHENTICATION_FAILED",
        403: "AUTHENTICATION_FAILED",
        404: "MODEL_NOT_FOUND",
        413: "RESOURCE_EXHAUSTED",
        429: "RATE_LIMITED",
    }.get(status_code, "REQUEST_UNSUPPORTED" if 400 <= status_code < 500 else "PROVIDER_ERROR")
