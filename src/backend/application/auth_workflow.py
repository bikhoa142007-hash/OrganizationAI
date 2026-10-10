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
from src.backend.db.models import (
    AuthWorkflowAttachment,
    AuthWorkflowDecision,
    AuthWorkflowEngineDecision,
    AuthWorkflowEvent,
    AuthWorkflowEvaluationRun,
    AuthWorkflowPlan,
    AuthWorkflowVersion,
    Role,
    User,
    UserRole,
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
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(User.id == checker_id, User.status == "ACTIVE", Role.code == "CHECKER")
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


def _now_datetime() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp() -> str:
    return _now_datetime().isoformat(timespec="milliseconds").replace("+00:00", "Z")


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
) -> AuthWorkflowEvent:
    last_sequence = session.scalar(
        select(func.max(AuthWorkflowEvent.sequence_number)).where(AuthWorkflowEvent.plan_id == plan_id)
    ) or 0
    event = AuthWorkflowEvent(
        id=uuid4(),
        plan_id=plan_id,
        actor_id=actor_id,
        actor_type=actor_type,
        sequence_number=int(last_sequence) + 1,
        action=action,
        status_before=status_before,
        status_after=status_after,
        details=details,
    )
    session.add(event)
    return event


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
            .order_by(AuthWorkflowEvaluationRun.round_number)
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
            .where(AuthWorkflowEngineDecision.plan_id == plan.id)
            .order_by(AuthWorkflowEngineDecision.round_number)
        ).all()],
        "history": history,
        "created_at": plan.created_at,
        "updated_at": plan.updated_at,
    }


