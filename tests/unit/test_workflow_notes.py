from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.backend.api.auth import AuthenticatedPrincipal, get_auth_db, get_current_principal
from src.backend.api.errors import error_response
from src.backend.api.internal_notes import router
from src.backend.application.workflow import ApplicationError
from src.backend.application.workflow_notes import add_internal_note, list_internal_notes
from src.backend.db.base import Base
from src.backend.db.models.auth_workflow import AuthWorkflowPlan, AuthWorkflowVersion
from src.backend.db.models.workflow_internal_note import (
    WorkflowInternalNote,
    WorkflowInternalNoteAuditEvent,
)


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    Base.metadata.drop_all(engine)
    engine.dispose()


def principal(role: str, user_id=None) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        id=user_id or uuid4(),
        user_code=f"{role}-1",
        username=f"{role.lower()}-1",
        email=None,
        phone=None,
        display_name=f"{role.title()} One",
        status="ACTIVE",
        roles=(role,),
        permissions=(),
    )


def add_plan(session, checker_id=None):
    plan = AuthWorkflowPlan(
        code=f"MKT-{uuid4().hex[:12]}",
        maker_id=uuid4(),
        checker_id=checker_id,
        payload={},
        status="PENDING_APPROVAL",
        processing_stage="HUMAN_REVIEW_REQUIRED",
        current_version=1,
        current_round=1,
    )
    session.add(plan)
    session.flush()
    session.add(AuthWorkflowVersion(
        plan_id=plan.id,
        version_number=1,
        round_number=1,
        payload_snapshot={},
        attachment_snapshot=[],
        snapshot_hash="a" * 64,
        submitted_by=plan.maker_id,
    ))
    session.flush()
    return plan


def test_assigned_checker_can_append_note_and_audit_contains_metadata_only(session):
    checker = principal("CHECKER")
    plan = add_plan(session, checker.id)

    note = add_internal_note(
        session, checker, plan.id, 1, "  Keep the label visible.  ", "note-key-1", "corr-note-1"
    )

    audit = session.query(WorkflowInternalNoteAuditEvent).one()
    assert note["content"] == "Keep the label visible."
    assert note["approval_round"] == 1
    assert audit.note_id == note["note_id"]
    assert audit.plan_id == plan.id
    assert audit.actor_id == checker.id
    assert audit.action == "INTERNAL_NOTE_ADDED"
    assert set(audit.__table__.columns.keys()) == {"note_id", "plan_id", "actor_id", "action", "created_at"}
    assert not hasattr(audit, "content")
    assert list_internal_notes(session, checker, plan.id, "corr-note-list") == [note]


def test_only_assigned_checker_can_read_or_write_notes(session):
    checker = principal("CHECKER")
    other_checker = principal("CHECKER")
    maker = principal("MAKER")
    admin = principal("ADMIN")
    plan = add_plan(session, checker.id)

    for caller in (other_checker, maker, admin):
        with pytest.raises(ApplicationError) as error:
            list_internal_notes(session, caller, plan.id, "corr-forbidden")
        assert error.value.code == "FORBIDDEN"
        with pytest.raises(ApplicationError) as write_error:
            add_internal_note(session, caller, plan.id, 1, "private", f"key-{caller.id}", "corr-forbidden")
        assert write_error.value.code == "FORBIDDEN"


def test_note_round_must_belong_to_plan(session):
    checker = principal("CHECKER")
    plan = add_plan(session, checker.id)

    with pytest.raises(ApplicationError) as error:
        add_internal_note(session, checker, plan.id, 2, "Private note", "note-key-2", "corr-round")

    assert error.value.code == "VALIDATION_ERROR"
    assert session.query(WorkflowInternalNote).count() == 0


@pytest.mark.parametrize("content", ["   ", "\n\t"])
def test_note_content_must_not_be_empty_after_trim(session, content):
    checker = principal("CHECKER")
    plan = add_plan(session, checker.id)

    with pytest.raises(ApplicationError) as error:
        add_internal_note(session, checker, plan.id, None, content, "note-key-empty", "corr-empty")

    assert error.value.code == "VALIDATION_ERROR"
    assert session.query(WorkflowInternalNote).count() == 0


def test_note_content_limit_is_checked_after_trim(session):
    checker = principal("CHECKER")
    plan = add_plan(session, checker.id)

    accepted = add_internal_note(session, checker, plan.id, None, f"  {'x' * 4000}  ", "note-key-max", "corr-max")

    assert len(accepted["content"]) == 4000
    with pytest.raises(ApplicationError) as error:
        add_internal_note(session, checker, plan.id, None, "x" * 4001, "note-key-too-long", "corr-too-long")
    assert error.value.code == "VALIDATION_ERROR"


def test_note_idempotency_replays_same_body_and_rejects_key_reuse(session):
    checker = principal("CHECKER")
    plan = add_plan(session, checker.id)

    first = add_internal_note(session, checker, plan.id, 1, "Private note", "same-key", "corr-1")
    replay = add_internal_note(session, checker, plan.id, 1, " Private note ", "same-key", "corr-2")

    assert replay["note_id"] == first["note_id"]
    assert session.query(WorkflowInternalNote).count() == 1
    assert session.query(WorkflowInternalNoteAuditEvent).count() == 1
    with pytest.raises(ApplicationError) as error:
        add_internal_note(session, checker, plan.id, 1, "Different note", "same-key", "corr-3")
    assert error.value.code == "IDEMPOTENCY_CONFLICT"


def test_audit_failure_rolls_back_note_insert(session):
    checker = principal("CHECKER")
    plan = add_plan(session, checker.id)
    session.execute(text("""
        CREATE TRIGGER fail_internal_note_audit
        BEFORE INSERT ON workflow_internal_note_audit_events
        BEGIN SELECT RAISE(ABORT, 'audit unavailable'); END
    """))
    session.commit()

    with pytest.raises(ApplicationError) as error:
        add_internal_note(session, checker, plan.id, 1, "Private note", "audit-failure", "corr-audit-fail")

    assert error.value.code == "UNAVAILABLE"
    assert session.query(WorkflowInternalNote).count() == 0
    assert session.query(WorkflowInternalNoteAuditEvent).count() == 0


def test_internal_note_api_is_checker_only_and_returns_private_envelope(session):
    checker = principal("CHECKER")
    plan = add_plan(session, checker.id)
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(
        ApplicationError,
        lambda _request, error: error_response(error.code, error.message, error.correlation_id),
    )
    app.dependency_overrides[get_auth_db] = lambda: session
    app.dependency_overrides[get_current_principal] = lambda: checker
    client = TestClient(app)

    response = client.post(
        f"/api/workflow/plans/{plan.id}/internal-notes",
        headers={"Idempotency-Key": "api-note-key"},
        json={"approval_round": 1, "content": "  Internal review detail  "},
    )
    listed = client.get(f"/api/workflow/plans/{plan.id}/internal-notes")

    assert response.status_code == 201
    assert response.json()["content"] == "Internal review detail"
    assert response.json()["approval_round"] == 1
    assert listed.status_code == 200
    assert listed.json()["items"] == [response.json()]
    assert response.json()["created_at"].endswith("Z") or "+00:00" in response.json()["created_at"]
