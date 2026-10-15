"""Loopback-only, bearer-authenticated allowlist proxy for a local Ollama runtime.

This is an operator-run bridge for the approved synthetic inference endpoint. It
does not expose Ollama's wider local API and never logs credentials or bodies.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import http.client
import os
import socket
import sys
import threading
import time
from urllib.parse import urlsplit


LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 11435
EXPECTED_PROXY_HOST = "127.0.0.1:11435"
UPSTREAM_HOST = "127.0.0.1"
UPSTREAM_PORT = 11434
# Four maximum-size (5 MiB) attachments can total 20 MiB raw; their data URLs
# expand by about 4/3 before the local VLM provider sends the JSON request.
MAX_REQUEST_BYTES = 32 * 1024 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_IN_FLIGHT = 2
MAX_CONNECTIONS = 8
REQUEST_BODY_TIMEOUT_SECONDS = 30
UPSTREAM_TIMEOUT_SECONDS = 55
IDLE_SOCKET_TIMEOUT_SECONDS = 10

ALLOWED_ROUTES = {
    ("GET", "/api/tags"): "ollama-tags",
    ("GET", "/v1/models"): "openai-models",
    ("POST", "/v1/chat/completions"): "chat-completions",
}
ROUTE_METHODS = {
    "/api/tags": "GET",
    "/v1/models": "GET",
    "/v1/chat/completions": "POST",
}


class LocalOllamaBearerProxyServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 16

    def __init__(
        self,
        server_address,
        token: str,
        *,
        upstream_host: str = UPSTREAM_HOST,
        upstream_port: int = UPSTREAM_PORT,
        expected_host: str | None = EXPECTED_PROXY_HOST,
        max_request_bytes: int = MAX_REQUEST_BYTES,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        max_in_flight: int = MAX_IN_FLIGHT,
        max_connections: int = MAX_CONNECTIONS,
        upstream_timeout_seconds: float = UPSTREAM_TIMEOUT_SECONDS,
        body_timeout_seconds: float = REQUEST_BODY_TIMEOUT_SECONDS,
    ):
        if len(token) < 64 or not token.isascii():
            raise ValueError("proxy bearer token must be at least 64 ASCII characters")
        self.proxy_token = token
        self.upstream_host = upstream_host
        self.upstream_port = upstream_port
        self.expected_host = expected_host
        self.max_request_bytes = max_request_bytes
        self.max_response_bytes = max_response_bytes
        self.max_in_flight = max_in_flight
        self.max_connections = max_connections
        self.upstream_timeout_seconds = upstream_timeout_seconds
        self.body_timeout_seconds = body_timeout_seconds
        self.in_flight = threading.BoundedSemaphore(max_in_flight)
        self.connection_slots = threading.BoundedSemaphore(max_connections)
        super().__init__(server_address, LocalOllamaBearerProxyHandler)
        if self.expected_host is None:
            self.expected_host = f"{self.server_address[0]}:{self.server_port}"

    def process_request(self, request, client_address):
        if not self.connection_slots.acquire(blocking=False):
            body = _error_body(503)
            response = (
                b"HTTP/1.1 503 Service Unavailable\r\n"
                b"Content-Type: application/json\r\n"
                + f"Content-Length: {len(body)}\r\n".encode("ascii")
                + b"Cache-Control: no-store\r\n"
                b"Connection: close\r\n\r\n"
                + body
            )
            try:
                request.sendall(response)
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.connection_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.connection_slots.release()


class LocalOllamaBearerProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "LocalInferenceProxy"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(IDLE_SOCKET_TIMEOUT_SECONDS)

    def version_string(self):
        return self.server_version

    def log_message(self, _format, *_args):
        # BaseHTTPRequestHandler's request log can contain attacker-controlled URLs.
        return

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def handle_expect_100(self):
        status = self._preflight("POST")
        if status is not None:
            self._respond(status, _error_body(status), close=True)
            return False
        metadata_status, _length = self._request_metadata()
        if metadata_status is not None:
            self._respond(metadata_status, _error_body(metadata_status), close=True)
            return False
        self.send_response_only(100)
        self.end_headers()
        return True

    def __getattr__(self, name):
        # Make unsupported HTTP verbs authenticate and receive an explicit 405.
        if name.startswith("do_"):
            return self._handle_unsupported
        raise AttributeError(name)

    def _handle_unsupported(self):
        self._handle(self.command or "UNKNOWN")

    def _handle(self, method: str):
        started = time.monotonic()
        route_label = "blocked"
        status = 500
        error_type = ""
        acquired = False
        try:
            preflight_status = self._preflight(method)
            if preflight_status is not None:
                status = preflight_status
                self._respond(status, _error_body(status), close=True)
                return

            parsed = urlsplit(self.path)
            route = (method, parsed.path)
            route_label = ALLOWED_ROUTES.get(route, "blocked")
            if parsed.query or parsed.fragment or parsed.scheme or parsed.netloc:
                status = 400
                self._respond(status, _error_body(status), close=True)
                return
            if route_label == "blocked":
                if parsed.path in ROUTE_METHODS:
                    status = 405
                    self._respond(
                        status,
                        _error_body(status),
                        close=True,
                        extra_headers={"Allow": ROUTE_METHODS[parsed.path]},
                    )
                else:
                    status = 404
                    self._respond(status, _error_body(status), close=True)
                return

            if not self.server.in_flight.acquire(blocking=False):
                status = 503
                self._respond(
                    status,
                    _error_body(status),
                    close=True,
                    extra_headers={"Retry-After": "1"},
                )
                return
            acquired = True

            body = b""
            if method == "POST":
                metadata_status, length = self._request_metadata()
                if metadata_status is not None:
                    status = metadata_status
                    self._respond(status, _error_body(status), close=True)
                    return
                body_status, body = self._read_body(length)
                if body_status is not None:
                    status = body_status
                    self._respond(status, _error_body(status), close=True)
                    return
            elif self.headers.get("Transfer-Encoding") or self.headers.get("Content-Length", "0") not in {"0", ""}:
                status = 400
                self._respond(status, _error_body(status), close=True)
                return

            status, response_headers, response_body = self._forward(method, parsed.path, body)
            error_type = self.upstream_error_type if hasattr(self, "upstream_error_type") else ""
            self._respond(
                status,
                response_body,
                close=True,
                content_type=response_headers.get("Content-Type", "application/json"),
            )
        except ConnectionError:
            status = 499
        except Exception as error:
            status = 502
            error_type = type(error).__name__
            if not self.close_connection:
                self._respond(status, _error_body(status), close=True)
        finally:
            if acquired:
                self.server.in_flight.release()
            elapsed_ms = int((time.monotonic() - started) * 1000)
            _log_request(method, route_label, status, elapsed_ms, error_type)

    def _preflight(self, method: str) -> int | None:
        if not _authorized(self.headers, self.server.proxy_token):
            return 401
        if self.headers.get("Host", "").lower() != self.server.expected_host.lower():
            return 403
        try:
            parsed = urlsplit(self.path)
        except ValueError:
            return 400
        if parsed.query or parsed.fragment or parsed.scheme or parsed.netloc:
            return 400
        if (method, parsed.path) not in ALLOWED_ROUTES:
            return 405 if parsed.path in ROUTE_METHODS else 404
        return None

    def _request_metadata(self) -> tuple[int | None, int]:
        if self.headers.get("Transfer-Encoding"):
            return 400, 0
        values = self.headers.get_all("Content-Length", [])
        if len(values) != 1:
            return 411, 0
        try:
            length = int(values[0])
        except (TypeError, ValueError):
            return 400, 0
        if length < 0:
            return 400, 0
        if length > self.server.max_request_bytes:
            return 413, 0
        if length == 0:
            return 400, 0
        if self.headers.get_content_type().lower() != "application/json":
            return 415, 0
        return None, length

    def _read_body(self, length: int) -> tuple[int | None, bytes]:
        deadline = time.monotonic() + self.server.body_timeout_seconds
        chunks: list[bytes] = []
        remaining = length
        while remaining:
            time_left = deadline - time.monotonic()
            if time_left <= 0:
                return 408, b""
            self.connection.settimeout(min(5.0, time_left))
            try:
                chunk = self.rfile.read1(min(64 * 1024, remaining))
            except (socket.timeout, TimeoutError, OSError):
                return 408, b""
            if not chunk:
                return 400, b""
            chunks.append(chunk)
            remaining -= len(chunk)
        return None, b"".join(chunks)

    def _forward(self, method: str, path: str, body: bytes):
        self.upstream_error_type = ""
        deadline = time.monotonic() + self.server.upstream_timeout_seconds
        connection = http.client.HTTPConnection(
            self.server.upstream_host,
            self.server.upstream_port,
            timeout=self.server.upstream_timeout_seconds,
        )
        try:
            headers = {
                "Host": f"{self.server.upstream_host}:{self.server.upstream_port}",
                "Accept": "application/json",
                "Connection": "close",
            }
            if method == "POST":
                headers["Content-Type"] = "application/json"
            connection.request(method, path, body=body if method == "POST" else None, headers=headers)
            if connection.sock is None:
                self.upstream_error_type = "upstream_socket_missing"
                return 502, {}, _error_body(502)
            time_left = deadline - time.monotonic()
            if time_left <= 0:
                return 504, {}, _error_body(504)
            upstream_socket = connection.sock
            upstream_socket.settimeout(time_left)
            response = connection.getresponse()
            declared_length = response.getheader("Content-Length")
            if declared_length is not None:
                try:
                    declared_size = int(declared_length)
                    if declared_size < 0 or declared_size > self.server.max_response_bytes:
                        self.upstream_error_type = "invalid_response_size"
                        return 502, {}, _error_body(502)
                except ValueError:
                    self.upstream_error_type = "invalid_response_size"
                    return 502, {}, _error_body(502)
            chunks: list[bytes] = []
            total = 0
            while not response.isclosed():
                time_left = deadline - time.monotonic()
                if time_left <= 0:
                    return 504, {}, _error_body(504)
                upstream_socket.settimeout(time_left)
                try:
                    chunk = response.read(min(64 * 1024, self.server.max_response_bytes + 1 - total))
                except (socket.timeout, TimeoutError, OSError, http.client.HTTPException):
                    return 504, {}, _error_body(504)
                if not chunk:
                    break
                total += len(chunk)
                if total > self.server.max_response_bytes:
                    self.upstream_error_type = "response_too_large"
                    return 502, {}, _error_body(502)
                chunks.append(chunk)
            return response.status, {"Content-Type": response.getheader("Content-Type", "application/json")}, b"".join(chunks)
        except (socket.timeout, TimeoutError) as error:
            self.upstream_error_type = type(error).__name__
            return 504, {}, _error_body(504)
        except (OSError, http.client.HTTPException) as error:
            error_code = getattr(error, "winerror", None) or getattr(error, "errno", None)
            self.upstream_error_type = f"{type(error).__name__}_{error_code or 'unknown'}"
            return 502, {}, _error_body(502)
        finally:
            connection.close()

    def _respond(
        self,
        status: int,
        body: bytes,
        *,
        close: bool,
        content_type: str = "application/json",
        extra_headers: dict[str, str] | None = None,
    ):
        self.close_connection = close
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if status == 401:
            self.send_header("WWW-Authenticate", "Bearer")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        if close:
            self.send_header("Connection", "close")
        self.end_headers()
        if body:
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True


def _authorized(headers, token: str) -> bool:
    values = headers.get_all("Authorization", [])
    if len(values) != 1:
        return False
    supplied = values[0]
    expected = "Bearer " + token
    return hmac.compare_digest(supplied.encode("utf-8", "ignore"), expected.encode("ascii"))


def _error_body(status: int) -> bytes:
    messages = {
        400: "bad request",
        401: "authentication required",
        403: "host not allowed",
        404: "route not allowed",
        405: "method not allowed",
        408: "request timeout",
        411: "content length required",
        413: "request too large",
        415: "application/json required",
        502: "upstream unavailable",
        503: "proxy busy",
        504: "upstream timeout",
    }
    import json

    return json.dumps({"error": messages.get(status, "request rejected")}, separators=(",", ":")).encode("utf-8")


def _log_request(method: str, route_label: str, status: int, elapsed_ms: int, error_type: str = ""):
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    error_field = f" error_type={error_type}" if error_type else ""
    print(
        f"{timestamp} method={method} route={route_label} status={status} elapsed_ms={elapsed_ms}{error_field}",
        file=sys.stderr,
        flush=True,
    )


def main():
    token = os.environ.get("OLLAMA_PROXY_BEARER_TOKEN", "")
    if len(token) < 64 or not token.isascii():
        raise SystemExit("OLLAMA_PROXY_BEARER_TOKEN must be set to a 64+ character ASCII secret")
    server = LocalOllamaBearerProxyServer((LISTEN_HOST, LISTEN_PORT), token)
    print(
        f"LocalInferenceProxy listening on {LISTEN_HOST}:{LISTEN_PORT}; upstream=127.0.0.1:11434; routes=3; max_in_flight={MAX_IN_FLIGHT}; max_connections={MAX_CONNECTIONS}",
        file=sys.stderr,
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
