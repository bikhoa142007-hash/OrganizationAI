from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from src.ai_pipeline.orchestrator import EvaluationOrchestrator
from src.backend.api.auth import (
    AuthenticatedPrincipal,
    _check_browser_origin,
    get_current_principal,
    get_auth_db,
    require_role,
)
from src.backend.application import auth_workflow as workflow
from src.backend.application.auth_workflow_ai import provider_metadata
from .auth_workflow_schemas import (
    CreateWorkflowPlanRequest,
    SubmitWorkflowPlanRequest,
    UpdateWorkflowPlanRequest,
    WorkflowDecisionRequest,
    WorkflowPlanResponse,
    WorkflowCheckerResponse,
)

router = APIRouter(prefix="/api/workflow", tags=["authenticated workflow"])


def _correlation(request: Request) -> str:
    return getattr(request.state, "correlation_id", "workflow-request")


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
    principal: AuthenticatedPrincipal = Depends(require_role("MAKER")),
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
):
    _check_browser_origin(request)
    return workflow.create_plan(
        session,
        principal,
        body.payload.model_dump(),
        body.checker_user_id,
        _correlation(request),
    )


@router.get("/plans/{plan_id}", response_model=WorkflowPlanResponse)
def detail(
    plan_id: UUID,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_auth_db),
):
    return workflow.get_plan(session, principal, plan_id, _correlation(request))


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
    provider_name, model_version = provider_metadata(provider)
    submitted = workflow.submit_plan(
        session, principal, plan_id, body.expected_revision, _correlation(request),
        provider_name=provider_name,
        model_version=model_version,
        configuration=request.app.state.auth_workflow_configuration,
    )
    return workflow.evaluate_submission(
        session, plan_id, submitted["current_round"],
        EvaluationOrchestrator(provider), _correlation(request),
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
