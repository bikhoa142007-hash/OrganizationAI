from datetime import datetime, timezone
import hashlib
import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from src.backend.api.auth import AuthenticatedPrincipal
from src.backend.application.workflow import ApplicationError
from src.backend.db.models.auth_workflow import AuthWorkflowPlan, AuthWorkflowVersion
from src.backend.db.models.workflow_internal_note import (
    WorkflowInternalNote,
    WorkflowInternalNoteAuditEvent,
)


def _require_assigned_checker(
    session: Session,
    principal: AuthenticatedPrincipal,
    plan_id: UUID,
    correlation_id: str,
) -> AuthWorkflowPlan:
    plan = session.get(AuthWorkflowPlan, plan_id)
    if plan is None:
        raise ApplicationError("NOT_FOUND", "Plan was not found.", correlation_id)
    if "CHECKER" not in principal.roles or plan.checker_id != principal.id:
        raise ApplicationError("FORBIDDEN", "Only the assigned Checker can access internal notes.", correlation_id)
    return plan


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _serialize_note(note: WorkflowInternalNote) -> dict[str, Any]:
    return {
        "note_id": note.note_id,
        "plan_id": note.plan_id,
        "approval_round": note.approval_round,
        "author_id": note.author_id,
        "created_at": _as_utc(note.created_at),
        "content": note.content,
    }


def list_internal_notes(
    session: Session,
    principal: AuthenticatedPrincipal,
    plan_id: UUID,
    correlation_id: str,
) -> list[dict[str, Any]]:
    _require_assigned_checker(session, principal, plan_id, correlation_id)
    notes = session.scalars(
        select(WorkflowInternalNote)
        .where(WorkflowInternalNote.plan_id == plan_id)
        .order_by(WorkflowInternalNote.created_at, WorkflowInternalNote.note_id)
    ).all()
    return [_serialize_note(note) for note in notes]


def _find_idempotent_note(
    session: Session,
    plan_id: UUID,
    actor_id: UUID,
    idempotency_key: str,
) -> WorkflowInternalNote | None:
    return session.scalar(
        select(WorkflowInternalNote).where(
            WorkflowInternalNote.plan_id == plan_id,
            WorkflowInternalNote.author_id == actor_id,
            WorkflowInternalNote.idempotency_key == idempotency_key,
        )
    )


def add_internal_note(
    session: Session,
    principal: AuthenticatedPrincipal,
    plan_id: UUID,
    approval_round: int | None,
    content: str,
    idempotency_key: str,
    correlation_id: str,
) -> dict[str, Any]:
    _require_assigned_checker(session, principal, plan_id, correlation_id)
    if not isinstance(content, str):
        raise ApplicationError("VALIDATION_ERROR", "Note content is invalid.", correlation_id)
    normalized_content = content.strip()
    if not normalized_content or len(normalized_content) > 4000:
        raise ApplicationError("VALIDATION_ERROR", "Note content must contain 1 to 4000 characters.", correlation_id)
    if approval_round is not None:
        if type(approval_round) is not int or approval_round < 1:
            raise ApplicationError("VALIDATION_ERROR", "Approval round is invalid.", correlation_id)
        matching_round = session.scalar(
            select(AuthWorkflowVersion.id).where(
                AuthWorkflowVersion.plan_id == plan_id,
                AuthWorkflowVersion.round_number == approval_round,
            ).limit(1)
        )
        if matching_round is None:
            raise ApplicationError("VALIDATION_ERROR", "Approval round does not belong to this plan.", correlation_id)
    if not isinstance(idempotency_key, str) or not idempotency_key.strip() or len(idempotency_key) > 200:
        raise ApplicationError("VALIDATION_ERROR", "Idempotency key is invalid.", correlation_id)

    request_hash = hashlib.sha256(json.dumps(
        {"approval_round": approval_round, "content": normalized_content},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    existing = _find_idempotent_note(session, plan_id, principal.id, idempotency_key)
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ApplicationError("IDEMPOTENCY_CONFLICT", "Idempotency key was already used for another note.", correlation_id)
        return _serialize_note(existing)

    note = WorkflowInternalNote(note_id=uuid4(),
        plan_id=plan_id,
        approval_round=approval_round,
        author_id=principal.id,
        content=normalized_content,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )
    audit = WorkflowInternalNoteAuditEvent(
        note_id=note.note_id,
        plan_id=plan_id,
        actor_id=principal.id,
        action="INTERNAL_NOTE_ADDED",
    )
    try:
        session.add(note)
        session.flush()
        session.add(audit)
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = _find_idempotent_note(session, plan_id, principal.id, idempotency_key)
        if existing is not None:
            if existing.request_hash != request_hash:
                raise ApplicationError("IDEMPOTENCY_CONFLICT", "Idempotency key was already used for another note.", correlation_id)
            return _serialize_note(existing)
        raise ApplicationError("UNAVAILABLE", "Could not persist internal note and audit metadata.", correlation_id)
    except SQLAlchemyError as exc:
        session.rollback()
        raise ApplicationError("UNAVAILABLE", "Could not persist internal note and audit metadata.", correlation_id) from exc
    return _serialize_note(note)
