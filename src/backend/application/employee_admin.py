from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from src.backend.application.workflow import ApplicationError
from src.backend.db.models import (
    AdminAuditEvent, AuthManagementToken, AuthWorkflowEvent, AuthWorkflowPlan,
    EmployeeProfile, Role, RolePermission, User, UserRole,
)
from src.backend.db.security import hash_password
from src.backend.application.role_admin import PERMISSION_ROLE_REQUIREMENTS, effective_role_filter

if TYPE_CHECKING:
    from src.backend.api.auth import AuthenticatedPrincipal

ACTIVATION_TOKEN_TTL = timedelta(minutes=30)
RESET_TOKEN_TTL = timedelta(minutes=30)


def _require_admin(principal: AuthenticatedPrincipal, correlation_id: str) -> None:
    if "ADMIN" not in principal.roles and "ADMIN_EMPLOYEE_MANAGE" not in principal.permissions:
        raise ApplicationError("FORBIDDEN", "You do not have permission to manage employees.", correlation_id)


def _write_transaction(session: Session):
    if session.in_transaction():
        session.rollback()
    return session.begin()


def _audit(session: Session, actor_id: UUID, employee_id: UUID | None, action: str,
           before: dict[str, Any] | None, after: dict[str, Any] | None) -> None:
    session.add(AdminAuditEvent(
        actor_id=actor_id, employee_id=employee_id, action=action,
        before_state=before, after_state=after,
    ))


def _profile_state(profile: EmployeeProfile) -> dict[str, Any]:
    return {
        "user_code": profile.user_code, "display_name": profile.display_name,
        "email": profile.email, "phone": profile.phone,
        "department": profile.department, "job_title": profile.job_title,
        "employment_start_date": profile.employment_start_date.isoformat()
        if profile.employment_start_date else None,
        "employment_status": profile.employment_status,
        "user_id": str(profile.user_id) if profile.user_id else None,
    }


def _employee_dict(profile: EmployeeProfile, user: User | None) -> dict[str, Any]:
    active_links = [link for link in user.user_roles if link.role.status == "ACTIVE"] if user else []
    roles = sorted(link.role.code for link in active_links)
    permissions = ({permission.permission_code for link in active_links for permission in link.role.permissions}
                   if user else set())
    if user:
        roles = sorted(set(roles).union(
            role for role, required in PERMISSION_ROLE_REQUIREMENTS.items() if required <= permissions
        ))
    return {
        "id": str(profile.id), "user_code": profile.user_code,
        "account_id": str(user.id) if user else None,
        "username": user.username if user else None,
        "display_name": profile.display_name, "email": profile.email,
        "phone": profile.phone, "department": profile.department,
        "job_title": profile.job_title,
        "employment_start_date": profile.employment_start_date.isoformat()
        if profile.employment_start_date else None,
        "employment_status": profile.employment_status,
        "status": user.status if user else None,
        "account_status": (
            "PENDING_ACTIVATION" if user and user.activation_pending else user.status
        ) if user else None,
        "roles": roles,
        "effective_permissions": sorted(permissions),
    }


def _employee_query():
    return select(EmployeeProfile, User).outerjoin(User, EmployeeProfile.user_id == User.id).options(
        selectinload(User.user_roles).selectinload(UserRole.role)
    )


