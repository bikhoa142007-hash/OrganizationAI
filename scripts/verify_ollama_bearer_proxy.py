"""Synthetic black-box checks for the local or public Ollama Bearer proxy."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time

import httpx


SYNTHETIC_PNG = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d4944415408d763f8cfc0f01f00050001ff89993d1d0000000049454e44ae426082"
    )
).decode("ascii")


def check(condition: bool, label: str):
    if not condition:
        raise RuntimeError(label)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:11435")
    parser.add_argument("--model", default="qwen3-vl:4b")
    parser.add_argument(
        "--digest",
        default="sha256:e8503d318d8df6622abc18a317c0e5eee044821322c87a16a6acddd62984da84",
    )
    parser.add_argument("--inference-timeout", type=float, default=65.0)
    args = parser.parse_args()

    token = os.environ.get("OLLAMA_PROXY_BEARER_TOKEN", "")
    check(len(token) >= 64 and token.isascii(), "proxy token missing or invalid")
    base_url = args.base_url.rstrip("/")
    authorized = {"Authorization": "Bearer " + token}
    wrong_key = {"Authorization": "Bearer " + ("0" * len(token))}

    with httpx.Client(timeout=args.inference_timeout, follow_redirects=False) as client:
        no_auth = client.get(base_url + "/api/tags")
        check(no_auth.status_code == 401, "missing Bearer was not rejected")
        bad_auth = client.get(base_url + "/api/tags", headers=wrong_key)
        check(bad_auth.status_code == 401, "wrong Bearer was not rejected")
        blocked_path = client.get(base_url + "/api/pull", headers=authorized)
        check(blocked_path.status_code == 404, "unlisted route was not blocked")
        blocked_method = client.post(base_url + "/api/tags", headers=authorized, content=b"{}")
        check(blocked_method.status_code == 405, "unlisted method was not blocked")

        tags_response = client.get(base_url + "/api/tags", headers=authorized)
        check(tags_response.status_code == 200, "authenticated Ollama tags request failed")
        tags = tags_response.json()
        models = tags.get("models") if isinstance(tags, dict) else None
        model = next((item for item in models or [] if item.get("name") == args.model), None)
        check(model is not None, "pinned model name absent from Ollama tags")
        actual_digest = str(model.get("digest", "")).lower().removeprefix("sha256:")
        check(actual_digest == args.digest.lower().removeprefix("sha256:"), "model digest mismatch")

        models_response = client.get(base_url + "/v1/models", headers=authorized)
        check(models_response.status_code == 200, "authenticated OpenAI models request failed")
        model_items = models_response.json().get("data", [])
        check(any(item.get("id") == args.model for item in model_items), "model absent from OpenAI models response")

        body = {
            "model": args.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are doing a synthetic connectivity check. Return one brief, literal sentence.",
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Briefly describe this synthetic image in one sentence. /no_think",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/png;base64," + SYNTHETIC_PNG,
                                "detail": "high",
                            },
                        },
                    ],
                },
            ],
            "temperature": 0,
            "max_tokens": 512,
            "stream": False,
        }
        started = time.monotonic()
        inference = client.post(
            base_url + "/v1/chat/completions",
            headers=authorized,
            json=body,
            timeout=args.inference_timeout,
        )
        elapsed_ms = int((time.monotonic() - started) * 1000)
        check(inference.status_code == 200, "authenticated synthetic image inference failed")
        result = inference.json()
        check(result.get("model") == args.model, "inference response model ID mismatch")
        choices = result.get("choices")
        check(bool(choices) and isinstance(choices[0].get("message", {}).get("content"), str), "inference response is invalid")
        check(bool(choices[0]["message"]["content"].strip()), "inference response is empty")

    print("missing_key=401 wrong_key=401 unlisted_path=404 unlisted_method=405")
    print("metadata_tags=200 openai_models=200 model_identity=PASS digest_match=PASS")
    print(f"synthetic_image_inference=200 model={args.model} elapsed_ms={elapsed_ms}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Error type/code only; never print the response body, key, or synthetic payload.
        print(f"PROXY_VERIFY_FAILED error_type={type(error).__name__} message={error}", file=sys.stderr)
        raise SystemExit(1)
