from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from src.backend.application.workflow import ApplicationError
from src.backend.db.models import AdminAuditEvent, AuthWorkflowPlan, EmployeeProfile, Role, RolePermission, User, UserRole

if TYPE_CHECKING:
    from src.backend.api.auth import AuthenticatedPrincipal

PHASE1_PERMISSION_CATALOG = {
    "MARKETING_PLAN_READ": "View marketing plans",
    "MARKETING_PLAN_CREATE": "Create marketing plans",
    "MARKETING_PLAN_EDIT_OWN": "Edit own draft or rejected plans",
    "MARKETING_ATTACHMENT_MANAGE": "Manage attachments on editable own plans",
    "MARKETING_PLAN_SUBMIT": "Submit own plans for approval",
    "MARKETING_REVIEW_ASSIGNED": "View assigned approval plans",
    "MARKETING_APPROVE": "Approve assigned plans",
    "MARKETING_REJECT": "Reject assigned plans",
    "MARKETING_PLAN_VIEW_ALL": "View all workflow plans",
    "MARKETING_HISTORY_READ": "View workflow history",
    "MARKETING_INTERNAL_NOTE": "Add internal workflow notes",
    "ADMIN_EMPLOYEE_MANAGE": "Manage employee profiles and accounts",
    "ADMIN_ROLE_MANAGE": "Manage custom role catalog and assignments",
    "ADMIN_APPROVER_MANAGE": "Manage approver assignments",
    "ADMIN_SLA_MANAGE": "Manage SLA configuration",
    "ADMIN_AUDIT_READ": "Read administration audit history",
}
BUILTIN_PERMISSIONS = {
    "MAKER": ("MARKETING_PLAN_READ", "MARKETING_PLAN_CREATE", "MARKETING_PLAN_EDIT_OWN",
              "MARKETING_ATTACHMENT_MANAGE", "MARKETING_PLAN_SUBMIT", "MARKETING_HISTORY_READ"),
    "CHECKER": ("MARKETING_PLAN_READ", "MARKETING_REVIEW_ASSIGNED", "MARKETING_APPROVE",
                "MARKETING_REJECT", "MARKETING_HISTORY_READ"),
    "ADMIN": ("MARKETING_PLAN_READ", "MARKETING_PLAN_VIEW_ALL", "MARKETING_HISTORY_READ",
              "ADMIN_EMPLOYEE_MANAGE", "ADMIN_ROLE_MANAGE", "ADMIN_APPROVER_MANAGE",
              "ADMIN_SLA_MANAGE", "ADMIN_AUDIT_READ"),
}
PERMISSION_ROLE_REQUIREMENTS = {
    "MAKER": frozenset({"MARKETING_PLAN_CREATE", "MARKETING_PLAN_EDIT_OWN",
                         "MARKETING_ATTACHMENT_MANAGE", "MARKETING_PLAN_SUBMIT"}),
    "CHECKER": frozenset({"MARKETING_REVIEW_ASSIGNED", "MARKETING_APPROVE", "MARKETING_REJECT"}),
}
OWNER_ONLY_PERMISSIONS = frozenset(
    permission for permission in PHASE1_PERMISSION_CATALOG if permission.startswith("ADMIN_")
)


def effective_role_filter(role_code: str):
    direct_role = User.user_roles.any(
        UserRole.role.has(and_(Role.code == role_code, Role.status == "ACTIVE"))
    )
    required = PERMISSION_ROLE_REQUIREMENTS.get(role_code)
    if not required:
        return direct_role
    permission_bundle = and_(*(
        User.user_roles.any(UserRole.role.has(and_(
            Role.status == "ACTIVE",
            Role.permissions.any(RolePermission.permission_code == permission_code),
        )))
        for permission_code in sorted(required)
    ))
    return or_(direct_role, permission_bundle)


def _effective_role_codes(roles: list[Role]) -> set[str]:
    active_roles = [role for role in roles if role.status == "ACTIVE"]
    codes = {role.code for role in active_roles}
    permissions = {link.permission_code for role in active_roles for link in role.permissions}
    codes.update(code for code, required in PERMISSION_ROLE_REQUIREMENTS.items()
                 if required <= permissions)
    return codes


def _require_admin(principal: AuthenticatedPrincipal, correlation_id: str) -> None:
    if "ADMIN" not in principal.roles and "ADMIN_ROLE_MANAGE" not in principal.permissions:
        raise ApplicationError("FORBIDDEN", "You do not have permission to manage roles.", correlation_id)


