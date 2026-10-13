from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from src.backend.api.auth import AuthenticatedPrincipal
from src.backend.application.workflow import ApplicationError
from src.backend.db.models.auth_workflow import AuthWorkflowPlan


def get_dashboard(
    session: Session,
    principal: AuthenticatedPrincipal,
    correlation_id: str,
) -> dict[str, Any]:
    """Return status counts for exactly the plan scope readable by this principal."""
    roles = set(principal.roles)
    if "ADMIN" in roles:
        conditions = []
        principal_scope = "ADMIN_READ_ONLY"
    else:
        conditions = []
        if "MAKER" in roles:
            conditions.append(AuthWorkflowPlan.maker_id == principal.id)
        if "CHECKER" in roles:
            conditions.append(AuthWorkflowPlan.checker_id == principal.id)
        if not conditions:
            raise ApplicationError(
                "FORBIDDEN",
                "You do not have permission to view the workflow dashboard.",
                correlation_id,
            )
        principal_scope = (
            "MAKER_AND_CHECKER"
            if {"MAKER", "CHECKER"}.issubset(roles)
            else "MAKER_OWN" if "MAKER" in roles
            else "CHECKER_ASSIGNED"
        )

    scope_filter = or_(*conditions) if conditions else None
    grouped = select(
        AuthWorkflowPlan.status,
        AuthWorkflowPlan.processing_stage,
        func.count(AuthWorkflowPlan.id),
    )
    if scope_filter is not None:
        grouped = grouped.where(scope_filter)
    rows = session.execute(
        grouped.group_by(AuthWorkflowPlan.status, AuthWorkflowPlan.processing_stage)
    ).all()

    counts = {
        "draft": 0,
        "pending_ai": 0,
        "human_review": 0,
        "approved": 0,
        "rejected": 0,
    }
    for status, stage, amount in rows:
        if status == "DRAFT":
            counts["draft"] += amount
        elif status == "APPROVED":
            counts["approved"] += amount
        elif status == "REJECTED":
            counts["rejected"] += amount
        elif status == "PENDING_APPROVAL":
            if stage in {"AI_PENDING", "AI_PROCESSING"}:
                counts["pending_ai"] += amount
            else:
                counts["human_review"] += amount

    active_assignments_query = select(func.count(AuthWorkflowPlan.id)).where(
        AuthWorkflowPlan.status == "PENDING_APPROVAL",
        AuthWorkflowPlan.checker_id.is_not(None),
    )
    if scope_filter is not None:
        active_assignments_query = active_assignments_query.where(scope_filter)
    active_assignments = session.scalar(active_assignments_query) or 0

    return {
        "as_of": datetime.now(timezone.utc),
        "principal_scope": principal_scope,
        "counts": counts,
        "active_assignments": active_assignments,
    }