def list_employees(
    session: Session, principal: AuthenticatedPrincipal, correlation_id: str, *,
    query: str | None = None, role: str | None = None, status: str | None = None,
    department: str | None = None, job_title: str | None = None,
    employment_status: str | None = None, offset: int = 0, limit: int = 50,
) -> dict:
    _require_admin(principal, correlation_id)
    filters = []
    search = query.strip().casefold() if query else ""
    if search:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        filters.append(or_(
            func.lower(EmployeeProfile.user_code).like(pattern, escape="\\"),
            func.lower(EmployeeProfile.display_name).like(pattern, escape="\\"),
            func.lower(EmployeeProfile.email).like(pattern, escape="\\"),
            func.lower(EmployeeProfile.phone).like(pattern, escape="\\"),
            func.lower(User.username).like(pattern, escape="\\"),
        ))
    if role:
        filters.append(EmployeeProfile.user_id.is_not(None))
        role_filters = [UserRole.role.has(and_(Role.code == role, Role.status == "ACTIVE"))]
        required_permissions = PERMISSION_ROLE_REQUIREMENTS.get(role)
        if required_permissions:
            role_filters.append(and_(*[
                UserRole.role.has(and_(Role.status == "ACTIVE",
                                       Role.permissions.any(RolePermission.permission_code == permission)))
                for permission in sorted(required_permissions)
            ]))
        filters.append(User.user_roles.any(or_(*role_filters)))
    if status:
        filters.append(EmployeeProfile.user_id.is_not(None))
        if status == "PENDING_ACTIVATION":
            filters.append(User.activation_pending.is_(True))
        else:
            filters.extend((User.status == status, User.activation_pending.is_(False)))
    if department and department.strip():
        filters.append(func.lower(EmployeeProfile.department) == department.strip().casefold())
    if job_title and job_title.strip():
        filters.append(func.lower(EmployeeProfile.job_title) == job_title.strip().casefold())
    if employment_status:
        filters.append(EmployeeProfile.employment_status == employment_status)

    total = session.scalar(select(func.count(EmployeeProfile.id)).select_from(EmployeeProfile)
                           .outerjoin(User, EmployeeProfile.user_id == User.id).where(*filters)) or 0
    rows = session.execute(
        _employee_query().where(*filters)
        .order_by(func.lower(EmployeeProfile.user_code), EmployeeProfile.id)
        .offset(offset).limit(limit)
    ).all()
    return {
        "items": [_employee_dict(profile, user) for profile, user in rows],
        "offset": offset, "limit": limit, "total": total,
    }


def get_employee(session: Session, principal: AuthenticatedPrincipal, employee_id: UUID,
                 correlation_id: str) -> dict:
    _require_admin(principal, correlation_id)
    row = session.execute(_employee_query().where(EmployeeProfile.id == employee_id)).first()
    if row is None:
        raise ApplicationError("NOT_FOUND", "Employee not found.", correlation_id)
    return _employee_dict(*row)


def list_pending_checker_plans(session: Session, principal: AuthenticatedPrincipal,
                               employee_id: UUID, correlation_id: str, *,
                               offset: int = 0, limit: int = 100) -> dict[str, Any]:
    _require_admin(principal, correlation_id)
    profile = session.get(EmployeeProfile, employee_id)
    if profile is None:
        raise ApplicationError("NOT_FOUND", "Employee not found.", correlation_id)
    filters = [AuthWorkflowPlan.checker_id == profile.user_id,
               AuthWorkflowPlan.status == "PENDING_APPROVAL"]
    total = session.scalar(select(func.count(AuthWorkflowPlan.id)).where(*filters)) or 0
    plans = session.scalars(select(AuthWorkflowPlan).where(*filters)
                            .order_by(AuthWorkflowPlan.code, AuthWorkflowPlan.id)
                            .offset(offset).limit(limit)).all()
    return {"items": [{"id": str(plan.id), "code": plan.code,
                        "maker_id": str(plan.maker_id)} for plan in plans],
            "offset": offset, "limit": limit, "total": total}


def list_admin_audit_events(session: Session, principal: AuthenticatedPrincipal,
                            correlation_id: str, *, offset: int = 0,
                            limit: int = 100) -> dict[str, Any]:
    if "ADMIN" not in principal.roles and "ADMIN_AUDIT_READ" not in principal.permissions:
        raise ApplicationError("FORBIDDEN", "You do not have permission to view administration audit events.", correlation_id)
    total = session.scalar(select(func.count(AdminAuditEvent.id))) or 0
    rows = session.execute(
        select(AdminAuditEvent, User.display_name, EmployeeProfile.user_code)
        .join(User, User.id == AdminAuditEvent.actor_id)
        .outerjoin(EmployeeProfile, EmployeeProfile.id == AdminAuditEvent.employee_id)
        .order_by(AdminAuditEvent.created_at.desc(), AdminAuditEvent.id.desc())
        .offset(offset).limit(limit)
    ).all()
    return {"items": [{
        "id": str(event.id), "actor_id": str(event.actor_id), "actor_name": actor_name,
        "employee_id": str(event.employee_id) if event.employee_id else None,
        "employee_code": employee_code, "action": event.action,
        "before_state": event.before_state, "after_state": event.after_state,
        "created_at": event.created_at,
    } for event, actor_name, employee_code in rows], "offset": offset, "limit": limit, "total": total}


