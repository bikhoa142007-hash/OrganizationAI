"""Opt-in provider adapters for external and local inference runtimes."""

import base64
import hashlib
import ipaddress
import json
import os
from contextlib import contextmanager
from collections.abc import Mapping

import httpx

from .base import (
    ProviderAnalysis,
    ProviderConfigurationError,
    ProviderError,
    ProviderNonRetryableError,
    ProviderTimeout,
    VisualModelProvider,
)
from src.ai_pipeline.vlm_extraction import (
    OUTPUT_JSON_SCHEMA,
    SYSTEM_PROMPT,
    USER_PROMPT,
    verified_images,
)


class OpenAIProvider(VisualModelProvider):
    def __init__(self, *, api_key=None, model=None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model_version = model or os.getenv("OPENAI_MODEL")
        if not self.api_key or not self.model_version:
            raise ProviderError("OpenAI provider is not configured")

    def health_check(self):
        return bool(self.api_key and self.model_version)

    def get_model_metadata(self):
        return {"provider": "LOCAL_VLM", "model_version": self.model_version}

    def analyze_image(self, request):
        raise ProviderError("External provider execution is disabled without approved transport")


class LocalVLMProvider(VisualModelProvider):
    """Local OpenAI-compatible transport; this provider extracts image evidence only."""

    output_kind = "VISUAL_EXTRACTION"

    def __init__(
        self,
        *,
        model=None,
        base_url=None,
        api_key=None,
        timeout_seconds=None,
        max_output_tokens=None,
        max_response_bytes=None,
        max_input_bytes=None,
        allow_remote=None,
        client=None,
    ):
        self.model_id = (model if model is not None else os.getenv("LOCAL_VLM_MODEL", "")).strip()
        self.base_url = (base_url if base_url is not None else os.getenv("LOCAL_VLM_BASE_URL", "")).strip().rstrip("/")
        self.api_key = api_key if api_key is not None else os.getenv("LOCAL_VLM_API_KEY", "")
        self.timeout_seconds = _bounded_setting(
            timeout_seconds, "LOCAL_VLM_TIMEOUT_SECONDS", 30, 1, 45
        )
        self.max_output_tokens = _bounded_setting(
            max_output_tokens, "LOCAL_VLM_MAX_OUTPUT_TOKENS", 1536, 128, 4096
        )
        self.max_response_bytes = _bounded_setting(
            max_response_bytes, "LOCAL_VLM_MAX_RESPONSE_BYTES", 262_144, 1_024, 1_048_576
        )
        self.max_input_bytes = _bounded_setting(
            max_input_bytes, "LOCAL_VLM_MAX_INPUT_BYTES", 20_971_520, 1_024, 104_857_600
        )
        self.allow_remote, invalid_remote_setting = _boolean_setting(
            allow_remote, "LOCAL_VLM_ALLOW_REMOTE", default=False
        )
        self._client = client
        setting_specs = (
            (timeout_seconds, "LOCAL_VLM_TIMEOUT_SECONDS", 1, 45),
            (max_output_tokens, "LOCAL_VLM_MAX_OUTPUT_TOKENS", 128, 4096),
            (max_response_bytes, "LOCAL_VLM_MAX_RESPONSE_BYTES", 1_024, 1_048_576),
            (max_input_bytes, "LOCAL_VLM_MAX_INPUT_BYTES", 1_024, 104_857_600),
        )
        invalid_setting = any(not _setting_is_valid(*spec) for spec in setting_specs)
        self.configuration_error = _validate_base_url(
            self.base_url, allow_remote=self.allow_remote
        ) or (
            "INVALID_PROVIDER_CONFIGURATION" if invalid_setting else None
        ) or (
            "INVALID_PROVIDER_CONFIGURATION" if invalid_remote_setting else None
        )

    def health_check(self):
        if self.configuration_error or not self.model_id or not self.base_url:
            return False
        try:
            with self._client_context() as client:
                response = client.get(
                    f"{self.base_url}/models",
                    headers=self._headers(),
                    timeout=self.timeout_seconds,
                )
            return 200 <= response.status_code < 300
        except (httpx.HTTPError, ValueError):
            return False

    def get_model_metadata(self):
        # The configured model ID is not an immutable runtime/model revision.
        return {
            "provider": "LOCAL_VLM",
            "model_id": self.model_id or None,
            "runtime_protocol": "OPENAI_COMPATIBLE_CHAT_COMPLETIONS",
            "model_version": None,
        }

    def analyze_image(self, request):
        if self.configuration_error:
            raise ProviderConfigurationError(code=self.configuration_error)
        if not self.base_url or not self.model_id:
            raise ProviderConfigurationError()
        snapshotted_model_id = request.metadata.get("model_id")
        if "model_id" in request.metadata and snapshotted_model_id != self.model_id:
            raise ProviderConfigurationError(
                "The configured model changed after submission.",
                code="MODEL_CONFIGURATION_CHANGED",
            )

        images = verified_images(request)
        input_bytes = sum(len(image["content"]) for image in images)
        if input_bytes > self.max_input_bytes:
            raise ProviderNonRetryableError(
                "Image input exceeds the configured extraction limit.", code="INPUT_TOO_LARGE"
            )

        message_content = [{"type": "text", "text": USER_PROMPT}]
        for index, image in enumerate(images):
            data_url = "data:" + image["media_type"] + ";base64," + base64.b64encode(
                image["content"]
            ).decode("ascii")
            message_content.append({"type": "text", "text": f"Image index: {index}"})
            message_content.append({
                "type": "image_url",
                "image_url": {"url": data_url, "detail": "high"},
            })

        body = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message_content},
            ],
            "temperature": 0,
            "max_tokens": self.max_output_tokens,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "visual_extraction",
                    "strict": True,
                    "schema": OUTPUT_JSON_SCHEMA,
                },
            },
        }
        try:
            response_bytes = self._post_chat_completion(body)
        except ProviderError:
            raise
        try:
            response = json.loads(response_bytes)
            choice = response["choices"][0]
            finish_reason = choice["finish_reason"]
            if finish_reason == "length":
                raise ProviderNonRetryableError(
                    "Provider output was truncated.", code="TRUNCATED_OUTPUT"
                )
            if finish_reason != "stop":
                raise ValueError("provider response did not finish normally")
            content = choice["message"]["content"]
            if not isinstance(content, str):
                raise ValueError("message content is not text")
            output = json.loads(content)
        except ProviderNonRetryableError:
            raise
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
            raise ProviderNonRetryableError(
                "Provider returned an invalid response.", code="INVALID_PROVIDER_RESPONSE"
            ) from None
        if not isinstance(output, Mapping):
            raise ProviderNonRetryableError(
                "Provider returned an invalid response.", code="INVALID_SCHEMA"
            )

        return ProviderAnalysis(
            output=output,
            raw_output_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            model_revision=_optional_metadata(response.get("system_fingerprint")),
            reported_model_id=_optional_metadata(response.get("model")),
        )

    @contextmanager
    def _client_context(self):
        if self._client is not None:
            yield self._client
        else:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                yield client

    def _headers(self):
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.api_key and self.api_key.strip():
            headers["Authorization"] = "Bearer " + self.api_key.strip()
        return headers

    def _post_chat_completion(self, body):
        endpoint = f"{self.base_url}/chat/completions"
        raw = bytearray()
        try:
            with self._client_context() as client:
                with client.stream(
                    "POST", endpoint, headers=self._headers(), json=body,
                    timeout=self.timeout_seconds,
                ) as response:
                    if response.status_code >= 400:
                        code = _status_error_code(response.status_code, _error_hint(response))
                        # Never persist or return provider response text; it can contain secrets.
                        raise _provider_http_error(code)
                    for chunk in response.iter_bytes(chunk_size=64 * 1024):
                        if len(raw) + len(chunk) > self.max_response_bytes:
                            raise ProviderNonRetryableError(
                                "Provider response exceeded the configured limit.",
                                code="RESOURCE_EXHAUSTED",
                            )
                        raw.extend(chunk)
        except ProviderError:
            raise
        except httpx.TimeoutException:
            raise ProviderTimeout() from None
        except httpx.ConnectError:
            raise ProviderError("Local inference endpoint is unavailable.", code="PROVIDER_UNAVAILABLE") from None
        except httpx.HTTPError:
            raise ProviderError("Local inference request failed.", code="PROVIDER_ERROR") from None
        return bytes(raw)


