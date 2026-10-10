from types import SimpleNamespace
from uuid import UUID, uuid4
import hashlib

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from src.backend.application import auth_workflow, employee_admin, role_admin
from src.backend.api.auth import _user_roles
from src.backend.application.workflow import ApplicationError
from src.backend.db.base import Base
from src.backend.db.models import (
    AdminAuditEvent, AuthManagementToken, AuthWorkflowEvent, AuthWorkflowPlan,
    EmployeeProfile, Role, RolePermission, User, UserRole,
)
from src.backend.db.security import verify_password


@pytest.fixture
def admin_db():
    import src.backend.db.models
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory.begin() as session:
        for code in ("MAKER", "CHECKER", "ADMIN"):
            session.add(Role(code=code, name=code.title(), is_builtin=True))
    with factory() as session:
        admin = User(user_code="U-ADMIN", username="admin.user", email="admin@example.test",
                     phone=None, password_hash="unused", display_name="Admin", status="ACTIVE")
        session.add(admin)
        session.flush()
        session.add(UserRole(user_id=admin.id, role_id=session.scalar(select(Role.id).where(Role.code == "ADMIN"))))
        session.flush()
        principal = SimpleNamespace(id=admin.id, roles=("ADMIN",), permissions=())
    try:
        yield factory, principal
    finally:
        engine.dispose()


def add_profile(factory, code: str, name: str, *, email: str | None = None,
                roles: tuple[str, ...] = (), active: bool = True):
    with factory.begin() as session:
        contact_email = email or (f"{code.lower()}@example.test" if roles else None)
        profile = EmployeeProfile(user_code=code, display_name=name, email=email,
                                  employment_status="ACTIVE" if active else "INACTIVE")
        session.add(profile)
        session.flush()
        user = None
        if roles:
            profile.email = contact_email
            user = User(user_code=code, username=code.lower(), email=contact_email,
                        phone=None, password_hash="unused", display_name=name,
                        status="ACTIVE", employment_status="ACTIVE" if active else "INACTIVE")
            session.add(user)
            session.flush()
            profile.user_id = user.id
            for code_role in roles:
                session.add(UserRole(user_id=user.id, role_id=session.scalar(select(Role.id).where(Role.code == code_role))))
        return profile.id, user.id if user else None


def test_employee_profile_can_exist_without_an_account_and_is_audited(admin_db):
    factory, principal = admin_db
    with factory() as session:
        employee = employee_admin.create_employee(session, principal, "test", {
            "user_code": "EMP-100", "display_name": "No Login", "email": None,
            "phone": None, "department": None, "job_title": None,
            "employment_start_date": None,
        })
        assert employee["username"] is None
        assert employee["status"] is None
        assert employee["account_status"] is None
        assert employee["roles"] == []
        assert employee["employment_status"] == "ACTIVE"
        audit = session.scalar(select(AdminAuditEvent).where(AdminAuditEvent.action == "EMPLOYEE_CREATED"))
        assert audit is not None and audit.employee_id == UUID(employee["id"])