def create_employee(session: Session, principal: AuthenticatedPrincipal, correlation_id: str,
                    values: dict[str, Any]) -> dict:
    _require_admin(principal, correlation_id)
    values = {**values, "employment_status": values.get("employment_status", "ACTIVE")}
    if values["employment_status"] != "ACTIVE":
        raise ApplicationError("VALIDATION_ERROR", "New employee profiles must start active.", correlation_id)
    profile = EmployeeProfile(id=uuid4(), **values)
    try:
        with _write_transaction(session):
            session.add(profile)
            session.flush()
            _audit(session, principal.id, profile.id, "EMPLOYEE_CREATED", None, _profile_state(profile))
        return _employee_dict(profile, None)
    except IntegrityError as exc:
        session.rollback()
        raise ApplicationError("CONFLICT", "Employee code, email or phone is already in use.", correlation_id) from exc


def update_employee(session: Session, principal: AuthenticatedPrincipal, employee_id: UUID,
                    correlation_id: str, changes: dict[str, Any]) -> dict:
    _require_admin(principal, correlation_id)
    try:
        with _write_transaction(session):
            profile = session.scalar(select(EmployeeProfile).where(EmployeeProfile.id == employee_id).with_for_update())
            if profile is None:
                raise ApplicationError("NOT_FOUND", "Employee not found.", correlation_id)
            before = _profile_state(profile)
            for key, value in changes.items():
                setattr(profile, key, value)
            if not profile.display_name.strip():
                raise ApplicationError("VALIDATION_ERROR", "Employee name cannot be blank.", correlation_id)
            if profile.user_id:
                user = session.scalar(select(User).where(User.id == profile.user_id).with_for_update())
                if user:
                    if bool(profile.email) == bool(profile.phone):
                        raise ApplicationError("VALIDATION_ERROR", "An account must have exactly one email or phone contact.", correlation_id)
                    user.user_code = profile.user_code
                    user.display_name = profile.display_name
                    user.email, user.phone = profile.email, profile.phone
                    user.department, user.job_title = profile.department, profile.job_title
                    user.employment_start_date = profile.employment_start_date
                    user.employment_status = profile.employment_status
            session.flush()
            _audit(session, principal.id, profile.id, "EMPLOYEE_UPDATED", before, _profile_state(profile))
        return get_employee(session, principal, employee_id, correlation_id)
    except IntegrityError as exc:
        session.rollback()
        raise ApplicationError("CONFLICT", "Employee code, email or phone is already in use.", correlation_id) from exc


def _active_checker(session: Session, checker_id: UUID) -> User | None:
    return session.scalar(select(User).where(
        User.id == checker_id, User.status == "ACTIVE", User.activation_pending.is_(False),
        User.employment_status == "ACTIVE", effective_role_filter("CHECKER"),
    ).with_for_update())


