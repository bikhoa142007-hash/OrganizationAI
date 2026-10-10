from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from src.ai_pipeline.authenticated_orchestrator import AuthenticatedEvaluationOrchestrator
from src.backend.api.auth import (
    AuthenticatedPrincipal,
    _check_browser_origin,
    get_current_principal,
    get_auth_db,
    require_any_role,
    require_role,
)
from src.backend.application import auth_workflow as workflow
from src.backend.application import employee_admin
from src.backend.application import role_admin
from src.backend.application.workflow import ApplicationError
from src.backend.application.auth_workflow_ai import provider_metadata
from .auth_workflow_schemas import (
    AccountHandoverResponse,
    AdminRoleCreateRequest,
    AdminRolePageResponse,
    AdminRoleResponse,
    AdminRoleUpdateRequest,
    AdminAuditPageResponse,
    CreateWorkflowPlanRequest,
    EmployeeAccountCreateRequest,
    EmployeeAccountCreateResponse,
    EmployeeDeactivateRequest,
    EmployeeProfileCreateRequest,
    EmployeeProfileUpdateRequest,
    EmployeePendingPlanPageResponse,
    EmployeeRoleRequest,
    SubmitWorkflowPlanRequest,
    UpdateWorkflowPlanRequest,
    WorkflowDecisionRequest,
    WorkflowPlanResponse,
    WorkflowCheckerResponse,
    WorkflowAuditPageResponse,
    WorkflowEmployeePageResponse,
    WorkflowEmployeeResponse,
)

router = APIRouter(prefix="/api/workflow", tags=["authenticated workflow"])


def _correlation(request: Request) -> str:
    return getattr(request.state, "correlation_id", "workflow-request")


@router.get("/audit", response_model=WorkflowAuditPageResponse)
def audit_events(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_role("ADMIN")),
    session: Session = Depends(get_auth_db),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
):
    return workflow.list_audit_events(
        session, principal, _correlation(request), offset=offset, limit=limit
    )


@router.get("/employees", response_model=WorkflowEmployeePageResponse)
def employees(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_auth_db),
    query: str | None = Query(default=None, max_length=120),
    role: str | None = Query(default=None, pattern="^(MAKER|CHECKER|ADMIN)$"),
    status: str | None = Query(default=None, pattern="^(ACTIVE|DISABLED|PENDING_ACTIVATION)$"),
    department: str | None = Query(default=None, max_length=120),
    job_title: str | None = Query(default=None, max_length=120),
    employment_status: str | None = Query(default=None, pattern="^(ACTIVE|INACTIVE)$"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    return employee_admin.list_employees(
        session, principal, _correlation(request),
        query=query, role=role, status=status, department=department, job_title=job_title,
        employment_status=employment_status, offset=offset, limit=limit,
    )


def _normalize_employee_contacts(values: dict, correlation_id: str) -> None:
    from src.backend.api.auth import _normalize_contact

    for field, expected_kind in (("email", "email"), ("phone", "phone")):
        if field not in values:
            continue
        value = values.get(field)
        if value is None or not value.strip():
            values[field] = None
            continue
        try:
            email, phone = _normalize_contact(value)
        except ValueError as exc:
            raise ApplicationError("VALIDATION_ERROR", str(exc), correlation_id) from exc
        normalized = email if expected_kind == "email" else phone
        if normalized is None:
            raise ApplicationError("VALIDATION_ERROR", f"{field} has an invalid format.", correlation_id)
        values[field] = normalized


@router.post("/employees", response_model=WorkflowEmployeeResponse, status_code=201)
def create_employee(
    body: EmployeeProfileCreateRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_auth_db),
):
    _check_browser_origin(request)
    values = body.model_dump()
    _normalize_employee_contacts(values, _correlation(request))
    values["user_code"] = values["user_code"].strip()
    values["display_name"] = values["display_name"].strip()
    if not values["user_code"] or not values["display_name"]:
        raise ApplicationError("VALIDATION_ERROR", "Employee code and name are required.", _correlation(request))
    for key in ("email", "phone", "department", "job_title"):
        if isinstance(values[key], str):
            values[key] = values[key].strip() or None
    return employee_admin.create_employee(session, principal, _correlation(request), values)


