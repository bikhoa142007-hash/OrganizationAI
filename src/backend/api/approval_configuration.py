from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.backend.api.auth import (
    AuthenticatedPrincipal,
    _check_browser_origin,
    get_current_principal,
    get_auth_db,
    require_role,
)
from src.backend.api.approval_configuration_schemas import (
    ConfigurationCurrentResponse,
    ConfigurationHistoryResponse,
    ConfigurationRevisionCreate,
    ConfigurationRevisionResponse,
    ApprovalPolicySignoffRequest,
    ApprovalPolicySignoffResponse,
)
from src.backend.application import approval_configuration as configuration

router = APIRouter(prefix="/api/workflow/configuration", tags=["workflow configuration"])


def _correlation(request: Request) -> str:
    return getattr(request.state, "correlation_id", "workflow-configuration")


@router.get("", response_model=ConfigurationCurrentResponse)
def get_current_configuration(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_role("ADMIN")),
    session: Session = Depends(get_auth_db),
):
    return configuration.current_configuration(session, principal, _correlation(request))


@router.get("/{kind}/history", response_model=ConfigurationHistoryResponse)
def get_configuration_history(
    kind: str,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_role("ADMIN")),
    session: Session = Depends(get_auth_db),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    return configuration.configuration_history(
        session, kind, principal, _correlation(request), offset=offset, limit=limit,
    )


@router.post("/{kind}/revisions", response_model=ConfigurationRevisionResponse, status_code=201)
def create_configuration_revision(
    kind: str,
    body: ConfigurationRevisionCreate,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_role("ADMIN")),
    session: Session = Depends(get_auth_db),
):
    _check_browser_origin(request)
    return configuration.create_configuration_revision(
        session,
        principal,
        _correlation(request),
        kind=kind,
        expected_revision=body.expected_revision,
        effective_at=body.effective_at.astimezone(timezone.utc) if body.effective_at.tzinfo else body.effective_at,
        change_reason=body.change_reason,
        value=body.value,
    )


@router.post("/approval-policy/signoff", response_model=ApprovalPolicySignoffResponse)
def sign_off_approval_policy(
    body: ApprovalPolicySignoffRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_auth_db),
):
    _check_browser_origin(request)
    return configuration.sign_off_approval_policy(
        session,
        principal,
        _correlation(request),
        expected_revisions={
            kind: {"revision_id": str(item.revision_id), "configuration_hash": item.configuration_hash}
            for kind, item in body.expected_revisions.items()
        },
    )
