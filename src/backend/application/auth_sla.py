from __future__ import annotations
"""Transactional configuration and read models for approval-round SLAs."""
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.backend.application.workflow import ApplicationError
from src.backend.application.sla_rules import (
    SlaDeadlines,
    SlaStatus,
    calculate_deadlines,
    calculate_status,
    seconds_until_due,
    validate_sla_duration,
)
from src.backend.db.models import (
    AdminAuditEvent,
    AuthWorkflowEvent,
    AuthWorkflowNotification,
    AuthWorkflowPlan,
    AuthWorkflowSlaConfiguration,
    AuthWorkflowSlaRound,
    User,
)

if TYPE_CHECKING:
    from src.backend.api.auth import AuthenticatedPrincipal


CONFIGURATION_PERMISSION = "ADMIN_SLA_MANAGE"


def _fail(code: str, message: str, correlation_id: str) -> None:
    raise ApplicationError(code, message, correlation_id)


def _require_sla_admin(principal: AuthenticatedPrincipal, correlation_id: str) -> None:
    if "ADMIN" not in principal.roles or CONFIGURATION_PERMISSION not in principal.permissions:
        _fail("FORBIDDEN", "Only an authorized Admin can manage SLA configuration.", correlation_id)


def _write_transaction(session: Session):
    if session.in_transaction():
        session.rollback()
    return session.begin()


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _latest_configuration(session: Session, *, lock: bool = False) -> AuthWorkflowSlaConfiguration | None:
    statement = select(AuthWorkflowSlaConfiguration).order_by(
        AuthWorkflowSlaConfiguration.revision.desc()
    ).limit(1)
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)


def _configuration_dict(
    session: Session,
    configuration: AuthWorkflowSlaConfiguration | None,
) -> dict[str, Any]:
    if configuration is None:
        return {
            "configured": False,
            "revision": 0,
            "enabled": False,
            "duration_minutes": None,
            "warning_before_minutes": None,
            "changed_by_id": None,
            "changed_by_name": None,
            "change_reason": None,
            "updated_at": None,
        }
    actor = session.get(User, configuration.changed_by)
    return {
        "configured": True,
        "revision": configuration.revision,
        "enabled": configuration.enabled,
        "duration_minutes": configuration.duration_minutes,
        "warning_before_minutes": configuration.warning_before_minutes,
        "changed_by_id": str(configuration.changed_by),
        "changed_by_name": actor.display_name if actor else "Unknown user",
        "change_reason": configuration.change_reason,
        "updated_at": _utc(configuration.created_at),
    }


def get_configuration(
    session: Session,
    principal: AuthenticatedPrincipal,
    correlation_id: str,
) -> dict[str, Any]:
    _require_sla_admin(principal, correlation_id)
    return _configuration_dict(session, _latest_configuration(session))


