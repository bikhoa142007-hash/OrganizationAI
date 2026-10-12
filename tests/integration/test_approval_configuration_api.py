from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from src.backend.api import approval_configuration as configuration_api
from src.backend.api.auth import AuthenticatedPrincipal, get_auth_db, get_current_principal
from src.backend.application import approval_configuration
from src.backend.application.workflow import ApplicationError
from src.backend.db.base import Base
from src.backend.db.models.approval_configuration import AuthWorkflowRoundConfigurationSnapshot
from src.backend.db.models.auth_workflow import AuthWorkflowPlan, AuthWorkflowVersion
from src.backend.db.models.employee import EmployeeProfile
from src.backend.db.models import Role, User, UserRole


@pytest.fixture
def configuration_postgres():
    """Use an explicitly named, run-specific PostgreSQL target; never inherit DATABASE_URL."""
    url = os.environ.get("SCOPE1_B_POSTGRES_TEST_URL", "").strip()
    if not url.startswith("postgresql+psycopg://"):
        pytest.skip("Set SCOPE1_B_POSTGRES_TEST_URL to a disposable PostgreSQL database for this run.")
    schema = f"scope1_b_{uuid4().hex[:20]}"
    base_engine = create_engine(url, pool_pre_ping=True)
    with base_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, pool_pre_ping=True, connect_args={"options": f"-csearch_path={schema}"})
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    try:
        yield engine, factory
    finally:
        engine.dispose()
        with base_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base_engine.dispose()


def _principal(user: User, roles: tuple[str, ...]) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        id=user.id,
        user_code=user.user_code,
        username=user.username,
        email=user.email,
        phone=user.phone,
        display_name=user.display_name,
        status="ACTIVE",
        roles=roles,
        permissions=(),
    )


def _app(factory, principal):
    app = FastAPI()
    app.state.allowed_origins = {"http://localhost"}
    app.include_router(configuration_api.router)

    def db_session():
        with factory() as session:
            yield session

    app.dependency_overrides[get_auth_db] = db_session
    app.dependency_overrides[get_current_principal] = lambda: principal

    @app.exception_handler(ApplicationError)
    async def application_error(_request: Request, exc: ApplicationError):
        status = {"UNAUTHENTICATED": 401, "FORBIDDEN": 403, "NOT_FOUND": 404, "CONFLICT": 409, "VALIDATION_ERROR": 422}.get(exc.code, 503)
        return JSONResponse(status_code=status, content={"code": exc.code, "message": exc.message, "correlation_id": exc.correlation_id})

    return TestClient(app)


def _admin(factory):
    with factory.begin() as session:
        for code in ("ADMIN", "MAKER"):
            if session.scalar(select(Role).where(Role.code == code)) is None:
                session.add(Role(code=code, name=code.title(), is_builtin=True))
        session.flush()
        suffix = uuid4().hex[:12]
        user = User(
            user_code=f"B-ADMIN-{suffix}", username=f"b_admin_{suffix}",
            email=f"b_admin_{suffix}@example.test", password_hash="synthetic-test-only",
            display_name="Synthetic config administrator", status="ACTIVE",
        )
        session.add(user)
        session.flush()
        admin_role = session.scalar(select(Role).where(Role.code == "ADMIN"))
        session.add(UserRole(user_id=user.id, role_id=admin_role.id))
        session.flush()
        return user


def test_admin_api_returns_unconfigured_and_rejects_maker(configuration_postgres):
    _engine, factory = configuration_postgres
    admin_user = _admin(factory)
    admin_client = _app(factory, _principal(admin_user, ("ADMIN",)))
    response = admin_client.get("/api/workflow/configuration")
    assert response.status_code == 200
    assert len(response.json()["items"]) == 6
    assert {item["status"] for item in response.json()["items"]} == {"UNCONFIGURED"}

    maker_client = _app(factory, _principal(admin_user, ("MAKER",)))
    assert maker_client.get("/api/workflow/configuration").status_code == 403


