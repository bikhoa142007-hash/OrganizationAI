from datetime import timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.backend.api.errors import error_response
from src.backend.application.workflow import ApplicationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.backend.api.auth import AuthenticatedPrincipal, get_auth_db, get_current_principal
from src.backend.api.workflow_dashboard import router
from src.backend.application.workflow_dashboard import get_dashboard
from src.backend.db.base import Base
from src.backend.db.models.auth_workflow import AuthWorkflowPlan


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


def add_plan(session, *, maker_id=None, checker_id=None, status="DRAFT", stage="DRAFT"):
    plan = AuthWorkflowPlan(
        code=f"MKT-{uuid4().hex[:12]}",
        maker_id=maker_id or uuid4(),
        checker_id=checker_id,
        payload={},
        status=status,
        processing_stage=stage,
    )
    session.add(plan)
    return plan


def test_dashboard_returns_zero_counts_for_an_empty_allowed_scope(session):
    maker = principal("MAKER")

    result = get_dashboard(session, maker, "dashboard-empty")

    assert result["counts"] == {
        "draft": 0,
        "pending_ai": 0,
        "human_review": 0,
        "approved": 0,
        "rejected": 0,
    }
    assert result["active_assignments"] == 0
    assert result["principal_scope"] == "MAKER_OWN"
    assert result["as_of"].utcoffset().total_seconds() == 0


def test_dashboard_aggregates_all_visible_rows_and_uses_defined_status_buckets(session):
    maker = principal("MAKER")
    add_plan(session, maker_id=maker.id, status="DRAFT", stage="DRAFT")
    add_plan(session, maker_id=maker.id, status="PENDING_APPROVAL", checker_id=uuid4(), stage="AI_PENDING")
    add_plan(session, maker_id=maker.id, status="PENDING_APPROVAL", checker_id=uuid4(), stage="AI_PROCESSING")
    add_plan(session, maker_id=maker.id, status="PENDING_APPROVAL", checker_id=uuid4(), stage="HUMAN_REVIEW_REQUIRED")
    add_plan(session, maker_id=maker.id, status="PENDING_APPROVAL", checker_id=uuid4(), stage="UNRECOGNIZED_STAGE")
    add_plan(session, maker_id=maker.id, status="APPROVED", stage="AI_AUTO_APPROVED")
    add_plan(session, maker_id=maker.id, status="REJECTED", stage="COMPLETED")
    for _ in range(120):
        add_plan(session, maker_id=maker.id)

    result = get_dashboard(session, maker, "dashboard-buckets")

    assert result["counts"] == {
        "draft": 121,
        "pending_ai": 2,
        "human_review": 2,
        "approved": 1,
        "rejected": 1,
    }
    assert result["active_assignments"] == 4


def test_dashboard_scope_matches_readable_maker_checker_and_admin_rows(session):
    maker = principal("MAKER")
    checker = principal("CHECKER")
    admin = principal("ADMIN")
    add_plan(session, maker_id=maker.id, checker_id=checker.id, status="DRAFT", stage="DRAFT")
    add_plan(session, maker_id=uuid4(), checker_id=checker.id, status="PENDING_APPROVAL", stage="HUMAN_REVIEW_REQUIRED")
    add_plan(session, maker_id=uuid4(), checker_id=uuid4(), status="APPROVED", stage="AI_AUTO_APPROVED")

    maker_result = get_dashboard(session, maker, "dashboard-maker")
    checker_result = get_dashboard(session, checker, "dashboard-checker")
    admin_result = get_dashboard(session, admin, "dashboard-admin")

    assert maker_result["counts"]["draft"] == 1
    assert sum(maker_result["counts"].values()) == 1
    assert checker_result["counts"]["human_review"] == 1
    assert sum(checker_result["counts"].values()) == 2
    assert admin_result["counts"] == {
        "draft": 1,
        "pending_ai": 0,
        "human_review": 1,
        "approved": 1,
        "rejected": 0,
    }
    assert admin_result["principal_scope"] == "ADMIN_READ_ONLY"


def test_dashboard_forbids_a_principal_without_workflow_roles(session):
    from src.backend.application.workflow import ApplicationError

    unauthorized = AuthenticatedPrincipal(
        id=uuid4(),
        user_code="NONE-1",
        username="none-1",
        email=None,
        phone=None,
        display_name="No Workflow Role",
        status="ACTIVE",
        roles=(),
        permissions=(),
    )

    with pytest.raises(ApplicationError) as error:
        get_dashboard(session, unauthorized, "dashboard-forbidden")

    assert error.value.code == "FORBIDDEN"


def test_dashboard_route_enforces_authenticated_workflow_role(session):
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(ApplicationError, lambda _request, error: error_response(error.code, error.message, error.correlation_id))
    app.dependency_overrides[get_auth_db] = lambda: session
    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal(
        id=uuid4(),
        user_code="NONE-1",
        username="none-1",
        email=None,
        phone=None,
        display_name="No Workflow Role",
        status="ACTIVE",
        roles=(),
        permissions=(),
    )

    response = TestClient(app).get("/api/workflow/dashboard")

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_dashboard_route_returns_only_authorized_aggregate(session):
    checker = principal("CHECKER")
    add_plan(
        session,
        maker_id=uuid4(),
        checker_id=checker.id,
        status="PENDING_APPROVAL",
        stage="HUMAN_REVIEW_REQUIRED",
    )

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_auth_db] = lambda: session
    app.dependency_overrides[get_current_principal] = lambda: checker

    response = TestClient(app).get("/api/workflow/dashboard")

    assert response.status_code == 200
    assert set(response.json()) == {"as_of", "principal_scope", "counts", "active_assignments"}
    assert response.json()["principal_scope"] == "CHECKER_ASSIGNED"
    assert response.json()["counts"]["human_review"] == 1
    assert response.json()["active_assignments"] == 1
    assert "plan_id" not in response.json()