@router.get("/employees/{employee_id}", response_model=WorkflowEmployeeResponse)
def get_employee(
    employee_id: UUID,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_auth_db),
):
    return employee_admin.get_employee(session, principal, employee_id, _correlation(request))


@router.put("/employees/{employee_id}", response_model=WorkflowEmployeeResponse)
def update_employee(
    employee_id: UUID,
    body: EmployeeProfileUpdateRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_auth_db),
):
    _check_browser_origin(request)
    changes = body.model_dump(exclude_unset=True)
    _normalize_employee_contacts(changes, _correlation(request))
    for key, value in list(changes.items()):
        if isinstance(value, str):
            changes[key] = value.strip() or None
    if "user_code" in changes and not changes["user_code"]:
        raise ApplicationError("VALIDATION_ERROR", "Employee code cannot be blank.", _correlation(request))
    if "display_name" in changes and not changes["display_name"]:
        raise ApplicationError("VALIDATION_ERROR", "Employee name cannot be blank.", _correlation(request))
    return employee_admin.update_employee(session, principal, employee_id, _correlation(request), changes)


@router.post("/employees/{employee_id}/deactivation", response_model=WorkflowEmployeeResponse)
def deactivate_employee(
    employee_id: UUID,
    body: EmployeeDeactivateRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_auth_db),
):
    _check_browser_origin(request)
    try:
        reassignments = {UUID(plan_id): UUID(checker_id) for plan_id, checker_id in body.reassignments.items()}
    except ValueError as exc:
        raise ApplicationError("VALIDATION_ERROR", "Plan and Checker IDs must be valid UUIDs.", _correlation(request)) from exc
    return employee_admin.deactivate_employee(session, principal, employee_id, _correlation(request), reassignments)


@router.post("/employees/{employee_id}/reactivation", response_model=WorkflowEmployeeResponse)
def reactivate_employee(
    employee_id: UUID,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_auth_db),
):
    _check_browser_origin(request)
    return employee_admin.reactivate_employee(session, principal, employee_id, _correlation(request))


@router.get("/employees/{employee_id}/pending-plans", response_model=EmployeePendingPlanPageResponse)
def pending_checker_plans(
    employee_id: UUID,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_auth_db),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
):
    return employee_admin.list_pending_checker_plans(
        session, principal, employee_id, _correlation(request), offset=offset, limit=limit,
    )


@router.get("/admin-audit", response_model=AdminAuditPageResponse)
def admin_audit_events(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_auth_db),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
):
    return employee_admin.list_admin_audit_events(
        session, principal, _correlation(request), offset=offset, limit=limit,
    )


@router.post("/employees/{employee_id}/account", response_model=EmployeeAccountCreateResponse, status_code=201)
def create_employee_account(
    employee_id: UUID,
    body: EmployeeAccountCreateRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_auth_db),
):
    _check_browser_origin(request)
    return employee_admin.create_account(session, principal, employee_id, body.username, _correlation(request))


@router.post("/employees/{employee_id}/account/activation", response_model=AccountHandoverResponse)
def reissue_employee_activation_link(
    employee_id: UUID,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_auth_db),
):
    _check_browser_origin(request)
    return employee_admin.reissue_activation_link(session, principal, employee_id, _correlation(request))


@router.post("/employees/{employee_id}/account/password-reset", response_model=AccountHandoverResponse)
def request_employee_password_reset(
    employee_id: UUID,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_auth_db),
):
    _check_browser_origin(request)
    return employee_admin.request_password_reset(session, principal, employee_id, _correlation(request))


