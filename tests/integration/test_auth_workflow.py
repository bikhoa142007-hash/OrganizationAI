from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
import struct
from uuid import UUID, uuid4
import zlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine

from src.ai_pipeline.providers.mock import MockVLMProvider
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


def make_plan(client: TestClient, checker_id: UUID, *, title: str = "Spring campaign") -> dict:
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
        },
    })
    assert response.status_code == 201, response.text
    return response.json()


def auto_approval_configuration(checker_id: UUID) -> ApprovalConfiguration:
    return ApprovalConfiguration(
        PolicySnapshot(
            "TEST-AUTH-POLICY", "TEST-AUTH-POLICY-1", True, MANDATORY_FIELDS,
            (Criterion("strategy", 100),), ("mock-1",),
            ("image/png", "image/jpeg", "image/webp"), 5_000_000,
        ),
        (BudgetConfiguration("TEST-AUTH-BUDGET", "VND", 0, "100000000", "marketing", True),),
        AuthoritySnapshot(
            "TEST-AUTH-AUTHORITY", "VND", "100000000", ("marketing",),
            str(checker_id), str(checker_id), str(checker_id), True,
        ),
    )


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


def test_maker_submits_and_only_assigned_checker_can_approve(workflow_client):
    client, factory, app = workflow_client
    maker = create_user(factory, "maker.one", ("MAKER",))
    checker = create_user(factory, "checker.one", ("CHECKER",))
    outsider = create_user(factory, "checker.two", ("CHECKER",))
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
    assert submitted["ai_evaluations"][0]["provider"] == "LOCAL_VLM"
    assert submitted["ai_evaluations"][0]["attempts"] == 2
    assert submitted["ai_evaluations"][0]["retried"] is True
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


def test_authenticated_submission_uses_existing_policy_for_auto_approval(workflow_client):
    client, factory, app = workflow_client
    maker = create_user(factory, "maker.auto", ("MAKER",))
    checker = create_user(factory, "checker.auto", ("CHECKER",))
    login(client, maker)
    app.state.auth_workflow_provider = MockVLMProvider("pass", model_version="mock-1")
    app.state.auth_workflow_configuration = auto_approval_configuration(checker.id)

    draft = make_plan(client, checker.id, title="Eligible campaign")
    draft = upload_plan_image(client, draft["id"], draft["revision"])
    submitted = submit_plan(client, draft)

    assert submitted["status"] == "APPROVED"
    assert submitted["processing_stage"] == "AI_AUTO_APPROVED"
    assert submitted["ai_evaluations"][0]["status"] == "SUCCEEDED"
    assert submitted["ai_evaluations"][0]["provider"] == "MOCK_VLM"
    assert submitted["engine_decisions"][0]["outcome"] == "AUTO_APPROVED"
    assert submitted["engine_decisions"][0]["decision"]["budget_validation"]["result"] == "PASS"
    assert len([event for event in submitted["history"] if event["action"] == "AI_AUTO_APPROVED"]) == 1


def test_authenticated_provider_failure_is_persisted_and_checker_can_review(workflow_client):
    client, factory, app = workflow_client
    maker = create_user(factory, "maker.timeout", ("MAKER",))
    checker = create_user(factory, "checker.timeout", ("CHECKER",))
    login(client, maker)
    app.state.auth_workflow_provider = MockVLMProvider("timeout", model_version="mock-1")
    app.state.auth_workflow_configuration = auto_approval_configuration(checker.id)

    draft = make_plan(client, checker.id, title="Provider timeout campaign")
    draft = upload_plan_image(client, draft["id"], draft["revision"])
    submitted = submit_plan(client, draft)

    assert submitted["status"] == "PENDING_APPROVAL"
    assert submitted["processing_stage"] == "HUMAN_REVIEW_REQUIRED"
    assert submitted["ai_evaluations"][0]["status"] == "TIMED_OUT"
    assert submitted["ai_evaluations"][0]["provider"] == "MOCK_VLM"
    assert submitted["ai_evaluations"][0]["attempts"] == 2
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


def test_stale_run_with_invalid_policy_routes_to_checker_review(workflow_client, monkeypatch):
    client, factory, _app = workflow_client
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

    with factory.begin() as session:
        run = session.scalar(select(AuthWorkflowEvaluationRun).where(
            AuthWorkflowEvaluationRun.plan_id == UUID(queued["id"]),
            AuthWorkflowEvaluationRun.round_number == 1,
        ))
        run.created_at = datetime.now(timezone.utc) - timedelta(minutes=2)
        run.policy_snapshot = {"invalid": True}

    detail = client.get(f"/api/workflow/plans/{queued['id']}")
    assert detail.status_code == 200, detail.text
    recovered = detail.json()
    assert recovered["processing_stage"] == "HUMAN_REVIEW_REQUIRED"
    assert recovered["status"] == "PENDING_APPROVAL"
    assert recovered["ai_evaluations"][0]["status"] == "FAILED"
    assert recovered["ai_evaluations"][0]["evaluation"]["agent_errors"][0]["code"] == (
        "POLICY_SNAPSHOT_INVALID"
    )
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


def test_non_workflow_role_cannot_create_and_submission_requires_attachment(workflow_client):
    client, factory, app = workflow_client
    admin = create_user(factory, "admin.one", ("ADMIN",))
    maker = create_user(factory, "maker.one", ("MAKER",))
    checker = create_user(factory, "checker.one", ("CHECKER",))
    login(client, admin)
    assert client.get("/api/workflow/plans").status_code == 403
    assert client.post("/api/workflow/plans", json={"payload": {}}).status_code == 403

    maker_client = authenticated_client(app, maker)
    draft = make_plan(maker_client, checker.id)
    response = maker_client.post(
        f"/api/workflow/plans/{draft['id']}/submit",
        json={"expected_revision": draft["revision"]},
    )
    assert response.status_code == 422


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