def test_account_activation_and_reset_links_are_single_use_and_never_store_raw_token(admin_db):
    factory, principal = admin_db
    employee_id, _ = add_profile(factory, "EMP-101", "Account Holder", email="account@example.test")
    with factory() as session:
        result = employee_admin.create_account(session, principal, employee_id, "account.holder", "test")
        activation = result["handover_token"]
        assert result["employee"]["account_status"] == "PENDING_ACTIVATION"
        stored = session.scalar(select(AuthManagementToken))
        assert stored.token_hash != activation
        assert len(stored.token_hash) == 64
        employee_resource_id = UUID(result["employee"]["id"])
        renewed_activation = employee_admin.reissue_activation_link(session, principal, employee_id, "test")
        assert renewed_activation["purpose"] == "ACTIVATE"
        session.refresh(stored)
        assert stored.consumed_at is not None
        with pytest.raises(ApplicationError, match="invalid or expired"):
            employee_admin.consume_management_token(session, activation, "Old-activation-password-123", "test")
        # The activation may be completed by the recipient without a logged-in Admin.
        activation = renewed_activation["handover_token"]
        employee_admin.consume_management_token(session, activation, "New-secure-password-123", "test")
        user = session.get(User, session.scalar(select(EmployeeProfile.user_id).where(EmployeeProfile.id == employee_id)))
        assert user.status == "ACTIVE" and user.activation_pending is False
        assert verify_password(user.password_hash, "New-secure-password-123")
        with pytest.raises(ApplicationError, match="pending activation"):
            employee_admin.reissue_activation_link(session, principal, employee_id, "test")
        assert employee_resource_id == employee_id

        before_version = user.session_version
        reset = employee_admin.request_password_reset(session, principal, employee_id, "test")
        old_reset_token = reset["handover_token"]
        assert user.session_version == before_version
        renewed_reset = employee_admin.request_password_reset(session, principal, employee_id, "test")
        reset_token = renewed_reset["handover_token"]
        with pytest.raises(ApplicationError, match="invalid or expired"):
            employee_admin.consume_management_token(session, old_reset_token, "Another-secure-password-456", "test")
        employee_admin.consume_management_token(session, reset_token, "Another-secure-password-456", "test")
        assert user.session_version == before_version + 1
        assert verify_password(user.password_hash, "Another-secure-password-456")
        audit_values = str([
            (event.before_state, event.after_state)
            for event in session.scalars(select(AdminAuditEvent)).all()
        ])
        assert reset_token not in audit_values and old_reset_token not in audit_values and activation not in audit_values
        with pytest.raises(ApplicationError, match="invalid or expired"):
            employee_admin.consume_management_token(session, reset_token, "Third-secure-password-789", "test")


def test_management_token_purpose_constraint_rejects_unknown_and_savepoint_rolls_back(admin_db):
    factory, principal = admin_db
    from sqlalchemy.exc import IntegrityError

    employee_id, _ = add_profile(factory, "EMP-101Y", "Purpose Constraint Holder", email="purpose@example.test")
    with factory() as session:
        issued = employee_admin.create_account(session, principal, employee_id, "purpose.constraint", "test")
        account_id = session.scalar(select(EmployeeProfile.user_id).where(EmployeeProfile.id == employee_id))
        token_hash = hashlib.sha256(issued["handover_token"].encode("utf-8")).hexdigest()
        token = session.scalar(select(AuthManagementToken).where(AuthManagementToken.token_hash == token_hash))
        assert token.purpose == "ACTIVATE"
        before_user = session.get(User, account_id)
        before_password_hash = before_user.password_hash
        before_audit_count = session.scalar(select(func.count(AdminAuditEvent.id)))

        with pytest.raises(IntegrityError) as caught:
            with session.begin_nested():
                token.purpose = "UNKNOWN"
                session.flush()

        assert "ck_auth_management_tokens_purpose" in str(caught.value.orig)
        session.expire_all()
        after_user = session.get(User, account_id)
        after_token = session.scalar(select(AuthManagementToken).where(AuthManagementToken.token_hash == token_hash))
        after_audit_count = session.scalar(select(func.count(AdminAuditEvent.id)))
        assert after_user.password_hash == before_password_hash
        assert after_user.status == "DISABLED" and after_user.activation_pending is True
        assert after_user.session_version == 0
        assert after_token.consumed_at is None and after_token.purpose == "ACTIVATE"
        assert after_audit_count == before_audit_count


