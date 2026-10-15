from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
from io import BytesIO
import re
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, NoReturn
from uuid import UUID, uuid4
import warnings

from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.backend.application.workflow import ApplicationError
from src.backend.application.auth_sla import close_round_snapshot, plan_sla_read_model, start_round_snapshot
from src.backend.application.approval_configuration import (
    apply_round_configuration_snapshot,
    capture_round_configuration_snapshot,
    get_round_configuration_snapshot,
    lock_configuration_registry,
)
from src.backend.application.checker_assignment_configuration import (
    list_effective_checker_options,
    resolve_checker_assignment,
)
from src.backend.application.role_admin import effective_role_filter
from src.backend.db.models import (
    AuthWorkflowAttachment,
    AuthWorkflowDecision,
    AuthWorkflowEngineDecision,
    AuthWorkflowEvent,
    AuthWorkflowEvaluationRun,
    AuthWorkflowNotification,
    AuthWorkflowPlan,
    AuthWorkflowVersion,
    EmployeeProfile,
    User,
)
from src.ai_pipeline.models import EvaluationRequest
from src.ai_pipeline.orchestrator import EvaluationOrchestrator
from src.ai_pipeline.authenticated_orchestrator import initial_evaluation_step
from src.backend.domain.models import AttachmentManifest, MarketingPlan
from src.backend.domain.policy import ApprovalConfiguration
from src.backend.rules.decision import DecisionContext, decide
from src.shared.validation import canonical_hash

if TYPE_CHECKING:
    from src.backend.api.auth import AuthenticatedPrincipal

MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
ALLOWED_MEDIA = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
    "image/webp": "WEBP",
}
MAX_IMAGE_PIXELS = 25_000_000


def _fail(code: str, message: str, correlation_id: str) -> NoReturn:
    raise ApplicationError(code, message, correlation_id)


def _valid_image(content: bytes, media_type: str) -> bool:
    expected_format = ALLOWED_MEDIA.get(media_type)
    if expected_format is None:
        return False
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                width, height = image.size
                if image.format != expected_format or width <= 0 or height <= 0:
                    return False
                if width * height > MAX_IMAGE_PIXELS:
                    return False
                image.verify()
        return True
    except (Image.DecompressionBombError, Image.DecompressionBombWarning,
            UnidentifiedImageError, OSError, ValueError, SyntaxError):
        return False


def _require_permission(principal: AuthenticatedPrincipal, permission_code: str, correlation_id: str) -> None:
    if permission_code not in principal.permissions:
        _fail("FORBIDDEN", "You do not have permission to perform this action.", correlation_id)


def _require_role(principal: AuthenticatedPrincipal, role: str, correlation_id: str) -> None:
    if role not in principal.roles:
        _fail("FORBIDDEN", "You do not have permission to perform this action.", correlation_id)


def _require_workflow_role(principal: AuthenticatedPrincipal, correlation_id: str) -> None:
    if not {"MAKER", "CHECKER", "ADMIN"}.intersection(principal.roles):
        _fail("FORBIDDEN", "You do not have permission to perform this action.", correlation_id)


def _write_transaction(session: Session):
    # get_current_principal performs a read with the same request-scoped Session.
    # End that read transaction before opening an explicit write transaction.
    if session.in_transaction():
        session.rollback()
    return session.begin()


def _checker_user(session: Session, checker_id: UUID | None) -> User | None:
    if checker_id is None:
        return None
    return session.scalar(
        select(User)
        .where(
            User.id == checker_id,
            User.status == "ACTIVE",
            User.activation_pending.is_(False),
            User.employment_status == "ACTIVE",
            effective_role_filter("CHECKER"),
        ).with_for_update()
    )


def _validate_checker(
    session: Session,
    principal: AuthenticatedPrincipal,
    checker_id: UUID | None,
    correlation_id: str,
    *,
    required: bool = False,
) -> None:
    if checker_id is None:
        if required:
            _fail("VALIDATION_ERROR", "A valid Checker must be assigned before submission.", correlation_id)
        return
    if checker_id == principal.id:
        _fail("VALIDATION_ERROR", "A Maker cannot be assigned to approve their own plan.", correlation_id)
    if _checker_user(session, checker_id) is None:
        _fail("VALIDATION_ERROR", "The selected Checker is not an active Checker account.", correlation_id)


def _resolve_plan_checker_assignment(
    session: Session,
    principal: AuthenticatedPrincipal,
    payload: dict[str, Any],
    selected_checker_id: UUID | None,
    effective_at: datetime,
    correlation_id: str,
    *,
    lock_configuration: bool = False,
):
    department = payload.get("department")
    assignment = resolve_checker_assignment(
        session,
        department if isinstance(department, str) else None,
        principal.id,
        selected_checker_id,
        effective_at,
        lock_eligible_checker=True,
        lock_configuration=lock_configuration,
    )
    if (
        selected_checker_id is not None
        and (assignment.status != "CONFIGURED" or not assignment.eligible)
    ):
        _fail(
            "VALIDATION_ERROR",
            "The selected Checker is not allowed by the effective department assignment.",
            correlation_id,
        )
    return assignment


def _plan_or_404(session: Session, plan_id: UUID, correlation_id: str, *, lock: bool = False):
    statement = select(AuthWorkflowPlan).where(AuthWorkflowPlan.id == plan_id)
    if lock:
        statement = statement.with_for_update()
    plan = session.scalar(statement)
    if plan is None:
        _fail("NOT_FOUND", "Plan not found.", correlation_id)
    return plan


def _maker_plan(plan: AuthWorkflowPlan, principal: AuthenticatedPrincipal, correlation_id: str) -> None:
    if "MAKER" not in principal.roles or plan.maker_id != principal.id:
        _fail("NOT_FOUND", "Plan not found.", correlation_id)


def _readable_plan(plan: AuthWorkflowPlan, principal: AuthenticatedPrincipal, correlation_id: str) -> None:
    _require_workflow_role(principal, correlation_id)
    if "ADMIN" in principal.roles:
        return
    owns = "MAKER" in principal.roles and plan.maker_id == principal.id
    assigned = "CHECKER" in principal.roles and plan.checker_id == principal.id
    if not owns and not assigned:
        _fail("NOT_FOUND", "Plan not found.", correlation_id)


def _attachment_dict(item: AuthWorkflowAttachment) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "filename": item.filename,
        "media_type": item.media_type,
        "byte_size": item.byte_size,
        "content_hash": item.content_hash,
        "created_at": item.created_at,
    }


def _domain_snapshot(
    plan_id: UUID | str,
    version_number: int,
    round_number: int,
    payload: dict[str, Any],
    attachment_snapshot: list[dict[str, Any]],
) -> MarketingPlan:
    return MarketingPlan(
        str(plan_id),
        version_number,
        round_number,
        payload,
        tuple(AttachmentManifest(
            attachment_id=str(item["id"]),
            content_hash=item["content_hash"],
            media_type=item["media_type"],
            byte_size=item["byte_size"],
        ) for item in attachment_snapshot),
    )


def _round_configuration_snapshot_is_valid(
    snapshot,
    plan_id: UUID,
    plan_version: int,
    approval_round: int,
) -> bool:
    if (
        snapshot is None
        or snapshot.plan_id != plan_id
        or snapshot.plan_version != plan_version
        or snapshot.approval_round != approval_round
    ):
        return False
    body = snapshot.as_dict()
    recorded_hash = body.pop("snapshot_hash", None)
    body.pop("snapshot_id", None)
    return isinstance(recorded_hash, str) and canonical_hash(body) == recorded_hash