@router.post("/employees/{employee_id}/account/lock", response_model=WorkflowEmployeeResponse)
def lock_employee_account(
    employee_id: UUID,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_auth_db),
):
    _check_browser_origin(request)
    return employee_admin.set_account_lock(session, principal, employee_id, _correlation(request), locked=True)


@router.post("/employees/{employee_id}/account/unlock", response_model=WorkflowEmployeeResponse)
def unlock_employee_account(
    employee_id: UUID,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_auth_db),
):
    _check_browser_origin(request)
    return employee_admin.set_account_lock(session, principal, employee_id, _correlation(request), locked=False)


@router.put("/employees/{employee_id}/roles")
def replace_employee_roles(
    employee_id: UUID,
    body: EmployeeRoleRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_auth_db),
):
    _check_browser_origin(request)
    return role_admin.replace_employee_roles(session, principal, employee_id, _correlation(request), body.role_codes)


@router.get("/roles", response_model=AdminRolePageResponse)
def list_roles(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_auth_db),
    query: str | None = Query(default=None, max_length=120),
    status: str | None = Query(default=None, pattern="^(ACTIVE|INACTIVE)$"),
    builtin: bool | None = Query(default=None),
):
    return role_admin.list_roles(session, principal, _correlation(request),
                                 query=query, status=status, builtin=builtin)


@router.post("/roles", response_model=AdminRoleResponse, status_code=201)
def create_role(
    body: AdminRoleCreateRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_auth_db),
):
    _check_browser_origin(request)
    return role_admin.create_role(session, principal, _correlation(request), body.code, body.name,
                                  body.description, body.permissions)


@router.put("/roles/{role_id}", response_model=AdminRoleResponse)
def update_role(
    role_id: UUID,
    body: AdminRoleUpdateRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_auth_db),
):
    _check_browser_origin(request)
    return role_admin.update_role(session, principal, role_id, _correlation(request),
                                  name=body.name, description=body.description,
                                  permissions=body.permissions)


@router.post("/roles/{role_id}/deactivation", response_model=AdminRoleResponse)
def deactivate_role(
    role_id: UUID,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_auth_db),
):
    _check_browser_origin(request)
    return role_admin.deactivate_role(session, principal, role_id, _correlation(request))


@router.get("/checkers", response_model=list[WorkflowCheckerResponse])
def checkers(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_role("MAKER")),
    session: Session = Depends(get_auth_db),
):
    return workflow.list_checkers(session, principal, _correlation(request))


@router.get("/plans", response_model=list[WorkflowPlanResponse])
def plans(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_any_role("MAKER", "ADMIN")),
    session: Session = Depends(get_auth_db),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
):
    return workflow.list_plans(
        session, principal, _correlation(request), offset=offset, limit=limit
    )


@router.get("/reviews", response_model=list[WorkflowPlanResponse])
def reviews(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_role("CHECKER")),
    session: Session = Depends(get_auth_db),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
):
    return workflow.list_plans(
        session, principal, _correlation(request),
        offset=offset, limit=limit, reviews_only=True,
    )


@router.post("/plans", response_model=WorkflowPlanResponse, status_code=201)
def create_plan(
    body: CreateWorkflowPlanRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_role("MAKER")),
    session: Session = Depends(get_auth_db),
    idempotency_key: Annotated[str | None, Header(min_length=1, max_length=200)] = None,
):
    _check_browser_origin(request)
    return workflow.create_plan(
        session,
        principal,
        body.payload.model_dump(),
        body.checker_user_id,
        _correlation(request),
        idempotency_key=idempotency_key,
    )


@router.get("/plans/{plan_id}", response_model=WorkflowPlanResponse)
def detail(
    plan_id: UUID,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_auth_db),
):
    return workflow.get_plan(session, principal, plan_id, _correlation(request))