def test_management_token_consumption_rolls_back_all_changes_when_audit_fails(admin_db, monkeypatch):
    factory, principal = admin_db
    employee_id, _ = add_profile(factory, "EMP-101Z", "Rollback Holder", email="rollback@example.test")
    with factory() as session:
        issued = employee_admin.create_account(session, principal, employee_id, "rollback.holder", "test")
        account_id = session.scalar(select(EmployeeProfile.user_id).where(EmployeeProfile.id == employee_id))
        employee_admin.consume_management_token(
            session, issued["handover_token"], "Initial-secure-password-123", "test",
        )
        reset = employee_admin.request_password_reset(session, principal, employee_id, "test")
        reset_hash = hashlib.sha256(reset["handover_token"].encode("utf-8")).hexdigest()
        before_user = session.get(User, account_id)
        before_password_hash = before_user.password_hash
        before_session_version = before_user.session_version
        before_audit_count = session.scalar(select(func.count(AdminAuditEvent.id)).where(
            AdminAuditEvent.action == "PASSWORD_RESET_COMPLETED",
        ))

        def fail_audit(*_args, **_kwargs):
            raise RuntimeError("synthetic audit write failure")

        monkeypatch.setattr(employee_admin, "_audit", fail_audit)
        with pytest.raises(RuntimeError, match="synthetic audit write failure"):
            employee_admin.consume_management_token(
                session, reset["handover_token"], "Replacement-secure-password-456", "test",
            )

        session.expire_all()
        after_user = session.get(User, account_id)
        after_token = session.scalar(select(AuthManagementToken).where(AuthManagementToken.token_hash == reset_hash))
        after_audit_count = session.scalar(select(func.count(AdminAuditEvent.id)).where(
            AdminAuditEvent.action == "PASSWORD_RESET_COMPLETED",
        ))
        assert after_user.password_hash == before_password_hash
        assert after_user.session_version == before_session_version
        assert verify_password(after_user.password_hash, "Initial-secure-password-123")
        assert not verify_password(after_user.password_hash, "Replacement-secure-password-456")
        assert after_token.consumed_at is None
        assert after_audit_count == before_audit_count


def test_management_token_expiry_is_enforced(admin_db):
    factory, principal = admin_db
    employee_id, _ = add_profile(factory, "EMP-101X", "Expiry Holder", email="expiry@example.test")
    with factory() as session:
        issued = employee_admin.create_account(session, principal, employee_id, "expiry.holder", "test")
        token = session.scalar(select(AuthManagementToken))
        token.expires_at = token.expires_at.replace(year=token.expires_at.year - 1)
        session.commit()
        with pytest.raises(ApplicationError, match="invalid or expired"):
            employee_admin.consume_management_token(session, issued["handover_token"], "New-secure-password-123", "test")


def test_checker_deactivation_requires_explicit_reassignment_and_preserves_event_history(admin_db):
    factory, principal = admin_db
    employee_id, departing_user_id = add_profile(factory, "EMP-102", "Departing Checker", roles=("CHECKER",))
    _, replacement_id = add_profile(factory, "EMP-103", "Replacement Checker", roles=("CHECKER",))
    _, maker_id = add_profile(factory, "EMP-104", "Plan Maker", roles=("MAKER",))
    with factory.begin() as session:
        plan = AuthWorkflowPlan(code="PLAN-1", maker_id=maker_id, checker_id=departing_user_id,
                                payload={}, status="PENDING_APPROVAL", processing_stage="HUMAN_REVIEW_REQUIRED")
        session.add(plan)
        session.flush()
        plan_id = plan.id
    with factory() as session:
        with pytest.raises(ApplicationError, match="every pending plan"):
            employee_admin.deactivate_employee(session, principal, employee_id, "test", {})
    with factory() as session:
        changed = employee_admin.deactivate_employee(session, principal, employee_id, "test", {plan_id: replacement_id})
        assert changed["employment_status"] == "INACTIVE"
        assert changed["status"] == "DISABLED"
        departing_user = session.get(User, departing_user_id)
        assert departing_user.employment_status == "INACTIVE"
        assert departing_user.session_version == 1
        assert session.get(AuthWorkflowPlan, plan_id).checker_id == replacement_id
        event = session.scalar(select(AuthWorkflowEvent).where(AuthWorkflowEvent.plan_id == plan_id))
        assert event.action == "CHECKER_REASSIGNED"
        assert event.details["previous_checker_id"] == str(departing_user_id)
        assert session.scalar(select(AdminAuditEvent).where(AdminAuditEvent.action == "EMPLOYEE_DEACTIVATED"))