def deactivate_employee(session: Session, principal: AuthenticatedPrincipal, employee_id: UUID,
                        correlation_id: str, reassignments: dict[UUID, UUID]) -> dict:
    _require_admin(principal, correlation_id)
    with _write_transaction(session):
        profile = session.scalar(select(EmployeeProfile).where(EmployeeProfile.id == employee_id).with_for_update())
        if profile is None:
            raise ApplicationError("NOT_FOUND", "Employee not found.", correlation_id)
        if profile.employment_status == "INACTIVE":
            return _employee_dict(profile, session.get(User, profile.user_id) if profile.user_id else None)
        before = _profile_state(profile)
        user = session.scalar(select(User).where(User.id == profile.user_id).with_for_update()) if profile.user_id else None
        if user:
            before["account_status"] = user.status
            before["session_version"] = user.session_version
        pending: list[AuthWorkflowPlan] = []
        if profile.user_id:
            pending = session.scalars(select(AuthWorkflowPlan).where(
                AuthWorkflowPlan.checker_id == profile.user_id,
                AuthWorkflowPlan.status == "PENDING_APPROVAL",
            ).order_by(AuthWorkflowPlan.id).with_for_update()).all()
        required_ids = {str(plan.id) for plan in pending}
        if set(map(str, reassignments)) != required_ids:
            raise ApplicationError("CONFLICT", "Provide one eligible replacement Checker for every pending plan.", correlation_id)
        now = datetime.now(timezone.utc)
        for plan in pending:
            replacement_id = reassignments[plan.id]
            replacement = _active_checker(session, replacement_id)
            if replacement is None or replacement.id == plan.maker_id or replacement.id == profile.user_id:
                raise ApplicationError("VALIDATION_ERROR", "Replacement must be an active Checker distinct from the Maker and departing Checker.", correlation_id)
            previous_id = plan.checker_id
            plan.checker_id = replacement.id
            sequence = (session.scalar(select(func.max(AuthWorkflowEvent.sequence_number)).where(
                AuthWorkflowEvent.plan_id == plan.id)) or 0) + 1
            session.add(AuthWorkflowEvent(
                plan_id=plan.id, actor_id=principal.id, actor_type="HUMAN",
                sequence_number=sequence, action="CHECKER_REASSIGNED",
                status_before=plan.status, status_after=plan.status,
                details={"previous_checker_id": str(previous_id), "new_checker_id": str(replacement.id),
                         "reason": "Employee deactivation with explicit reassignment"},
            ))
        profile.employment_status = "INACTIVE"
        if user:
            user.employment_status = "INACTIVE"
            user.status = "DISABLED"
            user.session_version += 1
            invalidated_tokens = session.execute(
                AuthManagementToken.__table__.update()
                .where(AuthManagementToken.user_id == user.id, AuthManagementToken.consumed_at.is_(None))
                .values(consumed_at=now)
            ).rowcount or 0
        session.flush()
        after = _profile_state(profile)
        if profile.user_id:
            after["account_status"] = user.status
            after["session_version"] = user.session_version
            after["invalidated_management_tokens"] = invalidated_tokens
        _audit(session, principal.id, profile.id, "EMPLOYEE_DEACTIVATED", before, after)
    return get_employee(session, principal, employee_id, correlation_id)


def reactivate_employee(session: Session, principal: AuthenticatedPrincipal, employee_id: UUID,
                        correlation_id: str) -> dict:
    """Reactivate employment without granting roles or unlocking the account."""
    _require_admin(principal, correlation_id)
    with _write_transaction(session):
        profile = session.scalar(select(EmployeeProfile).where(EmployeeProfile.id == employee_id).with_for_update())
        if profile is None:
            raise ApplicationError("NOT_FOUND", "Employee not found.", correlation_id)
        if profile.employment_status == "ACTIVE":
            return _employee_dict(profile, session.get(User, profile.user_id) if profile.user_id else None)
        before = _profile_state(profile)
        user = session.scalar(select(User).where(User.id == profile.user_id).with_for_update()) if profile.user_id else None
        if user:
            before["account_status"] = user.status
            before["session_version"] = user.session_version
            before["roles"] = sorted({link.role.code for link in user.user_roles if link.role.status == "ACTIVE"})
        profile.employment_status = "ACTIVE"
        if user:
            user.employment_status = "ACTIVE"
        session.flush()
        after = _profile_state(profile)
        if user:
            after["account_status"] = user.status
            after["session_version"] = user.session_version
            after["roles"] = sorted({link.role.code for link in user.user_roles if link.role.status == "ACTIVE"})
        _audit(session, principal.id, profile.id, "EMPLOYEE_REACTIVATED", before, after)
    return get_employee(session, principal, employee_id, correlation_id)


def _issue_token(session: Session, user: User, actor_id: UUID, purpose: str) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    session.execute(
        AuthManagementToken.__table__.update()
        .where(AuthManagementToken.user_id == user.id, AuthManagementToken.purpose == purpose,
               AuthManagementToken.consumed_at.is_(None))
        .values(consumed_at=now)
    )
    raw = secrets.token_urlsafe(32)
    expires = now + (ACTIVATION_TOKEN_TTL if purpose == "ACTIVATE" else RESET_TOKEN_TTL)
    session.add(AuthManagementToken(
        user_id=user.id, issued_by=actor_id, purpose=purpose,
        token_hash=hashlib.sha256(raw.encode("ascii")).hexdigest(), expires_at=expires,
    ))
    return raw, expires


