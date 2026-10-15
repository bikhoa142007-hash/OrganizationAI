"""Process-local manager for authenticated synthetic Verify runs."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock, Thread, Timer
from time import monotonic
from typing import Any
from uuid import uuid4

from .competition import _load_cases, run_competition_suite


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class VerifyRunNotFound(LookupError):
    pass


class VerifyRunConflict(RuntimeError):
    pass


class VerifyRunManager:
    """Keep one active synthetic suite and owner-scoped run history per API process."""

    def __init__(self, *, timeout_seconds: float = 90):
        if timeout_seconds <= 0:
            raise ValueError("Verify timeout must be positive.")
        self.timeout_seconds = timeout_seconds
        self._lock = Lock()
        self._runs: dict[str, dict[str, Any]] = {}
        self._idempotency: dict[tuple[str, str], str] = {}
        self._active_run_id: str | None = None

    def start(self, owner_id: str, idempotency_key: str) -> dict[str, Any]:
        if not idempotency_key or len(idempotency_key) > 200:
            raise ValueError("A valid Idempotency-Key is required.")
        with self._lock:
            replay_id = self._idempotency.get((owner_id, idempotency_key))
            if replay_id:
                return self._snapshot(replay_id, idempotent_replay=True)
            if self._active_run_id is not None:
                raise VerifyRunConflict("A Verify suite is already running.")

            configuration, cases = _load_cases()
            run_id = f"VERIFY-{uuid4()}"
            started_at = _now()
            run = {
                "owner_id": owner_id,
                "idempotency_key": idempotency_key,
                "created_monotonic": monotonic(),
                "data": {
                    "run_id": run_id,
                    "suite": "competition",
                    "suite_version": "VERIFY-1.0",
                    "status": "RUNNING",
                    "environment": "SYNTHETIC_TEST",
                    "provider_mode": "MOCK_VLM (external calls disabled)",
                    "timezone": "Asia/Ho_Chi_Minh",
                    "started_at": started_at,
                    "completed_at": None,
                    "duration_ms": 0,
                    "commit_sha": None,
                    "configuration": deepcopy(configuration),
                    "current_case_id": None,
                    "completed_cases": 0,
                    "passed_cases": 0,
                    "failed_cases": 0,
                    "rows": [
                        {
                            "case_id": case["id"],
                            "case_name": case["name"],
                            "input": deepcopy(case["input"]),
                            "expected": deepcopy(case["expected"]),
                            "actual": None,
                            "assertions": [],
                            "status": "WAITING",
                            "reason": None,
                            "started_at": None,
                            "completed_at": None,
                            "duration_ms": 0,
                        }
                        for case in cases
                    ],
                },
                "timer": None,
            }
            self._runs[run_id] = run
            self._idempotency[(owner_id, idempotency_key)] = run_id
            self._active_run_id = run_id
            timer = Timer(self.timeout_seconds, self._expire, args=(run_id,))
            timer.daemon = True
            run["timer"] = timer
            timer.start()
            worker = Thread(target=self._execute, args=(run_id,), daemon=True)
            worker.start()
            return self._snapshot(run_id, idempotent_replay=False)

    def latest(self, owner_id: str) -> dict[str, Any]:
        with self._lock:
            owned = [
                (run_id, run) for run_id, run in self._runs.items()
                if run["owner_id"] == owner_id
            ]
            if not owned:
                raise VerifyRunNotFound("No Verify run is available.")
            run_id, _ = max(owned, key=lambda item: item[1]["created_monotonic"])
            return self._snapshot(run_id)

    def get(self, owner_id: str, run_id: str) -> dict[str, Any]:
        with self._lock:
            run = self._runs.get(run_id)
            if not run or run["owner_id"] != owner_id:
                raise VerifyRunNotFound("Verify run not found.")
            return self._snapshot(run_id)

    def report(self, owner_id: str, run_id: str) -> dict[str, Any]:
        return self.get(owner_id, run_id)

    def _snapshot(self, run_id: str, *, idempotent_replay: bool | None = None) -> dict[str, Any]:
        run = self._runs[run_id]
        snapshot = deepcopy(run["data"])
        if idempotent_replay is not None:
            snapshot["idempotent_replay"] = idempotent_replay
        return snapshot

    def _case_started(self, run_id: str, case_id: str) -> None:
        with self._lock:
            run = self._runs[run_id]
            data = run["data"]
            if data["status"] != "RUNNING":
                return
            data["current_case_id"] = case_id
            row = next(item for item in data["rows"] if item["case_id"] == case_id)
            row.update(status="RUNNING", started_at=_now())

    def _case_completed(self, run_id: str, completed: dict[str, Any]) -> None:
        with self._lock:
            run = self._runs[run_id]
            data = run["data"]
            if data["status"] != "RUNNING":
                return
            row = next(item for item in data["rows"] if item["case_id"] == completed["case_id"])
            row.update(deepcopy(completed))
            data["current_case_id"] = None
            self._update_counts(data)

    @staticmethod
    def _update_counts(data: dict[str, Any]) -> None:
        done = [row for row in data["rows"] if row["status"] in {"PASS", "FAIL"}]
        data["completed_cases"] = len(done)
        data["passed_cases"] = sum(row["status"] == "PASS" for row in done)
        data["failed_cases"] = sum(row["status"] == "FAIL" for row in done)

    def _expire(self, run_id: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if not run or run["data"]["status"] != "RUNNING":
                return
            data = run["data"]
            now = _now()
            for row in data["rows"]:
                if row["status"] in {"RUNNING", "WAITING"}:
                    row.update(
                        status="FAIL",
                        reason=f"Verify exceeded the {self.timeout_seconds}-second total deadline.",
                        assertions=[{
                            "name": "total_timeout",
                            "expected": f"completed within {self.timeout_seconds}s",
                            "actual": "deadline exceeded",
                            "passed": False,
                        }],
                        completed_at=now,
                    )
            data.update(
                status="TIMED_OUT",
                completed_at=now,
                duration_ms=max(0, int((monotonic() - run["created_monotonic"]) * 1000)),
                current_case_id=None,
                error=f"Verify exceeded the {self.timeout_seconds}-second total deadline.",
            )
            self._update_counts(data)

    def _execute(self, run_id: str) -> None:
        with self._lock:
            run = self._runs[run_id]
        try:
            result = run_competition_suite(
                run_id=run_id,
                on_case_started=lambda case_id: self._case_started(run_id, case_id),
                on_case_completed=lambda row: self._case_completed(run_id, row),
                total_timeout_seconds=self.timeout_seconds,
            )
        except Exception:
            result = None
        finally:
            with self._lock:
                run = self._runs[run_id]
                data = run["data"]
                timer = run.get("timer")
                if timer:
                    timer.cancel()
                if data["status"] == "RUNNING":
                    if result is None:
                        completed_at = _now()
                        for row in data["rows"]:
                            if row["status"] in {"WAITING", "RUNNING"}:
                                row.update(
                                    status="FAIL",
                                    reason="Synthetic Verify harness failed before the case completed.",
                                    assertions=[{
                                        "name": "harness_execution",
                                        "expected": "actual workflow observation",
                                        "actual": "harness error",
                                        "passed": False,
                                    }],
                                    completed_at=completed_at,
                                )
                        data.update(
                            status="ERROR",
                            completed_at=completed_at,
                            current_case_id=None,
                            error="Verify could not complete because the synthetic harness failed.",
                        )
                        self._update_counts(data)
                    else:
                        data.update(deepcopy(result))
                        data["environment"] = "SYNTHETIC_TEST"
                        data["provider_mode"] = "MOCK_VLM (external calls disabled)"
                        data["current_case_id"] = None
                if self._active_run_id == run_id:
                    self._active_run_id = None