def _validate_custom_permissions(permissions: list[str], correlation_id: str) -> None:
    unknown = set(permissions) - set(PHASE1_PERMISSION_CATALOG)
    if unknown:
        raise ApplicationError("VALIDATION_ERROR", "Role permissions must come from the Phase 1 permission catalog.", correlation_id)
    if set(permissions) & OWNER_ONLY_PERMISSIONS:
        raise ApplicationError(
            "FORBIDDEN", "ADMIN permissions are reserved for the designated system owner/operator.", correlation_id,
        )


def _audit(session: Session, actor: UUID, employee_id: UUID | None, action: str,
           before: dict[str, Any] | None, after: dict[str, Any] | None) -> None:
    session.add(AdminAuditEvent(actor_id=actor, employee_id=employee_id, action=action,
                                before_state=before, after_state=after))


def _role_view(session: Session, role: Role) -> dict[str, Any]:
    assigned = session.scalar(select(func.count(UserRole.user_id)).where(UserRole.role_id == role.id)) or 0
    permissions = sorted(link.permission_code for link in role.permissions)
    return {"id": str(role.id), "code": role.code, "name": role.name,
            "description": role.description, "is_builtin": role.is_builtin,
            "status": role.status, "permissions": permissions, "assigned_users": assigned}


def list_roles(session: Session, principal: AuthenticatedPrincipal, correlation_id: str, *,
               query: str | None = None, status: str | None = None,
               builtin: bool | None = None) -> dict[str, Any]:
    _require_admin(principal, correlation_id)
    filters = []
    if query and query.strip():
        pattern = f"%{query.strip().casefold()}%"
        filters.append(or_(func.lower(Role.code).like(pattern), func.lower(Role.name).like(pattern),
                           func.lower(Role.description).like(pattern)))
    if status:
        filters.append(Role.status == status)
    if builtin is not None:
        filters.append(Role.is_builtin.is_(builtin))
    roles = session.scalars(select(Role).options(selectinload(Role.permissions)).where(*filters)
                            .order_by(Role.is_builtin.desc(), Role.code)).all()
    return {"items": [_role_view(session, role) for role in roles],
            "permission_catalog": [{"code": code, "name": name} for code, name in PHASE1_PERMISSION_CATALOG.items()]}


def create_role(session: Session, principal: AuthenticatedPrincipal, correlation_id: str,
                code: str, name: str, description: str | None, permissions: list[str]) -> dict[str, Any]:
    _require_admin(principal, correlation_id)
    normalized_code = code.strip().upper()
    if not re.fullmatch(r"CUSTOM_[A-Z0-9_]{2,35}", normalized_code):
        raise ApplicationError("VALIDATION_ERROR", "Custom role codes must use CUSTOM_ followed by 2–35 letters, numbers or underscores.", correlation_id)
    _validate_custom_permissions(permissions, correlation_id)
    role = Role(id=uuid4(), code=normalized_code, name=name.strip(), description=description,
                is_builtin=False, status="ACTIVE")
    try:
        if session.in_transaction():
            session.rollback()
        with session.begin():
            session.add(role)
            session.flush()
            for permission in sorted(set(permissions)):
                session.add(RolePermission(role_id=role.id, permission_code=permission))
            _audit(session, principal.id, None, "CUSTOM_ROLE_CREATED", None,
                   {"code": role.code, "name": role.name, "permissions": sorted(set(permissions))})
    except IntegrityError as exc:
        session.rollback()
        raise ApplicationError("CONFLICT", "Role code is already in use.", correlation_id) from exc
    session.refresh(role)
    return _role_view(session, role)


def update_role(session: Session, principal: AuthenticatedPrincipal, role_id: UUID,
                correlation_id: str, *, name: str, description: str | None,
                permissions: list[str]) -> dict[str, Any]:
    _require_admin(principal, correlation_id)
    _validate_custom_permissions(permissions, correlation_id)
    if session.in_transaction():
        session.rollback()
    with session.begin():
        role = session.scalar(select(Role).where(Role.id == role_id).with_for_update())
        if role is None:
            raise ApplicationError("NOT_FOUND", "Role not found.", correlation_id)
        if role.is_builtin or role.code in BUILTIN_PERMISSIONS:
            raise ApplicationError("CONFLICT", "Built-in roles are immutable.", correlation_id)
        before = {"name": role.name, "description": role.description,
                  "permissions": sorted(link.permission_code for link in role.permissions)}
        role.name, role.description = name.strip(), description
        role.permissions.clear()
        role.permissions.extend(RolePermission(permission_code=code) for code in sorted(set(permissions)))
        _audit(session, principal.id, None, "CUSTOM_ROLE_UPDATED", before,
               {"name": role.name, "description": role.description, "permissions": sorted(set(permissions))})
    return _role_view(session, role)