def create_account(session: Session, principal: AuthenticatedPrincipal, employee_id: UUID,
                   username: str, correlation_id: str) -> dict:
    _require_admin(principal, correlation_id)
    from src.backend.api.auth import _normalize_username
    try:
        normalized = _normalize_username(username)
    except ValueError as exc:
        raise ApplicationError("VALIDATION_ERROR", str(exc), correlation_id) from exc
    try:
        with _write_transaction(session):
            profile = session.scalar(select(EmployeeProfile).where(EmployeeProfile.id == employee_id).with_for_update())
            if profile is None:
                raise ApplicationError("NOT_FOUND", "Employee not found.", correlation_id)
            if profile.employment_status != "ACTIVE" or profile.user_id is not None:
                raise ApplicationError("CONFLICT", "Only an active employee without an account can receive a login account.", correlation_id)
            if bool(profile.email) == bool(profile.phone):
                raise ApplicationError("VALIDATION_ERROR", "The employee must have exactly one email or phone contact before account creation.", correlation_id)
            user = User(
                id=uuid4(), user_code=profile.user_code, username=normalized,
                email=profile.email, phone=profile.phone,
                password_hash=hash_password(secrets.token_urlsafe(48)),
                display_name=profile.display_name, department=profile.department,
                job_title=profile.job_title, employment_start_date=profile.employment_start_date,
                employment_status=profile.employment_status, status="DISABLED", activation_pending=True,
            )
            session.add(user)
            session.flush()
            profile.user_id = user.id
            raw, expires = _issue_token(session, user, principal.id, "ACTIVATE")
            _audit(session, principal.id, profile.id, "ACCOUNT_ACTIVATION_ISSUED", None,
                   {"account_status": "PENDING_ACTIVATION", "username": normalized})
        return {"employee": get_employee(session, principal, employee_id, correlation_id),
                "handover_token": raw, "purpose": "ACTIVATE", "expires_at": expires}
    except IntegrityError as exc:
        session.rollback()
        raise ApplicationError("CONFLICT", "Username or employee contact is already in use.", correlation_id) from exc


def reissue_activation_link(session: Session, principal: AuthenticatedPrincipal, employee_id: UUID,
                            correlation_id: str) -> dict:
    _require_admin(principal, correlation_id)
    with _write_transaction(session):
        profile = session.scalar(select(EmployeeProfile).where(EmployeeProfile.id == employee_id).with_for_update())
        user = session.scalar(select(User).where(User.id == profile.user_id).with_for_update()) if profile and profile.user_id else None
        if profile is None or user is None:
            raise ApplicationError("NOT_FOUND", "Employee account not found.", correlation_id)
        if profile.employment_status != "ACTIVE" or user.status != "DISABLED" or not user.activation_pending:
            raise ApplicationError("CONFLICT", "Only an active employee account pending activation can receive a new activation link.", correlation_id)
        raw, expires = _issue_token(session, user, principal.id, "ACTIVATE")
        _audit(session, principal.id, profile.id, "ACCOUNT_ACTIVATION_REISSUED", None,
               {"account_status": "PENDING_ACTIVATION", "purpose": "ACTIVATE"})
    return {"handover_token": raw, "purpose": "ACTIVATE", "expires_at": expires}


def request_password_reset(session: Session, principal: AuthenticatedPrincipal, employee_id: UUID,
                           correlation_id: str) -> dict:
    _require_admin(principal, correlation_id)
    with _write_transaction(session):
        profile = session.scalar(select(EmployeeProfile).where(EmployeeProfile.id == employee_id).with_for_update())
        user = session.scalar(select(User).where(User.id == profile.user_id).with_for_update()) if profile and profile.user_id else None
        if profile is None or user is None:
            raise ApplicationError("NOT_FOUND", "Employee account not found.", correlation_id)
        if user.status != "ACTIVE" or user.activation_pending:
            raise ApplicationError("CONFLICT", "Only an active, activated account can receive a password reset link.", correlation_id)
        raw, expires = _issue_token(session, user, principal.id, "RESET")
        _audit(session, principal.id, profile.id, "PASSWORD_RESET_ISSUED",
               {"session_version": user.session_version}, {"session_version": user.session_version})
    return {"handover_token": raw, "purpose": "RESET", "expires_at": expires}


