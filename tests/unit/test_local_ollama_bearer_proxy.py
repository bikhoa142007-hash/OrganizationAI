from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import threading
import time

import httpx
import pytest

from scripts.local_ollama_bearer_proxy import MAX_REQUEST_BYTES, LocalOllamaBearerProxyServer


TOKEN = "a" * 96


def test_default_request_cap_fits_twenty_mib_of_base64_encoded_image_bytes():
    image_bytes = 20 * 1024 * 1024
    base64_bytes = ((image_bytes + 2) // 3) * 4
    json_and_prompt_overhead = 1024 * 1024

    assert MAX_REQUEST_BYTES >= base64_bytes + json_and_prompt_overhead


class FakeOllamaHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    calls = []
    gate = None
    delay_seconds = 0

    def log_message(self, _format, *_args):
        return

    def do_GET(self):
        type(self).calls.append(("GET", self.path, self.headers.get("Authorization"), b""))
        if self.path == "/api/tags":
            body = json.dumps({"models": [{"name": "synthetic", "digest": "f" * 64}]}).encode()
        else:
            body = json.dumps({"data": [{"id": "synthetic"}]}).encode()
        self._respond(body)

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        type(self).calls.append(("POST", self.path, self.headers.get("Authorization"), body))
        if type(self).delay_seconds:
            time.sleep(type(self).delay_seconds)
        response = json.dumps({"id": "synthetic-response"}).encode()
        self._respond(response)

    def _respond(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True


@pytest.fixture
def proxy():
    FakeOllamaHandler.calls = []
    FakeOllamaHandler.delay_seconds = 0
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllamaHandler)
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()

    gateway = LocalOllamaBearerProxyServer(
        ("127.0.0.1", 0),
        TOKEN,
        upstream_host="127.0.0.1",
        upstream_port=upstream.server_port,
        expected_host=None,
    )
    gateway_thread = threading.Thread(target=gateway.serve_forever, daemon=True)
    gateway_thread.start()
    try:
        yield f"http://127.0.0.1:{gateway.server_port}", gateway
    finally:
        gateway.shutdown()
        gateway.server_close()
        upstream.shutdown()
        upstream.server_close()


def _auth(token: str = TOKEN):
    return {"Authorization": f"Bearer {token}"}


def test_valid_allowlisted_metadata_and_inference_forward_without_bearer_to_ollama(proxy):
    base_url, _gateway = proxy
    with httpx.Client() as client:
        tags = client.get(base_url + "/api/tags", headers=_auth())
        models = client.get(base_url + "/v1/models", headers=_auth())
        completion = client.post(
            base_url + "/v1/chat/completions",
            headers=_auth(),
            json={"model": "synthetic", "messages": [], "stream": False},
        )

    assert tags.status_code == models.status_code == completion.status_code == 200
    assert json.loads(tags.content)["models"][0]["digest"] == "f" * 64
    assert json.loads(models.content)["data"][0]["id"] == "synthetic"
    assert json.loads(completion.content)["id"] == "synthetic-response"
    assert [item[1] for item in FakeOllamaHandler.calls] == [
        "/api/tags", "/v1/models", "/v1/chat/completions",
    ]
    assert all(item[2] is None for item in FakeOllamaHandler.calls)


@pytest.mark.parametrize("authorization", [None, "Bearer wrong-token"])
def test_missing_or_wrong_bearer_is_rejected_before_forwarding(proxy, authorization):
    base_url, _gateway = proxy
    headers = {} if authorization is None else {"Authorization": authorization}

    response = httpx.get(base_url + "/api/tags", headers=headers)

    assert response.status_code == 401
    assert FakeOllamaHandler.calls == []


def test_authenticated_requests_outside_exact_method_path_allowlist_are_blocked(proxy):
    base_url, _gateway = proxy
    with httpx.Client() as client:
        unknown_path = client.get(base_url + "/api/pull", headers=_auth())
        wrong_method = client.post(base_url + "/api/tags", headers=_auth(), content=b"{}")
        unsupported_method = client.request("PUT", base_url + "/api/tags", headers=_auth())
        unauthenticated_unknown_method = client.request("PUT", base_url + "/api/tags")

    assert unknown_path.status_code == 404
    assert wrong_method.status_code == 405
    assert unsupported_method.status_code == 405
    assert unauthenticated_unknown_method.status_code == 401
    assert FakeOllamaHandler.calls == []


def test_wrong_host_and_oversized_body_are_rejected(proxy):
    base_url, gateway = proxy
    gateway.max_request_bytes = 8
    with httpx.Client() as client:
        bad_host = client.get(base_url + "/api/tags", headers={**_auth(), "Host": "example.invalid"})
        too_large = client.post(
            base_url + "/v1/chat/completions",
            headers=_auth(),
            content=b"{" + b" " * 20 + b"}",
        )

    assert bad_host.status_code == 403
    assert too_large.status_code == 413
    assert FakeOllamaHandler.calls == []


def test_server_enforces_concurrency_limit(proxy):
    _base_url, gateway = proxy
    assert gateway.max_in_flight == 2


def test_server_caps_open_connections_even_before_request_authentication(proxy):
    base_url, gateway = proxy
    held_connections = []
    try:
        for _ in range(gateway.max_connections):
            connection = socket.create_connection(("127.0.0.1", gateway.server_port))
            connection.sendall(b"GET /api/tags HTTP/1.1\r\n")
            held_connections.append(connection)

        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and gateway.connection_slots._value != 0:
            time.sleep(0.01)

        assert gateway.connection_slots._value == 0
        with httpx.Client(timeout=2) as client:
            try:
                overflow = client.get(base_url + "/api/tags", headers=_auth())
            except httpx.ReadError:
                overflow = None
        assert overflow is None or overflow.status_code == 503
        assert FakeOllamaHandler.calls == []
    finally:
        for connection in held_connections:
            connection.close()


def test_slow_ollama_response_hits_upstream_timeout(proxy):
    base_url, gateway = proxy
    FakeOllamaHandler.delay_seconds = 0.25
    gateway.upstream_timeout_seconds = 0.05

    response = httpx.post(
        base_url + "/v1/chat/completions",
        headers=_auth(),
        json={"model": "synthetic", "messages": [], "stream": False},
        timeout=2,
    )

    assert response.status_code == 504
