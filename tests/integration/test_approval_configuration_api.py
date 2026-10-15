from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import UUID, uuid4
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import selectinload, sessionmaker

from src.backend.api import approval_configuration as configuration_api
from src.backend.api import auth_workflow
from src.backend.api.auth import AuthenticatedPrincipal, _user_roles, get_auth_db, get_current_principal
from src.backend.application import approval_configuration, employee_admin, role_admin
from scripts.postgres_test_target import verify_runner_provisioned_database
from src.backend.application.workflow import ApplicationError
from src.backend.db.base import Base
from src.backend.db.models.approval_configuration import AuthWorkflowRoundConfigurationSnapshot
from src.backend.db.models.auth_workflow import AuthWorkflowPlan, AuthWorkflowVersion
from src.backend.db.models.employee import EmployeeProfile
from src.backend.db.models import AdminAuditEvent, AuthWorkflowEvent, Role, RolePermission, User, UserRole


@pytest.fixture
def configuration_postgres():
    """Use only a run-scoped PostgreSQL target verified before any schema writes."""
    explicit_url = os.environ.get("SCOPE1_B_POSTGRES_TEST_URL", "").strip()
    target_environment = os.environ.copy()
    if explicit_url:
        target_environment["DATABASE_URL"] = explicit_url
    if not target_environment.get("DATABASE_URL", "").strip():
        pytest.skip("A verified run-scoped PostgreSQL test target is required.")
    try:
        url = verify_runner_provisioned_database(target_environment)
    except RuntimeError as error:
        pytest.fail(str(error), pytrace=False)
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


def _principal(
    user: User,
    roles: tuple[str, ...],
    *,
    permissions: tuple[str, ...] | None = None,
) -> AuthenticatedPrincipal:
    effective_permissions = permissions if permissions is not None else tuple(sorted({
        permission
        for role in roles
        for permission in role_admin.BUILTIN_PERMISSIONS.get(role, ())
    }))
    return AuthenticatedPrincipal(
        id=user.id,
        user_code=user.user_code,
        username=user.username,
        email=user.email,
        phone=user.phone,
        display_name=user.display_name,
        status="ACTIVE",
        roles=roles,
        permissions=effective_permissions,
    )


def _app(factory, principal, *, include_workflow: bool = False):
    app = FastAPI()
    app.state.allowed_origins = {"http://localhost"}
    app.include_router(configuration_api.router)
    if include_workflow:
        app.include_router(auth_workflow.router)

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


