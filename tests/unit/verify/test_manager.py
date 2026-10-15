import time
from threading import Event

import pytest

from src.verify import manager as manager_module
from src.verify.manager import VerifyRunConflict, VerifyRunManager, VerifyRunNotFound


def test_manager_scopes_runs_and_replays_idempotent_start(monkeypatch):
    entered = Event()
    release = Event()

    def fake_suite(*, run_id, on_case_started, on_case_completed, total_timeout_seconds):
        on_case_started("TC01")
        entered.set()
        release.wait(timeout=2)
        return {"run_id": run_id, "status": "COMPLETED", "rows": []}

    monkeypatch.setattr(manager_module, "run_competition_suite", fake_suite)
    manager = VerifyRunManager(timeout_seconds=5)
    started = manager.start("admin-1", "verify-request-0001")
    assert entered.wait(timeout=1)

    replay = manager.start("admin-1", "verify-request-0001")
    assert replay["run_id"] == started["run_id"]
    assert replay["idempotent_replay"] is True
    assert manager.latest("admin-1")["run_id"] == started["run_id"]
    with pytest.raises(VerifyRunNotFound):
        manager.get("admin-2", started["run_id"])
    with pytest.raises(VerifyRunConflict):
        manager.start("admin-1", "verify-request-0002")

    release.set()
    deadline = time.monotonic() + 1
    while manager.get("admin-1", started["run_id"])["status"] == "RUNNING" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert manager.get("admin-1", started["run_id"])["status"] == "COMPLETED"


def test_total_deadline_marks_current_and_waiting_cases_failed(monkeypatch):
    entered = Event()
    release = Event()

    def slow_suite(*, run_id, on_case_started, on_case_completed, total_timeout_seconds):
        on_case_started("TC01")
        entered.set()
        release.wait(timeout=1)
        return {"run_id": run_id, "status": "COMPLETED", "rows": []}

    monkeypatch.setattr(manager_module, "run_competition_suite", slow_suite)
    manager = VerifyRunManager(timeout_seconds=0.05)
    started = manager.start("admin-1", "verify-timeout-0001")
    assert entered.wait(timeout=1)

    deadline = time.monotonic() + 1
    snapshot = manager.get("admin-1", started["run_id"])
    while snapshot["status"] == "RUNNING" and time.monotonic() < deadline:
        time.sleep(0.01)
        snapshot = manager.get("admin-1", started["run_id"])
    assert snapshot["status"] == "TIMED_OUT"
    assert snapshot["failed_cases"] == 4
    assert [row["status"] for row in snapshot["rows"]] == ["FAIL"] * 4

    release.set()
    time.sleep(0.05)
    assert manager.get("admin-1", started["run_id"])["status"] == "TIMED_OUT"


def test_timed_out_worker_does_not_block_a_new_verify_run(monkeypatch):
    entered = Event()
    release = Event()
    calls = 0

    def slow_first_suite(*, run_id, on_case_started, on_case_completed, total_timeout_seconds):
        nonlocal calls
        calls += 1
        if calls == 1:
            on_case_started("TC01")
            entered.set()
            release.wait(timeout=2)
        return {"run_id": run_id, "status": "COMPLETED", "rows": []}

    monkeypatch.setattr(manager_module, "run_competition_suite", slow_first_suite)
    manager = VerifyRunManager(timeout_seconds=0.05)
    first = manager.start("admin-1", "verify-stuck-0001")
    assert entered.wait(timeout=1)

    try:
        deadline = time.monotonic() + 1
        snapshot = manager.get("admin-1", first["run_id"])
        while snapshot["status"] == "RUNNING" and time.monotonic() < deadline:
            time.sleep(0.01)
            snapshot = manager.get("admin-1", first["run_id"])
        assert snapshot["status"] == "TIMED_OUT"

        second = manager.start("admin-1", "verify-retry-0001")
        assert second["run_id"] != first["run_id"]
        deadline = time.monotonic() + 1
        snapshot = manager.get("admin-1", second["run_id"])
        while snapshot["status"] == "RUNNING" and time.monotonic() < deadline:
            time.sleep(0.01)
            snapshot = manager.get("admin-1", second["run_id"])
        assert snapshot["status"] == "COMPLETED"
    finally:
        release.set()


def test_harness_exception_marks_all_cases_failed_without_exposing_exception_text(monkeypatch):
    def failing_suite(**_kwargs):
        raise RuntimeError("sensitive provider detail")

    monkeypatch.setattr(manager_module, "run_competition_suite", failing_suite)
    manager = VerifyRunManager(timeout_seconds=2)
    started = manager.start("admin-1", "verify-error-0001")

    deadline = time.monotonic() + 1
    snapshot = manager.get("admin-1", started["run_id"])
    while snapshot["status"] == "RUNNING" and time.monotonic() < deadline:
        time.sleep(0.01)
        snapshot = manager.get("admin-1", started["run_id"])
    assert snapshot["status"] == "ERROR"
    assert snapshot["failed_cases"] == 4
    assert [row["status"] for row in snapshot["rows"]] == ["FAIL"] * 4
    assert "sensitive provider detail" not in str(snapshot)
