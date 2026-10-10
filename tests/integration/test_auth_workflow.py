from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
import json
import struct
from uuid import UUID, uuid4
import zlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine

from src.ai_pipeline.providers.base import ProviderAnalysis
from src.ai_pipeline.providers.mock import AuthenticatedMockVLMProvider
from src.ai_pipeline.task_evaluation import STRATEGY_CRITERIA, media_policy_from_json, strategy_rubric_from_json
from src.ai_pipeline.task_providers import TaskModelSettings
from src.backend.api.app import create_app
from src.backend.api.auth import get_auth_db
from src.backend.api.dependencies import Settings
from src.backend.application import auth_workflow as auth_workflow_application
from src.backend.db.base import Base
from src.backend.db.models import AuthWorkflowEvaluationRun, AuthWorkflowPlan, Role, User, UserRole
from src.backend.db.security import hash_password
from src.backend.domain.policy import (
    ApprovalConfiguration,
    AuthoritySnapshot,
    BudgetConfiguration,
    Criterion,
    MANDATORY_FIELDS,
    PolicySnapshot,
)


def png_chunk(kind: bytes, content: bytes) -> bytes:
    body = kind + content
    return struct.pack(">I", len(content)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


PNG = (
    b"\x89PNG\r\n\x1a\n"
    + png_chunk(b"IHDR", struct.pack(">2I5B", 1, 1, 8, 6, 0, 0, 0))
    + png_chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00\xff"))
    + png_chunk(b"IEND", b"")
)


@pytest.fixture
def workflow_client(monkeypatch) -> Iterator[tuple[TestClient, sessionmaker[Session], object]]:
    monkeypatch.setenv("JWT_SECRET", "test-only-auth-secret-that-is-at-least-32-bytes")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    monkeypatch.setenv("AUTH_COOKIE_SAMESITE", "lax")
    monkeypatch.setenv("AUTH_WORKFLOW_AI_PROVIDER", "MOCK_VLM")
    monkeypatch.setenv("AUTH_WORKFLOW_MOCK_SCENARIO", "malformed")
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory.begin() as session:
        for code in ("MAKER", "CHECKER", "ADMIN"):
            session.add(Role(id=uuid4(), code=code, name=code.title(), description=None))
    app = create_app(Settings(app_env="demo", cors_origins=("http://localhost:5173",)))

    def override_db() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_auth_db] = override_db
    with TestClient(app) as client:
        yield client, factory, app
    engine.dispose()


def create_user(factory, username: str, roles: tuple[str, ...]) -> User:
    with factory.begin() as session:
        user = User(
            id=uuid4(),
            user_code=f"USR-{uuid4().hex[:12].upper()}",
            username=username,
            email=f"{username}@example.com",
            phone=None,
            password_hash=hash_password("Local-demo-password-123"),
            display_name=username.title(),
            status="ACTIVE",
        )
        session.add(user)
        session.flush()
        for code in roles:
            role = session.scalar(select(Role).where(Role.code == code))
            session.add(UserRole(user_id=user.id, role_id=role.id))
        session.flush()
        session.expunge(user)
    return user


def login(client: TestClient, user: User) -> None:
    response = client.post("/api/auth/login", json={
        "identifier": user.username,
        "password": "Local-demo-password-123",
    })
    assert response.status_code == 200


def authenticated_client(app, user: User) -> TestClient:
    client = TestClient(app)
    login(client, user)
    return client


def make_plan(client: TestClient, checker_id: UUID, *, title: str = "Spring campaign",
              channels: tuple[str, ...] = ()) -> dict:
    response = client.post("/api/workflow/plans", json={
        "checker_user_id": str(checker_id),
        "payload": {
            "title": title,
            "objective": "Reach qualified customers",
            "summary": "A measured campaign with a clear audience and outcome.",
            "department": "marketing",
            "start_date": "2026-10-01",
            "end_date": "2026-10-31",
            "budget_minor_units": "50000000",
            "currency": "VND",
            "channels": list(channels),
        },
    })
    assert response.status_code == 201, response.text
    return response.json()


def auto_approval_configuration(checker_id: UUID) -> ApprovalConfiguration:
    media_policy = media_policy_from_json('''{
      "policy_id":"TEST-MEDIA","policy_version":"1","status":"ACTIVE",
      "scope_departments":["marketing"],"scope_channels":["social"],
      "rules":[{"rule_id":"TEST-LOGO","severity":"WARNING","description":"Test evidence rule",
        "required_evidence_kinds":["OBSERVATION"]}]
    }''')
    rubric = strategy_rubric_from_json(json.dumps({
        "rubric_id": "TEST-STRATEGY", "rubric_version": "1", "status": "ACTIVE",
        "criteria": [
            {"criterion_id": key, "label": label, "weight": weight}
            for key, label, weight in STRATEGY_CRITERIA
        ],
    }))
    media_settings = _task_settings("MEDIA_COMPLIANCE")
    strategy_settings = _task_settings("STRATEGY_EVALUATION")
    return ApprovalConfiguration(
        PolicySnapshot(
            "TEST-AUTH-POLICY", "TEST-AUTH-POLICY-1", True, MANDATORY_FIELDS,
            tuple(Criterion(key, weight) for key, _label, weight in STRATEGY_CRITERIA), ("mock-1",),
            ("image/png", "image/jpeg", "image/webp"), 5_000_000,
        ),
        (BudgetConfiguration("TEST-AUTH-BUDGET", "VND", 0, "100000000", "marketing", True),),
        AuthoritySnapshot(
            "TEST-AUTH-AUTHORITY", "VND", "100000000", ("marketing",),
            str(checker_id), str(checker_id), str(checker_id), True,
        ),
        media_policy=media_policy,
        strategy_rubric=rubric,
        media_model_snapshot=media_settings.public_snapshot(),
        strategy_model_snapshot=strategy_settings.public_snapshot(),
    )


