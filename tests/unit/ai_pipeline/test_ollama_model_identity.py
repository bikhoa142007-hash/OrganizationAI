import httpx
import pytest

from src.ai_pipeline.providers.base import ProviderNonRetryableError
from src.ai_pipeline.providers.ollama_identity import verify_ollama_model_digest


DIGEST = "sha256:" + "a" * 64


def inventory_client(body, *, status_code=200):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(status_code, json=body)

    client = httpx.Client(transport=httpx.MockTransport(respond))
    return client, requests


def test_exact_ollama_digest_is_verified_against_local_model_inventory():
    client, requests = inventory_client({"models": [{
        "name": "qwen3-vl:4b", "digest": "a" * 64,
    }]})
    try:
        verified = verify_ollama_model_digest(
            client, base_url="http://127.0.0.1:11434/v1", model_id="qwen3-vl:4b",
            expected_version=DIGEST, timeout_seconds=5,
        )
    finally:
        client.close()

    assert verified == DIGEST
    assert requests[0].method == "GET"
    assert requests[0].url == "http://127.0.0.1:11434/api/tags"


def test_digest_mismatch_fails_closed_without_exposing_inventory_payload():
    client, _ = inventory_client({"models": [{
        "name": "qwen3-vl:4b", "digest": "b" * 64,
    }]})
    try:
        with pytest.raises(ProviderNonRetryableError) as error:
            verify_ollama_model_digest(
                client, base_url="http://localhost:11434/v1", model_id="qwen3-vl:4b",
                expected_version=DIGEST, timeout_seconds=5,
            )
    finally:
        client.close()

    assert error.value.code == "MODEL_DIGEST_MISMATCH"


def test_digest_pin_requires_a_full_sha256_value():
    client, requests = inventory_client({"models": []})
    try:
        with pytest.raises(ProviderNonRetryableError) as error:
            verify_ollama_model_digest(
                client, base_url="http://localhost:11434/v1", model_id="qwen3-vl:4b",
                expected_version="sha256:abc", timeout_seconds=5,
            )
    finally:
        client.close()

    assert error.value.code == "INVALID_PROVIDER_CONFIGURATION"
    assert requests == []


def test_non_digest_model_revision_does_not_probe_ollama_inventory():
    client, requests = inventory_client({"models": []})
    try:
        verified = verify_ollama_model_digest(
            client, base_url="http://localhost:8000/v1", model_id="local-model",
            expected_version="model-revision-1", timeout_seconds=5,
        )
    finally:
        client.close()

    assert verified is None
    assert requests == []


def test_unavailable_digest_endpoint_is_not_treated_as_verified():
    client, _ = inventory_client({"error": "internal endpoint detail"}, status_code=404)
    try:
        with pytest.raises(ProviderNonRetryableError) as error:
            verify_ollama_model_digest(
                client, base_url="http://localhost:11434/v1", model_id="qwen3-vl:4b",
                expected_version=DIGEST, timeout_seconds=5,
            )
    finally:
        client.close()

    assert error.value.code == "MODEL_IDENTITY_UNVERIFIED"
    assert "internal endpoint detail" not in str(error.value)
