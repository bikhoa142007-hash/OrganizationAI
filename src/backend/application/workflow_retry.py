from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Callable
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from src.backend.api.auth import AuthenticatedPrincipal
from src.backend.application.workflow import ApplicationError
from src.backend.db.models.auth_workflow import (
    AuthWorkflowDecision,
    AuthWorkflowEngineDecision,
    AuthWorkflowEvaluationRun,
    AuthWorkflowEvent,
    AuthWorkflowPlan,
    AuthWorkflowVersion,
)

EvaluateRun = Callable[[Session, UUID, UUID, Any, str], Any]
_RETRYABLE_FAILURE_CODES = frozenset({
    "PIPELINE_TIMEOUT",
    "PROVIDER_TIMEOUT",
    "PROVIDER_ERROR",
    "PROVIDER_UNAVAILABLE",
    "RATE_LIMITED",
    "INVALID_SCHEMA",
    "INVALID_PROVIDER_RESPONSE",
})
_TERMINAL_FAILURE_CODES = frozenset({
    "UNKNOWN_MODEL",
    "MODEL_IDENTITY_UNVERIFIED",
    "MODEL_DIGEST_MISMATCH",
    "MODEL_NOT_FOUND",
    "MODEL_CONFIGURATION_CHANGED",
    "CONFIG_SNAPSHOT_MISMATCH",
    "POLICY_OUTPUT_CONFLICT",
    "EVALUATOR_RUBRIC_UNSUPPORTED",
})
_PERSISTABLE_EVALUATOR_FAILURE_CODES = _RETRYABLE_FAILURE_CODES | _TERMINAL_FAILURE_CODES
_REQUIRED_RETRY_COLUMNS = frozenset({
    "attempt_number",
    "retry_parent_run_id",
    "retry_idempotency_key",
    "retry_request_hash",
    "result_disposition",
})
_RUN_RESET_FIELDS = {
    "id",
    "run_id",
    "evaluation_id",
    "idempotency_key",
    "correlation_id",
    "status",
    "attempts",
    "retried",
    "evaluation",
    "visual_extraction",
    "media_evaluation",
    "strategy_evaluation",
    "failure_reason",
    "started_at",
    "completed_at",
    "created_at",
    "attempt_number",
    "retry_parent_run_id",
    "retry_idempotency_key",
    "retry_request_hash",
    "result_disposition",
}


def _fail(code: str, message: str, correlation_id: str) -> None:
    raise ApplicationError(code, message, correlation_id)