def _task_settings(task: str) -> TaskModelSettings:
    model = "test-media-model" if task == "MEDIA_COMPLIANCE" else "test-strategy-model"
    return TaskModelSettings(
        task=task, provider="OPENAI_COMPATIBLE_CHAT_COMPLETIONS",
        base_url=f"http://localhost:8000/v1/{task.lower()}", model_id=model,
        model_version=f"{model}-rev-1", api_key="test-secret", timeout_seconds=2,
        max_output_tokens=1024, max_response_bytes=4096, max_input_bytes=4096,
        max_retries=0, prompt_version=f"{task.lower()}-prompt-v1",
        schema_version=f"{task.lower()}-schema-v1",
    )


class FakeAuthenticatedTaskProvider:
    def __init__(self, task: str):
        self.settings = _task_settings(task)
        self.task = task
        self.calls = 0

    def evaluate(self, request):
        self.calls += 1
        if self.task == "MEDIA_COMPLIANCE":
            reference = next(item["evidence_id"] for item in request.evidence if item["kind"] == "OBSERVATION")
            output = {
                "policy_id": request.policy.policy_id, "policy_version": request.policy.policy_version,
                "outcome": "PASS", "confidence": 0.93, "reason": "Test policy check passed.",
                "rule_results": [{"rule_id": rule.rule_id, "result": "PASS",
                                  "rationale": "Cited test observation supports the check.",
                                  "evidence_refs": [reference]} for rule in request.policy.rules],
                "findings": [], "evidence_conflicts": [],
            }
        else:
            output = {
                "rubric_id": request.rubric.rubric_id,
                "rubric_version": request.rubric.rubric_version,
                "total_score": 71, "confidence": 0.82,
                "criterion_scores": [{
                    "criterion_id": item.criterion_id, "score": 71,
                    "rationale": "Grounded in the synthetic test plan.",
                    "evidence_refs": ["plan-field:objective"],
                } for item in request.rubric.criteria],
                "assumptions": [], "missing_facts": [], "critical_gaps": [],
                "evidence_conflicts": [], "reason": "Synthetic test evaluation.",
            }
        return ProviderAnalysis(output, model_revision=self.settings.model_version,
                                reported_model_id=self.settings.model_id)


class LowConfidenceMediaProvider(FakeAuthenticatedTaskProvider):
    def evaluate(self, request):
        analysis = super().evaluate(request)
        output = dict(analysis.output)
        output["confidence"] = 0.80
        return ProviderAnalysis(output, model_revision=analysis.model_revision,
                                reported_model_id=analysis.reported_model_id)