def test_admin_revision_requires_allowed_browser_origin_and_keeps_auto_approval_off(configuration_postgres):
    _engine, factory = configuration_postgres
    admin_user = _admin(factory)
    client = _app(factory, _principal(admin_user, ("ADMIN",)))
    body = {
        "expected_revision": None,
        "effective_at": (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),
        "change_reason": "Synthetic API acceptance fixture.",
        "value": {
            "enabled": False,
            "media_confidence_threshold": 0.85,
            "feasibility_score_threshold_exclusive": 70,
            "feasibility_confidence_threshold": 0.8,
        },
    }
    assert client.post("/api/workflow/configuration/approval_policy/revisions", json=body, headers={"Origin": "http://evil.invalid"}).status_code == 403
    response = client.post("/api/workflow/configuration/approval_policy/revisions", json=body, headers={"Origin": "http://localhost"})
    assert response.status_code == 201
    assert response.json()["value"]["enabled"] is False


def test_concurrent_first_revision_has_exactly_one_winner(configuration_postgres):
    _engine, factory = configuration_postgres
    admin_user = _admin(factory)
    principal = _principal(admin_user, ("ADMIN",))
    barrier = Barrier(2)
    body = {
        "currency": "VND",
        "limits": [{"department": "Synthetic Department", "limit_minor_units": "100", "active": True}],
    }

    def write(index: int):
        barrier.wait(timeout=10)
        with factory() as session:
            try:
                return approval_configuration.create_configuration_revision(
                    session,
                    principal,
                    f"concurrent-config-{index}",
                    kind="budget",
                    expected_revision=None,
                    effective_at=datetime.now(timezone.utc) + timedelta(seconds=index),
                    change_reason="Synthetic concurrent first write.",
                    value=body,
                )["revision_id"]
            except ApplicationError as exc:
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(write, (1, 2)))
    assert outcomes.count("CONFLICT") == 1
    assert len([value for value in outcomes if value != "CONFLICT"]) == 1


def test_round_version_and_configuration_snapshot_rollback_together(configuration_postgres):
    _engine, factory = configuration_postgres
    maker = _admin(factory)
    suffix = uuid4().hex[:12]
    with factory.begin() as session:
        checker_role = session.scalar(select(Role).where(Role.code == "CHECKER"))
        if checker_role is None:
            checker_role = Role(code="CHECKER", name="Checker", is_builtin=True)
            session.add(checker_role)
            session.flush()
        checker = User(
            user_code=f"B-CHECKER-{suffix}", username=f"b_checker_{suffix}",
            email=f"b_checker_{suffix}@example.test", password_hash="synthetic-test-only",
            display_name="Synthetic Checker", status="ACTIVE",
        )
        session.add(checker)
        session.flush()
        session.add(UserRole(user_id=checker.id, role_id=checker_role.id))
        session.add(EmployeeProfile(
            user_code=checker.user_code, display_name=checker.display_name, email=checker.email,
            department="Synthetic", employment_status="ACTIVE", user_id=checker.id,
        ))
        checker_id = checker.id

    plan_id = None
    with pytest.raises(RuntimeError, match="abort synthetic approval round"):
        with factory.begin() as session:
            plan = AuthWorkflowPlan(
                code=f"B-ROUND-{suffix}", maker_id=maker.id, checker_id=checker_id,
                payload={"department": "Synthetic"}, status="PENDING_APPROVAL",
                processing_stage="HUMAN_REVIEW_REQUIRED", current_version=1, current_round=1,
            )
            session.add(plan)
            session.flush()
            plan_id = plan.id
            session.add(AuthWorkflowVersion(
                plan_id=plan.id, version_number=1, round_number=1,
                payload_snapshot=plan.payload, attachment_snapshot=[], submitted_by=maker.id,
            ))
            session.flush()
            approval_configuration.capture_round_configuration_snapshot(
                session,
                plan_id=plan.id,
                plan_version=1,
                approval_round=1,
                department_id="Synthetic",
                maker_id=maker.id,
                selected_checker_id=checker_id,
                effective_at=datetime.now(timezone.utc),
            )
            raise RuntimeError("abort synthetic approval round")

    with factory() as session:
        assert session.get(AuthWorkflowPlan, plan_id) is None
        assert session.scalar(select(AuthWorkflowVersion.id).where(
            AuthWorkflowVersion.plan_id == plan_id,
            AuthWorkflowVersion.round_number == 1,
        )) is None
        assert session.scalar(select(AuthWorkflowRoundConfigurationSnapshot.id).where(
            AuthWorkflowRoundConfigurationSnapshot.plan_id == plan_id,
            AuthWorkflowRoundConfigurationSnapshot.approval_round == 1,
        )) is None
