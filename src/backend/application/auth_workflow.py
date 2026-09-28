from __future__ import annotations

from datetime import date
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
    AuthWorkflowEvent,
    AuthWorkflowPlan,
    AuthWorkflowVersion,
    Role,
    User,
    UserRole,
)

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
    if not {"MAKER", "CHECKER"}.intersection(principal.roles):
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


def _record_event(
    session: Session,
    *,
    plan_id: UUID,
    actor_id: UUID,
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
        actor = session.get(User, event.actor_id)
        history.append({
            "id": str(event.id),
            "actor_id": str(event.actor_id),
            "actor_name": actor.display_name if actor else "Unknown user",
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
            "submitted_by": str(item.submitted_by),
            "created_at": item.created_at,
        } for item in versions],
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


def create_plan(
    session: Session,
    principal: AuthenticatedPrincipal,
    payload: dict[str, Any],
    checker_id: UUID | None,
    correlation_id: str,
):
    _require_role(principal, "MAKER", correlation_id)
    try:
        with _write_transaction(session):
            _validate_checker(session, principal, checker_id, correlation_id)
            plan_id = uuid4()
            plan = AuthWorkflowPlan(
                id=plan_id,
                code=f"MKT-{plan_id.hex[:12].upper()}",
                maker_id=principal.id,
                checker_id=checker_id,
                payload=payload,
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
            # Auth workflow is an explicit human-review path. The SQLite Judge Demo
            # remains the only workflow currently connected to the AI pipeline.
            plan.processing_stage = "HUMAN_REVIEW_REQUIRED"
            plan.decision_reason = None
            plan.revision += 1
            attachment_manifest = [{
                "id": str(item.id),
                "filename": item.filename,
                "media_type": item.media_type,
                "byte_size": item.byte_size,
                "content_hash": item.content_hash,
            } for item in attachments]
            session.add(AuthWorkflowVersion(
                id=uuid4(),
                plan_id=plan.id,
                version_number=plan.current_version,
                round_number=plan.current_round,
                payload_snapshot=dict(plan.payload),
                attachment_snapshot=attachment_manifest,
                submitted_by=principal.id,
            ))
            _record_event(
                session, plan_id=plan.id, actor_id=principal.id,
                action="SUBMITTED", status_before=before, status_after=plan.status,
                details={
                    "version": plan.current_version,
                    "round": plan.current_round,
                    "checker_id": str(plan.checker_id),
                    "attachment_hashes": [item["content_hash"] for item in attachment_manifest],
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
    if not re.fullmatch(r"[1-9][0-9]{0,23}", amount):
        _fail("VALIDATION_ERROR", "Budget must be a positive whole-number amount.", correlation_id)


def decide_plan(
    session: Session,
    principal: AuthenticatedPrincipal,
    plan_id: UUID,
    round_number: int,
    action: str,
    reason: str | None,
    correlation_id: str,
):
    _require_role(principal, "CHECKER", correlation_id)
    normalized_reason = reason.strip() if reason and reason.strip() else None
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
                and plan.status == action
            ):
                result = _plan_dict(session, plan)
            else:
                if plan.status != "PENDING_APPROVAL" or plan.current_round != round_number:
                    _fail("CONFLICT", "This approval round is not active.", correlation_id)
                if existing is not None:
                    _fail("CONFLICT", "A final decision already exists for this round.", correlation_id)
                before = plan.status
                decision = AuthWorkflowDecision(
                    id=uuid4(),
                    plan_id=plan.id,
                    round_number=round_number,
                    checker_id=principal.id,
                    action=action,
                    reason=normalized_reason,
                )
                plan.status = action
                plan.processing_stage = "COMPLETED"
                plan.decision_reason = normalized_reason
                plan.revision += 1
                session.add(decision)
                _record_event(
                    session, plan_id=plan.id, actor_id=principal.id,
                    action=action, status_before=before, status_after=plan.status,
                    details={"round": round_number, "reason": normalized_reason},
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
    attachment = session.scalar(select(AuthWorkflowAttachment).where(
        AuthWorkflowAttachment.id == attachment_id,
        AuthWorkflowAttachment.plan_id == plan.id,
    ))
    if attachment is None:
        _fail("NOT_FOUND", "Attachment not found.", correlation_id)
    return attachment.media_type, attachment.content