def deactivate_role(session: Session, principal: AuthenticatedPrincipal, role_id: UUID,
                    correlation_id: str) -> dict[str, Any]:
    _require_admin(principal, correlation_id)
    if session.in_transaction():
        session.rollback()
    with session.begin():
        role = session.scalar(select(Role).where(Role.id == role_id).with_for_update())
        if role is None:
            raise ApplicationError("NOT_FOUND", "Role not found.", correlation_id)
        if role.is_builtin or role.code in BUILTIN_PERMISSIONS:
            raise ApplicationError("CONFLICT", "Built-in roles cannot be deactivated.", correlation_id)
        assigned = session.scalar(select(func.count(UserRole.user_id)).where(UserRole.role_id == role.id)) or 0
        if assigned:
            raise ApplicationError("CONFLICT", "Reassign employees before deactivating this role.", correlation_id)
        before = {"status": role.status}
        role.status = "INACTIVE"
        _audit(session, principal.id, None, "CUSTOM_ROLE_DEACTIVATED", before, {"status": role.status})
    return _role_view(session, role)


def replace_employee_roles(session: Session, principal: AuthenticatedPrincipal,
                           employee_id: UUID, correlation_id: str,
                           role_codes: list[str]) -> dict[str, Any]:
    _require_admin(principal, correlation_id)
    if session.in_transaction():
        session.rollback()
    with session.begin():
        profile = session.scalar(select(EmployeeProfile).where(EmployeeProfile.id == employee_id).with_for_update())
        user = session.scalar(select(User).where(User.id == profile.user_id).with_for_update()) if profile and profile.user_id else None
        if profile is None:
            raise ApplicationError("NOT_FOUND", "Employee not found.", correlation_id)
        if user is None:
            raise ApplicationError("CONFLICT", "Roles require a linked employee account.", correlation_id)
        if user.id == principal.id:
            raise ApplicationError("FORBIDDEN", "Administrators cannot assign or revoke roles for themselves.", correlation_id)
        requested = set(role_codes)
        if "ADMIN" in requested:
            raise ApplicationError("FORBIDDEN", "ADMIN role assignment is reserved for the designated system owner/operator.", correlation_id)
        can_assign = user.status == "ACTIVE" and not user.activation_pending and user.employment_status == "ACTIVE"
        roles = session.scalars(select(Role).options(selectinload(Role.permissions)).where(
            Role.code.in_(requested), Role.status == "ACTIVE"
        )).all() if requested else []
        if len(roles) != len(requested):
            raise ApplicationError("VALIDATION_ERROR", "One or more requested roles are unknown or inactive.", correlation_id)
        current_links = session.scalars(select(UserRole).options(
            selectinload(UserRole.role).selectinload(Role.permissions)
        ).where(UserRole.user_id == user.id)).all()
        current_role_objects = [link.role for link in current_links]
        current_codes = {role.code for role in current_role_objects if role.status == "ACTIVE"}
        current_role_ids = {role.id for role in current_role_objects}
        if any(
            role.id not in current_role_ids
            and OWNER_ONLY_PERMISSIONS.intersection(link.permission_code for link in role.permissions)
            for role in roles
        ):
            raise ApplicationError(
                "FORBIDDEN", "ADMIN permissions are reserved for the designated system owner/operator.", correlation_id,
            )
        if not can_assign and not requested <= current_codes:
            raise ApplicationError(
                "CONFLICT", "Inactive or locked employee accounts may have roles revoked but cannot receive roles.",
                correlation_id,
            )
        preserved_admin_role = session.scalar(select(Role).options(selectinload(Role.permissions)).where(
            Role.code == "ADMIN", Role.status == "ACTIVE"
        )) if "ADMIN" in current_codes else None
        next_role_objects = list(roles)
        if preserved_admin_role is not None:
            next_role_objects.append(preserved_admin_role)
        removed_checkers = (
            "CHECKER" in _effective_role_codes(current_role_objects)
            and "CHECKER" not in _effective_role_codes(next_role_objects)
        )
        if removed_checkers:
            pending_count = session.scalar(select(func.count(AuthWorkflowPlan.id)).where(
                AuthWorkflowPlan.checker_id == user.id,
                AuthWorkflowPlan.status == "PENDING_APPROVAL",
            )) or 0
            if pending_count:
                raise ApplicationError("CONFLICT", "Reassign pending plans before removing Checker access.", correlation_id)
        before = sorted(current_codes)
        for link in current_links:
            session.delete(link)
        for role in next_role_objects:
            session.add(UserRole(user_id=user.id, role_id=role.id, assigned_by=principal.id))
        _audit(session, principal.id, profile.id, "EMPLOYEE_ROLES_REPLACED",
               {"roles": before}, {"roles": sorted({role.code for role in next_role_objects})})
    return {"employee_id": str(employee_id), "roles": sorted({role.code for role in next_role_objects})}
