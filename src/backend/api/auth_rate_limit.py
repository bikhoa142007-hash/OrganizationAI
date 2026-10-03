from collections import deque
from hashlib import sha256
from math import ceil
from threading import Lock
from time import monotonic
from typing import Callable


class AuthAttemptLimiter:
    """Process-local sliding-window limits for a single-instance staging API."""

    def __init__(
        self,
        *,
        login_per_ip: int = 50,
        login_per_identifier: int = 10,
        register_per_ip: int = 5,
        register_per_service: int = 25,
        login_window_seconds: int = 15 * 60,
        registration_window_seconds: int = 60 * 60,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.login_per_ip = login_per_ip
        self.login_per_identifier = login_per_identifier
        self.register_per_ip = register_per_ip
        self.register_per_service = register_per_service
        self.login_window_seconds = login_window_seconds
        self.registration_window_seconds = registration_window_seconds
        self._clock = clock
        self._attempts: dict[tuple[str, str], deque[float]] = {}
        self._lock = Lock()
        self._operations = 0

    def record_login(self, client_ip: str, identifier: str) -> int | None:
        identity_hash = sha256(identifier.strip().casefold().encode("utf-8")).hexdigest()
        return self._record((
            (("login-ip", client_ip), self.login_per_ip, self.login_window_seconds),
            (("login-identity", identity_hash), self.login_per_identifier,
             self.login_window_seconds),
        ))

    def record_registration(self, client_ip: str) -> int | None:
        return self._record((
            (("register-ip", client_ip), self.register_per_ip, self.registration_window_seconds),
            (("register-service", "all"), self.register_per_service,
             self.registration_window_seconds),
        ))

    def _record(self, buckets: tuple[tuple[tuple[str, str], int, int], ...]) -> int | None:
        now = self._clock()
        with self._lock:
            self._operations += 1
            if self._operations % 256 == 0:
                stale_before = now - max(self.login_window_seconds, self.registration_window_seconds)
                for key, attempts in tuple(self._attempts.items()):
                    if not attempts or attempts[-1] <= stale_before:
                        del self._attempts[key]
            active: list[tuple[tuple[str, str], int, int, deque[float]]] = []
            retry_after = 0
            for key, limit, window in buckets:
                attempts = self._attempts.setdefault(key, deque())
                while attempts and now - attempts[0] >= window:
                    attempts.popleft()
                if len(attempts) >= limit:
                    retry_after = max(retry_after, ceil(window - (now - attempts[0])))
                active.append((key, limit, window, attempts))
            if retry_after:
                return retry_after
            for _, _, _, attempts in active:
                attempts.append(now)
        return None
