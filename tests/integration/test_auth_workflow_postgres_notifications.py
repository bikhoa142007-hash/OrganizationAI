"""PostgreSQL-backed acceptance checks for authenticated workflow notifications.

The PostgreSQL runner provisions the database, temporary users, and password.
This module deliberately fails when those inputs are missing instead of skipping.
"""
from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json
import os
import struct
import zlib
from threading import Barrier, Event
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from scripts.postgres_test_target import verify_runner_provisioned_database

from src.ai_pipeline.providers.base import ProviderAnalysis, ProviderError
from src.ai_pipeline.providers.mock import AuthenticatedMockVLMProvider
from src.ai_pipeline.task_evaluation import STRATEGY_CRITERIA, media_policy_from_json, strategy_rubric_from_json
from src.ai_pipeline.task_providers import TaskModelSettings
from src.backend.api.app import create_app
from src.backend.api.auth import get_auth_db
from src.backend.api.dependencies import Settings
from src.backend.application import auth_workflow as workflow
from src.backend.db.models import (
    AuthWorkflowDecision,
    AuthWorkflowEngineDecision,
    AuthWorkflowEvaluationRun,
    AuthWorkflowNotification,
    AuthWorkflowPlan,
    AuthWorkflowRoundConfigurationSnapshot,
    EmployeeProfile,
    Role,
    User,
    UserRole,
)
from src.backend.db.security import hash_password
from src.backend.domain.policy import (
    ApprovalConfiguration,
    AuthoritySnapshot,
    BudgetConfiguration,
    Criterion,
    MANDATORY_FIELDS,
    PolicySnapshot,
)


def _png() -> bytes:
    def chunk(kind: bytes, content: bytes) -> bytes:
        body = kind + content
        return struct.pack(">I", len(content)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">2I5B", 1, 1, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00\xff"))
        + chunk(b"IEND", b"")
    )


def _create_user(factory: sessionmaker[Session], username: str, role_code: str, password: str) -> User:
    with factory.begin() as session:
        role = session.scalar(select(Role).where(Role.code == role_code))
        assert role is not None, f"Migration did not seed the {role_code} role."
        user = User(
            id=uuid4(),
            user_code=f"PG-{uuid4().hex[:12].upper()}",
            username=username,
            email=f"{username}@example.invalid",
            phone=None,
            password_hash=hash_password(password),
            display_name=username,
            status="ACTIVE",
        )
        session.add(user)
        session.flush()
        session.add(UserRole(user_id=user.id, role_id=role.id))
        session.add(EmployeeProfile(
            id=user.id,
            user_code=user.user_code,
            display_name=user.display_name,
            email=user.email,
            phone=user.phone,
            user_id=user.id,
        ))
        session.flush()
        session.expunge(user)
    return user


def _login(client: TestClient, username: str, password: str) -> None:
    response = client.post("/api/auth/login", json={"identifier": username, "password": password})
    assert response.status_code == 200, response.text