def test_checker_assignment_config_requires_approver_permission(configuration_postgres):
    _engine, factory = configuration_postgres
    admin = _admin(factory)
    permissions = tuple(
        permission for permission in role_admin.BUILTIN_PERMISSIONS["ADMIN"]
        if permission != "ADMIN_APPROVER_MANAGE"
    )
    client = _app(factory, _principal(admin, ("ADMIN",), permissions=permissions))

    history = client.get("/api/workflow/configuration/checker_assignment/history")
    assert history.status_code == 403

    revision = client.post(
        "/api/workflow/configuration/checker_assignment/revisions",
        json={
            "expected_revision": None,
            "effective_at": (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(),
            "change_reason": "Synthetic denied permission test.",
            "value": {"maker_may_select_other": False, "defaults": []},
        },
    )
    assert revision.status_code == 403


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
    with factory() as session:
        audit = session.scalar(select(AdminAuditEvent).where(
            AdminAuditEvent.action == "WORKFLOW_CONFIG_REVISION_CREATED",
        ))
        assert audit is not None
        assert audit.after_state["result"] == "SUCCESS"


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

def _linked_employee(factory, prefix: str) -> tuple[UUID, UUID]:
    suffix = uuid4().hex[:12]
    user_code = f"{prefix}-{suffix}"
    with factory.begin() as session:
        user = User(
            user_code=user_code,
            username=f"{prefix.lower()}_{suffix}",
            email=f"{prefix.lower()}_{suffix}@example.test",
            password_hash="synthetic-test-only",
            display_name=f"Synthetic {prefix}",
            status="ACTIVE",
            employment_status="ACTIVE",
            activation_pending=False,
        )
        session.add(user)
        session.flush()
        profile = EmployeeProfile(
            user_code=user_code,
            display_name=user.display_name,
            email=user.email,
            employment_status="ACTIVE",
            user_id=user.id,
        )
        session.add(profile)
        session.flush()
        return profile.id, user.id


def test_postgres_employee_role_filter_uses_permissions_across_custom_roles(configuration_postgres):
    _engine, factory = configuration_postgres
    admin = _admin(factory)
    principal = _principal(admin, ("ADMIN",))
    maker_profile_id, maker_user_id = _linked_employee(factory, "GOV-SPLIT-MAKER")
    checker_profile_id, checker_user_id = _linked_employee(factory, "GOV-SPLIT-CHECKER")
    role_specs = (
        (
            "CUSTOM_GOV_SPLIT_MAKER_CORE",
            "Synthetic Maker core",
            ["MARKETING_PLAN_READ", "MARKETING_PLAN_CREATE", "MARKETING_PLAN_EDIT_OWN"],
        ),
        (
            "CUSTOM_GOV_SPLIT_MAKER_SUBMIT",
            "Synthetic Maker submit",
            ["MARKETING_ATTACHMENT_MANAGE", "MARKETING_PLAN_SUBMIT", "MARKETING_HISTORY_READ"],
        ),
        (
            "CUSTOM_GOV_SPLIT_CHECKER_CORE",
            "Synthetic Checker core",
            ["MARKETING_PLAN_READ", "MARKETING_REVIEW_ASSIGNED", "MARKETING_APPROVE"],
        ),
        (
            "CUSTOM_GOV_SPLIT_CHECKER_FINALIZE",
            "Synthetic Checker finalize",
            ["MARKETING_REJECT", "MARKETING_HISTORY_READ"],
        ),
    )

    for code, name, permissions in role_specs:
        with factory() as session:
            role_admin.create_role(
                session,
                principal,
                "synthetic-split-role-test",
                code,
                name,
                "Synthetic split-bundle acceptance role.",
                permissions,
            )

    with factory() as session:
        role_admin.replace_employee_roles(
            session,
            principal,
            maker_profile_id,
            "synthetic-split-role-test",
            ["CUSTOM_GOV_SPLIT_MAKER_CORE", "CUSTOM_GOV_SPLIT_MAKER_SUBMIT"],
        )
        role_admin.replace_employee_roles(
            session,
            principal,
            checker_profile_id,
            "synthetic-split-role-test",
            ["CUSTOM_GOV_SPLIT_CHECKER_CORE", "CUSTOM_GOV_SPLIT_CHECKER_FINALIZE"],
        )

    with factory() as session:
        user_options = selectinload(User.user_roles).selectinload(UserRole.role).selectinload(Role.permissions)
        maker = session.scalar(select(User).options(user_options).where(User.id == maker_user_id))
        checker = session.scalar(select(User).options(user_options).where(User.id == checker_user_id))
        assert maker is not None and "MAKER" in _user_roles(maker)
        assert checker is not None and "CHECKER" in _user_roles(checker)

    with _app(factory, principal, include_workflow=True) as client:
        maker_response = client.get("/api/workflow/employees", params={"role": "MAKER"})
        checker_response = client.get("/api/workflow/employees", params={"role": "CHECKER"})

    assert maker_response.status_code == 200, maker_response.text
    assert maker_profile_id in {UUID(item["id"]) for item in maker_response.json()["items"]}
    assert checker_response.status_code == 200, checker_response.text
    assert checker_profile_id in {UUID(item["id"]) for item in checker_response.json()["items"]}


def test_postgres_employee_update_rejects_status_mass_assignment(configuration_postgres):
    _engine, factory = configuration_postgres
    admin = _admin(factory)
    principal = _principal(admin, ("ADMIN",))
    profile_id, checker_id = _linked_employee(factory, "GOV-STATUS")
    suffix = uuid4().hex[:12]

    with factory.begin() as session:
        checker_role = session.scalar(select(Role).where(Role.code == "CHECKER"))
        if checker_role is None:
            checker_role = Role(code="CHECKER", name="Checker", is_builtin=True)
            session.add(checker_role)
            session.flush()
        session.add(UserRole(user_id=checker_id, role_id=checker_role.id))
        session.add(AuthWorkflowPlan(
            code=f"GOV-STATUS-{suffix}",
            maker_id=admin.id,
            checker_id=checker_id,
            payload={"department": "Synthetic"},
            status="PENDING_APPROVAL",
            processing_stage="HUMAN_REVIEW_REQUIRED",
            current_version=1,
            current_round=1,
        ))

    with factory() as session:
        with pytest.raises(ApplicationError, match="dedicated administrative action"):
            employee_admin.update_employee(
                session,
                principal,
                profile_id,
                "synthetic-employee-status",
                {"employment_status": "INACTIVE"},
            )

    with factory() as session:
        profile = session.get(EmployeeProfile, profile_id)
        user = session.get(User, checker_id)
        plan = session.scalar(select(AuthWorkflowPlan).where(AuthWorkflowPlan.checker_id == checker_id))
        assert profile.employment_status == "ACTIVE"
        assert user.employment_status == "ACTIVE"
        assert user.status == "ACTIVE"
        assert user.session_version == 0
        assert plan is not None and plan.status == "PENDING_APPROVAL"
        assert session.scalar(select(AdminAuditEvent.id).where(
            AdminAuditEvent.employee_id == profile_id,
            AdminAuditEvent.action == "EMPLOYEE_UPDATED",
        )) is None


def test_postgres_custom_role_crud_assignment_and_audit(configuration_postgres):
    _engine, factory = configuration_postgres
    admin = _admin(factory)
    principal = _principal(admin, ("ADMIN",))
    profile_id, user_id = _linked_employee(factory, "GOV-ROLE")
    checker_permissions = [
        "MARKETING_REVIEW_ASSIGNED",
        "MARKETING_APPROVE",
        "MARKETING_REJECT",
    ]

    with factory() as session:
        created = role_admin.create_role(
            session,
            principal,
            "synthetic-role-test",
            "CUSTOM_GOV_REVIEW",
            "Synthetic Review",
            "Synthetic acceptance role.",
            checker_permissions,
        )
        role_id = UUID(created["id"])
    assert created["is_builtin"] is False
    assert set(created["permissions"]) == set(checker_permissions)

    with factory() as session:
        updated = role_admin.update_role(
            session,
            principal,
            role_id,
            "synthetic-role-test",
            name="Synthetic Checker",
            description="Updated synthetic acceptance role.",
            permissions=checker_permissions + ["MARKETING_HISTORY_READ"],
        )
    assert updated["name"] == "Synthetic Checker"
    assert set(updated["permissions"]) == set(checker_permissions + ["MARKETING_HISTORY_READ"])

    with factory() as session:
        assignment = role_admin.replace_employee_roles(
            session,
            principal,
            profile_id,
            "synthetic-role-test",
            ["CUSTOM_GOV_REVIEW"],
        )
    assert assignment == {
        "employee_id": str(profile_id),
        "roles": ["CUSTOM_GOV_REVIEW"],
    }

    with factory.begin() as session:
        session.add(AuthWorkflowPlan(
            code=f"GOV-PENDING-{uuid4().hex[:12]}",
            maker_id=admin.id,
            checker_id=user_id,
            payload={"department": "Synthetic"},
            status="PENDING_APPROVAL",
            processing_stage="HUMAN_REVIEW_REQUIRED",
            current_version=1,
            current_round=1,
        ))

    with factory() as session:
        with pytest.raises(ApplicationError, match="Reassign pending plans"):
            role_admin.update_role(
                session,
                principal,
                role_id,
                "synthetic-role-test",
                name="Synthetic role without Checker authority",
                description="Must preserve access to pending work.",
                permissions=["MARKETING_REVIEW_ASSIGNED", "MARKETING_APPROVE"],
            )

    with factory() as session:
        assert session.scalar(
            select(User.id).where(
                User.id == user_id,
                role_admin.effective_role_filter("CHECKER"),
            )
        ) == user_id
        persisted = session.get(Role, role_id)
        assert persisted is not None
        assert persisted.name == "Synthetic Checker"
        assert {
            link.permission_code for link in persisted.permissions
        } == set(checker_permissions + ["MARKETING_HISTORY_READ"])
        audit_events = session.scalars(
            select(AdminAuditEvent)
            .where(AdminAuditEvent.actor_id == admin.id)
            .order_by(AdminAuditEvent.created_at, AdminAuditEvent.id)
        ).all()
        actions = [event.action for event in audit_events]
        assert actions == [
            "CUSTOM_ROLE_CREATED",
            "CUSTOM_ROLE_UPDATED",
            "EMPLOYEE_ROLES_REPLACED",
        ]
        assert all(event.after_state["result"] == "SUCCESS" for event in audit_events)


def test_postgres_role_admin_keeps_admin_grants_self_assignment_and_builtins_locked(
    configuration_postgres,
):
    _engine, factory = configuration_postgres
    admin = _admin(factory)
    principal = _principal(admin, ("ADMIN",))
    target_profile_id, _target_user_id = _linked_employee(factory, "GOV-TARGET")
    suffix = uuid4().hex[:12]
    with factory.begin() as session:
        self_profile = EmployeeProfile(
            user_code=f"GOV-SELF-{suffix}",
            display_name="Synthetic admin profile",
            employment_status="ACTIVE",
            user_id=admin.id,
        )
        session.add(self_profile)
        session.flush()
        self_profile_id = self_profile.id

    with factory() as session:
        custom = role_admin.create_role(
            session,
            principal,
            "synthetic-role-test",
            "CUSTOM_GOV_SAFE",
            "Synthetic safe role",
            None,
            ["MARKETING_PLAN_READ"],
        )
        safe_role_id = UUID(custom["id"])
        with pytest.raises(ApplicationError, match="ADMIN permissions are reserved"):
            role_admin.create_role(
                session,
                principal,
                "synthetic-role-test",
                "CUSTOM_GOV_ADMIN",
                "Synthetic admin role",
                None,
                ["ADMIN_EMPLOYEE_MANAGE"],
            )
        with pytest.raises(ApplicationError, match="ADMIN permissions are reserved"):
            role_admin.update_role(
                session,
                principal,
                safe_role_id,
                "synthetic-role-test",
                name="Unsafe role",
                description=None,
                permissions=["ADMIN_ROLE_MANAGE"],
            )
        with pytest.raises(ApplicationError, match="Built-in roles are immutable"):
            role_admin.update_role(
                session,
                principal,
                UUID(str(session.scalar(select(Role.id).where(Role.code == "MAKER")))),
                "synthetic-role-test",
                name="Changed built-in",
                description=None,
                permissions=[],
            )
        with pytest.raises(ApplicationError, match="Built-in roles cannot be deactivated"):
            role_admin.deactivate_role(
                session,
                principal,
                UUID(str(session.scalar(select(Role.id).where(Role.code == "MAKER")))),
                "synthetic-role-test",
            )
        with pytest.raises(ApplicationError, match="ADMIN role assignment is reserved"):
            role_admin.replace_employee_roles(
                session, principal, target_profile_id, "synthetic-role-test", ["ADMIN"],
            )
        with pytest.raises(ApplicationError, match="cannot assign or revoke roles for themselves"):
            role_admin.replace_employee_roles(
                session, principal, self_profile_id, "synthetic-role-test", ["CUSTOM_GOV_SAFE"],
            )

    with factory.begin() as session:
        legacy_role = Role(
            code="CUSTOM_GOV_LEGACY_ADMIN",
            name="Synthetic legacy owner permission",
            is_builtin=False,
            status="ACTIVE",
        )
        session.add(legacy_role)
        session.flush()
        session.add(RolePermission(
            role_id=legacy_role.id,
            permission_code="ADMIN_EMPLOYEE_MANAGE",
        ))
        legacy_role_code = legacy_role.code

    with factory() as session:
        with pytest.raises(ApplicationError, match="ADMIN permissions are reserved"):
            role_admin.replace_employee_roles(
                session,
                principal,
                target_profile_id,
                "synthetic-role-test",
                [legacy_role_code],
            )


def test_postgres_checker_reassignment_audit_records_version_round_and_result(configuration_postgres):
    _engine, factory = configuration_postgres
    admin = _admin(factory)
    principal = _principal(admin, ("ADMIN",))
    departing_profile_id, departing_id = _linked_employee(factory, "GOV-DEPARTING")
    _replacement_profile_id, replacement_id = _linked_employee(factory, "GOV-REPLACEMENT")
    _maker_profile_id, maker_id = _linked_employee(factory, "GOV-MAKER")

    with factory.begin() as session:
        checker_role = session.scalar(select(Role).where(Role.code == "CHECKER"))
        if checker_role is None:
            checker_role = Role(code="CHECKER", name="Checker", is_builtin=True)
            session.add(checker_role)
            session.flush()
        maker_role = session.scalar(select(Role).where(Role.code == "MAKER"))
        session.add_all([
            UserRole(user_id=departing_id, role_id=checker_role.id),
            UserRole(user_id=replacement_id, role_id=checker_role.id),
            UserRole(user_id=maker_id, role_id=maker_role.id),
        ])

    effective_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    with factory() as session:
        approval_configuration.create_configuration_revision(
            session,
            principal,
            "synthetic-checker-reassignment-audit",
            kind="checker_assignment",
            expected_revision=None,
            effective_at=effective_at,
            change_reason="Synthetic PostgreSQL reassignment audit fixture.",
            value={
                "maker_may_select_other": False,
                "defaults": [{"department": "Synthetic", "checker_id": str(replacement_id)}],
            },
        )

    with factory.begin() as session:
        plan = AuthWorkflowPlan(
            code=f"GOV-REASSIGN-{uuid4().hex[:12]}",
            maker_id=maker_id,
            checker_id=departing_id,
            payload={"department": "Synthetic"},
            status="PENDING_APPROVAL",
            processing_stage="HUMAN_REVIEW_REQUIRED",
            current_version=4,
            current_round=3,
        )
        session.add(plan)
        session.flush()
        plan_id = plan.id

    with factory() as session:
        employee_admin.deactivate_employee(
            session, principal, departing_profile_id, "synthetic-reassignment", {},
        )

    with factory() as session:
        plan = session.get(AuthWorkflowPlan, plan_id)
        event = session.scalar(select(AuthWorkflowEvent).where(
            AuthWorkflowEvent.plan_id == plan_id,
            AuthWorkflowEvent.action == "CHECKER_REASSIGNED",
        ))
        assert plan is not None and plan.checker_id == replacement_id
        assert event is not None
        assert event.status_before == event.status_after == "PENDING_APPROVAL"
        assert event.details["version"] == 4
        assert event.details["round"] == 3
        assert event.details["result"] == "SUCCESS"
        assert event.details["previous_checker_id"] == str(departing_id)
        assert event.details["new_checker_id"] == str(replacement_id)
        employee_audit = session.scalar(select(AdminAuditEvent).where(
            AdminAuditEvent.action == "EMPLOYEE_DEACTIVATED",
        ))
        assert employee_audit is not None
        assert employee_audit.after_state["result"] == "SUCCESS"
