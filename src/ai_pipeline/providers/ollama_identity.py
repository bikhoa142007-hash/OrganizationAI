"""Verify SHA-256 model pins against the local Ollama inventory."""

import re

import httpx

from .base import ProviderError, ProviderNonRetryableError, ProviderTimeout


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_INVENTORY_BYTES = 1_048_576
OLLAMA_TAG_DIGEST = "OLLAMA_TAG_DIGEST"
GENERIC_OPAQUE_REVISION = "GENERIC_OPAQUE_REVISION"
IDENTITY_MODES = frozenset({OLLAMA_TAG_DIGEST, GENERIC_OPAQUE_REVISION})


def resolve_identity_mode(identity_mode, model_version):
    """Infer legacy digest pins as Ollama; otherwise use opaque provider identity."""
    if identity_mode is not None:
        return identity_mode
    return OLLAMA_TAG_DIGEST if (
        isinstance(model_version, str) and model_version.lower().startswith("sha256:")
    ) else GENERIC_OPAQUE_REVISION


def is_sha256_pin(value):
    return isinstance(value, str) and value.lower().startswith("sha256:") and bool(
        _SHA256.fullmatch(value[7:].lower())
    )


def verify_ollama_model_digest(
    client,
    *,
    base_url: str,
    model_id: str,
    expected_version: str | None,
    timeout_seconds: float,
    headers: dict[str, str] | None = None,
) -> str | None:
    """Return a locally observed digest, or fail before inference when a SHA pin is wrong.

    Opaque model revisions remain supported for compatible runtimes. A sha256 pin is
    treated as a content identity and therefore requires Ollama's local /api/tags
    inventory to confirm the exact model name and digest on every inference.
    """
    if not isinstance(expected_version, str) or not expected_version.lower().startswith("sha256:"):
        return None
    expected_digest = expected_version[7:].lower()
    if not _SHA256.fullmatch(expected_digest):
        raise ProviderNonRetryableError(
            "Configured model digest is invalid.", code="INVALID_PROVIDER_CONFIGURATION"
        )

    base = str(httpx.URL(base_url)).rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    endpoint = base + "/api/tags"
    try:
        response = client.get(
            endpoint,
            headers=headers or {"Accept": "application/json"},
            timeout=timeout_seconds,
        )
    except httpx.TimeoutException:
        raise ProviderTimeout() from None
    except httpx.ConnectError:
        raise ProviderError(
            "Local model identity service is unavailable.", code="PROVIDER_UNAVAILABLE"
        ) from None
    except httpx.HTTPError:
        raise ProviderError(
            "Local model identity could not be verified.", code="MODEL_IDENTITY_UNVERIFIED"
        ) from None

    if response.status_code < 200 or response.status_code >= 300:
        raise ProviderNonRetryableError(
            "Runtime does not expose a verifiable local model inventory.",
            code="MODEL_IDENTITY_UNVERIFIED",
        )
    if len(response.content) > _MAX_INVENTORY_BYTES:
        raise ProviderNonRetryableError(
            "Local model inventory exceeded the configured response limit.",
            code="RESOURCE_EXHAUSTED",
        )
    try:
        inventory = response.json()
    except ValueError:
        inventory = None
    models = inventory.get("models") if isinstance(inventory, dict) else None
    if not isinstance(models, list):
        raise ProviderNonRetryableError(
            "Runtime returned an unverifiable local model inventory.",
            code="MODEL_IDENTITY_UNVERIFIED",
        )

    match = next((item for item in models
                  if isinstance(item, dict) and item.get("name") == model_id), None)
    if match is None:
        raise ProviderNonRetryableError(
            "Pinned model is absent from the local runtime inventory.", code="MODEL_NOT_FOUND"
        )
    actual_digest = match.get("digest")
    if not isinstance(actual_digest, str):
        raise ProviderNonRetryableError(
            "Runtime did not report a model digest.", code="MODEL_IDENTITY_UNVERIFIED"
        )
    actual_digest = actual_digest.lower().removeprefix("sha256:")
    if not _SHA256.fullmatch(actual_digest):
        raise ProviderNonRetryableError(
            "Runtime reported an invalid model digest.", code="MODEL_IDENTITY_UNVERIFIED"
        )
    actual_version = "sha256:" + actual_digest
    if actual_version != "sha256:" + expected_digest:
        raise ProviderNonRetryableError(
            "Local model digest does not match the submitted pin.", code="MODEL_DIGEST_MISMATCH"
        )
    return actual_version