def _now_datetime() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp() -> str:
    return _now_datetime().isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _utc_datetime(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _audit_evaluation_summary(evaluation: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    """Keep only decision-relevant scalar outcomes in the workflow audit trail."""
    findings = evaluation.get("media_findings") or []
    errors = evaluation.get("agent_errors") or []
    budget = decision.get("budget_validation") or {}
    rule_checks = decision.get("rule_checks") or []
    return {
        "status": evaluation.get("status"),
        "media_result": evaluation.get("media_result"),
        "media_confidence": evaluation.get("media_confidence"),
        "hard_violation_count": sum(item.get("severity") == "HARD_VIOLATION" for item in findings),
        "warning_count": sum(item.get("severity") == "WARNING" for item in findings),
        "feasibility_score": evaluation.get("feasibility_score"),
        "criterion_scores": [
            {
                "criterion_id": item.get("criterion_id"),
                "score": item.get("score"),
                "maximum_score": item.get("maximum_score"),
            }
            for item in evaluation.get("criterion_scores") or []
            if item.get("criterion_id")
        ],
        "feasibility_confidence": evaluation.get("feasibility_confidence"),
        "agent_error_codes": sorted({item.get("code") for item in errors if item.get("code")}),
        "budget_result": budget.get("result"),
        "rule_results": [
            {"rule_id": item.get("rule_id"), "result": item.get("result")}
            for item in rule_checks if item.get("rule_id") and item.get("result")
        ],
        "decision_outcome": decision.get("outcome"),
    }


def _record_event(
    session: Session,
    *,
    plan_id: UUID,
    actor_id: UUID | None,
    actor_type: str = "HUMAN",
    action: str,
    status_before: str | None,
    status_after: str,
    details: dict[str, Any],
    actor_role: str | None = None,
    result: str = "SUCCESS",
) -> AuthWorkflowEvent:
    last_sequence = session.scalar(
        select(func.max(AuthWorkflowEvent.sequence_number)).where(AuthWorkflowEvent.plan_id == plan_id)
    ) or 0
    audit_details = dict(details)
    plan = session.get(AuthWorkflowPlan, plan_id)
    if plan is not None:
        audit_details.setdefault("version", plan.current_version or None)
        audit_details.setdefault("round", plan.current_round or None)
    audit_details.setdefault("result", result)
    if actor_role is not None:
        audit_details.setdefault("actor_role", actor_role)
    event = AuthWorkflowEvent(
        id=uuid4(),
        plan_id=plan_id,
        actor_id=actor_id,
        actor_type=actor_type,
        sequence_number=int(last_sequence) + 1,
        action=action,
        status_before=status_before,
        status_after=status_after,
        details=audit_details,
    )
    session.add(event)
    return event


def _record_notification(
    session: Session,
    *,
    recipient_user_id: UUID,
    plan: AuthWorkflowPlan,
    event_type: str,
    version_number: int,
    round_number: int,
    reason: str | None = None,
) -> AuthWorkflowNotification:
    copy = {
        "PLAN_SUBMITTED": (
            "Kế hoạch cần được duyệt",
            f"Kế hoạch {plan.code} đã được gửi duyệt (phiên bản {version_number}, vòng {round_number}).",
        ),
        "PLAN_APPROVED": (
            "Kế hoạch đã được phê duyệt",
            f"Checker đã phê duyệt kế hoạch {plan.code} (vòng {round_number}).",
        ),
        "PLAN_AUTO_APPROVED": (
            "Kế hoạch đã được phê duyệt tự động",
            f"Hệ thống đã tự động phê duyệt kế hoạch {plan.code} (vòng {round_number}).",
        ),
        "PLAN_REJECTED": (
            "Kế hoạch cần được chỉnh sửa",
            f"Checker đã từ chối kế hoạch {plan.code} (vòng {round_number}). Lý do: {reason.strip() if isinstance(reason, str) else ''}",
        ),
        "PLAN_AUTO_REJECTED": (
            "Hệ thống từ chối kế hoạch",
            f"Hệ thống đã từ chối kế hoạch {plan.code} theo rule đã ký (vòng {round_number}). Lý do: {reason.strip() if isinstance(reason, str) else ''}",
        ),
    }.get(event_type)
    if copy is None:
        raise ValueError("Unsupported workflow notification event type")
    if event_type in {"PLAN_REJECTED", "PLAN_AUTO_REJECTED"} and (not isinstance(reason, str) or not reason.strip()):
        raise ValueError("A rejection notification requires its decision reason")
    event_key = f"plan:{plan.id}:round:{round_number}:{event_type.lower()}:user:{recipient_user_id}"
    existing = session.scalar(
        select(AuthWorkflowNotification).where(AuthWorkflowNotification.event_key == event_key)
    )
    if existing is not None:
        return existing
    notification = AuthWorkflowNotification(
        id=uuid4(),
        recipient_user_id=recipient_user_id,
        plan_id=plan.id,
        event_key=event_key,
        event_type=event_type,
        title=copy[0],
        message=copy[1],
        version_number=version_number,
        round_number=round_number,
    )
    session.add(notification)
    return notification


def _notification_dict(notification: AuthWorkflowNotification, plan_code: str) -> dict[str, Any]:
    return {
        "id": str(notification.id),
        "event_type": notification.event_type,
        "plan_id": str(notification.plan_id),
        "plan_code": plan_code,
        "title": notification.title,
        "message": notification.message,
        "version_number": notification.version_number,
        "round_number": notification.round_number,
        "created_at": _utc_datetime(notification.created_at),
        "read_at": _utc_datetime(notification.read_at),
    }


def _plan_dict(session: Session, plan: AuthWorkflowPlan) -> dict[str, Any]:
    maker = session.get(User, plan.maker_id)
    checker = session.get(User, plan.checker_id) if plan.checker_id else None
    attachments = session.scalars(
        select(AuthWorkflowAttachment)
        .where(AuthWorkflowAttachment.plan_id == plan.id)
        .order_by(AuthWorkflowAttachment.created_at, AuthWorkflowAttachment.id)
    ).all()
    versions = session.scalars(
        select(AuthWorkflowVersion)
        .where(AuthWorkflowVersion.plan_id == plan.id)
        .order_by(AuthWorkflowVersion.version_number)
    ).all()
    events = session.scalars(
        select(AuthWorkflowEvent)
        .where(AuthWorkflowEvent.plan_id == plan.id)
        .order_by(AuthWorkflowEvent.sequence_number)
    ).all()
    sla_current, sla_history = plan_sla_read_model(session, plan, versions)
    history = []
    for event in events:
        actor = session.get(User, event.actor_id) if event.actor_id else None
        history.append({
            "id": str(event.id),
            "actor_id": str(event.actor_id) if event.actor_id else None,
            "actor_type": event.actor_type,
            "actor_name": actor.display_name if actor else "OrganizationAI" if event.actor_type == "SYSTEM" else "Unknown user",
            "action": event.action,
            "status_before": event.status_before,
            "status_after": event.status_after,
            "details": event.details or {},
            "created_at": event.created_at,
        })
    return {
        "id": str(plan.id),
        "code": plan.code,
        "payload": plan.payload or {},
        "status": plan.status,
        "processing_stage": plan.processing_stage,
        "maker_id": str(plan.maker_id),
        "maker_name": maker.display_name if maker else "Unknown user",
        "checker_id": str(plan.checker_id) if plan.checker_id else None,
        "checker_name": checker.display_name if checker else None,
        "current_version": plan.current_version,
        "current_round": plan.current_round,
        "revision": plan.revision,
        "decision_reason": plan.decision_reason,
        "sla_current": sla_current,
        "sla_history": sla_history,
        "attachments": [_attachment_dict(item) for item in attachments],
        "versions": [{
            "version_number": item.version_number,
            "round_number": item.round_number,
            "payload": item.payload_snapshot,
            "attachments": item.attachment_snapshot,
            "snapshot_hash": item.snapshot_hash,
            "submitted_by": str(item.submitted_by),
            "created_at": item.created_at,
        } for item in versions],
        "ai_evaluations": [{
            "id": str(item.id),
            "version_number": item.version_number,
            "round_number": item.round_number,
            "attempt_number": item.attempt_number,
            "result_disposition": item.result_disposition,
            "run_id": item.run_id,
            "evaluation_id": item.evaluation_id,
            "correlation_id": item.correlation_id,
            "input_hash": item.input_hash,
            "provider": item.provider,
            "model_id": item.model_id,
            "model_version": item.model_version,
            "policy_version": item.policy_version,
            "policy_snapshot_id": item.policy_snapshot_id,
            "policy_snapshot_hash": item.policy_snapshot_hash,
            "status": item.status,
            "attempts": item.attempts,
            "retried": item.retried,
            "evaluation": item.evaluation,
            "visual_extraction": item.visual_extraction,
            "media_evaluation": item.media_evaluation,
            "strategy_evaluation": item.strategy_evaluation,
            "failure_reason": item.failure_reason,
            "started_at": item.started_at,
            "completed_at": item.completed_at,
            "created_at": item.created_at,
        } for item in session.scalars(
            select(AuthWorkflowEvaluationRun)
            .where(AuthWorkflowEvaluationRun.plan_id == plan.id)
            .order_by(
                AuthWorkflowEvaluationRun.round_number,
                AuthWorkflowEvaluationRun.attempt_number,
            )
        ).all()],
        "engine_decisions": [{
            "id": str(item.id),
            "version_number": item.version_number,
            "round_number": item.round_number,
            "decision_id": item.decision_id,
            "outcome": item.outcome,
            "decision": item.decision,
            "created_at": item.created_at,
        } for item in session.scalars(
            select(AuthWorkflowEngineDecision)
            .join(
                AuthWorkflowEvaluationRun,
                AuthWorkflowEvaluationRun.id == AuthWorkflowEngineDecision.evaluation_run_id,
            )
            .where(AuthWorkflowEngineDecision.plan_id == plan.id)
            .order_by(
                AuthWorkflowEngineDecision.round_number,
                AuthWorkflowEvaluationRun.attempt_number,
            )
        ).all()],
        "history": history,
        "created_at": plan.created_at,
        "updated_at": plan.updated_at,
    }


def list_checkers(
    session: Session,
    principal: AuthenticatedPrincipal,
    correlation_id: str,
    department_id: str | None = None,
):
    _require_role(principal, "MAKER", correlation_id)
    if department_id is not None:
        users = list_effective_checker_options(
            session,
            department_id,
            principal.id,
            _now_datetime(),
        )
        return [{"id": str(user.id), "display_name": user.display_name} for user in users]

    # Preserve the legacy unfiltered response for existing clients. The Maker
    # form supplies a department and uses the effective-assignment-filtered path.
    users = session.scalars(
        select(User)
        .where(
            User.status == "ACTIVE", User.activation_pending.is_(False),
            User.employment_status == "ACTIVE", effective_role_filter("CHECKER"),
            User.id != principal.id,
        )
        .order_by(User.display_name, User.user_code)
    ).unique().all()
    return [{"id": str(user.id), "display_name": user.display_name} for user in users]


def list_plans(
    session: Session,
    principal: AuthenticatedPrincipal,
    correlation_id: str,
    *,
    offset: int = 0,
    limit: int = 100,
    reviews_only: bool = False,
):
    if reviews_only:
        _require_permission(principal, "MARKETING_REVIEW_ASSIGNED", correlation_id)
    else:
        _require_permission(principal, "MARKETING_PLAN_READ", correlation_id)
        if "ADMIN" in principal.roles:
            _require_permission(principal, "MARKETING_PLAN_VIEW_ALL", correlation_id)
    _require_workflow_role(principal, correlation_id)
    conditions = []
    if "MAKER" in principal.roles and not reviews_only:
        conditions.append(AuthWorkflowPlan.maker_id == principal.id)
    if "CHECKER" in principal.roles:
        conditions.append(AuthWorkflowPlan.checker_id == principal.id)
    if "ADMIN" in principal.roles and not reviews_only:
        conditions.append(AuthWorkflowPlan.id.is_not(None))
    if reviews_only:
        _require_role(principal, "CHECKER", correlation_id)
        conditions = [
            AuthWorkflowPlan.checker_id == principal.id,
            AuthWorkflowPlan.status == "PENDING_APPROVAL",
        ]
    plans = session.scalars(
        select(AuthWorkflowPlan)
        .where(or_(*conditions))
        .order_by(AuthWorkflowPlan.updated_at.desc(), AuthWorkflowPlan.id)
        .offset(offset)
        .limit(limit)
    ).all()
    return [_plan_dict(session, plan) for plan in plans]


def get_plan(
    session: Session,
    principal: AuthenticatedPrincipal,
    plan_id: UUID,
    correlation_id: str,
):
    _require_permission(principal, "MARKETING_PLAN_READ", correlation_id)
    _require_permission(principal, "MARKETING_HISTORY_READ", correlation_id)
    if "ADMIN" in principal.roles:
        _require_permission(principal, "MARKETING_PLAN_VIEW_ALL", correlation_id)
    _require_workflow_role(principal, correlation_id)
    plan = _plan_or_404(session, plan_id, correlation_id)
    _readable_plan(plan, principal, correlation_id)
    return _plan_dict(session, plan)


def list_notifications(
    session: Session,
    principal: AuthenticatedPrincipal,
    *,
    offset: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    recipient_id = principal.id
    recipient_filter = AuthWorkflowNotification.recipient_user_id == recipient_id
    total = session.scalar(
        select(func.count(AuthWorkflowNotification.id)).where(recipient_filter)
    ) or 0
    unread_count = session.scalar(
        select(func.count(AuthWorkflowNotification.id)).where(
            recipient_filter, AuthWorkflowNotification.read_at.is_(None)
        )
    ) or 0
    rows = session.execute(
        select(AuthWorkflowNotification, AuthWorkflowPlan.code)
        .join(AuthWorkflowPlan, AuthWorkflowPlan.id == AuthWorkflowNotification.plan_id)
        .where(recipient_filter)
        .order_by(AuthWorkflowNotification.created_at.desc(), AuthWorkflowNotification.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return {
        "items": [_notification_dict(notification, plan_code) for notification, plan_code in rows],
        "offset": offset,
        "limit": limit,
        "total": total,
        "unread_count": unread_count,
    }


def mark_notification_read(
    session: Session,
    principal: AuthenticatedPrincipal,
    notification_id: UUID,
    correlation_id: str,
) -> dict[str, Any]:
    with _write_transaction(session):
        notification = session.scalar(
            select(AuthWorkflowNotification)
            .where(
                AuthWorkflowNotification.id == notification_id,
                AuthWorkflowNotification.recipient_user_id == principal.id,
            )
            .with_for_update()
        )
        if notification is None:
            _fail("NOT_FOUND", "Notification not found.", correlation_id)
        if notification.read_at is None:
            notification.read_at = _now_datetime()
            session.flush()
        plan_code = session.scalar(
            select(AuthWorkflowPlan.code).where(AuthWorkflowPlan.id == notification.plan_id)
        )
        return _notification_dict(notification, plan_code)


def list_audit_events(
    session: Session,
    principal: AuthenticatedPrincipal,
    correlation_id: str,
    *,
    offset: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    _require_role(principal, "ADMIN", correlation_id)
    _require_permission(principal, "ADMIN_AUDIT_READ", correlation_id)
    total = session.scalar(select(func.count(AuthWorkflowEvent.id))) or 0
    rows = session.execute(
        select(AuthWorkflowEvent, AuthWorkflowPlan.code, User.display_name)
        .join(AuthWorkflowPlan, AuthWorkflowPlan.id == AuthWorkflowEvent.plan_id)
        .outerjoin(User, User.id == AuthWorkflowEvent.actor_id)
        .order_by(
            AuthWorkflowEvent.created_at.desc(),
            AuthWorkflowEvent.plan_id,
            AuthWorkflowEvent.sequence_number.desc(),
        )
        .offset(offset)
        .limit(limit)
    ).all()
    return {
        "items": [{
            "id": str(event.id),
            "plan_id": str(event.plan_id),
            "plan_code": plan_code,
            "actor_id": str(event.actor_id) if event.actor_id else None,
            "actor_type": event.actor_type,
            "actor_name": actor_name or "System",
            "action": event.action,
            "status_before": event.status_before,
            "status_after": event.status_after,
            "details": event.details,
            "created_at": event.created_at,
        } for event, plan_code, actor_name in rows],
        "offset": offset,
        "limit": limit,
        "total": total,
    }


def create_plan(
    session: Session,
    principal: AuthenticatedPrincipal,
    payload: dict[str, Any],
    checker_id: UUID | None,
    correlation_id: str,
    *,
    idempotency_key: str | None = None,
):
    _require_role(principal, "MAKER", correlation_id)
    _require_permission(principal, "MARKETING_PLAN_CREATE", correlation_id)
    request_hash = canonical_hash({
        "payload": payload,
        "checker_user_id": str(checker_id) if checker_id is not None else None,
    })
    try:
        with _write_transaction(session):
            existing = None
            if idempotency_key is not None:
                existing = session.scalar(select(AuthWorkflowPlan).where(
                    AuthWorkflowPlan.maker_id == principal.id,
                    AuthWorkflowPlan.creation_idempotency_key == idempotency_key,
                ))
            if existing is not None:
                if existing.creation_request_hash != request_hash:
                    _fail("IDEMPOTENCY_CONFLICT", "The draft request key was already used for different plan data.", correlation_id)
                result = _plan_dict(session, existing)
            else:
                checker_assignment = _resolve_plan_checker_assignment(
                    session, principal, payload, checker_id, _now_datetime(), correlation_id,
                    lock_configuration=True,
                )
                checker_id = checker_assignment.checker_id
                _validate_checker(session, principal, checker_id, correlation_id)
                plan_id = uuid4()
                plan = AuthWorkflowPlan(
                    id=plan_id,
                    code=f"MKT-{plan_id.hex[:12].upper()}",
                    maker_id=principal.id,
                    checker_id=checker_id,
                    payload=payload,
                    creation_idempotency_key=idempotency_key,
                    creation_request_hash=request_hash if idempotency_key is not None else None,
                    status="DRAFT",
                    processing_stage="DRAFT",
                    current_version=0,
                    current_round=0,
                    revision=0,
                )
                session.add(plan)
                session.flush()
                _record_event(
                    session, plan_id=plan.id, actor_id=principal.id,
                    action="CREATED", status_before=None, status_after=plan.status,
                    details={
                        "code": plan.code,
                        "checker_id": str(plan.checker_id) if plan.checker_id else None,
                        "checker_assignment_source": checker_assignment.source,
                        "checker_assignment_revision": checker_assignment.configuration_revision,
                    }, actor_role="MAKER",
                )
                session.flush()
                session.refresh(plan)
                result = _plan_dict(session, plan)
    except IntegrityError:
        session.rollback()
        if idempotency_key is not None:
            existing = session.scalar(select(AuthWorkflowPlan).where(
                AuthWorkflowPlan.maker_id == principal.id,
                AuthWorkflowPlan.creation_idempotency_key == idempotency_key,
            ))
            if existing is not None:
                if existing.creation_request_hash != request_hash:
                    _fail("IDEMPOTENCY_CONFLICT", "The draft request key was already used for different plan data.", correlation_id)
                return _plan_dict(session, existing)
        _fail("CONFLICT", "Could not create the plan; retry with a new request.", correlation_id)
    return result


def update_plan(
    session: Session,
    principal: AuthenticatedPrincipal,
    plan_id: UUID,
    payload: dict[str, Any],
    checker_id: UUID | None,
    update_checker: bool,
    expected_revision: int,
    correlation_id: str,
):
    _require_role(principal, "MAKER", correlation_id)
    _require_permission(principal, "MARKETING_PLAN_EDIT_OWN", correlation_id)
    try:
        with _write_transaction(session):
            plan = _plan_or_404(session, plan_id, correlation_id, lock=True)
            _maker_plan(plan, principal, correlation_id)
            if plan.status not in {"DRAFT", "REJECTED"}:
                _fail("CONFLICT", "Submitted and approved plans are read-only.", correlation_id)
            if plan.revision != expected_revision:
                _fail("CONFLICT", "The plan changed. Reload it before saving.", correlation_id)
            current_payload = plan.payload or {}
            previous_checker = plan.checker_id
            department_changed = current_payload.get("department") != payload.get("department")
            next_checker = checker_id if update_checker else plan.checker_id
            if not update_checker and department_changed:
                next_checker = None
            checker_assignment = _resolve_plan_checker_assignment(
                session, principal, payload, next_checker, _now_datetime(), correlation_id,
                lock_configuration=True,
            )
            next_checker = checker_assignment.checker_id
            _validate_checker(session, principal, next_checker, correlation_id)
            before = plan.status
            changed_fields = sorted(
                key for key in set(current_payload) | set(payload)
                if current_payload.get(key) != payload.get(key)
            )
            if previous_checker != next_checker:
                changed_fields.append("checker_id")
            plan.payload = payload
            plan.checker_id = next_checker
            plan.revision += 1
            _record_event(
                session, plan_id=plan.id, actor_id=principal.id,
                action="UPDATED", status_before=before, status_after=plan.status,
                details={
                    "revision": plan.revision,
                    "changed_fields": changed_fields,
                    **({
                        "checker_id_before": str(previous_checker) if previous_checker else None,
                        "checker_id_after": str(next_checker) if next_checker else None,
                    } if previous_checker != next_checker else {}),
                }, actor_role="MAKER",
            )
            session.flush()
            session.refresh(plan)
            result = _plan_dict(session, plan)
    except IntegrityError:
        session.rollback()
        _fail("CONFLICT", "Could not update the plan.", correlation_id)
    return result


def upload_attachment(
    session: Session,
    principal: AuthenticatedPrincipal,
    plan_id: UUID,
    filename: str,
    media_type: str,
    content: bytes,
    expected_revision: int,
    correlation_id: str,
):
    _require_role(principal, "MAKER", correlation_id)
    _require_permission(principal, "MARKETING_ATTACHMENT_MANAGE", correlation_id)
    if len(content) > MAX_ATTACHMENT_BYTES:
        _fail("VALIDATION_ERROR", "Attachment exceeds the 5 MB limit.", correlation_id)
    if not _valid_image(content, media_type):
        _fail("VALIDATION_ERROR", "Upload a valid PNG, JPEG, or WebP image.", correlation_id)
    safe_filename = PurePosixPath((filename or "attachment").replace("\\", "/")).name[:255] or "attachment"
    try:
        with _write_transaction(session):
            plan = _plan_or_404(session, plan_id, correlation_id, lock=True)
            _maker_plan(plan, principal, correlation_id)
            if plan.status not in {"DRAFT", "REJECTED"}:
                _fail("CONFLICT", "Attachments are locked after submission.", correlation_id)
            if plan.revision != expected_revision:
                _fail("CONFLICT", "The plan changed. Reload it before uploading.", correlation_id)
            attachment = AuthWorkflowAttachment(
                id=uuid4(), plan_id=plan.id, filename=safe_filename, media_type=media_type,
                byte_size=len(content), content_hash=hashlib.sha256(content).hexdigest(),
                content=content, uploaded_by=principal.id,
            )
            session.add(attachment)
            before = plan.status
            plan.revision += 1
            _record_event(
                session, plan_id=plan.id, actor_id=principal.id,
                action="ATTACHMENT_UPLOADED", status_before=before, status_after=plan.status,
                details={"attachment_id": str(attachment.id), "content_hash": attachment.content_hash},
                actor_role="MAKER",
            )
            session.flush()
            session.refresh(plan)
            result = _plan_dict(session, plan)
    except IntegrityError:
        session.rollback()
        _fail("CONFLICT", "Could not store this attachment.", correlation_id)
    return result


def submit_plan(
    session: Session,
    principal: AuthenticatedPrincipal,
    plan_id: UUID,
    expected_revision: int,
    correlation_id: str,
    *,
    provider_name: str,
    model_version: str | None,
    configuration: ApprovalConfiguration,
    model_id: str | None = None,
):
    _require_role(principal, "MAKER", correlation_id)
    _require_permission(principal, "MARKETING_PLAN_SUBMIT", correlation_id)
    try:
        with _write_transaction(session):
            plan = _plan_or_404(session, plan_id, correlation_id, lock=True)
            _maker_plan(plan, principal, correlation_id)
            if plan.status not in {"DRAFT", "REJECTED"}:
                _fail("CONFLICT", "Only a draft or rejected plan can be submitted.", correlation_id)
            if plan.revision != expected_revision:
                _fail("CONFLICT", "The plan changed. Reload it before submitting.", correlation_id)
            _validate_submission(plan.payload, correlation_id)
            lock_configuration_registry(session)
            attachments = session.scalars(
                select(AuthWorkflowAttachment)
                .where(AuthWorkflowAttachment.plan_id == plan.id)
                .order_by(AuthWorkflowAttachment.created_at, AuthWorkflowAttachment.id)
            ).all()
            if not attachments:
                _fail("VALIDATION_ERROR", "Add at least one image before submitting.", correlation_id)
            before = plan.status
            plan.current_version += 1
            plan.current_round += 1
            plan.status = "PENDING_APPROVAL"
            submitted_at = _now_datetime()
            sla_snapshot = start_round_snapshot(
                session, plan=plan, started_at=submitted_at, correlation_id=correlation_id
            )
            round_configuration_snapshot = capture_round_configuration_snapshot(
                session,
                plan_id=plan.id,
                plan_version=plan.current_version,
                approval_round=plan.current_round,
                department_id=(
                    plan.payload.get("department")
                    if isinstance(plan.payload.get("department"), str)
                    else None
                ),
                maker_id=plan.maker_id,
                selected_checker_id=plan.checker_id,
                effective_at=submitted_at,
            )
            checker_assignment = round_configuration_snapshot.checker_assignment
            resolved_checker_id = checker_assignment.get("checker_id")
            if (
                checker_assignment.get("status") != "CONFIGURED"
                or not checker_assignment.get("eligible")
                or not isinstance(resolved_checker_id, str)
            ):
                _fail(
                    "VALIDATION_ERROR",
                    "A Checker assignment must be effective and eligible before submission.",
                    correlation_id,
                )
            try:
                plan.checker_id = UUID(resolved_checker_id)
            except ValueError:
                _fail("VALIDATION_ERROR", "The configured Checker assignment is invalid.", correlation_id)
            _validate_checker(session, principal, plan.checker_id, correlation_id, required=True)
            processing_stage_before = plan.processing_stage
            plan.processing_stage = "AI_PENDING"
            plan.decision_reason = None
            plan.revision += 1
            attachment_manifest = [{
                "id": str(item.id),
                "filename": item.filename,
                "media_type": item.media_type,
                "byte_size": item.byte_size,
                "content_hash": item.content_hash,
            } for item in attachments]
            snapshot_payload = {
                **dict(plan.payload),
                "maker_id": str(plan.maker_id),
                "checker_id": str(plan.checker_id),
            }
            snapshot = _domain_snapshot(
                plan.id, plan.current_version, plan.current_round,
                snapshot_payload, attachment_manifest,
            )
            snapshot_hash = snapshot.input_hash
            run_id = "run-" + uuid4().hex
            evaluation_id = "evaluation-" + uuid4().hex
            session.add(AuthWorkflowVersion(
                id=uuid4(),
                plan_id=plan.id,
                version_number=plan.current_version,
                round_number=plan.current_round,
                payload_snapshot=snapshot_payload,
                attachment_snapshot=attachment_manifest,
                snapshot_hash=snapshot_hash,
                submitted_by=principal.id,
            ))
            configuration = apply_round_configuration_snapshot(
                configuration, round_configuration_snapshot,
            )
            policy_snapshot = configuration.to_dict()
            policy_snapshot_hash = canonical_hash(policy_snapshot)
            media_initial = initial_evaluation_step(
                "MEDIA_COMPLIANCE", snapshot_hash, configuration,
                configuration.media_model_snapshot,
            )
            strategy_initial = initial_evaluation_step(
                "STRATEGY_EVALUATION", snapshot_hash, configuration,
                configuration.strategy_model_snapshot,
            )
            session.add(AuthWorkflowEvaluationRun(
                id=uuid4(),
                plan_id=plan.id,
                version_number=plan.current_version,
                round_number=plan.current_round,
                run_id=run_id,
                evaluation_id=evaluation_id,
                idempotency_key=f"auth-submit:{plan.id}:{plan.current_round}:{snapshot_hash}",
                correlation_id=correlation_id,
                input_hash=snapshot_hash,
                provider=provider_name,
                model_id=model_id,
                model_version=model_version,
                policy_version=configuration.policy.policy_version,
                policy_snapshot_id=configuration.policy.snapshot_id,
                policy_snapshot_hash=policy_snapshot_hash,
                policy_snapshot=policy_snapshot,
                status="PENDING",
                media_evaluation=media_initial,
                strategy_evaluation=strategy_initial,
            ))
            _record_event(
                session, plan_id=plan.id, actor_id=principal.id,
                action="SUBMITTED", status_before=before, status_after=plan.status,
                actor_role="MAKER",
                details={
                    "version": plan.current_version,
                    "round": plan.current_round,
                    "checker_id": str(plan.checker_id),
                    "attachment_hashes": [item["content_hash"] for item in attachment_manifest],
                    "input_hash": snapshot_hash,
                    "sla_configuration_revision": sla_snapshot.configuration_revision if sla_snapshot else None,
                    "sla_due_at": sla_snapshot.due_at.isoformat() if sla_snapshot else None,
                },
            )
            _record_event(
                session, plan_id=plan.id, actor_id=None, actor_type="SYSTEM",
                action="AI_EVALUATION_QUEUED", status_before=plan.status,
                status_after=plan.status,
                details={
                    "version": plan.current_version,
                    "round": plan.current_round,
                    "run_id": run_id,
                    "evaluation_id": evaluation_id,
                    "input_hash": snapshot_hash,
                    "provider": provider_name,
                    "model_id": model_id,
                    "model_version": model_version,
                    "policy_version": configuration.policy.policy_version,
                    "policy_snapshot_hash": policy_snapshot_hash,
                    "round_configuration_snapshot_id": str(round_configuration_snapshot.snapshot_id),
                    "round_configuration_snapshot_hash": round_configuration_snapshot.snapshot_hash,
                    "processing_stage_before": processing_stage_before,
                    "processing_stage_after": plan.processing_stage,
                },
            )
            _record_notification(
                session,
                recipient_user_id=plan.checker_id,
                plan=plan,
                event_type="PLAN_SUBMITTED",
                version_number=plan.current_version,
                round_number=plan.current_round,
            )
            session.flush()
            session.refresh(plan)
            result = _plan_dict(session, plan)
    except IntegrityError:
        session.rollback()
        _fail("CONFLICT", "Could not submit the plan.", correlation_id)
    return result


def _validate_submission(payload: dict[str, Any], correlation_id: str) -> None:
    for field in ("title", "objective", "summary"):
        if not str(payload.get(field, "")).strip():
            _fail("VALIDATION_ERROR", f"{field} is required before submission.", correlation_id)
    for field in ("start_date", "end_date"):
        try:
            date.fromisoformat(payload.get(field, ""))
        except (TypeError, ValueError):
            _fail("VALIDATION_ERROR", f"{field} must be a valid ISO calendar date.", correlation_id)
    if date.fromisoformat(payload["end_date"]) < date.fromisoformat(payload["start_date"]):
        _fail("VALIDATION_ERROR", "The end date must be on or after the start date.", correlation_id)
    amount = payload.get("budget_minor_units", "")
    if not re.fullmatch(r"(?:0|[1-9][0-9]{0,23})", amount):
        _fail("VALIDATION_ERROR", "Budget must be a non-negative whole-number amount.", correlation_id)


def _record_ignored_stale_result(
    session: Session,
    plan: AuthWorkflowPlan,
    run: AuthWorkflowEvaluationRun,
) -> None:
    _record_event(
        session,
        plan_id=plan.id,
        actor_id=None,
        actor_type="SYSTEM",
        action="AI_RESULT_IGNORED_STALE",
        status_before=plan.status,
        status_after=plan.status,
        details={
            "version": run.version_number,
            "round": run.round_number,
            "run_id": run.run_id,
            "evaluation_id": run.evaluation_id,
            "input_hash": run.input_hash,
            "reason_code": "STALE_OR_ALREADY_APPLIED",
        },
        result="IGNORED_STALE",
    )


def evaluate_submission(
    session: Session,
    plan_id: UUID,
    round_number: int,
    orchestrator: EvaluationOrchestrator,
    correlation_id: str,
    *,
    evaluation_run_id: UUID | None = None,
):
    """Evaluate a committed snapshot outside DB transactions, then persist atomically."""
    request = None
    configuration = None
    snapshot = None
    round_configuration_snapshot = None
    verified_hashes: tuple[tuple[str, str], ...] = ()
    snapshot_is_valid = True
    prepared_response = None

    try:
        with _write_transaction(session):
            plan = _plan_or_404(session, plan_id, correlation_id, lock=True)
            run_query = select(AuthWorkflowEvaluationRun).where(
                AuthWorkflowEvaluationRun.plan_id == plan.id,
                AuthWorkflowEvaluationRun.round_number == round_number,
            )
            if evaluation_run_id is not None:
                run_query = run_query.where(AuthWorkflowEvaluationRun.id == evaluation_run_id)
            run = session.scalar(run_query.with_for_update())
            if run is None:
                _fail("NOT_FOUND", "Evaluation run not found.", correlation_id)
            if run.status in {"SUCCEEDED", "FAILED", "TIMED_OUT"}:
                prepared_response = _plan_dict(session, plan)
            elif run.status == "PROCESSING":
                # Another request owns this durable run. It must not start a second provider call.
                prepared_response = _plan_dict(session, plan)
            elif plan.status != "PENDING_APPROVAL" or plan.current_round != round_number:
                _fail("CONFLICT", "This approval round is no longer active.", correlation_id)
            else:
                version = session.scalar(
                    select(AuthWorkflowVersion).where(
                        AuthWorkflowVersion.plan_id == plan.id,
                        AuthWorkflowVersion.round_number == round_number,
                    )
                )
                if version is None or version.version_number != run.version_number:
                    _fail("CONFLICT", "The submitted snapshot is unavailable.", correlation_id)
                snapshot = _domain_snapshot(
                    plan.id, version.version_number, version.round_number,
                    version.payload_snapshot, version.attachment_snapshot,
                )
                round_configuration_snapshot = get_round_configuration_snapshot(
                    session, plan_id=plan.id, approval_round=round_number,
                )
                snapshot_is_valid = (
                    _round_configuration_snapshot_is_valid(
                        round_configuration_snapshot, plan.id, version.version_number, round_number,
                    )
                    and version.snapshot_hash == snapshot.input_hash
                    and run.input_hash == snapshot.input_hash
                    and isinstance(run.policy_snapshot_hash, str)
                    and canonical_hash(run.policy_snapshot) == run.policy_snapshot_hash
                )
                manifest = {str(item["id"]): item for item in version.attachment_snapshot}
                attachment_ids = tuple(UUID(key) for key in manifest)
                stored_attachments = session.scalars(
                    select(AuthWorkflowAttachment).where(
                        AuthWorkflowAttachment.plan_id == plan.id,
                        AuthWorkflowAttachment.id.in_(attachment_ids),
                    )
                ).all() if attachment_ids else []
                stored_by_id = {str(item.id): item for item in stored_attachments}
                contents = {}
                verified = []
                if len(stored_by_id) != len(manifest):
                    snapshot_is_valid = False
                for attachment_id, frozen in manifest.items():
                    item = stored_by_id.get(attachment_id)
                    if item is None:
                        continue
                    actual_hash = hashlib.sha256(item.content).hexdigest()
                    verified.append((attachment_id, actual_hash))
                    if actual_hash != frozen["content_hash"] or actual_hash != item.content_hash:
                        snapshot_is_valid = False
                    else:
                        contents[attachment_id] = item.content
                verified_hashes = tuple(sorted(verified))
                configuration = ApprovalConfiguration.from_dict(run.policy_snapshot)
                request = EvaluationRequest(
                    plan=snapshot,
                    policy_version=run.policy_version,
                    evaluation_id=run.evaluation_id,
                    run_id=run.run_id,
                    correlation_id=run.correlation_id,
                    provider=run.provider,
                    model_version=run.model_version,
                    configuration=configuration,
                    metadata={
                        "attachment_contents": contents,
                        "model_id": run.model_id,
                        "model_identity_mode": (
                            configuration.visual_model_snapshot.get("identity_mode")
                            if isinstance(configuration.visual_model_snapshot, dict)
                            else None
                        ),
                        "round_configuration_snapshot": (
                            round_configuration_snapshot.as_dict() if round_configuration_snapshot is not None else None
                        ),
                    },
                )
                run.status = "PROCESSING"
                run.attempts = 0
                run.retried = False
                run.started_at = _now_datetime()
                processing_stage_before = plan.processing_stage
                plan.processing_stage = "AI_PROCESSING"
                plan.revision += 1
                _record_event(
                    session, plan_id=plan.id, actor_id=None, actor_type="SYSTEM",
                    action="AI_EVALUATION_STARTED", status_before=plan.status,
                    status_after=plan.status,
                    details={
                        "version": version.version_number,
                        "round": round_number,
                        "run_id": run.run_id,
                        "evaluation_id": run.evaluation_id,
                        "input_hash": run.input_hash,
                        "provider": run.provider,
                        "model_version": run.model_version,
                        "processing_stage_before": processing_stage_before,
                        "processing_stage_after": plan.processing_stage,
                    },
                )
                session.flush()

        if request is None:
            return prepared_response

        # Provider I/O is deliberately outside the transaction and row lock.
        if snapshot_is_valid:
            try:
                if getattr(orchestrator, "supports_step_updates", False):
                    def persist_step(name, state):
                        column = {
                            "media_evaluation": "media_evaluation",
                            "strategy_evaluation": "strategy_evaluation",
                        }.get(name)
                        if column is None:
                            return
                        with _write_transaction(session):
                            current_run = session.scalar(
                                select(AuthWorkflowEvaluationRun)
                                .where(AuthWorkflowEvaluationRun.id == run.id)
                                .with_for_update()
                            )
                            if current_run is None or current_run.status != "PROCESSING" or current_run.evaluation is not None:
                                return
                            setattr(current_run, column, state)
                    pipeline_result = orchestrator.evaluate(request, on_step=persist_step)
                else:
                    pipeline_result = orchestrator.evaluate(request)
            except Exception:
                pipeline_result = orchestrator.fail_closed(
                    request, "ORCHESTRATOR_ERROR", "AI evaluation could not be completed."
                )
        else:
            pipeline_result = orchestrator.fail_closed(
                request, "SNAPSHOT_INTEGRITY", "The submitted attachment snapshot failed integrity checks."
            )
        raw_evaluation = pipeline_result.evaluation

        with _write_transaction(session):
            # Recovery or a Checker request may have committed while provider I/O
            # was in flight. This session has expire_on_commit=False, so reload its
            # identity map before checking whether the run still owns the active round.
            session.expire_all()
            plan = _plan_or_404(session, plan_id, correlation_id, lock=True)
            run = session.scalar(
                select(AuthWorkflowEvaluationRun)
                .where(AuthWorkflowEvaluationRun.id == run.id)
                .with_for_update()
            )
            if run is None:
                _fail("NOT_FOUND", "Evaluation run not found.", correlation_id)
            if run.evaluation is not None:
                _record_ignored_stale_result(session, plan, run)
                session.flush()
                return _plan_dict(session, plan)
            run.visual_extraction = pipeline_result.visual_extraction

            evaluation_status = raw_evaluation.get("status", "FAILED")
            if (
                plan.status != "PENDING_APPROVAL"
                or plan.current_version != run.version_number
                or plan.current_round != run.round_number
                or plan.processing_stage != "AI_PROCESSING"
            ):
                # A recovered or human-completed round owns the final state. Keep the
                # late output attached to its original run without applying it to a newer round.
                run.status = evaluation_status
                run.evaluation = raw_evaluation
                run.visual_extraction = pipeline_result.visual_extraction
                run.media_evaluation = pipeline_result.media_evaluation or run.media_evaluation
                run.strategy_evaluation = pipeline_result.strategy_evaluation or run.strategy_evaluation
                run.failure_reason = "Late evaluation result was retained but not applied to a newer plan state."
                run.result_disposition = "STALE"
                run.completed_at = _now_datetime()
                _record_ignored_stale_result(session, plan, run)
                session.flush()
                return _plan_dict(session, plan)

            run.attempts = pipeline_result.attempts
            run.retried = pipeline_result.retried
            run.media_evaluation = pipeline_result.media_evaluation or run.media_evaluation
            run.strategy_evaluation = pipeline_result.strategy_evaluation or run.strategy_evaluation
            config = ApprovalConfiguration.from_dict(run.policy_snapshot)
            valid_checkers = session.scalars(
                select(User.id)
                .join(EmployeeProfile, EmployeeProfile.user_id == User.id)
                .where(
                    User.status == "ACTIVE", User.activation_pending.is_(False),
                    User.employment_status == "ACTIVE",
                    EmployeeProfile.employment_status == "ACTIVE",
                    effective_role_filter("CHECKER"),
                )
            ).all()
            valid_authority_ids = session.scalars(
                select(User.id)
                .join(EmployeeProfile, EmployeeProfile.user_id == User.id)
                .where(
                    User.status == "ACTIVE", User.activation_pending.is_(False),
                    User.employment_status == "ACTIVE",
                    EmployeeProfile.employment_status == "ACTIVE",
                )
            ).all()
            context = DecisionContext(
                evaluation_id=run.evaluation_id,
                run_id=run.run_id,
                provider=run.provider,
                correlation_id=run.correlation_id,
                idempotency_key=run.idempotency_key,
                decided_at=_timestamp(),
                plan_status="PENDING_APPROVAL",
                approval_round_status="ACTIVE",
                round_revision=plan.revision,
                expected_input_hash=run.input_hash,
                verified_attachment_hashes=verified_hashes,
                valid_checker_ids=tuple(str(checker_id) for checker_id in valid_checkers),
                suspicious_input=not snapshot_is_valid,
                valid_authority_ids=tuple(str(user_id) for user_id in valid_authority_ids),
            )
            try:
                bundle = decide(snapshot, config, raw_evaluation, context)
            except Exception:
                # Engine faults are not approval evidence. Preserve a durable review route.
                run.status = "FAILED"
                run.failure_reason = "Decision policy could not complete; Checker review is required."
                run.result_disposition = "APPLIED"
                run.completed_at = _now_datetime()
                processing_stage_before = plan.processing_stage
                plan.processing_stage = "HUMAN_REVIEW_REQUIRED"
                plan.decision_reason = run.failure_reason
                plan.revision += 1
                _record_event(
                    session, plan_id=plan.id, actor_id=None, actor_type="SYSTEM",
                    action="AI_REVIEW_ROUTED", status_before=plan.status,
                    status_after=plan.status,
                    result="HUMAN_REVIEW_REQUIRED",
                    details={
                        "version": run.version_number,
                        "round": run.round_number,
                        "run_id": run.run_id,
                        "evaluation_id": run.evaluation_id,
                        "reason": run.failure_reason,
                        "processing_stage_before": processing_stage_before,
                        "processing_stage_after": plan.processing_stage,
                    },
                )
                session.flush()
                return _plan_dict(session, plan)

            evaluation = bundle.evaluation.to_dict()
            decision = bundle.decision.to_dict()
            run.status = bundle.evaluation.status
            run.evaluation = evaluation
            run.result_disposition = "APPLIED"
            errors = evaluation.get("agent_errors") or []
            run.failure_reason = errors[0].get("code") if errors else None
            run.model_version = bundle.evaluation.model_version
            run.completed_at = _now_datetime()
            engine_decision = AuthWorkflowEngineDecision(
                id=uuid4(),
                plan_id=plan.id,
                evaluation_run_id=run.id,
                version_number=run.version_number,
                round_number=run.round_number,
                decision_id=bundle.decision.decision_id,
                outcome=bundle.decision.outcome,
                decision=decision,
            )
            session.add(engine_decision)
            before_stage = plan.processing_stage
            if bundle.decision.outcome == "AUTO_APPROVED":
                plan.status = "APPROVED"
                close_round_snapshot(
                    session, plan_id=plan.id, round_number=run.round_number,
                    closed_at=run.completed_at or _now_datetime(),
                )
                plan.processing_stage = "AI_AUTO_APPROVED"
                plan.decision_reason = None
                action = "AI_AUTO_APPROVED"
            elif bundle.decision.outcome == "AUTO_REJECTED":
                plan.status = "REJECTED"
                close_round_snapshot(
                    session, plan_id=plan.id, round_number=run.round_number,
                    closed_at=run.completed_at or _now_datetime(),
                )
                plan.processing_stage = "AI_AUTO_REJECTED"
                plan.decision_reason = bundle.decision.reason
                action = "AI_AUTO_REJECTED"
            else:
                plan.processing_stage = "HUMAN_REVIEW_REQUIRED"
                plan.decision_reason = bundle.decision.reason
                action = "AI_REVIEW_ROUTED"
            plan.revision += 1
            auto_reject_audit_trace = {}
            if bundle.decision.outcome == "AUTO_REJECTED":
                snapshot_configurations = (
                    round_configuration_snapshot.configurations
                    if round_configuration_snapshot is not None else None
                )
                auto_reject_configuration = (
                    snapshot_configurations.get("auto_reject_policy")
                    if isinstance(snapshot_configurations, dict) else None
                )
                if (
                    not isinstance(auto_reject_configuration, dict)
                    or not isinstance(auto_reject_configuration.get("revision_id"), str)
                    or not isinstance(auto_reject_configuration.get("configuration_hash"), str)
                    or not isinstance(auto_reject_configuration.get("signoff"), dict)
                    or not isinstance(auto_reject_configuration["signoff"].get("policy_owner_id"), str)
                ):
                    _fail(
                        "CONFLICT",
                        "The signed auto-reject policy trace is missing from this approval-round snapshot.",
                        correlation_id,
                    )
                auto_reject_audit_trace = {
                    "auto_reject_policy_revision_id": auto_reject_configuration["revision_id"],
                    "auto_reject_policy_configuration_hash": auto_reject_configuration["configuration_hash"],
                    "auto_reject_policy_signoff_actor_id": auto_reject_configuration["signoff"]["policy_owner_id"],
                    "auto_reject_policy_signed_at": auto_reject_configuration["signoff"].get("signed_at"),
                }
            _record_event(
                session, plan_id=plan.id, actor_id=None, actor_type="SYSTEM",
                action="AI_EVALUATION_COMPLETED", status_before="PENDING_APPROVAL",
                status_after=plan.status,
                result=run.status,
                details={
                    "version": run.version_number,
                    "round": run.round_number,
                    "run_id": run.run_id,
                    "evaluation_id": run.evaluation_id,
                    "input_hash": run.input_hash,
                    "provider": run.provider,
                    "model_version": run.model_version,
                    "evaluation_status": run.status,
                    "failure_reason": run.failure_reason,
                    "result_summary": _audit_evaluation_summary(evaluation, decision),
                    "processing_stage_before": before_stage,
                    "processing_stage_after": plan.processing_stage,
                },
            )
            _record_event(
                session, plan_id=plan.id, actor_id=None, actor_type="SYSTEM",
                action=action, status_before="PENDING_APPROVAL", status_after=plan.status,
                result=bundle.decision.outcome,
                details={
                    "version": run.version_number,
                    "round": run.round_number,
                    "decision_id": bundle.decision.decision_id,
                    "evaluation_id": run.evaluation_id,
                    "reason": bundle.decision.reason,
                    "applied_rule_ids": list(bundle.decision.applied_rule_ids),
                    "policy_version": run.policy_version,
                    "policy_snapshot_hash": run.policy_snapshot_hash,
                    "input_hash": run.input_hash,
                    "processing_stage_before": before_stage,
                    "processing_stage_after": plan.processing_stage,
                    **({
                        "auto_reject_rule_id": bundle.decision.auto_reject_rule_id,
                        "reason_code": bundle.decision.reason_code,
                        "evidence_reference": next((list(check.evidence_refs)
                                                     for check in bundle.decision.rule_checks
                                                     if check.rule_id == "AUTO_REJECT_MATCH" and check.result == "FAIL"), []),
                        **auto_reject_audit_trace,
                    } if bundle.decision.outcome == "AUTO_REJECTED" else {}),
                },
            )
            if bundle.decision.outcome in {"AUTO_APPROVED", "AUTO_REJECTED"}:
                notification_event = (
                    "PLAN_AUTO_APPROVED" if bundle.decision.outcome == "AUTO_APPROVED"
                    else "PLAN_AUTO_REJECTED"
                )
                _record_notification(
                    session,
                    recipient_user_id=plan.maker_id,
                    plan=plan,
                    event_type=notification_event,
                    version_number=run.version_number,
                    round_number=run.round_number,
                    reason=bundle.decision.reason if bundle.decision.outcome == "AUTO_REJECTED" else None,
                )
            session.flush()
            session.refresh(plan)
            return _plan_dict(session, plan)
    except IntegrityError:
        session.rollback()
        _fail("CONFLICT", "The evaluation result could not be committed for this round.", correlation_id)


def evaluate_run_by_id(
    session: Session,
    plan_id: UUID,
    evaluation_run_id: UUID,
    orchestrator: EvaluationOrchestrator,
    correlation_id: str,
):
    """Run a claimed retry against its own immutable run and saved round snapshot."""
    run = session.scalar(select(AuthWorkflowEvaluationRun).where(
        AuthWorkflowEvaluationRun.id == evaluation_run_id,
        AuthWorkflowEvaluationRun.plan_id == plan_id,
    ))
    if run is None:
        _fail("NOT_FOUND", "Evaluation run not found.", correlation_id)
    return evaluate_submission(
        session,
        plan_id,
        run.round_number,
        orchestrator,
        correlation_id,
        evaluation_run_id=run.id,
    )


def recover_stale_evaluations(
    session: Session,
    correlation_id: str,
    *,
    age_seconds: int = 240,
    visible_plan_ids: tuple[UUID, ...] | None = None,
    round_number: int | None = None,
) -> None:
    """Move interrupted durable runs to Checker review after an explicit command."""
    cutoff = _now_datetime() - timedelta(seconds=age_seconds)
    query = select(AuthWorkflowEvaluationRun.id).where(
        AuthWorkflowEvaluationRun.status.in_(("PENDING", "PROCESSING")),
        func.coalesce(AuthWorkflowEvaluationRun.started_at, AuthWorkflowEvaluationRun.created_at) < cutoff,
    )
    if visible_plan_ids is not None:
        if not visible_plan_ids:
            return
        query = query.where(AuthWorkflowEvaluationRun.plan_id.in_(visible_plan_ids))
    if round_number is not None:
        query = query.where(AuthWorkflowEvaluationRun.round_number == round_number)
    run_ids = session.scalars(query.order_by(AuthWorkflowEvaluationRun.created_at)).all()
    for run_id in run_ids:
        try:
            with _write_transaction(session):
                run = session.scalar(
                    select(AuthWorkflowEvaluationRun)
                    .where(AuthWorkflowEvaluationRun.id == run_id)
                    .with_for_update()
                )
                if run is None or run.status not in {"PENDING", "PROCESSING"}:
                    continue
                plan = _plan_or_404(session, run.plan_id, correlation_id, lock=True)
                if (
                    plan.status != "PENDING_APPROVAL"
                    or plan.current_version != run.version_number
                    or plan.current_round != run.round_number
                    or plan.processing_stage not in {"AI_PENDING", "AI_PROCESSING"}
                ):
                    continue
                version = session.scalar(select(AuthWorkflowVersion).where(
                    AuthWorkflowVersion.plan_id == plan.id,
                    AuthWorkflowVersion.round_number == run.round_number,
                ))
                recovery_status_before = plan.status
                recovery_stage_before = plan.processing_stage
                recovery_run_status_before = run.status
                failure_reason = "AI evaluation was interrupted; Checker review is required."
                if version is None:
                    run.status = "FAILED"
                    run.failure_reason = "RUN_INTERRUPTED_SNAPSHOT_UNAVAILABLE"
                    run.result_disposition = "APPLIED"
                    run.completed_at = _now_datetime()
                    plan.processing_stage = "HUMAN_REVIEW_REQUIRED"
                    plan.decision_reason = failure_reason
                    plan.revision += 1
                    _record_event(
                        session, plan_id=plan.id, actor_id=None, actor_type="SYSTEM",
                        action="AI_RECOVERY_REVIEW_ROUTED", status_before=recovery_status_before,
                        status_after=plan.status,
                        result="HUMAN_REVIEW_REQUIRED",
                        details={
                            "version": run.version_number,
                            "round": run.round_number,
                            "run_id": run.run_id,
                            "evaluation_id": run.evaluation_id,
                            "correlation_id": run.correlation_id,
                            "input_hash": run.input_hash,
                            "run_status_before": recovery_run_status_before,
                            "run_status_after": run.status,
                            "failure_code": run.failure_reason,
                            "result_disposition": run.result_disposition,
                            "processing_stage_before": recovery_stage_before,
                            "processing_stage_after": plan.processing_stage,
                            "reason": run.failure_reason,
                        },
                    )
                    continue

                snapshot = _domain_snapshot(
                    plan.id, version.version_number, version.round_number,
                    version.payload_snapshot, version.attachment_snapshot,
                )
                try:
                    config = ApprovalConfiguration.from_dict(run.policy_snapshot)
                    configuration_error = None
                except Exception:
                    config = None
                    configuration_error = "POLICY_SNAPSHOT_INVALID"
                request = EvaluationRequest(
                    snapshot, run.policy_version, run.evaluation_id, run.run_id,
                    run.correlation_id, run.provider, run.model_version, config,
                    metadata={"model_id": run.model_id},
                )
                failure = EvaluationOrchestrator.fail_closed(
                    request,
                    configuration_error or "RUN_INTERRUPTED",
                    "AI evaluation did not finish; Checker review is required.",
                )
                checker_ids = session.scalars(
                    select(User.id)
                    .join(EmployeeProfile, EmployeeProfile.user_id == User.id)
                    .where(
                        User.status == "ACTIVE", User.activation_pending.is_(False),
                        User.employment_status == "ACTIVE",
                        EmployeeProfile.employment_status == "ACTIVE",
                        effective_role_filter("CHECKER"),
                    )
                ).all()
                authority_ids = session.scalars(
                    select(User.id)
                    .join(EmployeeProfile, EmployeeProfile.user_id == User.id)
                    .where(
                        User.status == "ACTIVE", User.activation_pending.is_(False),
                        User.employment_status == "ACTIVE",
                        EmployeeProfile.employment_status == "ACTIVE",
                    )
                ).all()
                verified = tuple(sorted(
                    (str(item["id"]), str(item["content_hash"]))
                    for item in version.attachment_snapshot
                ))
                context = DecisionContext(
                    run.evaluation_id, run.run_id, run.provider, run.correlation_id,
                    run.idempotency_key, _timestamp(), "PENDING_APPROVAL", "ACTIVE",
                    plan.revision, run.input_hash, verified,
                    tuple(str(checker_id) for checker_id in checker_ids),
                    snapshot.input_hash != run.input_hash or version.snapshot_hash != run.input_hash,
                    tuple(str(user_id) for user_id in authority_ids),
                )
                try:
                    if config is None:
                        raise ValueError("Saved policy snapshot is invalid")
                    bundle = decide(snapshot, config, failure.evaluation, context)
                except Exception:
                    bundle = None

                run.status = "FAILED"
                run.failure_reason = configuration_error or "RUN_INTERRUPTED"
                run.result_disposition = "APPLIED"
                run.completed_at = _now_datetime()
                plan.processing_stage = "HUMAN_REVIEW_REQUIRED"
                plan.decision_reason = failure_reason
                plan.revision += 1
                details = {
                    "version": run.version_number,
                    "round": run.round_number,
                    "run_id": run.run_id,
                    "evaluation_id": run.evaluation_id,
                    "correlation_id": run.correlation_id,
                    "run_status_before": recovery_run_status_before,
                    "input_hash": run.input_hash,
                    "processing_stage_before": recovery_stage_before,
                    "processing_stage_after": plan.processing_stage,
                    "reason": failure_reason,
                }
                for column in ("media_evaluation", "strategy_evaluation"):
                    stage = getattr(run, column)
                    if stage and stage.get("status") in {"PENDING", "PROCESSING"}:
                        setattr(run, column, {
                            **stage,
                            "status": "FAILED",
                            "error_code": "RUN_INTERRUPTED",
                            "reason": failure_reason,
                            "completed_at": _timestamp(),
                        })
                if bundle is not None:
                    run.evaluation = bundle.evaluation.to_dict()
                    run.visual_extraction = failure.visual_extraction
                    session.add(AuthWorkflowEngineDecision(
                        id=uuid4(), plan_id=plan.id, evaluation_run_id=run.id,
                        version_number=run.version_number, round_number=run.round_number,
                        decision_id=bundle.decision.decision_id,
                        outcome=bundle.decision.outcome,
                        decision=bundle.decision.to_dict(),
                    ))
                    details["decision_id"] = bundle.decision.decision_id
                    details["applied_rule_ids"] = list(bundle.decision.applied_rule_ids)
                else:
                    run.failure_reason = "RUN_INTERRUPTED_DECISION_POLICY_ERROR"
                    run.evaluation = failure.evaluation
                    run.visual_extraction = failure.visual_extraction
                details["run_status_after"] = run.status
                details["failure_code"] = run.failure_reason
                details["result_disposition"] = run.result_disposition
                if bundle is not None:
                    details["engine_decision_outcome"] = bundle.decision.outcome
                _record_event(
                    session, plan_id=plan.id, actor_id=None, actor_type="SYSTEM",
                    action="AI_RECOVERY_REVIEW_ROUTED", status_before=recovery_status_before,
                    status_after=plan.status, result="HUMAN_REVIEW_REQUIRED", details=details,
                )
        except IntegrityError:
            session.rollback()
            # A competing recovery or final decision won; the unique constraints are the guard.
            continue


def recover_stale_round(
    session: Session,
    principal: AuthenticatedPrincipal,
    plan_id: UUID,
    round_number: int,
    correlation_id: str,
) -> dict[str, Any]:
    """Explicit, idempotent Checker command; GET requests never recover runs."""
    _require_role(principal, "CHECKER", correlation_id)
    plan = _plan_or_404(session, plan_id, correlation_id)
    _readable_plan(plan, principal, correlation_id)
    if plan.checker_id != principal.id or plan.maker_id == principal.id:
        _fail("NOT_FOUND", "Plan not found.", correlation_id)
    if plan.status != "PENDING_APPROVAL" or plan.current_round != round_number:
        _fail("CONFLICT", "This approval round is not active.", correlation_id)
    if plan.processing_stage in {"AI_PENDING", "AI_PROCESSING"}:
        recover_stale_evaluations(
            session,
            correlation_id,
            visible_plan_ids=(plan.id,),
            round_number=round_number,
        )
        session.refresh(plan)
    return _plan_dict(session, plan)


def decide_plan(
    session: Session,
    principal: AuthenticatedPrincipal,
    plan_id: UUID,
    round_number: int,
    action: str,
    reason: str | None,
    override_reason: str | None,
    correlation_id: str,
):
    _require_role(principal, "CHECKER", correlation_id)
    if action == "APPROVED":
        _require_permission(principal, "MARKETING_APPROVE", correlation_id)
    elif action == "REJECTED":
        _require_permission(principal, "MARKETING_REJECT", correlation_id)
    else:
        _fail("VALIDATION_ERROR", "Decision action is invalid.", correlation_id)
    normalized_reason = reason.strip() if reason and reason.strip() else None
    normalized_override_reason = (
        override_reason.strip() if override_reason and override_reason.strip() else None
    )
    if action == "REJECTED" and normalized_reason is None:
        _fail("VALIDATION_ERROR", "A non-blank rejection reason is required.", correlation_id)
    try:
        with _write_transaction(session):
            plan = _plan_or_404(session, plan_id, correlation_id, lock=True)
            _readable_plan(plan, principal, correlation_id)
            if plan.checker_id != principal.id or plan.maker_id == principal.id:
                _fail("NOT_FOUND", "Plan not found.", correlation_id)
            existing = session.scalar(select(AuthWorkflowDecision).where(
                AuthWorkflowDecision.plan_id == plan.id,
                AuthWorkflowDecision.round_number == round_number,
            ))
            if (
                existing is not None
                and plan.current_round == round_number
                and existing.checker_id == principal.id
                and existing.action == action
                and existing.reason == normalized_reason
                and existing.override_reason == normalized_override_reason
                and plan.status == action
            ):
                result = _plan_dict(session, plan)
            else:
                if plan.status != "PENDING_APPROVAL" or plan.current_round != round_number:
                    _fail("CONFLICT", "This approval round is not active.", correlation_id)
                if existing is not None:
                    _fail("CONFLICT", "A final decision already exists for this round.", correlation_id)
                if plan.processing_stage in {"AI_PENDING", "AI_PROCESSING"}:
                    _fail("CONFLICT", "The AI evaluation is still processing.", correlation_id)
                engine_route = session.scalar(select(AuthWorkflowEngineDecision).where(
                    AuthWorkflowEngineDecision.plan_id == plan.id,
                    AuthWorkflowEngineDecision.round_number == round_number,
                ))
                if engine_route is not None and engine_route.outcome != "HUMAN_REVIEW_REQUIRED":
                    _fail("CONFLICT", "This round is not awaiting Checker review.", correlation_id)
                if engine_route is not None:
                    evaluation_run = session.get(AuthWorkflowEvaluationRun, engine_route.evaluation_run_id)
                    recommendation = (evaluation_run.evaluation or {}).get("proposed_action") if evaluation_run else None
                    expected_recommendation = (
                        "RECOMMEND_AUTO_APPROVAL" if action == "APPROVED"
                        else "RECOMMEND_HUMAN_REVIEW"
                    )
                    if recommendation != expected_recommendation and not normalized_override_reason:
                        _fail(
                            "VALIDATION_ERROR",
                            "A reason is required when overriding the AI recommendation.",
                            correlation_id,
                        )
                elif not normalized_override_reason:
                    _fail(
                        "VALIDATION_ERROR",
                        "A reason is required when approving a plan without an AI recommendation.",
                        correlation_id,
                    )
                before = plan.status
                decision = AuthWorkflowDecision(
                    id=uuid4(),
                    plan_id=plan.id,
                    round_number=round_number,
                    checker_id=principal.id,
                    action=action,
                    reason=normalized_reason,
                    override_reason=normalized_override_reason,
                )
                plan.status = action
                close_round_snapshot(
                    session, plan_id=plan.id, round_number=round_number, closed_at=_now_datetime()
                )
                plan.processing_stage = "COMPLETED"
                plan.decision_reason = normalized_reason
                plan.revision += 1
                session.add(decision)
                _record_event(
                    session, plan_id=plan.id, actor_id=principal.id,
                    action=action, status_before=before, status_after=plan.status,
                    actor_role="CHECKER",
                    details={
                        "version": plan.current_version,
                        "round": round_number,
                        "reason": normalized_reason,
                        "override_reason": normalized_override_reason,
                        "human_decision_id": str(decision.id),
                        **({
                            "engine_decision_id": engine_route.decision_id,
                            "evaluation_id": evaluation_run.evaluation_id if evaluation_run is not None else None,
                        } if engine_route is not None else {}),
                    },
                )
                _record_notification(
                    session,
                    recipient_user_id=plan.maker_id,
                    plan=plan,
                    event_type="PLAN_APPROVED" if action == "APPROVED" else "PLAN_REJECTED",
                    version_number=plan.current_version,
                    round_number=round_number,
                    reason=normalized_reason,
                )
                session.flush()
                session.refresh(plan)
                result = _plan_dict(session, plan)
    except IntegrityError:
        session.rollback()
        _fail("CONFLICT", "Another decision was recorded for this approval round.", correlation_id)
    return result


def get_attachment(
    session: Session,
    principal: AuthenticatedPrincipal,
    plan_id: UUID,
    attachment_id: UUID,
    correlation_id: str,
):
    _require_permission(principal, "MARKETING_PLAN_READ", correlation_id)
    if "ADMIN" in principal.roles:
        _require_permission(principal, "MARKETING_PLAN_VIEW_ALL", correlation_id)
    _require_workflow_role(principal, correlation_id)
    plan = _plan_or_404(session, plan_id, correlation_id)
    _readable_plan(plan, principal, correlation_id)
    if (
        "ADMIN" in principal.roles
        and not (
            ("MAKER" in principal.roles and plan.maker_id == principal.id)
            or ("CHECKER" in principal.roles and plan.checker_id == principal.id)
        )
    ):
        _fail("NOT_FOUND", "Plan not found.", correlation_id)
    attachment = session.scalar(select(AuthWorkflowAttachment).where(
        AuthWorkflowAttachment.id == attachment_id,
        AuthWorkflowAttachment.plan_id == plan.id,
    ))
    if attachment is None:
        _fail("NOT_FOUND", "Attachment not found.", correlation_id)
    return attachment.media_type, attachment.content