def _bounded_setting(value, name, default, minimum, maximum):
    raw = value if value is not None else os.getenv(name, str(default))
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return default
    return parsed if minimum <= parsed <= maximum else default


def _setting_is_valid(value, name, minimum, maximum):
    raw = value if value is not None else os.getenv(name)
    if raw is None or raw == "":
        return True
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return False
    return minimum <= parsed <= maximum


def _boolean_setting(value, name, *, default):
    raw = value if value is not None else os.getenv(name)
    if raw is None or raw == "":
        return default, False
    if isinstance(raw, bool):
        return raw, False
    normalized = str(raw).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True, False
    if normalized in {"0", "false", "no", "off"}:
        return False, False
    return default, True


def _validate_base_url(base_url, *, allow_remote=False):
    if not base_url:
        return None
    try:
        url = httpx.URL(base_url)
    except (TypeError, ValueError):
        return "INVALID_PROVIDER_CONFIGURATION"
    if (
        url.scheme not in {"http", "https"}
        or not url.host
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        return "INVALID_PROVIDER_CONFIGURATION"
    hostname = url.host.strip("[]").lower().rstrip(".")
    local_hostname = (
        hostname == "localhost"
        or hostname.endswith(".localhost")
        or hostname == "host.docker.internal"
    )
    try:
        local_hostname = local_hostname or ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        pass
    if not local_hostname and (not allow_remote or url.scheme != "https"):
        return "INVALID_PROVIDER_CONFIGURATION"
    return None


def _status_error_code(status_code, hint=""):
    if status_code == 404:
        return "MODEL_NOT_FOUND"
    if status_code in {413, 507}:
        return "RESOURCE_EXHAUSTED"
    if status_code == 429:
        return "RATE_LIMITED"
    if status_code == 400:
        if "model" in hint and "not found" in hint:
            return "MODEL_NOT_FOUND"
        if "image" in hint or "vision" in hint:
            return "IMAGE_UNSUPPORTED"
        if "json_schema" in hint or "response_format" in hint or "structured output" in hint:
            return "STRUCTURED_OUTPUT_UNSUPPORTED"
        return "REQUEST_UNSUPPORTED"
    return "PROVIDER_ERROR"


def _provider_http_error(code):
    if code in {
        "MODEL_NOT_FOUND", "RESOURCE_EXHAUSTED", "REQUEST_UNSUPPORTED",
        "IMAGE_UNSUPPORTED", "STRUCTURED_OUTPUT_UNSUPPORTED",
    }:
        message = "Configured model or request is not supported by the inference runtime."
        return ProviderNonRetryableError(message, code=code)
    return ProviderError("Local inference request failed.", code=code)


def _error_hint(response):
    """Read a tiny transient prefix only to categorize 4xx errors; never persist it."""
    chunks = []
    size = 0
    try:
        for chunk in response.iter_bytes(chunk_size=1024):
            remaining = 4096 - size
            chunks.append(chunk[:remaining])
            size += min(remaining, len(chunk))
            if size >= 4096:
                break
    except httpx.HTTPError:
        return ""
    return b"".join(chunks).decode("utf-8", errors="ignore").lower()


def _optional_metadata(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > 160 or any(ord(char) < 32 for char in value):
        return None
    return value