def upload_plan_image(client: TestClient, plan_id: str, revision: int) -> dict:
    response = client.post(
        f"/api/workflow/plans/{plan_id}/attachments",
        data={"expected_revision": str(revision)},
        files={"file": ("campaign.png", PNG, "image/png")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def submit_plan(client: TestClient, plan: dict) -> dict:
    response = client.post(
        f"/api/workflow/plans/{plan['id']}/submit",
        json={"expected_revision": plan["revision"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_auth_cookie_is_required_and_does_not_authenticate_judge_demo(workflow_client):
    client, factory, _app = workflow_client
    maker = create_user(factory, "maker.one", ("MAKER",))
    checker = create_user(factory, "checker.one", ("CHECKER",))

    assert client.get("/api/workflow/plans").status_code == 401
    login(client, maker)
    assert client.get("/api/workflow/plans").status_code == 200
    # The authenticated cookie is not a Judge Demo identity.
    assert client.get("/api/plans").status_code == 401
    # Judge Demo remains available only through its separate demo actor header.
    assert client.get("/api/plans", headers={"X-Demo-Actor": "DEMO-MAKER-01"}).status_code == 200
    assert maker.id != checker.id


def test_maker_is_assigned_from_cookie_and_cannot_read_another_makers_plan(workflow_client):
    client, factory, app = workflow_client
    maker = create_user(factory, "maker.one", ("MAKER",))
    other_maker = create_user(factory, "maker.two", ("MAKER",))
    checker = create_user(factory, "checker.one", ("CHECKER",))
    login(client, maker)

    spoofed = client.post("/api/workflow/plans", json={
        "maker_id": str(other_maker.id),
        "role": "CHECKER",
        "checker_user_id": str(checker.id),
        "payload": {"title": "Spoof attempt"},
    })
    assert spoofed.status_code == 422

    plan = make_plan(client, checker.id)
    assert plan["maker_id"] == str(maker.id)
    assert plan["status"] == "DRAFT"
    assert plan["checker_id"] == str(checker.id)
    assert plan["history"][-1]["action"] == "CREATED"

    other_client = authenticated_client(app, other_maker)
    assert other_client.get(f"/api/workflow/plans/{plan['id']}").status_code == 404


def test_admin_can_read_workflow_plans_but_cannot_mutate_or_recover(workflow_client):
    client, factory, app = workflow_client
    maker = create_user(factory, "maker.admin-read", ("MAKER",))
    checker = create_user(factory, "checker.admin-read", ("CHECKER",))
    admin = create_user(factory, "admin.read-only", ("ADMIN",))
    login(client, maker)
    plan = make_plan(client, checker.id, title="Admin-readable plan")
    plan = upload_plan_image(client, plan["id"], plan["revision"])

    admin_client = authenticated_client(app, admin)
    listed = admin_client.get("/api/workflow/plans")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [plan["id"]]
    detail = admin_client.get(f"/api/workflow/plans/{plan['id']}")
    assert detail.status_code == 200
    assert detail.json()["payload"]["title"] == "Admin-readable plan"
    attachment_id = detail.json()["attachments"][0]["id"]
    assert admin_client.get(
        f"/api/workflow/plans/{plan['id']}/attachments/{attachment_id}"
    ).status_code == 404
    assert admin_client.post("/api/workflow/plans", json={
        "checker_user_id": str(checker.id),
        "payload": plan["payload"],
    }).status_code == 403
    assert admin_client.put(f"/api/workflow/plans/{plan['id']}", json={
        "expected_revision": plan["revision"],
        "payload": plan["payload"],
    }).status_code == 403
    assert admin_client.post(
        f"/api/workflow/plans/{plan['id']}/submit",
        json={"expected_revision": plan["revision"]},
    ).status_code == 403
    assert admin_client.post(
        f"/api/workflow/plans/{plan['id']}/rounds/1/decision",
        json={"action": "REJECTED", "reason": "Admin cannot decide."},
    ).status_code == 403
    assert admin_client.post(
        f"/api/workflow/plans/{plan['id']}/rounds/1/decision",
        json={"action": "APPROVED", "override_reason": "Admin cannot decide."},
    ).status_code == 403
    assert admin_client.post(
        f"/api/workflow/plans/{plan['id']}/rounds/1/recovery",
    ).status_code == 403


def test_admin_maker_gets_maker_permissions_without_checker_authority(workflow_client):
    client, factory, app = workflow_client
    admin_maker = create_user(factory, "admin.maker", ("ADMIN", "MAKER"))
    other_maker = create_user(factory, "other.maker", ("MAKER",))
    checker = create_user(factory, "checker.admin-maker", ("CHECKER",))

    login(client, admin_maker)
    checkers = client.get("/api/workflow/checkers")
    assert checkers.status_code == 200
    assert str(admin_maker.id) not in {item["id"] for item in checkers.json()}
    assert str(checker.id) in {item["id"] for item in checkers.json()}

    own_plan = make_plan(client, checker.id, title="Admin Maker draft")
    assert own_plan["maker_id"] == str(admin_maker.id)
    updated_payload = {**own_plan["payload"], "title": "Admin Maker edited draft"}
    updated = client.put(f"/api/workflow/plans/{own_plan['id']}", json={
        "expected_revision": own_plan["revision"],
        "payload": updated_payload,
    })
    assert updated.status_code == 200, updated.text
    assert updated.json()["payload"]["title"] == "Admin Maker edited draft"

    updated_plan = upload_plan_image(client, own_plan["id"], updated.json()["revision"])
    submitted = submit_plan(client, updated_plan)
    assert submitted["status"] == "PENDING_APPROVAL"
    assert submitted["current_version"] == 1
    assert submitted["current_round"] == 1

    other_client = authenticated_client(app, other_maker)
    other_plan = make_plan(other_client, checker.id, title="Other Maker draft")
    all_plans = client.get("/api/workflow/plans")
    assert all_plans.status_code == 200
    assert {item["id"] for item in all_plans.json()} >= {own_plan["id"], other_plan["id"]}

    cross_owner_edit = client.put(f"/api/workflow/plans/{other_plan['id']}", json={
        "expected_revision": other_plan["revision"],
        "payload": other_plan["payload"],
    })
    assert cross_owner_edit.status_code == 404

    self_checker_assignment = other_client.post("/api/workflow/plans", json={
        "checker_user_id": str(admin_maker.id),
        "payload": {"title": "Cannot assign Admin Maker as Checker"},
    })
    assert self_checker_assignment.status_code == 422
    assert client.get("/api/workflow/reviews").status_code == 403
    self_approval = client.post(
        f"/api/workflow/plans/{own_plan['id']}/rounds/1/decision",
        json={"action": "APPROVED"},
    )
    assert self_approval.status_code == 403


def test_admin_audit_endpoint_is_paginated_and_denied_to_maker(workflow_client):
    maker_client, factory, app = workflow_client
    maker = create_user(factory, "maker.audit-view", ("MAKER",))
    checker = create_user(factory, "checker.audit-view", ("CHECKER",))
    admin = create_user(factory, "admin.audit-view", ("ADMIN",))
    login(maker_client, maker)
    plan = make_plan(maker_client, checker.id, title="Audited plan")

    denied = maker_client.get("/api/workflow/audit")
    assert denied.status_code == 403
    admin_client = authenticated_client(app, admin)
    response = admin_client.get("/api/workflow/audit?offset=0&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["offset"] == 0
    assert data["limit"] == 10
    created = next(item for item in data["items"] if item["action"] == "CREATED")
    assert created["plan_id"] == plan["id"]
    assert created["plan_code"] == plan["code"]
    assert created["actor_name"] == maker.display_name


def test_draft_creation_replays_an_idempotency_key_without_duplicate_plan_or_event(workflow_client):
    client, factory, app = workflow_client
    maker = create_user(factory, "maker.idempotent-create", ("MAKER",))
    checker = create_user(factory, "checker.idempotent-create", ("CHECKER",))
    other_maker = create_user(factory, "maker.other-idempotent-create", ("MAKER",))
    login(client, maker)
    headers = {"Idempotency-Key": "draft-intent-1"}
    body = {
        "checker_user_id": str(checker.id),
        "payload": {"title": "Retry-safe draft"},
    }

    first = client.post("/api/workflow/plans", json=body, headers=headers)
    replay = client.post("/api/workflow/plans", json=body, headers=headers)
    assert first.status_code == replay.status_code == 201
    assert first.json()["id"] == replay.json()["id"]

    client.cookies.clear()
    unauthenticated_retry = client.post("/api/workflow/plans", json=body, headers=headers)
    assert unauthenticated_retry.status_code == 401
    login(client, maker)

    other_client = authenticated_client(app, other_maker)
    other_owner_same_key = other_client.post("/api/workflow/plans", json=body, headers=headers)
    assert other_owner_same_key.status_code == 201
    assert other_owner_same_key.json()["id"] != first.json()["id"]
    assert other_owner_same_key.json()["maker_id"] == str(other_maker.id)
    assert other_client.get(f"/api/workflow/plans/{first.json()['id']}").status_code == 404

    changed_body = {**body, "payload": {"title": "Different draft"}}
    conflict = client.post("/api/workflow/plans", json=changed_body, headers=headers)
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    with factory() as session:
        assert session.query(AuthWorkflowPlan).filter_by(maker_id=maker.id).count() == 1
        assert session.query(AuthWorkflowPlan).filter_by(maker_id=other_maker.id).count() == 1
        assert session.query(auth_workflow_application.AuthWorkflowEvent).filter_by(
            plan_id=UUID(first.json()["id"]), action="CREATED",
        ).count() == 1


def test_checker_picker_includes_active_checkers_and_excludes_self_and_disabled_accounts(workflow_client):
    client, factory, _app = workflow_client
    dual_user = create_user(factory, "maker.checker-picker", ("MAKER", "CHECKER"))
    active_checker = create_user(factory, "checker.active-picker", ("CHECKER",))
    disabled_checker = create_user(factory, "checker.disabled-picker", ("CHECKER",))
    with factory.begin() as session:
        session.get(User, disabled_checker.id).status = "DISABLED"
    login(client, dual_user)

    response = client.get("/api/workflow/checkers")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(active_checker.id)]
    self_assignment = client.post("/api/workflow/plans", json={
        "checker_user_id": str(dual_user.id),
        "payload": {"title": "Cannot self-check"},
    })
    assert self_assignment.status_code == 422


def test_maker_submits_and_only_assigned_checker_can_approve(workflow_client):
    client, factory, app = workflow_client
    maker = create_user(factory, "maker.one", ("MAKER",))
    checker = create_user(factory, "checker.one", ("CHECKER",))
    outsider = create_user(factory, "checker.two", ("CHECKER",))
    admin = create_user(factory, "admin.audit-reason", ("ADMIN",))
    login(client, maker)

    draft = make_plan(client, checker.id)
    draft = upload_plan_image(client, draft["id"], draft["revision"])
    submitted = submit_plan(client, draft)
    assert submitted["status"] == "PENDING_APPROVAL"
    assert submitted["current_version"] == 1
    assert submitted["current_round"] == 1
    assert submitted["processing_stage"] == "HUMAN_REVIEW_REQUIRED"
    assert submitted["versions"][0]["payload"]["title"] == "Spring campaign"
    assert len(submitted["ai_evaluations"]) == 1
    assert submitted["ai_evaluations"][0]["status"] in {"FAILED", "TIMED_OUT"}
    assert submitted["ai_evaluations"][0]["provider"] == "MOCK_VLM"
    assert submitted["ai_evaluations"][0]["attempts"] == 1
    assert submitted["ai_evaluations"][0]["retried"] is False
    assert submitted["engine_decisions"][0]["outcome"] == "HUMAN_REVIEW_REQUIRED"
    locked_edit = client.put(f"/api/workflow/plans/{draft['id']}", json={
        "expected_revision": submitted["revision"],
        "payload": submitted["payload"],
    })
    assert locked_edit.status_code == 409
    locked_upload = client.post(
        f"/api/workflow/plans/{draft['id']}/attachments",
        data={"expected_revision": str(submitted["revision"])},
        files={"file": ("late.png", PNG, "image/png")},
    )
    assert locked_upload.status_code == 409

    self_decision = client.post(
        f"/api/workflow/plans/{draft['id']}/rounds/1/decision",
        json={"action": "APPROVED"},
    )
    assert self_decision.status_code == 403
    attachment_id = submitted["attachments"][0]["id"]
    assert client.get(f"/api/workflow/plans/{draft['id']}/attachments/{attachment_id}").status_code == 200

    checker_client = authenticated_client(app, checker)
    queue = checker_client.get("/api/workflow/reviews")
    assert queue.status_code == 200
    assert [item["id"] for item in queue.json()] == [draft["id"]]

    outsider_client = authenticated_client(app, outsider)
    assert outsider_client.get(f"/api/workflow/plans/{draft['id']}").status_code == 404
    assert outsider_client.post(
        f"/api/workflow/plans/{draft['id']}/rounds/1/decision",
        json={"action": "APPROVED"},
    ).status_code == 404

    decision_url = f"/api/workflow/plans/{draft['id']}/rounds/1/decision"
    approved = checker_client.post(decision_url, json={
        "action": "APPROVED", "reason": "Reviewed.",
        "override_reason": "Provider configuration was unavailable; reviewed the submission manually.",
    })
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    replay = checker_client.post(decision_url, json={
        "action": "APPROVED", "reason": "Reviewed.",
        "override_reason": "Provider configuration was unavailable; reviewed the submission manually.",
    })
    assert replay.status_code == 200
    assert replay.json()["revision"] == approved.json()["revision"]
    detail = checker_client.get(f"/api/workflow/plans/{draft['id']}").json()
    assert detail["history"][-1]["action"] == "APPROVED"
    assert detail["history"][-1]["actor_id"] == str(checker.id)
    audit = authenticated_client(app, admin).get("/api/workflow/audit?offset=0&limit=100").json()
    decision_event = next(
        event for event in audit["items"]
        if event["plan_id"] == draft["id"] and event["action"] == "APPROVED"
    )
    assert decision_event["details"]["reason"] == "Reviewed."
    assert decision_event["details"]["override_reason"] == (
        "Provider configuration was unavailable; reviewed the submission manually."
    )


def test_authenticated_submission_uses_existing_policy_for_auto_approval(workflow_client):
    client, factory, app = workflow_client
    maker = create_user(factory, "maker.auto", ("MAKER",))
    checker = create_user(factory, "checker.auto", ("CHECKER",))
    login(client, maker)
    app.state.auth_workflow_configuration = auto_approval_configuration(checker.id)
    app.state.auth_workflow_provider = AuthenticatedMockVLMProvider("pass", model_version="mock-1")
    app.state.auth_workflow_media_provider = FakeAuthenticatedTaskProvider("MEDIA_COMPLIANCE")
    app.state.auth_workflow_strategy_provider = FakeAuthenticatedTaskProvider("STRATEGY_EVALUATION")

    draft = make_plan(client, checker.id, title="Eligible campaign", channels=("social",))
    draft = upload_plan_image(client, draft["id"], draft["revision"])
    submitted = submit_plan(client, draft)

    assert submitted["status"] == "APPROVED", json.dumps(submitted["ai_evaluations"][0], indent=2)
    assert submitted["processing_stage"] == "AI_AUTO_APPROVED"
    assert submitted["ai_evaluations"][0]["status"] == "SUCCEEDED"
    assert submitted["ai_evaluations"][0]["provider"] == "MOCK_VLM"
    assert submitted["ai_evaluations"][0]["media_evaluation"]["status"] == "SUCCEEDED"
    assert submitted["ai_evaluations"][0]["strategy_evaluation"]["status"] == "SUCCEEDED"
    assert submitted["ai_evaluations"][0]["strategy_evaluation"]["result"]["feasibility_score"] == 71
    assert submitted["engine_decisions"][0]["outcome"] == "AUTO_APPROVED"
    assert submitted["engine_decisions"][0]["decision"]["budget_validation"]["result"] == "PASS"
    assert len([event for event in submitted["history"] if event["action"] == "AI_AUTO_APPROVED"]) == 1
    saved_media, saved_strategy = submitted["ai_evaluations"][0]["media_evaluation"], submitted["ai_evaluations"][0]["strategy_evaluation"]
    reloaded = client.get(f"/api/workflow/plans/{draft['id']}").json()
    assert reloaded["ai_evaluations"][0]["media_evaluation"] == saved_media
    assert reloaded["ai_evaluations"][0]["strategy_evaluation"] == saved_strategy
    assert app.state.auth_workflow_media_provider.calls == 1
    assert app.state.auth_workflow_strategy_provider.calls == 1
    assert app.state.auth_workflow_provider.calls == 1


def test_authenticated_provider_failure_is_persisted_and_checker_can_review(workflow_client):
    client, factory, app = workflow_client
    maker = create_user(factory, "maker.timeout", ("MAKER",))
    checker = create_user(factory, "checker.timeout", ("CHECKER",))
    login(client, maker)
    app.state.auth_workflow_provider = AuthenticatedMockVLMProvider("timeout", model_version="mock-1")
    app.state.auth_workflow_configuration = auto_approval_configuration(checker.id)
    app.state.auth_workflow_media_provider = FakeAuthenticatedTaskProvider("MEDIA_COMPLIANCE")
    app.state.auth_workflow_strategy_provider = FakeAuthenticatedTaskProvider("STRATEGY_EVALUATION")

    draft = make_plan(client, checker.id, title="Provider timeout campaign")
    draft = upload_plan_image(client, draft["id"], draft["revision"])
    submitted = submit_plan(client, draft)

    assert submitted["status"] == "PENDING_APPROVAL"
    assert submitted["processing_stage"] == "HUMAN_REVIEW_REQUIRED"
    assert submitted["ai_evaluations"][0]["status"] == "TIMED_OUT", json.dumps(submitted["ai_evaluations"][0], indent=2)
    assert submitted["ai_evaluations"][0]["provider"] == "MOCK_VLM"
    assert submitted["ai_evaluations"][0]["attempts"] == 3
    assert submitted["ai_evaluations"][0]["retried"] is True
    assert submitted["engine_decisions"][0]["outcome"] == "HUMAN_REVIEW_REQUIRED"
    assert "EVAL_VALID" in submitted["engine_decisions"][0]["decision"]["reason"]

    checker_client = authenticated_client(app, checker)
    decision = checker_client.post(
        f"/api/workflow/plans/{draft['id']}/rounds/1/decision",
        json={
            "action": "APPROVED",
            "reason": "Reviewed after provider timeout.",
            "override_reason": "Approved after checking the submitted media manually.",
        },
    )
    assert decision.status_code == 200, decision.text
    assert decision.json()["status"] == "APPROVED"
    assert decision.json()["history"][-1]["details"]["override_reason"] == (
        "Approved after checking the submitted media manually."
    )


def test_review_recommendation_routes_to_checker_without_deciding_the_final_action(workflow_client):
    client, _factory, app = workflow_client
    maker = create_user(_factory, "maker.review-recommendation", ("MAKER",))
    checker = create_user(_factory, "checker.review-recommendation", ("CHECKER",))
    login(client, maker)
    app.state.auth_workflow_configuration = auto_approval_configuration(checker.id)
    app.state.auth_workflow_provider = AuthenticatedMockVLMProvider("pass", model_version="mock-1")
    app.state.auth_workflow_media_provider = LowConfidenceMediaProvider("MEDIA_COMPLIANCE")
    app.state.auth_workflow_strategy_provider = FakeAuthenticatedTaskProvider("STRATEGY_EVALUATION")

    draft = make_plan(client, checker.id, title="Human review recommendation", channels=("social",))
    draft = upload_plan_image(client, draft["id"], draft["revision"])
    submitted = submit_plan(client, draft)
    evaluation = submitted["ai_evaluations"][0]["evaluation"]
    assert evaluation is not None, json.dumps(submitted, indent=2)
    assert evaluation["proposed_action"] == "RECOMMEND_HUMAN_REVIEW", json.dumps(submitted, indent=2)
    assert submitted["engine_decisions"][0]["outcome"] == "HUMAN_REVIEW_REQUIRED"
    assert submitted["processing_stage"] == "HUMAN_REVIEW_REQUIRED"
    assert submitted["status"] == "PENDING_APPROVAL"

    checker_client = authenticated_client(app, checker)
    decision_url = f"/api/workflow/plans/{draft['id']}/rounds/1/decision"
    approval_without_override = checker_client.post(decision_url, json={
        "action": "APPROVED", "reason": "Review completed.",
    })
    assert approval_without_override.status_code == 422

    rejection = checker_client.post(decision_url, json={
        "action": "REJECTED", "reason": "The plan needs a measurable KPI.",
    })
    assert rejection.status_code == 200, rejection.text
    assert rejection.json()["status"] == "REJECTED"
    assert rejection.json()["processing_stage"] == "COMPLETED"
    final_event = rejection.json()["history"][-1]
    assert final_event["action"] == "REJECTED"
    assert final_event["details"]["override_reason"] is None


def test_local_vlm_extraction_persists_separately_and_missing_evaluators_route_checker(workflow_client):
    import json

    import httpx

    from src.ai_pipeline.providers.openai_provider import LocalVLMProvider

    client, factory, app = workflow_client
    captured = []
    extraction = {
        "images": [{
            "image_index": 0,
            "status": "COMPLETE",
            "ocr_text": "Visible campaign headline",
            "observations": ["A blue campaign banner."],
            "uncertainties": [],
            "confidence": 0.97,
            "object_detections": ["campaign banner"],
            "visual_quality": {"result": "PASS", "findings": []},
        }],
    }

    def inference(request):
        captured.append(request)
        return httpx.Response(200, json={
            "model": "runtime-model-name",
            "system_fingerprint": "runtime-revision-1",
            "choices": [{
                "message": {"role": "assistant", "content": json.dumps(extraction)},
                "finish_reason": "stop",
            }],
        })

    app.state.auth_workflow_provider = LocalVLMProvider(
        model="configured-model-id",
        base_url="http://localhost:8000/v1",
        client=httpx.Client(transport=httpx.MockTransport(inference)),
    )
    maker = create_user(factory, "maker.vlm", ("MAKER",))
    checker = create_user(factory, "checker.vlm", ("CHECKER",))
    login(client, maker)
    draft = make_plan(client, checker.id, title="Local VLM extraction")
    attached = upload_plan_image(client, draft["id"], draft["revision"])

    response = client.post(
        f"/api/workflow/plans/{draft['id']}/submit",
        json={"expected_revision": attached["revision"]},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    evaluation_run = result["ai_evaluations"][0]
    visual = evaluation_run["visual_extraction"]

    assert len(captured) == 1
    assert result["processing_stage"] == "HUMAN_REVIEW_REQUIRED"
    assert result["status"] == "PENDING_APPROVAL"
    assert result["engine_decisions"][0]["outcome"] == "HUMAN_REVIEW_REQUIRED"
    assert evaluation_run["status"] == "FAILED"
    assert evaluation_run["model_id"] == "configured-model-id"
    assert evaluation_run["model_version"] is None
    assert evaluation_run["evaluation"]["media_result"] is None
    assert evaluation_run["evaluation"]["feasibility_score"] is None
    assert evaluation_run["media_evaluation"]["status"] == "NOT_CONFIGURED"
    assert evaluation_run["strategy_evaluation"]["status"] == "NOT_CONFIGURED"
    assert "MEDIA_NOT_CONFIGURED" in {
        error["code"] for error in evaluation_run["evaluation"]["agent_errors"]
    }, json.dumps(evaluation_run["evaluation"], indent=2)
    assert visual["status"] == "SUCCEEDED"
    assert visual["schema_version"] == "visual-extraction-schema-v2"
    assert visual["attachments"][0]["confidence"] == 0.97
    assert visual["attachments"][0]["object_detections"] == ["campaign banner"]
    assert visual["attachments"][0]["visual_quality"] == {"result": "PASS", "findings": []}
    assert visual["model_id"] == "configured-model-id"
    assert visual["model_revision"] == "runtime-revision-1"
    assert visual["attachments"][0]["attachment_id"] == attached["attachments"][0]["id"]
    assert visual["attachments"][0]["content_hash"] == attached["attachments"][0]["content_hash"]
    assert visual["attachments"][0]["evidence"][0]["text"] == "Visible campaign headline"
    assert evaluation_run["evaluation"]["evidence"][0]["source_ref"] == attached["attachments"][0]["id"]
    assert app.state.auth_workflow_configuration.policy.auto_approval_policy_enabled is False


def test_stale_run_with_invalid_policy_routes_to_checker_review(workflow_client, monkeypatch):
    client, factory, app = workflow_client
    maker = create_user(factory, "maker.recovery", ("MAKER",))
    checker = create_user(factory, "checker.recovery", ("CHECKER",))
    login(client, maker)

    def leave_run_queued(session, plan_id, _round_number, _orchestrator, _correlation_id):
        plan = session.get(AuthWorkflowPlan, plan_id)
        return auth_workflow_application._plan_dict(session, plan)

    monkeypatch.setattr(auth_workflow_application, "evaluate_submission", leave_run_queued)
    draft = make_plan(client, checker.id, title="Interrupted evaluation")
    draft = upload_plan_image(client, draft["id"], draft["revision"])
    queued = submit_plan(client, draft)
    assert queued["processing_stage"] == "AI_PENDING"
    checker_client = authenticated_client(app, checker)
    early_recovery = checker_client.post(
        f"/api/workflow/plans/{queued['id']}/rounds/1/recovery",
    )
    assert early_recovery.status_code == 200
    assert early_recovery.json()["processing_stage"] == "AI_PENDING"
    assert len(early_recovery.json()["history"]) == len(queued["history"])
    assert client.post(
        f"/api/workflow/plans/{queued['id']}/rounds/1/recovery",
    ).status_code == 403

    with factory.begin() as session:
        run = session.scalar(select(AuthWorkflowEvaluationRun).where(
            AuthWorkflowEvaluationRun.plan_id == UUID(queued["id"]),
            AuthWorkflowEvaluationRun.round_number == 1,
        ))
        run.created_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        run.policy_snapshot = {"invalid": True}

    with factory() as session:
        event_count_before = len(session.scalars(select(auth_workflow_application.AuthWorkflowEvent).where(
            auth_workflow_application.AuthWorkflowEvent.plan_id == UUID(queued["id"]),
        )).all())
        decision_count_before = len(session.scalars(select(auth_workflow_application.AuthWorkflowEngineDecision).where(
            auth_workflow_application.AuthWorkflowEngineDecision.plan_id == UUID(queued["id"]),
        )).all())

    detail = client.get(f"/api/workflow/plans/{queued['id']}")
    assert detail.status_code == 200, detail.text
    still_queued = detail.json()
    assert still_queued["processing_stage"] == "AI_PENDING"
    assert still_queued["ai_evaluations"][0]["status"] == "PENDING"
    with factory() as session:
        event_count_after_get = len(session.scalars(select(auth_workflow_application.AuthWorkflowEvent).where(
            auth_workflow_application.AuthWorkflowEvent.plan_id == UUID(queued["id"]),
        )).all())
        decision_count_after_get = len(session.scalars(select(auth_workflow_application.AuthWorkflowEngineDecision).where(
            auth_workflow_application.AuthWorkflowEngineDecision.plan_id == UUID(queued["id"]),
        )).all())
    assert event_count_after_get == event_count_before
    assert decision_count_after_get == decision_count_before

    recovered_response = checker_client.post(
        f"/api/workflow/plans/{queued['id']}/rounds/1/recovery",
    )
    assert recovered_response.status_code == 200, recovered_response.text
    recovered = recovered_response.json()
    assert recovered["processing_stage"] == "HUMAN_REVIEW_REQUIRED"
    assert recovered["status"] == "PENDING_APPROVAL"
    assert recovered["ai_evaluations"][0]["status"] == "FAILED"
    assert recovered["ai_evaluations"][0]["evaluation"]["agent_errors"][0]["code"] == (
        "POLICY_SNAPSHOT_INVALID"
    )
    assert recovered["history"][-1]["action"] == "AI_RECOVERY_REVIEW_ROUTED"

    # A retry after the recovery is committed is an idempotent read of that result.
    replay = checker_client.post(f"/api/workflow/plans/{queued['id']}/rounds/1/recovery")
    assert replay.status_code == 200
    assert replay.json()["history"] == recovered["history"]


def test_submission_accepts_zero_budget_but_rejects_negative_budget(workflow_client):
    client, factory, _app = workflow_client
    maker = create_user(factory, "maker.zero-budget", ("MAKER",))
    checker = create_user(factory, "checker.zero-budget", ("CHECKER",))
    login(client, maker)

    zero_budget = make_plan(client, checker.id, title="Zero budget plan")
    payload = {**zero_budget["payload"], "budget_minor_units": "0"}
    zero_budget = client.put(f"/api/workflow/plans/{zero_budget['id']}", json={
        "payload": payload,
        "checker_user_id": str(checker.id),
        "expected_revision": zero_budget["revision"],
    }).json()
    zero_budget = upload_plan_image(client, zero_budget["id"], zero_budget["revision"])
    submitted = submit_plan(client, zero_budget)
    assert submitted["status"] == "PENDING_APPROVAL"
    assert submitted["versions"][0]["payload"]["budget_minor_units"] == "0"

    negative_budget = make_plan(client, checker.id, title="Negative budget plan")
    payload = {**negative_budget["payload"], "budget_minor_units": "-1"}
    negative_budget = client.put(f"/api/workflow/plans/{negative_budget['id']}", json={
        "payload": payload,
        "checker_user_id": str(checker.id),
        "expected_revision": negative_budget["revision"],
    }).json()
    negative_budget = upload_plan_image(client, negative_budget["id"], negative_budget["revision"])
    response = client.post(f"/api/workflow/plans/{negative_budget['id']}/submit", json={
        "expected_revision": negative_budget["revision"],
    })
    assert response.status_code == 422
    assert client.get(f"/api/workflow/plans/{negative_budget['id']}").json()["status"] == "DRAFT"


def test_late_vlm_result_cannot_replace_a_run_recovered_during_inference(workflow_client):
    import json

    import httpx

    from src.ai_pipeline.providers.openai_provider import LocalVLMProvider

    client, factory, app = workflow_client
    maker = create_user(factory, "maker.late-vlm", ("MAKER",))
    checker = create_user(factory, "checker.late-vlm", ("CHECKER",))
    login(client, maker)
    captured = []
    plan_id = None

    def finish_after_recovery(_request):
        captured.append(True)
        with factory.begin() as session:
            run = session.scalar(select(AuthWorkflowEvaluationRun).where(
                AuthWorkflowEvaluationRun.plan_id == UUID(plan_id),
                AuthWorkflowEvaluationRun.round_number == 1,
            ))
            run.started_at = datetime.now(timezone.utc) - timedelta(minutes=3)
        with factory() as recovery_session:
            auth_workflow_application.recover_stale_evaluations(
                recovery_session,
                "late-vlm-test",
                age_seconds=120,
                visible_plan_ids=(UUID(plan_id),),
            )
        extraction = {
            "images": [{
                "image_index": 0,
                "status": "COMPLETE",
                "ocr_text": "Late output must not replace recovery.",
                "observations": [],
                "uncertainties": [],
            }],
        }
        return httpx.Response(200, json={
            "model": "runtime-model-name",
            "choices": [{
                "message": {"role": "assistant", "content": json.dumps(extraction)},
                "finish_reason": "stop",
            }],
        })

    app.state.auth_workflow_provider = LocalVLMProvider(
        model="configured-model-id",
        base_url="http://localhost:8000/v1",
        client=httpx.Client(transport=httpx.MockTransport(finish_after_recovery)),
    )
    draft = make_plan(client, checker.id, title="Slow inference")
    plan_id = draft["id"]
    attached = upload_plan_image(client, plan_id, draft["revision"])

    response = client.post(
        f"/api/workflow/plans/{plan_id}/submit",
        json={"expected_revision": attached["revision"]},
    )

    assert response.status_code == 200, response.text
    assert captured == [True]
    recovered = response.json()
    run = recovered["ai_evaluations"][0]
    assert recovered["processing_stage"] == "HUMAN_REVIEW_REQUIRED"
    assert run["status"] == "FAILED"
    assert run["evaluation"]["agent_errors"][0]["code"] == "RUN_INTERRUPTED"
    assert run["visual_extraction"]["error_code"] == "RUN_INTERRUPTED"
    assert "Late output must not replace recovery." not in json.dumps(run)
    assert len(recovered["engine_decisions"]) == 1
    assert recovered["history"][-1]["action"] == "AI_RECOVERY_REVIEW_ROUTED"


def test_rejection_needs_reason_and_resubmission_preserves_prior_version(workflow_client):
    client, factory, app = workflow_client
    maker = create_user(factory, "maker.one", ("MAKER",))
    checker = create_user(factory, "checker.one", ("CHECKER",))
    login(client, maker)
    draft = make_plan(client, checker.id)
    draft = upload_plan_image(client, draft["id"], draft["revision"])
    submitted = submit_plan(client, draft)

    checker_client = authenticated_client(app, checker)
    decision_url = f"/api/workflow/plans/{draft['id']}/rounds/1/decision"
    assert checker_client.post(decision_url, json={"action": "REJECTED", "reason": "  "}).status_code == 422
    rejected = checker_client.post(
        decision_url,
        json={
            "action": "REJECTED", "reason": "Add clearer measurement targets.",
            "override_reason": "Provider configuration was unavailable; reviewed the submission manually.",
        },
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "REJECTED"

    updated = client.put(f"/api/workflow/plans/{draft['id']}", json={
        "expected_revision": rejected.json()["revision"],
        "payload": {
            "title": "Spring campaign revised",
            "objective": "Reach qualified customers",
            "summary": "A revised campaign with measurement targets.",
            "start_date": "2026-10-01",
            "end_date": "2026-10-31",
            "budget_minor_units": "50000000",
            "currency": "VND",
        },
        "checker_user_id": str(checker.id),
    })
    assert updated.status_code == 200, updated.text
    resubmitted = submit_plan(client, updated.json())
    assert resubmitted["status"] == "PENDING_APPROVAL"
    assert resubmitted["current_version"] == 2
    assert resubmitted["current_round"] == 2
    assert len(resubmitted["ai_evaluations"]) == 2
    assert resubmitted["ai_evaluations"][0]["input_hash"] != resubmitted["ai_evaluations"][1]["input_hash"]
    assert [version["payload"]["title"] for version in resubmitted["versions"]] == [
        "Spring campaign", "Spring campaign revised",
    ]
    assert submitted["versions"][0]["payload"]["title"] == "Spring campaign"


def test_maker_submission_requires_attachment(workflow_client):
    client, factory, app = workflow_client
    maker = create_user(factory, "maker.one", ("MAKER",))
    checker = create_user(factory, "checker.one", ("CHECKER",))
    maker_client = authenticated_client(app, maker)
    draft = make_plan(maker_client, checker.id)
    response = maker_client.post(
        f"/api/workflow/plans/{draft['id']}/submit",
        json={"expected_revision": draft["revision"]},
    )
    assert response.status_code == 422
    current = maker_client.get(f"/api/workflow/plans/{draft['id']}")
    assert current.json()["status"] == "DRAFT"


def test_submission_rejects_incomplete_plan_even_when_attachment_exists(workflow_client):
    client, factory, _app = workflow_client
    maker = create_user(factory, "maker.one", ("MAKER",))
    checker = create_user(factory, "checker.one", ("CHECKER",))
    login(client, maker)
    created = client.post("/api/workflow/plans", json={
        "checker_user_id": str(checker.id),
        "payload": {"title": "Incomplete campaign"},
    })
    assert created.status_code == 201
    attached = upload_plan_image(client, created.json()["id"], created.json()["revision"])
    response = client.post(
        f"/api/workflow/plans/{created.json()['id']}/submit",
        json={"expected_revision": attached["revision"]},
    )
    assert response.status_code == 422


def test_attachment_mime_and_image_contents_must_match(workflow_client):
    client, factory, _app = workflow_client
    maker = create_user(factory, "maker.one", ("MAKER",))
    checker = create_user(factory, "checker.one", ("CHECKER",))
    login(client, maker)
    plan = make_plan(client, checker.id)

    fake_jpeg = client.post(
        f"/api/workflow/plans/{plan['id']}/attachments",
        data={"expected_revision": str(plan["revision"])},
        files={"file": ("fake.jpg", b"\xff\xd8\xffarbitrary bytes", "image/jpeg")},
    )
    mismatched_mime = client.post(
        f"/api/workflow/plans/{plan['id']}/attachments",
        data={"expected_revision": str(plan["revision"])},
        files={"file": ("image.jpg", PNG, "image/jpeg")},
    )

    assert fake_jpeg.status_code == 422
    assert mismatched_mime.status_code == 422
