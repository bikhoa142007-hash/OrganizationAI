from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.orm import Session

from src.backend.api.auth import AuthenticatedPrincipal, get_auth_db, require_any_role
from src.backend.api.internal_note_schemas import (
    InternalNoteCreateRequest,
    InternalNoteResponse,
    InternalNotesResponse,
)
from src.backend.application.workflow_notes import add_internal_note, list_internal_notes

router = APIRouter(prefix="/api/workflow", tags=["workflow internal notes"])


def _correlation(request: Request) -> str:
    return getattr(request.state, "correlation_id", "workflow-internal-notes")


@router.get("/plans/{plan_id}/internal-notes", response_model=InternalNotesResponse)
def read_internal_notes(
    plan_id: UUID,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_any_role("CHECKER")),
    session: Session = Depends(get_auth_db),
) -> InternalNotesResponse:
    return InternalNotesResponse(items=list_internal_notes(session, principal, plan_id, _correlation(request)))


@router.post(
    "/plans/{plan_id}/internal-notes",
    response_model=InternalNoteResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_internal_note(
    plan_id: UUID,
    body: InternalNoteCreateRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=200),
    principal: AuthenticatedPrincipal = Depends(require_any_role("CHECKER")),
    session: Session = Depends(get_auth_db),
) -> InternalNoteResponse:
    return InternalNoteResponse(**add_internal_note(
        session,
        principal,
        plan_id,
        body.approval_round,
        body.content,
        idempotency_key,
        _correlation(request),
    ))