def list_configuration_history(
    session: Session,
    principal: AuthenticatedPrincipal,
    correlation_id: str,
    *,
    offset: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    _require_sla_admin(principal, correlation_id)
    total = session.scalar(select(func.count(AuthWorkflowSlaConfiguration.id))) or 0
    rows = session.scalars(
        select(AuthWorkflowSlaConfiguration)
        .order_by(AuthWorkflowSlaConfiguration.revision.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return {
        "items": [_configuration_dict(session, row) for row in rows],
        "offset": offset,
        "limit": limit,
        "total": int(total),
    }


def _audit_state(configuration: AuthWorkflowSlaConfiguration | None) -> dict[str, Any] | None:
    if configuration is None:
        return None
    return {
        "revision": configuration.revision,
        "enabled": configuration.enabled,
        "duration_minutes": configuration.duration_minutes,
        "warning_before_minutes": configuration.warning_before_minutes,
    }


def update_configuration(
    session: Session,
    principal: AuthenticatedPrincipal,
    *,
    enabled: bool,
    duration_minutes: int,
    warning_before_minutes: int,
    expected_revision: int,
    change_reason: str,
    correlation_id: str,
) -> dict[str, Any]:
    _require_sla_admin(principal, correlation_id)
    if type(enabled) is not bool:
        _fail("VALIDATION_ERROR", "SLA enabled must be a boolean.", correlation_id)
    if type(expected_revision) is not int or expected_revision < 0:
        _fail("VALIDATION_ERROR", "Expected SLA revision must be a non-negative integer.", correlation_id)
    if not isinstance(change_reason, str) or not change_reason.strip() or len(change_reason.strip()) > 1000:
        _fail("VALIDATION_ERROR", "A change reason of 1 to 1000 characters is required.", correlation_id)
    try:
        validate_sla_duration(duration_minutes, warning_before_minutes)
    except ValueError as exc:
        _fail("VALIDATION_ERROR", str(exc), correlation_id)

    reason = change_reason.strip()
    try:
        with _write_transaction(session):
            current = _latest_configuration(session, lock=True)
            actual_revision = current.revision if current is not None else 0
            if actual_revision != expected_revision:
                _fail("CONFLICT", "SLA configuration changed. Reload it before saving.", correlation_id)
            if current is not None and (
                current.enabled == enabled
                and current.duration_minutes == duration_minutes
                and current.warning_before_minutes == warning_before_minutes
            ):
                _fail("VALIDATION_ERROR", "Change at least one SLA setting before saving.", correlation_id)
            configuration = AuthWorkflowSlaConfiguration(
                id=uuid4(),
                revision=actual_revision + 1,
                enabled=enabled,
                duration_minutes=duration_minutes,
                warning_before_minutes=warning_before_minutes,
                changed_by=principal.id,
                change_reason=reason,
            )
            session.add(configuration)
            session.flush()
            session.add(AdminAuditEvent(
                actor_id=principal.id,
                employee_id=None,
                action="SLA_CONFIGURATION_UPDATED",
                before_state=_audit_state(current),
                after_state={
                    **_audit_state(configuration),
                    "change_reason": reason,
                },
            ))
            session.flush()
            result = _configuration_dict(session, configuration)
    except IntegrityError:
        session.rollback()
        _fail("CONFLICT", "SLA configuration changed concurrently. Reload it before saving.", correlation_id)
    return result


def start_round_snapshot(
    session: Session,
    *,
    plan: AuthWorkflowPlan,
    started_at: datetime,
    correlation_id: str = "workflow-submit",
) -> AuthWorkflowSlaRound | None:
    """Snapshot the one immutable config revision visible in the submit transaction."""
    configuration = _latest_configuration(session)
    if configuration is None or not configuration.enabled:
        return None
    start = _utc(started_at)
    assert start is not None
    try:
        deadlines = calculate_deadlines(
            start,
            configuration.duration_minutes,
            configuration.warning_before_minutes,
        )
    except ValueError as exc:
        raise ApplicationError("VALIDATION_ERROR", str(exc), correlation_id) from exc
    snapshot = AuthWorkflowSlaRound(
        id=uuid4(),
        plan_id=plan.id,
        version_number=plan.current_version,
        round_number=plan.current_round,
        configuration_id=configuration.id,
        configuration_revision=configuration.revision,
        duration_minutes=configuration.duration_minutes,
        warning_before_minutes=configuration.warning_before_minutes,
        started_at=deadlines.started_at,
        warning_at=deadlines.warning_at,
        due_at=deadlines.due_at,
    )
    session.add(snapshot)
    return snapshot


def close_round_snapshot(
    session: Session,
    *,
    plan_id,
    round_number: int,
    closed_at: datetime,
) -> AuthWorkflowSlaRound | None:
    snapshot = session.scalar(
        select(AuthWorkflowSlaRound)
        .where(
            AuthWorkflowSlaRound.plan_id == plan_id,
            AuthWorkflowSlaRound.round_number == round_number,
        )
        .with_for_update()
    )
    if snapshot is not None and snapshot.closed_at is None:
        closed = _utc(closed_at)
        assert closed is not None
        snapshot.closed_at = closed
    return snapshot


def _record_sla_notification(
    session: Session,
    *,
    plan: AuthWorkflowPlan,
    snapshot: AuthWorkflowSlaRound,
    recipient_id: UUID,
    event_type: str,
) -> bool:
    if event_type == "SLA_WARNING":
        title = "Sắp đến hạn duyệt kế hoạch"
        message = f"Kế hoạch {plan.code} sẽ đến hạn trong thời gian ngắn. Vui lòng kiểm tra vòng {snapshot.round_number}."
        action = "SLA_WARNING_SENT"
    elif event_type == "SLA_OVERDUE":
        title = "Kế hoạch đã quá hạn duyệt"
        message = f"Kế hoạch {plan.code} đã quá hạn duyệt. Vui lòng kiểm tra vòng {snapshot.round_number}."
        action = "SLA_OVERDUE_SENT"
    else:
        raise ValueError("Unsupported SLA notification event type")

    event_key = f"plan:{plan.id}:round:{snapshot.round_number}:{event_type.lower()}:user:{recipient_id}"
    if session.scalar(
        select(AuthWorkflowNotification.id).where(AuthWorkflowNotification.event_key == event_key)
    ) is not None:
        return False
    session.add(AuthWorkflowNotification(
        id=uuid4(),
        recipient_user_id=recipient_id,
        plan_id=plan.id,
        event_key=event_key,
        event_type=event_type,
        title=title,
        message=message,
        version_number=snapshot.version_number,
        round_number=snapshot.round_number,
    ))
    last_sequence = session.scalar(
        select(func.max(AuthWorkflowEvent.sequence_number)).where(AuthWorkflowEvent.plan_id == plan.id)
    ) or 0
    session.add(AuthWorkflowEvent(
        id=uuid4(),
        plan_id=plan.id,
        actor_id=None,
        actor_type="SYSTEM",
        sequence_number=int(last_sequence) + 1,
        action=action,
        status_before=plan.status,
        status_after=plan.status,
        details={
            "version": snapshot.version_number,
            "round": snapshot.round_number,
            "recipient_id": str(recipient_id),
            "sla_configuration_revision": snapshot.configuration_revision,
            "sla_due_at": _utc(snapshot.due_at).isoformat(),
        },
    ))
    session.flush()
    return True


def notify_reassigned_checker(
    session: Session,
    *,
    plan: AuthWorkflowPlan,
    now: datetime,
) -> int:
    """Notify a replacement Checker if the active round has reached warning/overdue."""
    if plan.status != "PENDING_APPROVAL" or plan.checker_id is None:
        return 0
    snapshot = session.scalar(
        select(AuthWorkflowSlaRound)
        .where(
            AuthWorkflowSlaRound.plan_id == plan.id,
            AuthWorkflowSlaRound.round_number == plan.current_round,
            AuthWorkflowSlaRound.closed_at.is_(None),
        )
        .with_for_update()
    )
    if snapshot is None:
        return 0
    deadlines = SlaDeadlines(
        _utc(snapshot.started_at), _utc(snapshot.warning_at), _utc(snapshot.due_at)
    )
    status = calculate_status(deadlines, None, now)
    event_type = (
        "SLA_OVERDUE" if status == SlaStatus.OVERDUE
        else "SLA_WARNING" if status == SlaStatus.WARNING
        else None
    )
    if event_type is None:
        return 0
    recipients = {plan.checker_id}
    if event_type == "SLA_OVERDUE":
        recipients.add(plan.maker_id)
    return sum(
        _record_sla_notification(
            session, plan=plan, snapshot=snapshot, recipient_id=recipient,
            event_type=event_type,
        )
        for recipient in recipients
    )


def process_due_sla_notifications(
    session_factory,
    *,
    now: datetime | None = None,
    batch_size: int = 100,
) -> int:
    """Process one bounded batch; safe to invoke repeatedly from a scheduled worker."""
    if type(batch_size) is not int or not 1 <= batch_size <= 1000:
        raise ValueError("batch_size must be between 1 and 1000")
    current_time = _utc(now or datetime.now(timezone.utc))
    assert current_time is not None
    event_type_at_scan = case(
        (AuthWorkflowSlaRound.due_at <= current_time, "SLA_OVERDUE"),
        else_="SLA_WARNING",
    )
    notice_exists = select(AuthWorkflowNotification.id).where(
        AuthWorkflowNotification.plan_id == AuthWorkflowSlaRound.plan_id,
        AuthWorkflowNotification.round_number == AuthWorkflowSlaRound.round_number,
        AuthWorkflowNotification.event_type == event_type_at_scan,
    ).exists()
    with session_factory() as lookup_session:
        round_ids = lookup_session.scalars(
            select(AuthWorkflowSlaRound.id)
            .where(
                AuthWorkflowSlaRound.closed_at.is_(None),
                AuthWorkflowSlaRound.warning_at <= current_time,
                ~notice_exists,
            )
            .order_by(AuthWorkflowSlaRound.warning_at, AuthWorkflowSlaRound.id)
            .limit(batch_size)
        ).all()

    created = 0
    for round_id in round_ids:
        with session_factory() as session:
            batch_created = 0
            try:
                with session.begin():
                    candidate = session.scalar(
                        select(AuthWorkflowSlaRound).where(AuthWorkflowSlaRound.id == round_id)
                    )
                    if candidate is None:
                        continue
                    # Match final-decision lock order: plan first, SLA round second.
                    plan = session.scalar(
                        select(AuthWorkflowPlan)
                        .where(AuthWorkflowPlan.id == candidate.plan_id)
                        .with_for_update()
                    )
                    if plan is None:
                        continue
                    snapshot = session.scalar(
                        select(AuthWorkflowSlaRound)
                        .where(AuthWorkflowSlaRound.id == round_id)
                        .with_for_update()
                    )
                    if (
                        snapshot is None
                        or snapshot.closed_at is not None
                        or plan.status != "PENDING_APPROVAL"
                        or plan.current_round != snapshot.round_number
                        or plan.checker_id is None
                    ):
                        continue
                    deadlines = SlaDeadlines(
                        _utc(snapshot.started_at), _utc(snapshot.warning_at), _utc(snapshot.due_at)
                    )
                    status = calculate_status(deadlines, None, current_time)
                    event_type = (
                        "SLA_OVERDUE" if status == SlaStatus.OVERDUE
                        else "SLA_WARNING" if status == SlaStatus.WARNING
                        else None
                    )
                    if event_type is None:
                        continue
                    recipients = {plan.checker_id}
                    if event_type == "SLA_OVERDUE":
                        recipients.add(plan.maker_id)
                    batch_created += sum(
                        _record_sla_notification(
                            session, plan=plan, snapshot=snapshot, recipient_id=recipient,
                            event_type=event_type,
                        )
                        for recipient in recipients
                    )
                created += batch_created
            except IntegrityError:
                # Another worker won the same event-key race; the unique key is the idempotency guard.
                session.rollback()
    return created


def _not_applicable(version_number: int, round_number: int) -> dict[str, Any]:
    return {
        "version_number": version_number,
        "round_number": round_number,
        "applicable": False,
        "status": SlaStatus.NOT_APPLICABLE.value,
        "configuration_revision": None,
        "duration_minutes": None,
        "warning_before_minutes": None,
        "started_at": None,
        "warning_at": None,
        "due_at": None,
        "closed_at": None,
        "seconds_until_due": None,
    }


def _round_dict(snapshot: AuthWorkflowSlaRound, now: datetime) -> dict[str, Any]:
    started_at = _utc(snapshot.started_at)
    warning_at = _utc(snapshot.warning_at)
    due_at = _utc(snapshot.due_at)
    assert started_at is not None and warning_at is not None and due_at is not None
    closed_at = _utc(snapshot.closed_at)
    deadlines = SlaDeadlines(started_at, warning_at, due_at)
    return {
        "version_number": snapshot.version_number,
        "round_number": snapshot.round_number,
        "applicable": True,
        "status": calculate_status(deadlines, closed_at, now).value,
        "configuration_revision": snapshot.configuration_revision,
        "duration_minutes": snapshot.duration_minutes,
        "warning_before_minutes": snapshot.warning_before_minutes,
        "started_at": started_at,
        "warning_at": warning_at,
        "due_at": due_at,
        "closed_at": closed_at,
        "seconds_until_due": seconds_until_due(deadlines, now),
    }


def plan_sla_read_model(
    session: Session,
    plan: AuthWorkflowPlan,
    versions: list[Any],
    *,
    now: datetime | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Return server-calculated current SLA and history without writing on GET."""
    if not versions:
        return None, []
    current_time = _utc(now or datetime.now(timezone.utc))
    assert current_time is not None
    snapshots = session.scalars(
        select(AuthWorkflowSlaRound)
        .where(AuthWorkflowSlaRound.plan_id == plan.id)
        .order_by(AuthWorkflowSlaRound.round_number)
    ).all()
    by_round = {snapshot.round_number: snapshot for snapshot in snapshots}
    history = []
    for version in versions:
        snapshot = by_round.get(version.round_number)
        history.append(
            _round_dict(snapshot, current_time)
            if snapshot is not None
            else _not_applicable(version.version_number, version.round_number)
        )
    current = next(
        (item for item in history if item["round_number"] == plan.current_round),
        None,
    )
    return current, history
