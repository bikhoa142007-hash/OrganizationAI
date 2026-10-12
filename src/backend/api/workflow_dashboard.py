from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.backend.api.auth import AuthenticatedPrincipal, get_auth_db, require_any_role
from src.backend.api.workflow_dashboard_schemas import WorkflowDashboardResponse
from src.backend.application.workflow_dashboard import get_dashboard

router = APIRouter(prefix="/api/workflow", tags=["workflow completion"])


def _correlation(request: Request) -> str:
    return getattr(request.state, "correlation_id", "workflow-dashboard")


@router.get("/dashboard", response_model=WorkflowDashboardResponse)
def dashboard(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_any_role("MAKER", "CHECKER", "ADMIN")),
    session: Session = Depends(get_auth_db),
):
    return get_dashboard(session, principal, _correlation(request))
