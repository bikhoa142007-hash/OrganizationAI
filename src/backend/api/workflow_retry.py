from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from src.ai_pipeline.authenticated_orchestrator import AuthenticatedEvaluationOrchestrator
from src.backend.api.auth import AuthenticatedPrincipal, _check_browser_origin, get_auth_db, require_any_role
from src.backend.api.workflow_retry_schemas import (
    ManualEvaluationRetryRequest,
    ManualEvaluationRetryResponse,
)
from src.backend.application.workflow import ApplicationError
from src.backend.application.workflow_retry import request_manual_evaluation_retry

router = APIRouter(prefix="/api/workflow", tags=["workflow evaluation retry"])


def _correlation(request: Request) -> str:
    return getattr(request.state, "correlation_id", "workflow-retry")


def _orchestrator(request: Request, correlation_id: str) -> AuthenticatedEvaluationOrchestrator:
    state = request.app.state
    provider = getattr(state, "auth_workflow_provider", None)
    media_provider = getattr(state, "auth_workflow_media_provider", None)
    strategy_provider = getattr(state, "auth_workflow_strategy_provider", None)
    if provider is None or media_provider is None or strategy_provider is None:
        raise ApplicationError("UNAVAILABLE", "The retry evaluator is not configured.", correlation_id)
    provider_timeout = getattr(provider, "timeout_seconds", None)
    task_timeouts = [
        getattr(getattr(component, "settings", None), "timeout_seconds", 20)
        for component in (media_provider, strategy_provider)
    ]
    timeout_seconds = max(180, (provider_timeout or 30) * 2 + sum(task_timeouts) + 10)
    return AuthenticatedEvaluationOrchestrator(
        provider,
        media_provider=media_provider,
        strategy_provider=strategy_provider,
        timeout_seconds=timeout_seconds,
    )


@router.post(
    "/plans/{plan_id}/rounds/{round_number}/evaluation-retries",
    response_model=ManualEvaluationRetryResponse,
)
def retry_evaluation(
    plan_id: UUID,
    round_number: int,
    body: ManualEvaluationRetryRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=200),
    principal: AuthenticatedPrincipal = Depends(require_any_role("CHECKER")),
    session: Session = Depends(get_auth_db),
) -> ManualEvaluationRetryResponse:
    _check_browser_origin(request)
    correlation_id = _correlation(request)
    result = request_manual_evaluation_retry(
        session,
        principal,
        plan_id,
        round_number,
        expected_plan_version=body.expected_plan_version,
        expected_round_revision=body.expected_round_revision,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        orchestrator=_orchestrator(request, correlation_id),
    )
    return ManualEvaluationRetryResponse(**result)