def _request_hash(expected_plan_version: int, expected_round_revision: int) -> str:
    encoded = json.dumps(
        {"expected_plan_version": expected_plan_version, "expected_round_revision": expected_round_revision},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_retry_storage(correlation_id: str) -> None:
    mapped_columns = {column.key for column in AuthWorkflowEvaluationRun.__table__.columns}
    if not _REQUIRED_RETRY_COLUMNS.issubset(mapped_columns):
        _fail("UNAVAILABLE", "Manual AI retry storage is not integrated.", correlation_id)


def _resolve_evaluator(correlation_id: str) -> EvaluateRun:
    try:
        from src.backend.application.auth_workflow import evaluate_run_by_id
    except (ImportError, AttributeError) as exc:
        raise ApplicationError(
            "UNAVAILABLE",
            "Manual AI retry evaluation hook is not integrated.",
            correlation_id,
        ) from exc
    return evaluate_run_by_id


def _require_assigned_checker(
    session: Session,
    principal: AuthenticatedPrincipal,
    plan_id: UUID,
    correlation_id: str,
) -> AuthWorkflowPlan:
    if "CHECKER" not in principal.roles:
        _fail("FORBIDDEN", "Only the assigned Checker can retry an evaluation.", correlation_id)
    plan = session.get(AuthWorkflowPlan, plan_id)
    if plan is None:
        _fail("NOT_FOUND", "Plan was not found.", correlation_id)
    if plan.checker_id != principal.id or plan.maker_id == principal.id:
        _fail("FORBIDDEN", "Only the assigned Checker can retry this evaluation.", correlation_id)
    return plan


def _find_retry_by_key(
    session: Session,
    plan_id: UUID,
    round_number: int,
    idempotency_key: str,
):
    return session.scalar(
        select(AuthWorkflowEvaluationRun).where(
            AuthWorkflowEvaluationRun.plan_id == plan_id,
            AuthWorkflowEvaluationRun.round_number == round_number,
            AuthWorkflowEvaluationRun.retry_idempotency_key == idempotency_key,
        )
    )


def _response(session: Session, plan_id: UUID, retry_run: Any) -> dict[str, Any]:
    plan = session.get(AuthWorkflowPlan, plan_id)
    current_run = session.get(AuthWorkflowEvaluationRun, retry_run.id)
    if plan is None or current_run is None:
        raise ApplicationError("UNAVAILABLE", "Retry result could not be loaded.", "workflow-retry")
    engine_decision = session.scalar(
        select(AuthWorkflowEngineDecision)
        .where(AuthWorkflowEngineDecision.evaluation_run_id == current_run.id)
        .order_by(AuthWorkflowEngineDecision.created_at.desc())
        .limit(1)
    )
    return {
        "plan_id": plan.id,
        "plan_version": current_run.version_number,
        "approval_round": current_run.round_number,
        "run_id": current_run.run_id,
        "run_status": current_run.status,
        "processing_stage": plan.processing_stage,
        "decision_id": engine_decision.decision_id if engine_decision else None,
        "attempt_number": current_run.attempt_number,
        "result_disposition": current_run.result_disposition,
    }


def _failure_codes(run: Any) -> set[str]:
    codes: set[str] = set()
    if isinstance(run.failure_reason, str) and run.failure_reason:
        codes.add(run.failure_reason)
    evaluation = run.evaluation
    errors = evaluation.get("agent_errors") if isinstance(evaluation, dict) else None
    if isinstance(errors, list):
        codes.update(
            item["code"]
            for item in errors
            if isinstance(item, dict) and isinstance(item.get("code"), str)
        )
    return codes


def _is_retryable(run: Any) -> bool:
    if run.status not in {"FAILED", "TIMED_OUT"}:
        return False
    if run.result_disposition != "APPLIED":
        return False
    failure_codes = _failure_codes(run)
    return bool(failure_codes) and failure_codes.issubset(_RETRYABLE_FAILURE_CODES)


def _persistable_failure_code(error: Exception) -> str:
    if isinstance(error, ApplicationError) and error.code in _PERSISTABLE_EVALUATOR_FAILURE_CODES:
        return error.code
    return "RETRY_EVALUATOR_ERROR"


def _record_retry_evaluator_failure(
    session: Session,
    plan_id: UUID,
    evaluation_run_id: UUID,
    correlation_id: str,
    *,
    failure_code: str = "RETRY_EVALUATOR_ERROR",
) -> None:
    """Persist an evaluator exception as a terminal fail-closed run result."""
    session.rollback()
    try:
        plan = session.scalar(
            select(AuthWorkflowPlan)
            .where(AuthWorkflowPlan.id == plan_id)
            .with_for_update()
        )
        run = session.scalar(
            select(AuthWorkflowEvaluationRun)
            .where(
                AuthWorkflowEvaluationRun.id == evaluation_run_id,
                AuthWorkflowEvaluationRun.plan_id == plan_id,
            )
            .with_for_update()
        )
        if plan is None or run is None:
            _fail("NOT_FOUND", "The claimed retry run is unavailable.", correlation_id)

        if run.status not in {"PENDING", "PROCESSING"} and run.result_disposition in {"APPLIED", "STALE"}:
            session.commit()
            return

        current_decision = session.scalar(
            select(AuthWorkflowEngineDecision.id)
            .where(AuthWorkflowEngineDecision.evaluation_run_id == run.id)
            .limit(1)
        )
        checker_decision = session.scalar(
            select(AuthWorkflowDecision.id)
            .where(
                AuthWorkflowDecision.plan_id == plan_id,
                AuthWorkflowDecision.round_number == run.round_number,
            )
            .limit(1)
        )
        auto_approval = session.scalar(
            select(AuthWorkflowEngineDecision.id)
            .where(
                AuthWorkflowEngineDecision.plan_id == plan_id,
                AuthWorkflowEngineDecision.round_number == run.round_number,
                AuthWorkflowEngineDecision.outcome == "AUTO_APPROVED",
            )
            .limit(1)
        )
        owns_active_round = (
            plan.status == "PENDING_APPROVAL"
            and plan.current_version == run.version_number
            and plan.current_round == run.round_number
            and plan.processing_stage in {"AI_PENDING", "AI_PROCESSING", "HUMAN_REVIEW_REQUIRED"}
            and current_decision is None
            and checker_decision is None
            and auto_approval is None
        )

        run.status = "FAILED"
        run.failure_reason = failure_code
        completed_at = datetime.now(timezone.utc)
        if run.started_at is None:
            run.started_at = completed_at
        run.completed_at = completed_at
        run.result_disposition = "APPLIED" if owns_active_round else "STALE"
        if run.evaluation is None:
            run.evaluation = {
                "run_id": run.run_id,
                "plan_id": str(plan_id),
                "version": run.version_number,
                "approval_round": run.round_number,
                "status": "FAILED",
                "agent_errors": [{"code": failure_code}],
            }

        stage_before = plan.processing_stage
        if owns_active_round:
            plan.processing_stage = "HUMAN_REVIEW_REQUIRED"
            plan.decision_reason = "AI retry could not complete; Checker review is required."
            plan.revision += 1
        sequence = (session.scalar(
            select(func.max(AuthWorkflowEvent.sequence_number)).where(AuthWorkflowEvent.plan_id == plan_id)
        ) or 0) + 1
        session.add(AuthWorkflowEvent(
            id=uuid4(),
            plan_id=plan_id,
            actor_id=None,
            actor_type="SYSTEM",
            sequence_number=sequence,
            action="AI_EVALUATION_RETRY_FAILED",
            status_before=plan.status,
            status_after=plan.status,
            details={
                "round": run.round_number,
                "approval_round": run.round_number,
                "version": run.version_number,
                "attempt_number": run.attempt_number,
                "run_id": run.run_id,
                "failure_code": failure_code,
                "result_disposition": run.result_disposition,
                "processing_stage_before": stage_before,
                "processing_stage_after": plan.processing_stage,
                "result": (
                    "HUMAN_REVIEW_REQUIRED" if run.result_disposition == "APPLIED"
                    else "IGNORED_STALE"
                ),
            },
        ))
        session.commit()
    except ApplicationError:
        session.rollback()
        raise
    except SQLAlchemyError as exc:
        session.rollback()
        raise ApplicationError(
            "UNAVAILABLE",
            "Could not persist the failed retry result.",
            correlation_id,
        ) from exc


def _make_retry_run(
    latest: Any,
    *,
    attempt_number: int,
    idempotency_key: str,
    request_hash: str,
    correlation_id: str,
) -> Any:
    values: dict[str, Any] = {}
    for column in AuthWorkflowEvaluationRun.__table__.columns:
        name = column.key
        if name in _RUN_RESET_FIELDS or column.primary_key or column.computed is not None:
            continue
        if hasattr(latest, name):
            values[name] = deepcopy(getattr(latest, name))
    values.update({
        "id": uuid4(),
        "run_id": f"RUN-{uuid4().hex}",
        "evaluation_id": f"EVAL-{uuid4().hex}",
        "idempotency_key": idempotency_key,
        "correlation_id": correlation_id,
        "created_at": datetime.now(timezone.utc),
        "status": "PENDING",
        "attempts": 0,
        "retried": False,
        "evaluation": None,
        "visual_extraction": None,
        "media_evaluation": None,
        "strategy_evaluation": None,
        "failure_reason": None,
        "started_at": None,
        "completed_at": None,
        "attempt_number": attempt_number,
        "retry_parent_run_id": latest.id,
        "retry_idempotency_key": idempotency_key,
        "retry_request_hash": request_hash,
        "result_disposition": None,
    })
    return AuthWorkflowEvaluationRun(**values)


def _claim_retry(
    session: Session,
    principal: AuthenticatedPrincipal,
    plan_id: UUID,
    round_number: int,
    expected_plan_version: int,
    expected_round_revision: int,
    idempotency_key: str,
    correlation_id: str,
):
    request_hash = _request_hash(expected_plan_version, expected_round_revision)
    if session.in_transaction():
        session.commit()
    try:
        plan = session.scalar(
            select(AuthWorkflowPlan)
            .where(AuthWorkflowPlan.id == plan_id)
            .with_for_update()
        )
        if plan is None:
            _fail("NOT_FOUND", "Plan was not found.", correlation_id)
        if plan.checker_id != principal.id or plan.maker_id == principal.id:
            _fail("FORBIDDEN", "Only the assigned Checker can retry this evaluation.", correlation_id)

        existing = _find_retry_by_key(session, plan_id, round_number, idempotency_key)
        if existing is not None:
            if existing.retry_request_hash != request_hash:
                _fail("IDEMPOTENCY_CONFLICT", "Idempotency key was already used for another retry request.", correlation_id)
            session.commit()
            session.expire_all()
            return existing, False

        if (
            plan.status != "PENDING_APPROVAL"
            or plan.current_round != round_number
            or plan.current_version != expected_plan_version
            or plan.revision != expected_round_revision
            or plan.processing_stage != "HUMAN_REVIEW_REQUIRED"
        ):
            _fail("CONFLICT", "The plan or approval round has changed and cannot be retried.", correlation_id)
        if session.scalar(
            select(AuthWorkflowDecision.id).where(
                AuthWorkflowDecision.plan_id == plan_id,
                AuthWorkflowDecision.round_number == round_number,
            ).limit(1)
        ) is not None:
            _fail("CONFLICT", "A Checker has already decided this approval round.", correlation_id)
        if session.scalar(
            select(AuthWorkflowEngineDecision.id).where(
                AuthWorkflowEngineDecision.plan_id == plan_id,
                AuthWorkflowEngineDecision.round_number == round_number,
                AuthWorkflowEngineDecision.outcome == "AUTO_APPROVED",
            ).limit(1)
        ) is not None:
            _fail("CONFLICT", "This approval round is already auto-approved.", correlation_id)

        latest = session.scalar(
            select(AuthWorkflowEvaluationRun)
            .where(
                AuthWorkflowEvaluationRun.plan_id == plan_id,
                AuthWorkflowEvaluationRun.round_number == round_number,
            )
            .order_by(AuthWorkflowEvaluationRun.attempt_number.desc())
            .limit(1)
            .with_for_update()
        )
        if latest is None or latest.version_number != expected_plan_version:
            _fail("CONFLICT", "The terminal evaluation for this round is unavailable.", correlation_id)
        if latest.attempt_number != 1:
            _fail("CONFLICT", "Only one manual retry is allowed for an approval round.", correlation_id)
        if not _is_retryable(latest):
            _fail("CONFLICT", "The latest evaluation result is not eligible for manual retry.", correlation_id)

        version = session.scalar(
            select(AuthWorkflowVersion).where(
                AuthWorkflowVersion.plan_id == plan_id,
                AuthWorkflowVersion.version_number == expected_plan_version,
                AuthWorkflowVersion.round_number == round_number,
            )
        )
        if version is None or version.snapshot_hash != latest.input_hash:
            _fail("UNAVAILABLE", "The submitted version snapshot does not match the failed run.", correlation_id)

        retry_run = _make_retry_run(
            latest,
            attempt_number=latest.attempt_number + 1,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            correlation_id=correlation_id,
        )
        sequence = (session.scalar(
            select(func.max(AuthWorkflowEvent.sequence_number)).where(AuthWorkflowEvent.plan_id == plan_id)
        ) or 0) + 1
        session.add(retry_run)
        session.add(AuthWorkflowEvent(
            id=uuid4(),
            plan_id=plan_id,
            actor_id=principal.id,
            actor_type="HUMAN",
            sequence_number=sequence,
            action="AI_EVALUATION_RETRY_REQUESTED",
            status_before=plan.status,
            status_after=plan.status,
            details={
                "round": retry_run.round_number,
                "approval_round": round_number,
                "result": "RETRY_ACCEPTED",
                "version": expected_plan_version,
                "attempt_number": latest.attempt_number + 1,
                "run_id": retry_run.run_id,
                "retry_parent_run_id": str(latest.id),
                "failure_codes": sorted(_failure_codes(latest)),
            },
        ))
        session.flush()
        session.commit()
        return retry_run, True
    except ApplicationError:
        session.rollback()
        raise
    except IntegrityError:
        session.rollback()
        existing = _find_retry_by_key(session, plan_id, round_number, idempotency_key)
        if existing is not None:
            if existing.retry_request_hash != request_hash:
                _fail("IDEMPOTENCY_CONFLICT", "Idempotency key was already used for another retry request.", correlation_id)
            session.commit()
            return existing, False
        _fail("CONFLICT", "Another retry or Checker decision won the round claim.", correlation_id)
    except SQLAlchemyError as exc:
        session.rollback()
        raise ApplicationError("UNAVAILABLE", "Could not claim the manual retry.", correlation_id) from exc


def request_manual_evaluation_retry(
    session: Session,
    principal: AuthenticatedPrincipal,
    plan_id: UUID,
    round_number: int,
    *,
    expected_plan_version: int,
    expected_round_revision: int,
    idempotency_key: str,
    correlation_id: str,
    orchestrator: Any,
    evaluate_run: EvaluateRun | None = None,
) -> dict[str, Any]:
    if "CHECKER" not in principal.roles:
        _fail("FORBIDDEN", "Only the assigned Checker can retry an evaluation.", correlation_id)
    if (
        type(expected_plan_version) is not int or expected_plan_version < 1
        or type(expected_round_revision) is not int or expected_round_revision < 0
        or type(round_number) is not int or round_number < 1
        or not isinstance(idempotency_key, str)
        or not idempotency_key.strip()
        or len(idempotency_key) > 200
    ):
        _fail("VALIDATION_ERROR", "Retry request fields are invalid.", correlation_id)
    _require_assigned_checker(session, principal, plan_id, correlation_id)
    evaluator = evaluate_run or _resolve_evaluator(correlation_id)
    _require_retry_storage(correlation_id)

    retry_run, created = _claim_retry(
        session,
        principal,
        plan_id,
        round_number,
        expected_plan_version,
        expected_round_revision,
        idempotency_key,
        correlation_id,
    )
    if not created:
        session.expire_all()
        return _response(session, plan_id, retry_run)

    try:
        # The claim transaction is committed before the evaluator can make provider calls.
        evaluator(session, plan_id, retry_run.id, orchestrator, correlation_id)
    except Exception as exc:
        # Persist only a known code, never an evaluator message or raw provider output.
        _record_retry_evaluator_failure(
            session,
            plan_id,
            retry_run.id,
            correlation_id,
            failure_code=_persistable_failure_code(exc),
        )

    session.expire_all()
    return _response(session, plan_id, retry_run)
