"""PostgreSQL acceptance checks for approval-round SLA locking and snapshots.

Run with SLA_POSTGRES_TEST_URL and SLA_EMPTY_POSTGRES_TEST_URL pointing only to
isolated disposable databases. These tests never fall back to DATABASE_URL.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from threading import Event, Barrier
from time import monotonic, sleep
from uuid import UUID, uuid4
import os

import pytest
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from src.backend.api.auth import AuthenticatedPrincipal
from src.backend.application import approval_configuration, auth_sla, auth_workflow, employee_admin
from src.backend.application.sla_rules import SlaDeadlines, SlaStatus, calculate_status
from src.backend.application.workflow import ApplicationError
from src.backend.db.models import (
    AdminAuditEvent,
    AuthWorkflowDecision,
    AuthWorkflowEvent,
    AuthWorkflowNotification,
    AuthWorkflowPlan,
    AuthWorkflowSlaConfiguration,
    AuthWorkflowSlaRound,
    EmployeeProfile,
    Role,
    User,
    UserRole,
)


@pytest.fixture
def sla_postgres():
    """Require an explicit test-only URL; never inherit the app DATABASE_URL."""
    url = os.environ.get("SLA_POSTGRES_TEST_URL", "").strip()
    if not url.startswith("postgresql+psycopg://"):
        pytest.skip("SLA PostgreSQL acceptance requires its isolated run-specific URL.")
    engine = create_engine(url, pool_pre_ping=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    try:
        yield engine.url, engine, factory
    finally:
        engine.dispose()


def _people(factory):
    suffix = uuid4().hex[:12]
    users = {
        key: User(
            user_code=f"SLA-{key[:4].upper()}-{suffix}",
            username=f"sla_{key.lower()}_{suffix}",
            email=f"sla_{key.lower()}_{suffix}@example.test",
            password_hash="synthetic-test-only",
            display_name=f"Synthetic SLA {key}",
            status="ACTIVE",
        )
        for key in ("ADMIN", "MAKER", "CHECKER", "NEXT", "OUTSIDER")
    }
    with factory.begin() as session:
        session.add_all(users.values())
        session.flush()
        checker_role = session.scalar(select(Role).where(Role.code == "CHECKER"))
        maker_role = session.scalar(select(Role).where(Role.code == "MAKER"))
        admin_role = session.scalar(select(Role).where(Role.code == "ADMIN"))
        assert checker_role is not None and maker_role is not None and admin_role is not None
        session.add_all([
            UserRole(user_id=users["MAKER"].id, role_id=maker_role.id),
            UserRole(user_id=users["CHECKER"].id, role_id=checker_role.id),
            UserRole(user_id=users["NEXT"].id, role_id=checker_role.id),
            UserRole(user_id=users["OUTSIDER"].id, role_id=checker_role.id),
            UserRole(user_id=users["ADMIN"].id, role_id=admin_role.id),
        ])
    return users


def _principal(user: User, role: str, permissions: tuple[str, ...] = ()):
    return AuthenticatedPrincipal(
        id=user.id,
        user_code=user.user_code,
        username=user.username,
        email=user.email,
        phone=user.phone,
        display_name=user.display_name,
        status=user.status,
        roles=(role,),
        permissions=permissions,
    )


def _set_config(factory, admin: User, *, enabled: bool, duration: int, warning: int):
    principal = _principal(admin, "ADMIN", ("ADMIN_SLA_MANAGE",))
    with factory() as session:
        current = auth_sla.get_configuration(session, principal, "pg-sla-config-read")
        result = auth_sla.update_configuration(
            session,
            principal,
            enabled=enabled,
            duration_minutes=duration,
            warning_before_minutes=warning,
            expected_revision=current["revision"],
            change_reason="Synthetic PostgreSQL acceptance fixture.",
            correlation_id=f"pg-sla-{uuid4().hex[:12]}",
        )
    with factory() as session:
        latest = session.scalar(
            select(AuthWorkflowSlaConfiguration)
            .order_by(AuthWorkflowSlaConfiguration.revision.desc())
            .limit(1)
        )
        assert latest is not None and latest.revision == result["revision"]
        result["id"] = str(latest.id)
    return result


def _plan(factory, people: dict[str, User], *, round_number: int = 1):
    identifier = uuid4()
    suffix = identifier.hex[:12]
    with factory.begin() as session:
        session.add(AuthWorkflowPlan(
            id=identifier,
            code=f"MKT-SLA-PG-{suffix}",
            maker_id=people["MAKER"].id,
            checker_id=people["CHECKER"].id,
            payload={"title": "Synthetic PostgreSQL SLA acceptance"},
            status="PENDING_APPROVAL",
            processing_stage="HUMAN_REVIEW_REQUIRED",
            current_version=round_number,
            current_round=round_number,
            revision=round_number,
        ))
    return identifier


def _start_snapshot(factory, plan_id, started_at: datetime):
    with factory.begin() as session:
        plan = session.scalar(
            select(AuthWorkflowPlan).where(AuthWorkflowPlan.id == plan_id).with_for_update()
        )
        assert plan is not None
        snapshot = auth_sla.start_round_snapshot(session, plan=plan, started_at=started_at)
        session.flush()
        if snapshot is None:
            return None
        return {
            "id": snapshot.id,
            "configuration_id": snapshot.configuration_id,
            "configuration_revision": snapshot.configuration_revision,
            "duration_minutes": snapshot.duration_minutes,
            "warning_before_minutes": snapshot.warning_before_minutes,
            "started_at": snapshot.started_at,
            "warning_at": snapshot.warning_at,
            "due_at": snapshot.due_at,
        }


def _pg_lock_seen(observer_engine, application_name: str, *, timeout: float = 8.0) -> bool:
    deadline = monotonic() + timeout
    statement = text("""
        SELECT count(*) FROM pg_stat_activity
        WHERE application_name = :application_name
          AND state = 'active'
          AND wait_event_type = 'Lock'
    """)
    while monotonic() < deadline:
        with observer_engine.connect() as connection:
            if connection.scalar(statement, {"application_name": application_name}):
                return True
        sleep(0.01)
    return False


def test_postgres_snapshot_boundaries_recipients_replay_reassignment_and_resubmit(sla_postgres):
    _, _, factory = sla_postgres
    people = _people(factory)
    duration, warning = 131, 29
    first_config = _set_config(factory, people["ADMIN"], enabled=True, duration=duration, warning=warning)
    plan_id = _plan(factory, people)
    started = datetime(2031, 5, 1, 9, tzinfo=timezone.utc)
    snapshot = _start_snapshot(factory, plan_id, started)
    assert snapshot is not None
    warning_at, due_at = snapshot["warning_at"], snapshot["due_at"]
    deadlines = SlaDeadlines(started, warning_at, due_at)

    assert calculate_status(deadlines, None, warning_at - timedelta(microseconds=1)) == SlaStatus.IN_PROGRESS
    assert calculate_status(deadlines, None, warning_at) == SlaStatus.WARNING
    assert calculate_status(deadlines, None, warning_at + timedelta(microseconds=1)) == SlaStatus.WARNING
    assert calculate_status(deadlines, None, due_at - timedelta(microseconds=1)) == SlaStatus.WARNING
    assert calculate_status(deadlines, None, due_at) == SlaStatus.OVERDUE
    assert calculate_status(deadlines, None, due_at + timedelta(microseconds=1)) == SlaStatus.OVERDUE

    assert auth_sla.process_due_sla_notifications(factory, now=warning_at - timedelta(microseconds=1)) == 0
    assert auth_sla.process_due_sla_notifications(factory, now=warning_at) == 1
    assert auth_sla.process_due_sla_notifications(factory, now=warning_at) == 0

    disabled_config = _set_config(
        factory, people["ADMIN"], enabled=False, duration=duration + 1, warning=warning
    )
    with factory.begin() as session:
        plan = session.get(AuthWorkflowPlan, plan_id)
        assert plan is not None
        old_checker_notice_count = auth_sla.notify_reassigned_checker(
            session, plan=plan, now=warning_at
        )
        plan.checker_id = people["NEXT"].id
        new_checker_notice_count = auth_sla.notify_reassigned_checker(
            session, plan=plan, now=warning_at
        )
    assert disabled_config["revision"] > first_config["revision"]
    assert old_checker_notice_count == 0
    assert new_checker_notice_count == 1

    assert auth_sla.process_due_sla_notifications(factory, now=due_at - timedelta(microseconds=1)) == 0
    assert auth_sla.process_due_sla_notifications(factory, now=due_at) == 2
    assert auth_sla.process_due_sla_notifications(factory, now=due_at + timedelta(days=2)) == 0
    with factory() as session:
        stored = session.get(AuthWorkflowSlaRound, snapshot["id"])
        plan = session.get(AuthWorkflowPlan, plan_id)
        notifications = session.scalars(select(AuthWorkflowNotification).where(
            AuthWorkflowNotification.plan_id == plan_id
        )).all()
        assert stored is not None and plan is not None
        assert stored.configuration_id == UUID(first_config["id"])
        assert stored.configuration_revision == first_config["revision"]
        assert stored.duration_minutes == duration and stored.warning_before_minutes == warning
        assert stored.warning_at == warning_at and stored.due_at == due_at
        assert stored.closed_at is None
        assert plan.status == "PENDING_APPROVAL"
        assert plan.processing_stage == "HUMAN_REVIEW_REQUIRED"
        assert {(item.event_type, item.recipient_user_id) for item in notifications} == {
            ("SLA_WARNING", people["CHECKER"].id),
            ("SLA_WARNING", people["NEXT"].id),
            ("SLA_OVERDUE", people["MAKER"].id),
            ("SLA_OVERDUE", people["NEXT"].id),
        }

        old_checker_notices = auth_workflow.list_notifications(
            session, _principal(people["CHECKER"], "CHECKER")
        )
        outsider_notices = auth_workflow.list_notifications(
            session, _principal(people["OUTSIDER"], "CHECKER")
        )
        assert [item["event_type"] for item in old_checker_notices["items"]] == ["SLA_WARNING"]
        assert outsider_notices["total"] == 0
        with pytest.raises(ApplicationError) as stale_link:
            auth_workflow._readable_plan(
                plan, _principal(people["CHECKER"], "CHECKER"), "old-checker-plan-link"
            )
        assert stale_link.value.code == "NOT_FOUND"
        with pytest.raises(ApplicationError) as private_read:
            auth_workflow.mark_notification_read(
                session,
                _principal(people["OUTSIDER"], "CHECKER"),
                old_checker_notices["items"][0]["id"],
                "outsider-notification-read",
            )
        assert private_read.value.code == "NOT_FOUND"

    with factory.begin() as session:
        auth_sla.close_round_snapshot(
            session, plan_id=plan_id, round_number=1, closed_at=due_at
        )
        plan = session.get(AuthWorkflowPlan, plan_id)
        assert plan is not None
        plan.status = "REJECTED"
        plan.current_version = 2
        plan.current_round = 2
        plan.revision += 1
    next_config = _set_config(factory, people["ADMIN"], enabled=True, duration=240, warning=60)
    next_snapshot = _start_snapshot(factory, plan_id, due_at + timedelta(minutes=1))
    assert next_snapshot is not None
    assert next_snapshot["configuration_revision"] == next_config["revision"]
    assert next_snapshot["duration_minutes"] == 240
    assert next_snapshot["due_at"] > due_at
    with factory() as session:
        first_round = session.get(AuthWorkflowSlaRound, snapshot["id"])
        assert first_round is not None and first_round.closed_at == due_at
        assert auth_sla.plan_sla_read_model(
            session,
            session.get(AuthWorkflowPlan, plan_id),
            [SimpleNamespace(version_number=1, round_number=1)],
            now=due_at,
        )[1][0]["status"] == "CLOSED_LATE"
        assert session.scalar(select(func.count(AuthWorkflowSlaRound.id)).where(
            AuthWorkflowSlaRound.plan_id == plan_id
        )) == 2
    with factory.begin() as session:
        auth_sla.close_round_snapshot(
            session,
            plan_id=plan_id,
            round_number=2,
            closed_at=next_snapshot["started_at"],
        )


def test_postgres_concurrent_config_writes_and_submit_capture_one_revision(sla_postgres):
    _, _, factory = sla_postgres
    people = _people(factory)
    admin = people["ADMIN"]
    initial = _set_config(factory, admin, enabled=True, duration=211, warning=31)
    plan_id = _plan(factory, people)
    started = datetime(2034, 1, 2, tzinfo=timezone.utc)

    # The submit transaction reads one revision, then a concurrent Admin commit
    # creates the next revision before the submit snapshot itself commits.
    with factory() as submit_session:
        with submit_session.begin():
            plan = submit_session.scalar(
                select(AuthWorkflowPlan).where(AuthWorkflowPlan.id == plan_id).with_for_update()
            )
            assert plan is not None
            captured = auth_sla.start_round_snapshot(submit_session, plan=plan, started_at=started)
            assert captured is not None
            assert captured.configuration_revision == initial["revision"]
            concurrent = _set_config(
                factory, admin, enabled=True, duration=223, warning=33
            )
            assert concurrent["revision"] == initial["revision"] + 1
        captured_id = captured.id

    with factory() as session:
        captured = session.get(AuthWorkflowSlaRound, captured_id)
        assert captured is not None
        assert captured.configuration_id == UUID(initial["id"])
        assert captured.configuration_revision == initial["revision"]
        assert (captured.duration_minutes, captured.warning_before_minutes) == (211, 31)
    with factory.begin() as session:
        auth_sla.close_round_snapshot(
            session, plan_id=plan_id, round_number=1, closed_at=started
        )

    with factory() as session:
        current = auth_sla.get_configuration(
            session, _principal(admin, "ADMIN", ("ADMIN_SLA_MANAGE",)), "concurrency-revision"
        )
    expected = current["revision"]
    gate = Barrier(3)

    def update(duration: int):
        principal = _principal(admin, "ADMIN", ("ADMIN_SLA_MANAGE",))
        with factory() as session:
            gate.wait(timeout=8)
            try:
                return auth_sla.update_configuration(
                    session,
                    principal,
                    enabled=True,
                    duration_minutes=duration,
                    warning_before_minutes=duration // 3,
                    expected_revision=expected,
                    change_reason="Concurrent PostgreSQL revision test.",
                    correlation_id=f"pg-config-race-{uuid4().hex[:8]}",
                )
            except ApplicationError as exc:
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(update, 257)
        second = executor.submit(update, 263)
        gate.wait(timeout=8)
        outcomes = [first.result(timeout=10), second.result(timeout=10)]
    assert sum(isinstance(item, dict) for item in outcomes) == 1
    assert outcomes.count("CONFLICT") == 1


def test_postgres_parallel_workers_are_idempotent_and_rollback_is_atomic(sla_postgres, monkeypatch):
    url, _, factory = sla_postgres
    people = _people(factory)
    _set_config(factory, people["ADMIN"], enabled=True, duration=181, warning=41)
    start = datetime(2037, 2, 3, tzinfo=timezone.utc)
    plan_id = _plan(factory, people)
    snapshot = _start_snapshot(factory, plan_id, start)
    assert snapshot is not None
    gate = Barrier(3)

    def run_worker():
        gate.wait(timeout=8)
        return auth_sla.process_due_sla_notifications(factory, now=snapshot["due_at"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(run_worker)
        second = executor.submit(run_worker)
        gate.wait(timeout=8)
        created = [first.result(timeout=15), second.result(timeout=15)]
    assert sum(created) == 2
    with factory() as session:
        notices = session.scalars(select(AuthWorkflowNotification).where(
            AuthWorkflowNotification.plan_id == plan_id
        )).all()
        assert len(notices) == 2
        assert {item.event_type for item in notices} == {"SLA_OVERDUE"}
        assert len({item.event_key for item in notices}) == 2
    with factory.begin() as session:
        auth_sla.close_round_snapshot(
            session, plan_id=plan_id, round_number=1, closed_at=snapshot["due_at"]
        )

    rollback_plan = _plan(factory, people)
    rollback_snapshot = _start_snapshot(factory, rollback_plan, start + timedelta(days=10))
    assert rollback_snapshot is not None
    original = auth_sla._record_sla_notification
    attempted = 0

    def fail_after_second_recipient(*args, **kwargs):
        nonlocal attempted
        result = original(*args, **kwargs)
        attempted += 1
        if attempted == 2:
            raise RuntimeError("synthetic failure after notification and audit inserts")
        return result

    monkeypatch.setattr(auth_sla, "_record_sla_notification", fail_after_second_recipient)
    with pytest.raises(RuntimeError, match="synthetic failure"):
        auth_sla.process_due_sla_notifications(factory, now=rollback_snapshot["due_at"])
    with factory() as session:
        assert session.scalar(select(func.count(AuthWorkflowNotification.id)).where(
            AuthWorkflowNotification.plan_id == rollback_plan
        )) == 0
        assert session.scalar(select(func.count(AuthWorkflowEvent.id)).where(
            AuthWorkflowEvent.plan_id == rollback_plan,
            AuthWorkflowEvent.action == "SLA_OVERDUE_SENT",
        )) == 0
    assert attempted == 2
    with factory.begin() as session:
        auth_sla.close_round_snapshot(
            session, plan_id=rollback_plan, round_number=1,
            closed_at=rollback_snapshot["started_at"],
        )


def test_postgres_decision_and_checker_reassignment_win_worker_lock_races(sla_postgres, monkeypatch):
    url, observer_engine, factory = sla_postgres
    people = _people(factory)
    _set_config(factory, people["ADMIN"], enabled=True, duration=120, warning=30)
    started = datetime.now(timezone.utc) - timedelta(minutes=121)
    checker = _principal(people["CHECKER"], "CHECKER", ("MARKETING_APPROVE",))

    decision_plan = _plan(factory, people)
    decision_snapshot = _start_snapshot(factory, decision_plan, started)
    assert decision_snapshot is not None
    decision_entered = Event()
    allow_decision_commit = Event()
    original_notification = auth_workflow._record_notification

    def pause_decision_before_commit(*args, **kwargs):
        result = original_notification(*args, **kwargs)
        if kwargs.get("event_type") == "PLAN_APPROVED":
            decision_entered.set()
            if not allow_decision_commit.wait(10):
                raise TimeoutError("decision test gate was not released")
        return result

    monkeypatch.setattr(auth_workflow, "_record_notification", pause_decision_before_commit)
    monkeypatch.setattr(
        auth_workflow, "_now_datetime", lambda: decision_snapshot["due_at"]
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        def decide():
            with factory() as session:
                return auth_workflow.decide_plan(
                    session,
                    checker,
                    decision_plan,
                    1,
                    "APPROVED",
                    None,
                    "Synthetic PostgreSQL SLA race override.",
                    "sla-decision-race",
                )

        decision_future = executor.submit(decide)
        assert decision_entered.wait(8)
        worker_application = f"sla-worker-decision-{uuid4().hex[:8]}"
        worker_engine = create_engine(url, connect_args={"application_name": worker_application})
        worker_factory = sessionmaker(worker_engine, expire_on_commit=False)
        worker_future = executor.submit(
            auth_sla.process_due_sla_notifications,
            worker_factory,
            now=decision_snapshot["due_at"],
        )
        blocked = _pg_lock_seen(observer_engine, worker_application)
        allow_decision_commit.set()
        decided = decision_future.result(timeout=12)
        worker_created = worker_future.result(timeout=12)
        worker_engine.dispose()
    assert blocked, "worker must be observed waiting on the plan lock held by the decision transaction"
    assert decided["status"] == "APPROVED"
    assert worker_created == 0
    with factory() as session:
        closed = session.get(AuthWorkflowSlaRound, decision_snapshot["id"])
        assert closed is not None and closed.closed_at == decision_snapshot["due_at"]
        assert session.scalar(select(func.count(AuthWorkflowDecision.id)).where(
            AuthWorkflowDecision.plan_id == decision_plan,
            AuthWorkflowDecision.round_number == 1,
        )) == 1
        assert session.scalar(select(func.count(AuthWorkflowNotification.id)).where(
            AuthWorkflowNotification.plan_id == decision_plan,
            AuthWorkflowNotification.event_type.in_(("SLA_WARNING", "SLA_OVERDUE")),
        )) == 0

    # Reassignment uses the same plan -> SLA-round order. Its transaction wins
    # the lock first, routes the overdue notice to the replacement, then commits.
    reassignment_plan = _plan(factory, people)
    reassignment_started = datetime.now(timezone.utc) - timedelta(minutes=121)
    reassignment_snapshot = _start_snapshot(factory, reassignment_plan, reassignment_started)
    assert reassignment_snapshot is not None
    old_profile = EmployeeProfile(
        user_code=people["CHECKER"].user_code,
        display_name=people["CHECKER"].display_name,
        email=people["CHECKER"].email,
        department="Synthetic test",
        job_title="Checker",
        user_id=people["CHECKER"].id,
        employment_status="ACTIVE",
    )
    next_profile = EmployeeProfile(
        user_code=people["NEXT"].user_code,
        display_name=people["NEXT"].display_name,
        email=people["NEXT"].email,
        department="Synthetic test",
        job_title="Checker",
        user_id=people["NEXT"].id,
        employment_status="ACTIVE",
    )
    with factory.begin() as session:
        session.add_all([old_profile, next_profile])
        plan = session.get(AuthWorkflowPlan, reassignment_plan)
        assert plan is not None
        plan.payload = {**plan.payload, "department": "Synthetic test"}
    with factory() as session:
        approval_configuration.create_configuration_revision(
            session,
            _principal(people["ADMIN"], "ADMIN", ("ADMIN_APPROVER_MANAGE",)),
            "sla-reassignment-default-checker",
            kind="checker_assignment",
            expected_revision=None,
            effective_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            change_reason="Synthetic PostgreSQL race-test default Checker.",
            value={
                "maker_may_select_other": False,
                "defaults": [{"department": "Synthetic test", "checker_id": str(people["NEXT"].id)}],
            },
        )
    reassignment_entered = Event()
    allow_reassignment_commit = Event()
    original_reassignment_notice = employee_admin.notify_reassigned_checker

    def pause_reassignment_before_commit(*args, **kwargs):
        result = original_reassignment_notice(*args, **kwargs)
        reassignment_entered.set()
        if not allow_reassignment_commit.wait(10):
            raise TimeoutError("reassignment test gate was not released")
        return result

    monkeypatch.setattr(employee_admin, "notify_reassigned_checker", pause_reassignment_before_commit)
    with ThreadPoolExecutor(max_workers=2) as executor:
        def deactivate_and_reassign():
            with factory() as session:
                return employee_admin.deactivate_employee(
                    session,
                    _principal(people["ADMIN"], "ADMIN"),
                    old_profile.id,
                    "sla-reassignment-race",
                    {},
                )

        reassignment_future = executor.submit(deactivate_and_reassign)
        assert reassignment_entered.wait(8)
        worker_application = f"sla-worker-reassign-{uuid4().hex[:8]}"
        worker_engine = create_engine(url, connect_args={"application_name": worker_application})
        worker_factory = sessionmaker(worker_engine, expire_on_commit=False)
        worker_future = executor.submit(
            auth_sla.process_due_sla_notifications,
            worker_factory,
            now=reassignment_snapshot["due_at"],
        )
        blocked = _pg_lock_seen(observer_engine, worker_application)
        allow_reassignment_commit.set()
        reassignment_future.result(timeout=12)
        worker_created = worker_future.result(timeout=12)
        worker_engine.dispose()
    assert blocked, "worker must wait for the in-flight reassignment row lock"
    assert worker_created == 0
    with factory() as session:
        plan = session.get(AuthWorkflowPlan, reassignment_plan)
        snapshot = session.get(AuthWorkflowSlaRound, reassignment_snapshot["id"])
        notices = session.scalars(select(AuthWorkflowNotification).where(
            AuthWorkflowNotification.plan_id == reassignment_plan,
            AuthWorkflowNotification.event_type == "SLA_OVERDUE",
        )).all()
        assert plan is not None and plan.checker_id == people["NEXT"].id
        assert snapshot is not None and snapshot.due_at == reassignment_snapshot["due_at"]
        assert {item.recipient_user_id for item in notices} == {
            people["MAKER"].id, people["NEXT"].id,
        }
        assert people["CHECKER"].id not in {item.recipient_user_id for item in notices}
    with factory.begin() as session:
        auth_sla.close_round_snapshot(
            session,
            plan_id=reassignment_plan,
            round_number=1,
            closed_at=reassignment_snapshot["due_at"],
        )


def test_postgres_migration_constraints_indexes_and_immutability_triggers(sla_postgres):
    _, engine, factory = sla_postgres
    inspector = inspect(engine)
    config_checks = {item["name"] for item in inspector.get_check_constraints("auth_workflow_sla_configurations")}
    round_checks = {item["name"] for item in inspector.get_check_constraints("auth_workflow_sla_rounds")}
    assert {
        "ck_auth_workflow_sla_configurations_revision",
        "ck_auth_workflow_sla_configurations_duration",
        "ck_auth_workflow_sla_configurations_warning",
    } <= config_checks
    assert {
        "ck_auth_workflow_sla_rounds_version",
        "ck_auth_workflow_sla_rounds_round",
        "ck_auth_workflow_sla_rounds_duration",
        "ck_auth_workflow_sla_rounds_warning",
        "ck_auth_workflow_sla_rounds_deadlines",
        "ck_auth_workflow_sla_rounds_closed_after_start",
    } <= round_checks
    assert any(item["column_names"] == ["revision"] for item in inspector.get_unique_constraints("auth_workflow_sla_configurations"))
    assert any(item["column_names"] == ["plan_id", "round_number"] for item in inspector.get_unique_constraints("auth_workflow_sla_rounds"))
    config_fks = {(tuple(item["constrained_columns"]), item["referred_table"]) for item in inspector.get_foreign_keys("auth_workflow_sla_configurations")}
    round_fks = {(tuple(item["constrained_columns"]), item["referred_table"]) for item in inspector.get_foreign_keys("auth_workflow_sla_rounds")}
    assert (("changed_by",), "users") in config_fks
    assert (("plan_id",), "auth_workflow_plans") in round_fks
    assert (("configuration_id",), "auth_workflow_sla_configurations") in round_fks
    indexes = {item["name"] for item in inspector.get_indexes("auth_workflow_sla_rounds")}
    assert {"ix_auth_workflow_sla_rounds_open_warning", "ix_auth_workflow_sla_rounds_open_due"} <= indexes
    with engine.connect() as connection:
        trigger_count = connection.scalar(text("""
            SELECT count(*) FROM pg_trigger
            WHERE NOT tgisinternal
              AND tgname IN (
                'trg_auth_workflow_sla_configurations_immutable',
                'trg_auth_workflow_sla_rounds_immutable'
              )
        """))
    assert trigger_count == 2

    people = _people(factory)
    config = _set_config(factory, people["ADMIN"], enabled=True, duration=97, warning=17)
    plan_id = _plan(factory, people)
    snapshot = _start_snapshot(factory, plan_id, datetime(2041, 1, 1, tzinfo=timezone.utc))
    assert snapshot is not None
    with pytest.raises(DBAPIError, match="SLA configuration revisions are immutable"):
        with engine.begin() as connection:
            connection.execute(text(
                "UPDATE auth_workflow_sla_configurations SET enabled = false WHERE id = :id"
            ), {"id": UUID(config["id"])})
    with pytest.raises(DBAPIError, match="SLA round snapshot fields are immutable"):
        with engine.begin() as connection:
            connection.execute(text(
                "UPDATE auth_workflow_sla_rounds SET duration_minutes = duration_minutes + 1 WHERE id = :id"
            ), {"id": snapshot["id"]})


def test_postgres_missing_and_disabled_configuration_do_not_start_a_round(sla_postgres):
    empty_url = os.environ.get("SLA_EMPTY_POSTGRES_TEST_URL", "").strip()
    assert empty_url.startswith("postgresql+psycopg://"), "Explicit empty, temporary PostgreSQL URL is required."
    empty_engine = create_engine(empty_url, pool_pre_ping=True)
    empty_factory = sessionmaker(empty_engine, expire_on_commit=False)
    try:
        people = _people(empty_factory)
        principal = _principal(people["ADMIN"], "ADMIN", ("ADMIN_SLA_MANAGE",))
        with empty_factory() as session:
            assert auth_sla.get_configuration(session, principal, "no-sla-config")["configured"] is False
        plan_id = _plan(empty_factory, people)
        assert _start_snapshot(empty_factory, plan_id, datetime(2042, 1, 1, tzinfo=timezone.utc)) is None
        with empty_factory.begin() as session:
            count = session.scalar(select(func.count(AuthWorkflowSlaRound.id)))
        assert count == 0

        with empty_factory() as session:
            disabled = auth_sla.update_configuration(
                session, principal, enabled=False, duration_minutes=1440,
                warning_before_minutes=240, expected_revision=0,
                change_reason="Synthetic disabled-only verification fixture.",
                correlation_id="disabled-only-sla-config",
            )
        assert disabled["enabled"] is False
        next_plan = _plan(empty_factory, people)
        assert _start_snapshot(empty_factory, next_plan, datetime(2042, 1, 2, tzinfo=timezone.utc)) is None
        with empty_factory() as session:
            assert session.scalar(select(func.count(AuthWorkflowSlaRound.id))) == 0
            assert session.scalar(select(func.count(AuthWorkflowSlaConfiguration.id))) == 1
    finally:
        empty_engine.dispose()