def list_checkers(session: Session, principal: AuthenticatedPrincipal, correlation_id: str):
    _require_role(principal, "MAKER", correlation_id)
    users = session.scalars(
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(User.status == "ACTIVE", Role.code == "CHECKER", User.id != principal.id)
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
    _require_workflow_role(principal, correlation_id)
    plan = _plan_or_404(session, plan_id, correlation_id)
    _readable_plan(plan, principal, correlation_id)
    return _plan_dict(session, plan)


def list_audit_events(
    session: Session,
    principal: AuthenticatedPrincipal,
    correlation_id: str,
    *,
    offset: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    if "ADMIN" not in principal.roles:
        _fail("FORBIDDEN", "You do not have permission to view the audit log.", correlation_id)
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
                    details={"code": plan.code},
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
    try:
        with _write_transaction(session):
            plan = _plan_or_404(session, plan_id, correlation_id, lock=True)
            _maker_plan(plan, principal, correlation_id)
            if plan.status not in {"DRAFT", "REJECTED"}:
                _fail("CONFLICT", "Submitted and approved plans are read-only.", correlation_id)
            if plan.revision != expected_revision:
                _fail("CONFLICT", "The plan changed. Reload it before saving.", correlation_id)
            next_checker = checker_id if update_checker else plan.checker_id
            _validate_checker(session, principal, next_checker, correlation_id)
            before = plan.status
            plan.payload = payload
            plan.checker_id = next_checker
            plan.revision += 1
            _record_event(
                session, plan_id=plan.id, actor_id=principal.id,
                action="UPDATED", status_before=before, status_after=plan.status,
                details={"revision": plan.revision},
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
    try:
        with _write_transaction(session):
            plan = _plan_or_404(session, plan_id, correlation_id, lock=True)
            _maker_plan(plan, principal, correlation_id)
            if plan.status not in {"DRAFT", "REJECTED"}:
                _fail("CONFLICT", "Only a draft or rejected plan can be submitted.", correlation_id)
            if plan.revision != expected_revision:
                _fail("CONFLICT", "The plan changed. Reload it before submitting.", correlation_id)
            _validate_submission(plan.payload, correlation_id)
            _validate_checker(session, principal, plan.checker_id, correlation_id, required=True)
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
            policy_snapshot = configuration.to_dict()
            policy_snapshot_hash = canonical_hash(policy_snapshot)
            run_id = "run-" + uuid4().hex
            evaluation_id = "evaluation-" + uuid4().hex
            media_initial = initial_evaluation_step(
                "MEDIA_COMPLIANCE", snapshot_hash, configuration,
                configuration.media_model_snapshot,
            )
            strategy_initial = initial_evaluation_step(
                "STRATEGY_EVALUATION", snapshot_hash, configuration,
                configuration.strategy_model_snapshot,
            )
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
                details={
                    "version": plan.current_version,
                    "round": plan.current_round,
                    "checker_id": str(plan.checker_id),
                    "attachment_hashes": [item["content_hash"] for item in attachment_manifest],
                    "input_hash": snapshot_hash,
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
                },
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


def evaluate_submission(
    session: Session,
    plan_id: UUID,
    round_number: int,
    orchestrator: EvaluationOrchestrator,
    correlation_id: str,
):
    """Evaluate a committed snapshot outside DB transactions, then persist atomically."""
    request = None
    configuration = None
    snapshot = None
    verified_hashes: tuple[tuple[str, str], ...] = ()
    snapshot_is_valid = True
    prepared_response = None

    try:
        with _write_transaction(session):
            plan = _plan_or_404(session, plan_id, correlation_id, lock=True)
            run = session.scalar(
                select(AuthWorkflowEvaluationRun)
                .where(
                    AuthWorkflowEvaluationRun.plan_id == plan.id,
                    AuthWorkflowEvaluationRun.round_number == round_number,
                )
                .with_for_update()
            )
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
                snapshot_is_valid = (
                    version.snapshot_hash == snapshot.input_hash
                    and run.input_hash == snapshot.input_hash
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
                    metadata={"attachment_contents": contents, "model_id": run.model_id},
                )
                run.status = "PROCESSING"
                run.attempts = 0
                run.retried = False
                run.started_at = _now_datetime()
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
                run.completed_at = _now_datetime()
                _record_event(
                    session, plan_id=plan.id, actor_id=None, actor_type="SYSTEM",
                    action="AI_RESULT_IGNORED_STALE", status_before=plan.status,
                    status_after=plan.status,
                    details={
                        "version": run.version_number,
                        "round": run.round_number,
                        "run_id": run.run_id,
                        "evaluation_id": run.evaluation_id,
                        "input_hash": run.input_hash,
                    },
                )
                session.flush()
                return _plan_dict(session, plan)

            run.attempts = pipeline_result.attempts
            run.retried = pipeline_result.retried
            run.media_evaluation = pipeline_result.media_evaluation or run.media_evaluation
            run.strategy_evaluation = pipeline_result.strategy_evaluation or run.strategy_evaluation
            config = ApprovalConfiguration.from_dict(run.policy_snapshot)
            valid_checkers = session.scalars(
                select(User.id)
                .join(UserRole, UserRole.user_id == User.id)
                .join(Role, Role.id == UserRole.role_id)
                .where(User.status == "ACTIVE", Role.code == "CHECKER")
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
            )
            try:
                bundle = decide(snapshot, config, raw_evaluation, context)
            except Exception:
                # Engine faults are not approval evidence. Preserve a durable review route.
                run.status = "FAILED"
                run.failure_reason = "Decision policy could not complete; Checker review is required."
                run.completed_at = _now_datetime()
                plan.processing_stage = "HUMAN_REVIEW_REQUIRED"
                plan.decision_reason = run.failure_reason
                plan.revision += 1
                _record_event(
                    session, plan_id=plan.id, actor_id=None, actor_type="SYSTEM",
                    action="AI_REVIEW_ROUTED", status_before=plan.status,
                    status_after=plan.status,
                    details={
                        "version": run.version_number,
                        "round": run.round_number,
                        "run_id": run.run_id,
                        "evaluation_id": run.evaluation_id,
                        "reason": run.failure_reason,
                    },
                )
                session.flush()
                return _plan_dict(session, plan)

            evaluation = bundle.evaluation.to_dict()
            decision = bundle.decision.to_dict()
            run.status = bundle.evaluation.status
            run.evaluation = evaluation
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
                plan.processing_stage = "AI_AUTO_APPROVED"
                plan.decision_reason = None
                action = "AI_AUTO_APPROVED"
            else:
                plan.processing_stage = "HUMAN_REVIEW_REQUIRED"
                plan.decision_reason = bundle.decision.reason
                action = "AI_REVIEW_ROUTED"
            plan.revision += 1
            _record_event(
                session, plan_id=plan.id, actor_id=None, actor_type="SYSTEM",
                action="AI_EVALUATION_COMPLETED", status_before="PENDING_APPROVAL",
                status_after=plan.status,
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
                },
            )
            _record_event(
                session, plan_id=plan.id, actor_id=None, actor_type="SYSTEM",
                action=action, status_before="PENDING_APPROVAL", status_after=plan.status,
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
                },
            )
            session.flush()
            session.refresh(plan)
            return _plan_dict(session, plan)
    except IntegrityError:
        session.rollback()
        _fail("CONFLICT", "The evaluation result could not be committed for this round.", correlation_id)


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
                failure_reason = "AI evaluation was interrupted; Checker review is required."
                if version is None:
                    run.status = "FAILED"
                    run.failure_reason = "RUN_INTERRUPTED_SNAPSHOT_UNAVAILABLE"
                    run.completed_at = _now_datetime()
                    plan.processing_stage = "HUMAN_REVIEW_REQUIRED"
                    plan.decision_reason = failure_reason
                    plan.revision += 1
                    _record_event(
                        session, plan_id=plan.id, actor_id=None, actor_type="SYSTEM",
                        action="AI_RECOVERY_REVIEW_ROUTED", status_before=plan.status,
                        status_after=plan.status,
                        details={"round": run.round_number, "run_id": run.run_id,
                                 "reason": run.failure_reason},
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
                    .join(UserRole, UserRole.user_id == User.id)
                    .join(Role, Role.id == UserRole.role_id)
                    .where(User.status == "ACTIVE", Role.code == "CHECKER")
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
                )
                try:
                    if config is None:
                        raise ValueError("Saved policy snapshot is invalid")
                    bundle = decide(snapshot, config, failure.evaluation, context)
                except Exception:
                    bundle = None

                run.status = "FAILED"
                run.failure_reason = configuration_error or "RUN_INTERRUPTED"
                run.completed_at = _now_datetime()
                plan.processing_stage = "HUMAN_REVIEW_REQUIRED"
                plan.decision_reason = failure_reason
                plan.revision += 1
                details = {
                    "version": run.version_number,
                    "round": run.round_number,
                    "run_id": run.run_id,
                    "evaluation_id": run.evaluation_id,
                    "input_hash": run.input_hash,
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
                _record_event(
                    session, plan_id=plan.id, actor_id=None, actor_type="SYSTEM",
                    action="AI_RECOVERY_REVIEW_ROUTED", status_before=plan.status,
                    status_after=plan.status, details=details,
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
                plan.processing_stage = "COMPLETED"
                plan.decision_reason = normalized_reason
                plan.revision += 1
                session.add(decision)
                _record_event(
                    session, plan_id=plan.id, actor_id=principal.id,
                    action=action, status_before=before, status_after=plan.status,
                    details={
                        "round": round_number,
                        "reason": normalized_reason,
                        "override_reason": normalized_override_reason,
                    },
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