def test_checker_deactivation_rolls_back_reassignment_employee_account_and_audit_on_invalid_replacement(admin_db):
    factory, principal = admin_db
    employee_id, departing_user_id = add_profile(factory, "EMP-102A", "Departing Checker", roles=("CHECKER",))
    _, maker_id = add_profile(factory, "EMP-104A", "Plan Maker", roles=("MAKER",))
    _, not_checker_id = add_profile(factory, "EMP-104B", "Not Checker", roles=("MAKER",))
    with factory.begin() as session:
        plan = AuthWorkflowPlan(code="PLAN-ROLLBACK", maker_id=maker_id, checker_id=departing_user_id,
                                payload={}, status="PENDING_APPROVAL", processing_stage="HUMAN_REVIEW_REQUIRED")
        session.add(plan)
        session.flush()
        plan_id = plan.id
    with factory() as session:
        with pytest.raises(ApplicationError, match="Replacement must be an active Checker"):
            employee_admin.deactivate_employee(session, principal, employee_id, "test", {plan_id: not_checker_id})
    with factory() as session:
        assert session.get(EmployeeProfile, employee_id).employment_status == "ACTIVE"
        user = session.get(User, departing_user_id)
        assert user.employment_status == "ACTIVE" and user.status == "ACTIVE" and user.session_version == 0
        assert session.get(AuthWorkflowPlan, plan_id).checker_id == departing_user_id
        assert session.scalar(select(AuthWorkflowEvent).where(AuthWorkflowEvent.plan_id == plan_id)) is None
        assert session.scalar(select(AdminAuditEvent).where(AdminAuditEvent.action == "EMPLOYEE_DEACTIVATED")) is None


def test_checker_account_cannot_be_locked_while_pending_plans_exist(admin_db):
    factory, principal = admin_db
    employee_id, checker_id = add_profile(factory, "EMP-LOCK", "Pending Checker", roles=("CHECKER",))
    _, maker_id = add_profile(factory, "EMP-MAKER-LOCK", "Plan Maker", roles=("MAKER",))
    with factory.begin() as session:
        plan = AuthWorkflowPlan(code="PLAN-LOCK", maker_id=maker_id, checker_id=checker_id,
                                payload={}, status="PENDING_APPROVAL", processing_stage="HUMAN_REVIEW_REQUIRED")
        session.add(plan)
    with factory() as session:
        with pytest.raises(ApplicationError, match="Reassign pending plans before locking"):
            employee_admin.set_account_lock(session, principal, employee_id, "test", locked=True)
    with factory() as session:
        user = session.get(User, checker_id)
        assert user.status == "ACTIVE" and user.session_version == 0
        assert session.scalar(select(AuthWorkflowPlan).where(AuthWorkflowPlan.code == "PLAN-LOCK")).checker_id == checker_id
        assert session.scalar(select(AdminAuditEvent).where(AdminAuditEvent.action == "ACCOUNT_LOCKED")) is None


def test_reactivation_does_not_unlock_account_or_restore_revoked_roles(admin_db):
    factory, principal = admin_db
    employee_id, user_id = add_profile(factory, "EMP-REACT", "Returning Employee", roles=("MAKER",))
    with factory.begin() as session:
        profile = session.get(EmployeeProfile, employee_id)
        user = session.get(User, user_id)
        profile.employment_status = user.employment_status = "INACTIVE"
        user.status = "DISABLED"
        user.session_version = 9
    with factory() as session:
        role_admin.replace_employee_roles(session, principal, employee_id, "test", [])
    with factory() as session:
        changed = employee_admin.reactivate_employee(session, principal, employee_id, "test")
        assert changed["employment_status"] == "ACTIVE"
        assert changed["account_status"] == "DISABLED"
        assert changed["roles"] == []
        user = session.get(User, user_id)
        assert user.employment_status == "ACTIVE" and user.status == "DISABLED" and user.session_version == 9


