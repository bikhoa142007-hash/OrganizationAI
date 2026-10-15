"""Admin-only configuration APIs for approval-round SLAs."""
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.backend.api.auth import (
    AuthenticatedPrincipal,
    _check_browser_origin,
    get_auth_db,
    require_permission,
    require_role,
)
from src.backend.application import auth_sla as sla
from .auth_sla_schemas import (
    SlaConfigurationHistoryResponse,
    SlaConfigurationResponse,
    SlaConfigurationUpdateRequest,
)

router = APIRouter(prefix="/api/workflow/sla", tags=["approval-round SLA"])


def _correlation(request: Request) -> str:
    return getattr(request.state, "correlation_id", "workflow-request")


@router.get(
    "/configuration", response_model=SlaConfigurationResponse,
    dependencies=[Depends(require_permission("ADMIN_SLA_MANAGE"))],
)
def configuration(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_role("ADMIN")),
    session: Session = Depends(get_auth_db),
):
    return sla.get_configuration(session, principal, _correlation(request))


@router.get(
    "/configuration/history", response_model=SlaConfigurationHistoryResponse,
    dependencies=[Depends(require_permission("ADMIN_SLA_MANAGE"))],
)
def configuration_history(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_role("ADMIN")),
    session: Session = Depends(get_auth_db),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    return sla.list_configuration_history(
        session, principal, _correlation(request), offset=offset, limit=limit
    )


@router.put(
    "/configuration", response_model=SlaConfigurationResponse,
    dependencies=[Depends(require_permission("ADMIN_SLA_MANAGE"))],
)
def update_configuration(
    body: SlaConfigurationUpdateRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_role("ADMIN")),
    session: Session = Depends(get_auth_db),
):
    _check_browser_origin(request)
    return sla.update_configuration(
        session,
        principal,
        enabled=body.enabled,
        duration_minutes=body.duration_minutes,
        warning_before_minutes=body.warning_before_minutes,
        expected_revision=body.expected_revision,
        change_reason=body.change_reason,
        correlation_id=_correlation(request),
    )
