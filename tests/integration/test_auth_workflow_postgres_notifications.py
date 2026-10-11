"""PostgreSQL-backed acceptance checks for authenticated workflow notifications.

The PostgreSQL runner provisions the database, temporary users, and password.
This module deliberately fails when those inputs are missing instead of skipping.
"""
from __future__ import annotations

import json
import os
import struct
import zlib
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from scripts.postgres_test_target import verify_runner_provisioned_database

from src.ai_pipeline.providers.base import ProviderAnalysis
from src.ai_pipeline.providers.mock import AuthenticatedMockVLMProvider
from src.ai_pipeline.task_evaluation import STRATEGY_CRITERIA, media_policy_from_json, strategy_rubric_from_json
from src.ai_pipeline.task_providers import TaskModelSettings
from src.backend.api.app import create_app
from src.backend.api.auth import get_auth_db
from src.backend.api.dependencies import Settings
from src.backend.application import auth_workflow as workflow
from src.backend.db.models import (
    AuthWorkflowDecision,
    AuthWorkflowNotification,
    AuthWorkflowPlan,
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
        session.flush()
        session.expunge(user)
    return user


def _login(client: TestClient, username: str, password: str) -> None:
    response = client.post("/api/auth/login", json={"identifier": username, "password": password})
    assert response.status_code == 200, response.text


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
            model_revision=self.settings.model_version,
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

    # Controlled auto approval runs only with this test's synthetic DB policy.
    app = state["app"]
    app.state.auth_workflow_configuration = _auto_approval_configuration(next_checker.id)
    app.state.auth_workflow_provider = AuthenticatedMockVLMProvider("pass", model_version="mock-1")
    app.state.auth_workflow_media_provider = _SyntheticTaskProvider("MEDIA_COMPLIANCE")
    app.state.auth_workflow_strategy_provider = _SyntheticTaskProvider("STRATEGY_EVALUATION")
    auto_plan = _create_plan(maker_client, next_checker.id, "Synthetic auto approval notification")
    auto_approved = _upload_and_submit(maker_client, auto_plan)
    assert auto_approved["status"] == "APPROVED"
    assert auto_approved["processing_stage"] == "AI_AUTO_APPROVED"
    assert auto_approved["ai_evaluations"][0]["provider"] == "MOCK_VLM"
    assert auto_approved["engine_decisions"][0]["outcome"] == "AUTO_APPROVED"
    maker_notice_types = [item["event_type"] for item in maker_client.get("/api/workflow/notifications").json()["items"]]
    assert maker_notice_types.count("PLAN_AUTO_APPROVED") == 1
    auto_notice = next(item for item in maker_client.get("/api/workflow/notifications").json()["items"]
                       if item["event_type"] == "PLAN_AUTO_APPROVED")
    with factory.begin() as session:
        existing = session.get(AuthWorkflowNotification, UUID(auto_notice["id"]))
        plan_row = session.get(AuthWorkflowPlan, UUID(auto_plan["id"]))
        replay = workflow._record_notification(
            session,
            recipient_user_id=maker.id,
            plan=plan_row,
            event_type="PLAN_AUTO_APPROVED",
            version_number=1,
            round_number=1,
        )
        assert replay.id == existing.id
    with factory() as session:
        assert session.scalar(select(AuthWorkflowNotification).where(
            AuthWorkflowNotification.plan_id == UUID(auto_plan["id"]),
            AuthWorkflowNotification.event_type == "PLAN_AUTO_APPROVED",
        )) is not None
        assert session.scalar(select(AuthWorkflowNotification.id).where(
            AuthWorkflowNotification.plan_id == UUID(auto_plan["id"]),
            AuthWorkflowNotification.event_type == "PLAN_AUTO_APPROVED",
        ).limit(2)) is not None
        assert len(session.scalars(select(AuthWorkflowNotification).where(
            AuthWorkflowNotification.plan_id == UUID(auto_plan["id"]),
            AuthWorkflowNotification.event_type == "PLAN_AUTO_APPROVED",
        )).all()) == 1

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