def test_role_catalog_blocks_builtin_changes_admin_grants_and_permissions_outside_catalog(admin_db):
    factory, principal = admin_db
    employee_id, user_id = add_profile(factory, "EMP-105", "Role Target", email="role@example.test", roles=("MAKER",))
    with factory.begin() as session:
        profile = session.get(EmployeeProfile, employee_id)
        user = session.get(User, user_id)
        user.activation_pending = False
        user.status = "ACTIVE"
    with factory() as session:
        role = role_admin.create_role(session, principal, "test", "CUSTOM_CAMPAIGN_REVIEW", "Campaign Review",
                                      None, ["MARKETING_REVIEW_ASSIGNED", "MARKETING_APPROVE"])
        with pytest.raises(ApplicationError, match="permission catalog"):
            role_admin.create_role(session, principal, "test", "CUSTOM_UNSAFE_ROLE", "Unsafe", None, ["ADMIN_GRANT_ADMIN"])
        with pytest.raises(ApplicationError, match="ADMIN permissions are reserved"):
            role_admin.create_role(session, principal, "test", "CUSTOM_ADMIN_SCOPE", "Indirect Admin", None,
                                   ["ADMIN_EMPLOYEE_MANAGE"])
        with pytest.raises(ApplicationError, match="ADMIN permissions are reserved"):
            role_admin.update_role(session, principal, UUID(role["id"]), "test", name="Campaign Review",
                                   description=None, permissions=["ADMIN_ROLE_MANAGE"])
    with factory() as session:
        with pytest.raises(ApplicationError, match="ADMIN role assignment is reserved"):
            role_admin.replace_employee_roles(session, principal, employee_id, "test", ["ADMIN"])
    with factory() as session:
        assigned = role_admin.replace_employee_roles(session, principal, employee_id, "test", ["CUSTOM_CAMPAIGN_REVIEW"])
        assert "CUSTOM_CAMPAIGN_REVIEW" in assigned["roles"]
        assert session.scalar(select(RolePermission).where(RolePermission.permission_code == "MARKETING_APPROVE"))
        user = session.get(User, user_id)
        assert "CHECKER" not in _user_roles(user)
        with pytest.raises(ApplicationError, match="Built-in roles are immutable"):
            role_admin.update_role(session, principal, session.scalar(select(Role.id).where(Role.code == "MAKER")),
                                   "test", name="Changed", description=None, permissions=[])


def test_existing_custom_role_cannot_be_used_to_grant_admin_permissions(admin_db):
    factory, principal = admin_db
    employee_id, _ = add_profile(factory, "EMP-ADMIN-PERM", "Permission Target", roles=("MAKER",))
    with factory.begin() as session:
        role = Role(code="CUSTOM_OLD_ADMIN", name="Legacy Admin Bundle", is_builtin=False, status="ACTIVE")
        session.add(role)
        session.flush()
        session.add(RolePermission(role_id=role.id, permission_code="ADMIN_EMPLOYEE_MANAGE"))
    with factory() as session:
        with pytest.raises(ApplicationError, match="ADMIN permissions are reserved"):
            role_admin.replace_employee_roles(session, principal, employee_id, "test", ["CUSTOM_OLD_ADMIN"])


def test_custom_checker_permission_bundle_is_a_valid_replacement_and_cannot_be_removed_with_pending_work(admin_db):
    factory, principal = admin_db
    departing_id, departing_user_id = add_profile(factory, "EMP-106", "Departing Checker", roles=("CHECKER",))
    replacement_id, replacement_user_id = add_profile(factory, "EMP-107", "Custom Checker", roles=("MAKER",))
    _, maker_id = add_profile(factory, "EMP-108", "Plan Maker", roles=("MAKER",))
    permissions = ["MARKETING_REVIEW_ASSIGNED", "MARKETING_APPROVE", "MARKETING_REJECT"]
    with factory() as session:
        custom = role_admin.create_role(session, principal, "test", "CUSTOM_REVIEW", "Review", None, permissions)
        role_admin.replace_employee_roles(session, principal, replacement_id, "test", [custom["code"]])
    with factory() as session:
        checker_picker = auth_workflow.list_checkers(
            session, SimpleNamespace(id=maker_id, roles=("MAKER",)), "test",
        )
        assert replacement_user_id in {UUID(item["id"]) for item in checker_picker}
    with factory.begin() as session:
        plan = AuthWorkflowPlan(code="PLAN-CUSTOM-CHECKER", maker_id=maker_id, checker_id=departing_user_id,
                                payload={}, status="PENDING_APPROVAL", processing_stage="HUMAN_REVIEW_REQUIRED")
        session.add(plan)
        session.flush()
        plan_id = plan.id
    with factory() as session:
        updated = employee_admin.deactivate_employee(
            session, principal, departing_id, "test", {plan_id: replacement_user_id},
        )
        assert updated["employment_status"] == "INACTIVE"
    with factory() as session:
        with pytest.raises(ApplicationError, match="Reassign pending plans"):
            role_admin.replace_employee_roles(session, principal, replacement_id, "test", [])