def _create_configuration_revision(
    client: TestClient,
    kind: str,
    value: dict,
    *,
    expected_revision=None,
) -> dict:
    response = client.post(
        f"/api/workflow/configuration/{kind}/revisions",
        json={
            "expected_revision": expected_revision,
            "effective_at": (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(),
            "change_reason": "Synthetic PostgreSQL snapshot verification.",
            "value": value,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_plan(client: TestClient, checker_id: UUID, title: str) -> dict:
    response = client.post("/api/workflow/plans", json={
        "checker_user_id": str(checker_id),
        "payload": {
            "title": title,
            "objective": "PRIVATE-OBJECTIVE-DO-NOT-LEAK",
            "summary": "PRIVATE-SUMMARY-DO-NOT-LEAK",
            "department": "marketing",
            "start_date": "2026-12-01",
            "end_date": "2026-12-31",
            "budget_minor_units": "50000000",
            "currency": "VND",
            "target_audience": "Private audience details.",
            "channels": ["social"],
            "kpi_expected": "Private KPI details.",
            "notes": "PRIVATE-INTERNAL-NOTE-DO-NOT-LEAK",
        },
    })
    assert response.status_code == 201, response.text
    return response.json()


def _upload_and_submit(client: TestClient, plan: dict) -> dict:
    uploaded = client.post(
        f"/api/workflow/plans/{plan['id']}/attachments",
        data={"expected_revision": str(plan["revision"])},
        files={"file": ("synthetic.png", _png(), "image/png")},
    )
    assert uploaded.status_code == 200, uploaded.text
    submitted = client.post(
        f"/api/workflow/plans/{plan['id']}/submit",
        json={"expected_revision": uploaded.json()["revision"]},
    )
    assert submitted.status_code == 200, submitted.text
    return submitted.json()


def _task_settings(task: str) -> TaskModelSettings:
    model = "synthetic-media-model" if task == "MEDIA_COMPLIANCE" else "synthetic-strategy-model"
    return TaskModelSettings(
        task=task,
        provider="OPENAI_COMPATIBLE_CHAT_COMPLETIONS",
        base_url=f"http://localhost:8000/v1/{task.lower()}",
        model_id=model,
        model_version=f"{model}-rev-1",
        api_key="synthetic-test-only",
        timeout_seconds=2,
        max_output_tokens=1024,
        max_response_bytes=4096,
        max_input_bytes=4096,
        max_retries=0,
        identity_mode="GENERIC_OPAQUE_REVISION",
        prompt_version=f"{task.lower()}-prompt-v1",
        schema_version=f"{task.lower()}-schema-v1",
    )


class _SyntheticTaskProvider:
    def __init__(self, task: str):
        self.task = task
        self.settings = _task_settings(task)

    def evaluate(self, request):
        if self.task == "MEDIA_COMPLIANCE":
            reference = next(item["evidence_id"] for item in request.evidence if item["kind"] == "OBSERVATION")
            output = {
                "policy_id": request.policy.policy_id,
                "policy_version": request.policy.policy_version,
                "outcome": "PASS",
                "confidence": 0.93,
                "reason": "Synthetic PostgreSQL policy check passed.",
                "rule_results": [{
                    "rule_id": rule.rule_id,
                    "result": "PASS",
                    "rationale": "Synthetic evidence supports this check.",
                    "evidence_refs": [reference],
                } for rule in request.policy.rules],
                "findings": [],
                "evidence_conflicts": [],
            }
        else:
            output = {
                "rubric_id": request.rubric.rubric_id,
                "rubric_version": request.rubric.rubric_version,
                "total_score": 71,
                "confidence": 0.82,
                "criterion_scores": [{
                    "criterion_id": item.criterion_id,
                    "score": 71,
                    "rationale": "Grounded in the synthetic test plan.",
                    "evidence_refs": ["plan-field:objective"],
                } for item in request.rubric.criteria],
                "assumptions": [],
                "missing_facts": [],
                "critical_gaps": [],
                "evidence_conflicts": [],
                "reason": "Synthetic PostgreSQL evaluation.",
            }
        return ProviderAnalysis(
            output,
            model_revision=None,
            reported_model_id=self.settings.model_id,
        )


def _auto_approval_configuration(checker_id: UUID) -> ApprovalConfiguration:
    media_policy = media_policy_from_json(json.dumps({
        "policy_id": "SYNTHETIC-POSTGRES-MEDIA",
        "policy_version": "1",
        "status": "ACTIVE",
        "scope_departments": ["marketing"],
        "scope_channels": ["social"],
        "rules": [{
            "rule_id": "SYNTHETIC-OBSERVATION",
            "severity": "WARNING",
            "description": "Synthetic evidence check.",
            "required_evidence_kinds": ["OBSERVATION"],
        }],
    }))
    rubric = strategy_rubric_from_json(json.dumps({
        "rubric_id": "SYNTHETIC-POSTGRES-STRATEGY",
        "rubric_version": "1",
        "status": "ACTIVE",
        "criteria": [{"criterion_id": key, "label": label, "weight": weight}
                     for key, label, weight in STRATEGY_CRITERIA],
    }))
    media_settings = _task_settings("MEDIA_COMPLIANCE")
    strategy_settings = _task_settings("STRATEGY_EVALUATION")
    return ApprovalConfiguration(
        PolicySnapshot(
            "SYNTHETIC-POSTGRES-AUTO-POLICY",
            "SYNTHETIC-POSTGRES-AUTO-POLICY-1",
            True,
            MANDATORY_FIELDS,
            tuple(Criterion(key, weight) for key, _label, weight in STRATEGY_CRITERIA),
            ("mock-1",),
            ("image/png", "image/jpeg", "image/webp"),
            5_000_000,
        ),
        (BudgetConfiguration("SYNTHETIC-POSTGRES-BUDGET", "VND", 0, "100000000", "marketing", True),),
        AuthoritySnapshot(
            "SYNTHETIC-POSTGRES-AUTHORITY", "VND", "100000000", ("marketing",),
            str(checker_id), str(checker_id), str(checker_id), True,
        ),
        media_policy=media_policy,
        strategy_rubric=rubric,
        media_model_snapshot=media_settings.public_snapshot(),
        strategy_model_snapshot=strategy_settings.public_snapshot(),
    )


pytestmark = pytest.mark.postgres


@pytest.fixture
def postgres_workflow(monkeypatch):
    database_url = verify_runner_provisioned_database(os.environ)
    password = os.environ.get("AUTH_SEED_PASSWORD", "")
    if not password:
        raise RuntimeError("PostgreSQL acceptance runner must provide a temporary authentication password.")
    monkeypatch.setenv("JWT_SECRET", os.environ.get("JWT_SECRET", "synthetic-test-jwt-secret-32-bytes-minimum"))
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    monkeypatch.setenv("AUTH_COOKIE_SAMESITE", "lax")
    monkeypatch.setenv("AUTH_WORKFLOW_AI_PROVIDER", "MOCK_VLM")
    monkeypatch.setenv("AUTH_WORKFLOW_MOCK_SCENARIO", "review")
    engine = create_engine(database_url, pool_pre_ping=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex[:10]
    maker = _create_user(factory, f"pg_maker_{suffix}", "MAKER", password)
    checker = _create_user(factory, f"pg_checker_{suffix}", "CHECKER", password)
    next_checker = _create_user(factory, f"pg_checker_next_{suffix}", "CHECKER", password)
    outsider = _create_user(factory, f"pg_checker_outside_{suffix}", "CHECKER", password)
    app = create_app(Settings(app_env="demo", cors_origins=("http://testserver",)))
    default_configuration = app.state.auth_workflow_configuration

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_auth_db] = override_db
    clients = [TestClient(app, raise_server_exceptions=False) for _ in range(4)]
    for client, user in zip(clients, (maker, checker, next_checker, outsider)):
        _login(client, user.username, password)
    try:
        yield {
            "app": app,
            "default_configuration": default_configuration,
            "factory": factory,
            "maker": maker,
            "checker": checker,
            "next_checker": next_checker,
            "outsider": outsider,
            "maker_client": clients[0],
            "checker_client": clients[1],
            "next_checker_client": clients[2],
            "outsider_client": clients[3],
        }
    finally:
        for client in clients:
            client.close()
        engine.dispose()


def test_postgres_retry_race_reuses_the_round_snapshot(postgres_workflow):
    state = postgres_workflow
    app = state["app"]
    factory = state["factory"]
    checker = state["checker"]
    maker_client = state["maker_client"]
    checker_client = state["checker_client"]
    configuration = _auto_approval_configuration(checker.id)
    media_settings = replace(_task_settings("MEDIA_COMPLIANCE"), timeout_seconds=30)
    configuration = replace(
        configuration,
        policy=replace(configuration.policy, auto_approval_policy_enabled=False),
        media_model_snapshot=media_settings.public_snapshot(),
    )
    app.state.auth_workflow_configuration = configuration
    app.state.auth_workflow_provider = AuthenticatedMockVLMProvider("pass", model_version="mock-1")

    admin = _create_user(
        factory, f"pg_admin_snapshot_{uuid4().hex[:10]}", "ADMIN", os.environ["AUTH_SEED_PASSWORD"],
    )
    admin_client = TestClient(app, raise_server_exceptions=False)
    _login(admin_client, admin.username, os.environ["AUTH_SEED_PASSWORD"])
    _create_configuration_revision(admin_client, "approval_policy", {
        "enabled": False,
        "media_confidence_threshold": 0.85,
        "feasibility_score_threshold_exclusive": 70,
        "feasibility_confidence_threshold": 0.8,
    })
    original_rubric = {
        "rubric_id": "SYNTHETIC-POSTGRES-STRATEGY",
        "rubric_version": "snapshot-r1",
        "status": "ACTIVE",
        "criteria": [{"criterion_id": key, "label": label, "weight": weight}
                      for key, label, weight in STRATEGY_CRITERIA],
    }
    _create_configuration_revision(admin_client, "strategy_rubric", original_rubric)

    class FailOnceBlockingMediaProvider(_SyntheticTaskProvider):
        def __init__(self):
            super().__init__("MEDIA_COMPLIANCE")
            self.settings = media_settings
            self.calls = 0
            self.retry_started = Event()
            self.release_retry = Event()

        def evaluate(self, request):
            self.calls += 1
            if self.calls == 1:
                raise ProviderError("private synthetic transport response")
            self.retry_started.set()
            if not self.release_retry.wait(timeout=20):
                raise ProviderError("synthetic concurrency gate timed out")
            return super().evaluate(request)

    class SnapshotStrategyProvider(_SyntheticTaskProvider):
        def __init__(self):
            super().__init__("STRATEGY_EVALUATION")
            self.rubric_versions = []

        def evaluate(self, request):
            self.rubric_versions.append(request.rubric.rubric_version)
            return super().evaluate(request)

    media = FailOnceBlockingMediaProvider()
    strategy = SnapshotStrategyProvider()
    app.state.auth_workflow_media_provider = media
    app.state.auth_workflow_strategy_provider = strategy
    plan = _create_plan(maker_client, checker.id, "PostgreSQL snapshot retry race")
    failed = _upload_and_submit(maker_client, plan)
    assert failed["processing_stage"] == "HUMAN_REVIEW_REQUIRED"

    plan_id = UUID(failed["id"])
    with factory() as session:
        first_run = session.scalar(select(AuthWorkflowEvaluationRun).where(
            AuthWorkflowEvaluationRun.plan_id == plan_id,
            AuthWorkflowEvaluationRun.attempt_number == 1,
        ))
        round_snapshot = session.scalar(select(AuthWorkflowRoundConfigurationSnapshot).where(
            AuthWorkflowRoundConfigurationSnapshot.plan_id == plan_id,
            AuthWorkflowRoundConfigurationSnapshot.approval_round == 1,
        ))
        assert first_run is not None and round_snapshot is not None
        loaded_snapshot = workflow.get_round_configuration_snapshot(
            session, plan_id=plan_id, approval_round=1,
        )
        version_row = session.scalar(select(workflow.AuthWorkflowVersion).where(
            workflow.AuthWorkflowVersion.plan_id == plan_id,
            workflow.AuthWorkflowVersion.round_number == 1,
        ))
        domain_snapshot = workflow._domain_snapshot(
            plan_id, version_row.version_number, version_row.round_number,
            version_row.payload_snapshot, version_row.attachment_snapshot,
        )
        assert first_run.failure_reason == "PROVIDER_ERROR", {
            "failure_reason": first_run.failure_reason,
            "round_snapshot_valid": workflow._round_configuration_snapshot_is_valid(
                loaded_snapshot, plan_id, 1, 1,
            ),
            "policy_snapshot_hash_valid": (
                workflow.canonical_hash(first_run.policy_snapshot) == first_run.policy_snapshot_hash
            ),
            "version_input_hash_valid": version_row.snapshot_hash == domain_snapshot.input_hash,
            "run_input_hash_valid": first_run.input_hash == domain_snapshot.input_hash,
            "snapshot_hash": round_snapshot.snapshot_hash,
        }
        assert round_snapshot.configurations["strategy_rubric"]["value"]["rubric_version"] == "snapshot-r1"
        assert first_run.policy_snapshot["strategy_rubric"]["rubric_version"] == "snapshot-r1"
        frozen_policy = first_run.policy_snapshot
        frozen_policy_hash = first_run.policy_snapshot_hash
        frozen_round_hash = round_snapshot.snapshot_hash
        assert first_run.media_evaluation["attempt_history"][0]["error_code"] == "PROVIDER_ERROR"
        assert "private synthetic transport response" not in str(first_run.media_evaluation)

    current_rubric = {**original_rubric, "rubric_version": "current-r2"}
    _create_configuration_revision(
        admin_client, "strategy_rubric", current_rubric, expected_revision=1,
    )
    app.state.auth_workflow_configuration = replace(
        configuration,
        strategy_rubric=replace(configuration.strategy_rubric, rubric_version="volatile-current"),
    )

    parallel_checker = TestClient(app, raise_server_exceptions=False)
    _login(parallel_checker, checker.username, os.environ["AUTH_SEED_PASSWORD"])
    start_together = Barrier(2)
    retry_url = f"/api/workflow/plans/{failed['id']}/rounds/1/evaluation-retries"
    body = {
        "expected_plan_version": failed["current_version"],
        "expected_round_revision": failed["revision"],
    }

    def send_retry(client, key):
        start_together.wait(timeout=10)
        return client.post(retry_url, json=body, headers={"Idempotency-Key": key})

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            requests = [
                pool.submit(send_retry, checker_client, "pg-retry-race-a"),
                pool.submit(send_retry, parallel_checker, "pg-retry-race-b"),
            ]
            assert media.retry_started.wait(timeout=10), "The winning retry never reached the provider."
            completed, _pending = wait(requests, timeout=10, return_when=FIRST_COMPLETED)
            assert len(completed) == 1, "The losing retry should resolve while the winner is held in provider I/O."
            loser = next(iter(completed)).result()
            assert loser.status_code == 409, loser.text
            media.release_retry.set()
            responses = [request.result(timeout=30) for request in requests]
    finally:
        media.release_retry.set()
        parallel_checker.close()
        admin_client.close()

    assert sorted(response.status_code for response in responses) == [200, 409]
    assert strategy.rubric_versions == ["snapshot-r1", "snapshot-r1"]
    detail = checker_client.get(f"/api/workflow/plans/{failed['id']}").json()
    assert [item["attempt_number"] for item in detail["ai_evaluations"]] == [1, 2]
    assert [item["outcome"] for item in detail["engine_decisions"]] == [
        "HUMAN_REVIEW_REQUIRED", "HUMAN_REVIEW_REQUIRED",
    ]
    with factory() as session:
        runs = session.scalars(select(AuthWorkflowEvaluationRun).where(
            AuthWorkflowEvaluationRun.plan_id == plan_id,
        ).order_by(AuthWorkflowEvaluationRun.attempt_number)).all()
        round_snapshot = session.scalar(select(AuthWorkflowRoundConfigurationSnapshot).where(
            AuthWorkflowRoundConfigurationSnapshot.plan_id == plan_id,
            AuthWorkflowRoundConfigurationSnapshot.approval_round == 1,
        ))
        decisions = session.scalars(select(AuthWorkflowEngineDecision).where(
            AuthWorkflowEngineDecision.plan_id == plan_id,
            AuthWorkflowEngineDecision.round_number == 1,
        )).all()
        assert len(runs) == 2
        assert [run.attempt_number for run in runs] == [1, 2]
        assert runs[1].policy_snapshot == frozen_policy
        assert runs[1].policy_snapshot_hash == frozen_policy_hash
        assert round_snapshot.snapshot_hash == frozen_round_hash
        assert len(decisions) == 2
        assert sum(decision.outcome == "AUTO_APPROVED" for decision in decisions) <= 1


def test_postgres_policy_conflict_persists_safe_attempt_provenance_and_routes_to_checker(postgres_workflow):
    state = postgres_workflow
    app = state["app"]
    factory = state["factory"]
    checker = state["checker"]
    app.state.auth_workflow_configuration = _auto_approval_configuration(checker.id)
    app.state.auth_workflow_provider = AuthenticatedMockVLMProvider("pass", model_version="mock-1")
    app.state.auth_workflow_media_provider = _SyntheticTaskProvider("MEDIA_COMPLIANCE")

    class ConflictingStrategyProvider(_SyntheticTaskProvider):
        def __init__(self):
            super().__init__("STRATEGY_EVALUATION")
            self.raw_hash = None

        def evaluate(self, request):
            analysis = super().evaluate(request)
            output = dict(analysis.output)
            output["total_score"] = 71.01
            output["reason"] = "PRIVATE-RAW-STRATEGY-RESPONSE"
            self.raw_hash = sha256(json.dumps(output, sort_keys=True).encode("utf-8")).hexdigest()
            return ProviderAnalysis(
                output,
                model_revision=analysis.model_revision,
                reported_model_id=analysis.reported_model_id,
                raw_output_hash=self.raw_hash,
            )

    strategy = ConflictingStrategyProvider()
    app.state.auth_workflow_strategy_provider = strategy
    plan = _create_plan(state["maker_client"], checker.id, "PostgreSQL strategy conflict persistence")
    submitted = _upload_and_submit(state["maker_client"], plan)
    assert submitted["processing_stage"] == "HUMAN_REVIEW_REQUIRED"
    run_id = UUID(submitted["ai_evaluations"][0]["id"])

    with factory() as session:
        run = session.get(AuthWorkflowEvaluationRun, run_id)
        assert run is not None and run.status == "FAILED"
        attempt = run.strategy_evaluation["attempt_history"][0]
        assert run.failure_reason == "POLICY_OUTPUT_CONFLICT"
        assert run.strategy_evaluation["error_code"] == "POLICY_OUTPUT_CONFLICT"
        assert run.strategy_evaluation["attempts"] == 1
        assert attempt["status"] == "FAILED"
        assert attempt["error_code"] == "POLICY_OUTPUT_CONFLICT"
        assert attempt["reported_total"] == "71.01"
        assert Decimal(attempt["computed_total"]) == Decimal("71")
        assert attempt["raw_output_hash"] == strategy.raw_hash
        assert attempt["reported_model_id"] == strategy.settings.model_id
        assert attempt["model_revision"] is None
        assert run.strategy_evaluation["identity_mode"] == "GENERIC_OPAQUE_REVISION"
        assert "api_key" not in str(run.strategy_evaluation["model_configuration"])
        assert "PRIVATE-RAW-STRATEGY-RESPONSE" not in str(run.strategy_evaluation)
        assert "PRIVATE-RAW-STRATEGY-RESPONSE" not in str(run.evaluation)
        assert run.strategy_evaluation["result"] is None
        decision = session.scalar(select(AuthWorkflowEngineDecision).where(
            AuthWorkflowEngineDecision.evaluation_run_id == run_id,
        ))
        assert decision is not None and decision.outcome == "HUMAN_REVIEW_REQUIRED"

    retry = state["checker_client"].post(
        f"/api/workflow/plans/{submitted['id']}/rounds/1/evaluation-retries",
        json={
            "expected_plan_version": submitted["current_version"],
            "expected_round_revision": submitted["revision"],
        },
        headers={"Idempotency-Key": "pg-conflict-retry-must-be-terminal"},
    )
    assert retry.status_code == 409
    with factory() as session:
        assert session.scalar(select(AuthWorkflowEvaluationRun.id).where(
            AuthWorkflowEvaluationRun.plan_id == UUID(submitted["id"]),
            AuthWorkflowEvaluationRun.attempt_number == 2,
        )) is None


def test_postgres_notification_lifecycle_permissions_replay_and_rollback(postgres_workflow, monkeypatch):
    state = postgres_workflow
    maker, checker, next_checker = state["maker"], state["checker"], state["next_checker"]
    maker_client = state["maker_client"]
    checker_client = state["checker_client"]
    next_checker_client = state["next_checker_client"]
    outsider_client = state["outsider_client"]
    factory = state["factory"]

    # Submission notifies only the assigned Checker. GET remains read-only, and
    # the notice contains routing metadata but no private plan contents.
    plan = _create_plan(maker_client, checker.id, "PostgreSQL notification lifecycle")
    submitted = _upload_and_submit(maker_client, plan)
    assert submitted["ai_evaluations"][0]["provider"] == "MOCK_VLM"
    notice_response = checker_client.get("/api/workflow/notifications")
    assert notice_response.status_code == 200
    notice_page = notice_response.json()
    assert notice_page["total"] == notice_page["unread_count"] == 1
    submit_notice = notice_page["items"][0]
    assert submit_notice["event_type"] == "PLAN_SUBMITTED"
    assert submit_notice["plan_id"] == plan["id"]
    assert submit_notice["version_number"] == submit_notice["round_number"] == 1
    assert set(submit_notice) == {
        "id", "event_type", "plan_id", "plan_code", "title", "message",
        "version_number", "round_number", "created_at", "read_at",
    }
    notice_json = json.dumps(notice_page, ensure_ascii=False)
    for secret in ("PRIVATE-OBJECTIVE-DO-NOT-LEAK", "PRIVATE-SUMMARY-DO-NOT-LEAK", "PRIVATE-INTERNAL-NOTE-DO-NOT-LEAK"):
        assert secret not in notice_json
    assert state["outsider_client"].get("/api/workflow/notifications").json()["total"] == 0
    assert outsider_client.post(f"/api/workflow/notifications/{submit_notice['id']}/read").status_code == 404
    assert outsider_client.get(f"/api/workflow/plans/{plan['id']}").status_code == 404
    with factory() as session:
        stored_submit_notice = session.get(AuthWorkflowNotification, UUID(submit_notice["id"]))
        assert stored_submit_notice is not None and stored_submit_notice.read_at is None

    # Repeated GET does not mutate; repeated mark-read is safe and stable.
    assert checker_client.get("/api/workflow/notifications").json()["unread_count"] == 1
    still_unread = checker_client.get("/api/workflow/notifications").json()["items"][0]
    assert still_unread["read_at"] is None
    first_read = checker_client.post(f"/api/workflow/notifications/{submit_notice['id']}/read")
    second_read = checker_client.post(f"/api/workflow/notifications/{submit_notice['id']}/read")
    assert first_read.status_code == second_read.status_code == 200
    assert first_read.json()["read_at"] is not None
    assert second_read.json()["read_at"] == first_read.json()["read_at"]

    # Checker rejection replay creates one Maker notice. The Maker then changes
    # assignment and resubmits; the next Checker receives round 2 while the old
    # Checker keeps the old notice but cannot use its link as a permission grant.
    reject_body = {
        "action": "REJECTED",
        "reason": "Add a measurable conversion target.",
        "override_reason": "Synthetic Checker review after AI routed to human review.",
    }
    decision_url = f"/api/workflow/plans/{plan['id']}/rounds/1/decision"
    rejected = checker_client.post(decision_url, json=reject_body)
    replayed_rejection = checker_client.post(decision_url, json=reject_body)
    assert rejected.status_code == replayed_rejection.status_code == 200
    assert rejected.json()["status"] == "REJECTED"
    maker_notices = maker_client.get("/api/workflow/notifications").json()
    assert [(item["event_type"], item["round_number"]) for item in maker_notices["items"]] == [("PLAN_REJECTED", 1)]
    rejected_plan = rejected.json()
    updated = maker_client.put(f"/api/workflow/plans/{plan['id']}", json={
        "expected_revision": rejected_plan["revision"],
        "checker_user_id": str(next_checker.id),
        "payload": {**rejected_plan["payload"], "summary": "Updated synthetic summary."},
    })
    assert updated.status_code == 200, updated.text
    resubmitted = _upload_and_submit(maker_client, updated.json())
    assert resubmitted["current_version"] == resubmitted["current_round"] == 2
    next_checker_notices = next_checker_client.get("/api/workflow/notifications").json()
    assert next_checker_notices["total"] == 1
    assert next_checker_notices["items"][0]["event_type"] == "PLAN_SUBMITTED"
    assert next_checker_notices["items"][0]["version_number"] == next_checker_notices["items"][0]["round_number"] == 2
    assert checker_client.get("/api/workflow/plans/" + plan["id"]).status_code == 404
    assert checker_client.get("/api/workflow/notifications").json()["total"] == 1

    approve_body = {
        "action": "APPROVED",
        "reason": "The revised KPI is measurable.",
        "override_reason": "Synthetic Checker approval after reviewing the submitted version.",
    }
    round_two_url = f"/api/workflow/plans/{plan['id']}/rounds/2/decision"
    approved = next_checker_client.post(round_two_url, json=approve_body)
    approval_replay = next_checker_client.post(round_two_url, json=approve_body)
    assert approved.status_code == approval_replay.status_code == 200
    assert approved.json()["status"] == "APPROVED"
    assert {(item["event_type"], item["round_number"]) for item in maker_client.get("/api/workflow/notifications").json()["items"]} == {
        ("PLAN_REJECTED", 1), ("PLAN_APPROVED", 2),
    }

    # Admin configuration stays disabled until PO sign-off; even passing
    # synthetic providers must therefore route to the assigned Checker.
    app = state["app"]
    app.state.auth_workflow_configuration = _auto_approval_configuration(next_checker.id)
    admin = _create_user(
        factory, f"pg_admin_auto_{uuid4().hex[:10]}", "ADMIN", os.environ["AUTH_SEED_PASSWORD"],
    )
    admin_client = TestClient(app, raise_server_exceptions=False)
    _login(admin_client, admin.username, os.environ["AUTH_SEED_PASSWORD"])
    policy_history = admin_client.get("/api/workflow/configuration/approval_policy/history")
    assert policy_history.status_code == 200, policy_history.text
    current_policy_revision = max(
        (item["revision"] for item in policy_history.json()["items"]),
        default=None,
    )
    _create_configuration_revision(admin_client, "approval_policy", {
        "enabled": False,
        "media_confidence_threshold": 0.85,
        "feasibility_score_threshold_exclusive": 70,
        "feasibility_confidence_threshold": 0.8,
    }, expected_revision=current_policy_revision)
    app.state.auth_workflow_provider = AuthenticatedMockVLMProvider("pass", model_version="mock-1")
    app.state.auth_workflow_media_provider = _SyntheticTaskProvider("MEDIA_COMPLIANCE")
    app.state.auth_workflow_strategy_provider = _SyntheticTaskProvider("STRATEGY_EVALUATION")
    guarded_plan = _create_plan(maker_client, next_checker.id, "Auto approval stays disabled before PO sign-off")
    guarded = _upload_and_submit(maker_client, guarded_plan)
    assert guarded["status"] == "PENDING_APPROVAL"
    assert guarded["processing_stage"] == "HUMAN_REVIEW_REQUIRED"
    assert guarded["ai_evaluations"][0]["provider"] == "MOCK_VLM"
    assert guarded["engine_decisions"][0]["outcome"] == "HUMAN_REVIEW_REQUIRED"
    maker_notice_types = [item["event_type"] for item in maker_client.get("/api/workflow/notifications").json()["items"]]
    assert maker_notice_types.count("PLAN_AUTO_APPROVED") == 0
    with factory() as session:
        assert session.scalar(select(AuthWorkflowNotification.id).where(
            AuthWorkflowNotification.plan_id == UUID(guarded_plan["id"]),
            AuthWorkflowNotification.event_type == "PLAN_AUTO_APPROVED",
        )) is None
    admin_client.close()

    # A notification inserted before an injected failure rolls back with the
    # business transaction for both submission and Checker decisions.
    app.state.auth_workflow_configuration = state["default_configuration"]
    app.state.auth_workflow_provider = AuthenticatedMockVLMProvider("review", model_version="mock-1")
    app.state.auth_workflow_media_provider = None
    app.state.auth_workflow_strategy_provider = None
    rollback_submit_plan = _create_plan(maker_client, next_checker.id, "Synthetic rollback submit")
    upload_response = maker_client.post(
        f"/api/workflow/plans/{rollback_submit_plan['id']}/attachments",
        data={"expected_revision": str(rollback_submit_plan["revision"])},
        files={"file": ("synthetic.png", _png(), "image/png")},
    )
    assert upload_response.status_code == 200, upload_response.text
    original_recorder = workflow._record_notification

    def insert_then_fail(*args, **kwargs):
        original_recorder(*args, **kwargs)
        raise RuntimeError("synthetic notification rollback")

    with monkeypatch.context() as patch:
        patch.setattr(workflow, "_record_notification", insert_then_fail)
        failed_submit = maker_client.post(
            f"/api/workflow/plans/{rollback_submit_plan['id']}/submit",
            json={"expected_revision": upload_response.json()["revision"]},
        )
    assert failed_submit.status_code == 503
    with factory() as session:
        persisted = session.get(AuthWorkflowPlan, UUID(rollback_submit_plan["id"]))
        assert persisted.status == "DRAFT" and persisted.current_version == 0
        assert session.scalar(select(AuthWorkflowNotification.id).where(
            AuthWorkflowNotification.plan_id == persisted.id
        )) is None

    rollback_decision_plan = _create_plan(maker_client, next_checker.id, "Synthetic rollback decision")
    submitted_for_rollback = _upload_and_submit(maker_client, rollback_decision_plan)
    with monkeypatch.context() as patch:
        patch.setattr(workflow, "_record_notification", insert_then_fail)
        failed_decision = next_checker_client.post(
            f"/api/workflow/plans/{rollback_decision_plan['id']}/rounds/1/decision",
            json={
                "action": "APPROVED",
                "reason": "Synthetic rollback check.",
                "override_reason": "Synthetic rollback test.",
            },
        )
    assert failed_decision.status_code == 503
    with factory() as session:
        persisted = session.get(AuthWorkflowPlan, UUID(rollback_decision_plan["id"]))
        assert persisted.status == "PENDING_APPROVAL"
        assert session.scalar(select(AuthWorkflowDecision.id).where(
            AuthWorkflowDecision.plan_id == persisted.id
        )) is None
        assert session.scalar(select(AuthWorkflowNotification.id).where(
            AuthWorkflowNotification.plan_id == persisted.id,
            AuthWorkflowNotification.event_type.in_(("PLAN_APPROVED", "PLAN_REJECTED")),
        )) is None