@router.post(
    "/plans/{plan_id}/rounds/{round_number}/recovery",
    response_model=WorkflowPlanResponse,
)
def recover_interrupted_round(
    plan_id: UUID,
    round_number: int,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_role("CHECKER")),
    session: Session = Depends(get_auth_db),
):
    """Explicitly route a stale evaluation to Checker review; safe to replay."""
    _check_browser_origin(request)
    return workflow.recover_stale_round(
        session, principal, plan_id, round_number, _correlation(request)
    )


@router.put("/plans/{plan_id}", response_model=WorkflowPlanResponse)
def update_plan(
    plan_id: UUID,
    body: UpdateWorkflowPlanRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_role("MAKER")),
    session: Session = Depends(get_auth_db),
):
    _check_browser_origin(request)
    return workflow.update_plan(
        session,
        principal,
        plan_id,
        body.payload.model_dump(),
        body.checker_user_id,
        "checker_user_id" in body.model_fields_set,
        body.expected_revision,
        _correlation(request),
    )


@router.post("/plans/{plan_id}/attachments", response_model=WorkflowPlanResponse)
async def upload_attachment(
    plan_id: UUID,
    request: Request,
    file: Annotated[UploadFile, File()],
    expected_revision: Annotated[int, Form(ge=0)],
    principal: AuthenticatedPrincipal = Depends(require_role("MAKER")),
    session: Session = Depends(get_auth_db),
):
    _check_browser_origin(request)
    content = await file.read(workflow.MAX_ATTACHMENT_BYTES + 1)
    filename = file.filename or "attachment"
    media_type = file.content_type or "application/octet-stream"
    await file.close()
    return workflow.upload_attachment(
        session, principal, plan_id, filename, media_type, content,
        expected_revision, _correlation(request),
    )


@router.get("/plans/{plan_id}/attachments/{attachment_id}")
def attachment(
    plan_id: UUID,
    attachment_id: UUID,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_auth_db),
):
    media_type, content = workflow.get_attachment(
        session, principal, plan_id, attachment_id, _correlation(request)
    )
    return Response(content=content, media_type=media_type, headers={"Content-Disposition": "attachment"})


@router.post("/plans/{plan_id}/submit", response_model=WorkflowPlanResponse)
def submit_plan(
    plan_id: UUID,
    body: SubmitWorkflowPlanRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_role("MAKER")),
    session: Session = Depends(get_auth_db),
):
    _check_browser_origin(request)
    provider = request.app.state.auth_workflow_provider
    provider_name, model_version, model_id = provider_metadata(provider)
    submitted = workflow.submit_plan(
        session, principal, plan_id, body.expected_revision, _correlation(request),
        provider_name=provider_name,
        model_id=model_id,
        model_version=model_version,
        configuration=request.app.state.auth_workflow_configuration,
    )
    provider_timeout = getattr(provider, "timeout_seconds", None)
    media_provider = request.app.state.auth_workflow_media_provider
    strategy_provider = request.app.state.auth_workflow_strategy_provider
    task_timeouts = [
        getattr(getattr(item, "settings", None), "timeout_seconds", 20)
        for item in (media_provider, strategy_provider)
    ]
    orchestrator_timeout = max(180, (provider_timeout or 30) * 2 + sum(task_timeouts) + 10)
    return workflow.evaluate_submission(
        session, plan_id, submitted["current_round"],
        AuthenticatedEvaluationOrchestrator(
            provider, media_provider=media_provider, strategy_provider=strategy_provider,
            timeout_seconds=orchestrator_timeout,
        ),
        _correlation(request),
    )


@router.post("/plans/{plan_id}/rounds/{round_number}/decision", response_model=WorkflowPlanResponse)
def decide(
    plan_id: UUID,
    round_number: int,
    body: WorkflowDecisionRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_role("CHECKER")),
    session: Session = Depends(get_auth_db),
):
    _check_browser_origin(request)
    return workflow.decide_plan(
        session,
        principal,
        plan_id,
        round_number,
        body.action,
        body.reason,
        body.override_reason,
        _correlation(request),
    )