def set_account_lock(session: Session, principal: AuthenticatedPrincipal, employee_id: UUID,
                     correlation_id: str, *, locked: bool) -> dict:
    _require_admin(principal, correlation_id)
    with _write_transaction(session):
        profile = session.scalar(select(EmployeeProfile).where(EmployeeProfile.id == employee_id).with_for_update())
        user = session.scalar(select(User).where(User.id == profile.user_id).with_for_update()) if profile and profile.user_id else None
        if profile is None or user is None:
            raise ApplicationError("NOT_FOUND", "Employee account not found.", correlation_id)
        before = {"status": user.status, "session_version": user.session_version}
        changed = False
        if locked:
            has_checker_access = session.scalar(select(User.id).where(
                User.id == user.id, effective_role_filter("CHECKER"),
            )) is not None
            if has_checker_access:
                pending_count = session.scalar(select(func.count(AuthWorkflowPlan.id)).where(
                    AuthWorkflowPlan.checker_id == user.id,
                    AuthWorkflowPlan.status == "PENDING_APPROVAL",
                )) or 0
                if pending_count:
                    raise ApplicationError(
                        "CONFLICT", "Reassign pending plans before locking this Checker account.", correlation_id,
                    )
            if user.status != "DISABLED":
                user.status = "DISABLED"
                user.session_version += 1
                changed = True
            now = datetime.now(timezone.utc)
            invalidated_tokens = session.execute(
                AuthManagementToken.__table__.update()
                .where(AuthManagementToken.user_id == user.id, AuthManagementToken.consumed_at.is_(None))
                .values(consumed_at=now)
            ).rowcount or 0
            changed = changed or invalidated_tokens > 0
        else:
            if user.activation_pending:
                raise ApplicationError("CONFLICT", "The account must be activated by its recipient before it can be unlocked.", correlation_id)
            if profile.employment_status != "ACTIVE":
                raise ApplicationError("CONFLICT", "An inactive employee account cannot be unlocked.", correlation_id)
            if user.status != "ACTIVE":
                user.status = "ACTIVE"
                user.session_version += 1
                changed = True
        if changed:
            _audit(session, principal.id, profile.id, "ACCOUNT_LOCKED" if locked else "ACCOUNT_UNLOCKED",
                   before, {"status": user.status, "session_version": user.session_version,
                            "invalidated_management_tokens": invalidated_tokens if locked else 0})
    return get_employee(session, principal, employee_id, correlation_id)


def consume_management_token(session: Session, raw_token: str, password: str,
                             correlation_id: str) -> None:
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    with _write_transaction(session):
        # Read only the owner ID before locks. Loading the ORM token here would
        # leave a pre-lock instance in this Session's identity map; a waiter could
        # later observe its stale consumed_at value after the winning transaction
        # committed. Lock in the shared profile -> user -> token order instead.
        candidate_user_id = session.scalar(select(AuthManagementToken.user_id).where(
            AuthManagementToken.token_hash == token_hash,
        ))
        if candidate_user_id is None:
            raise ApplicationError("VALIDATION_ERROR", "This account link is invalid or expired.", correlation_id)
        profile = session.scalar(select(EmployeeProfile).where(
            EmployeeProfile.user_id == candidate_user_id,
        ).with_for_update())
        user = session.scalar(select(User).where(User.id == candidate_user_id).with_for_update())
        token = session.scalar(select(AuthManagementToken).where(
            AuthManagementToken.token_hash == token_hash,
        ).with_for_update().execution_options(populate_existing=True))
        now = datetime.now(timezone.utc)
        expires_at = token.expires_at.replace(tzinfo=timezone.utc) if token and token.expires_at.tzinfo is None else (token.expires_at if token else None)
        if (token is None or token.consumed_at is not None or expires_at <= now
                or token.purpose not in {"ACTIVATE", "RESET"}):
            raise ApplicationError("VALIDATION_ERROR", "This account link is invalid or expired.", correlation_id)
        if user is None or profile is None or profile.employment_status != "ACTIVE":
            raise ApplicationError("CONFLICT", "This account is not eligible for activation or reset.", correlation_id)
        if token.purpose == "ACTIVATE":
            if not user.activation_pending or user.status != "DISABLED":
                raise ApplicationError("CONFLICT", "This account has already been activated.", correlation_id)
            user.activation_pending = False
            user.status = "ACTIVE"
        elif token.purpose == "RESET":
            if user.status != "ACTIVE" or user.activation_pending:
                raise ApplicationError("CONFLICT", "This account is not active.", correlation_id)
        user.password_hash = hash_password(password)
        user.session_version += 1
        token.consumed_at = now
        _audit(session, user.id, profile.id,
               "ACCOUNT_ACTIVATED" if token.purpose == "ACTIVATE" else "PASSWORD_RESET_COMPLETED",
               None, {"purpose": token.purpose, "issued_by": str(token.issued_by)})
