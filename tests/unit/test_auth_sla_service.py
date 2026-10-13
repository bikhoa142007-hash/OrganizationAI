from datetime import datetime, timedelta, timezone

from uuid import uuid4



import pytest

from sqlalchemy import create_engine, func, select

from sqlalchemy.orm import sessionmaker

from sqlalchemy.pool import StaticPool



from src.backend.api.auth import AuthenticatedPrincipal

from src.backend.application import auth_sla

from src.backend.application.workflow import ApplicationError

from src.backend.db.base import Base

from src.backend.db.models import (

    AdminAuditEvent,

    AuthWorkflowEvent,

    AuthWorkflowNotification,

    AuthWorkflowPlan,

    AuthWorkflowSlaConfiguration,

    AuthWorkflowSlaRound,

    AuthWorkflowVersion,

    User,

)





@pytest.fixture



def db_factory():

    engine = create_engine(

        "sqlite://",

        connect_args={"check_same_thread": False},

        poolclass=StaticPool,

    )

    tables = [

        User.__table__,

        AuthWorkflowPlan.__table__,

        AuthWorkflowVersion.__table__,

        AuthWorkflowSlaConfiguration.__table__,

        AuthWorkflowSlaRound.__table__,

        AuthWorkflowEvent.__table__,

        AuthWorkflowNotification.__table__,

        AdminAuditEvent.__table__,

    ]

    Base.metadata.create_all(engine, tables=tables)

    factory = sessionmaker(bind=engine, expire_on_commit=False)

    yield factory

    engine.dispose()





def _user(code: str) -> User:

    return User(

        id=uuid4(),

        user_code=code,

        username=code.lower(),

        email=f"{code.lower()}@example.test",

        phone=None,

        password_hash="not-a-real-secret",

        display_name=code,

        status="ACTIVE",

        employment_status="ACTIVE",

        activation_pending=False,

    )





def _principal(user: User, *, roles=("ADMIN",), permissions=("ADMIN_SLA_MANAGE",)):

    return AuthenticatedPrincipal(

        id=user.id,

        user_code=user.user_code,

        username=user.username,

        email=user.email,

        phone=user.phone,

        display_name=user.display_name,

        status=user.status,

        roles=roles,

        permissions=permissions,

    )





def _seed_enabled_config(session, admin: User, duration=120, warning=30):

    configuration = AuthWorkflowSlaConfiguration(

        id=uuid4(),

        revision=1,

        enabled=True,

        duration_minutes=duration,

        warning_before_minutes=warning,

        changed_by=admin.id,

        change_reason="Enable for the unit-test scenario",

    )

    session.add(configuration)

    return configuration





def _seed_round(session, admin: User, *, started_at: datetime, maker: User, checker: User):

    _seed_enabled_config(session, admin)

    plan = AuthWorkflowPlan(

        id=uuid4(),

        code=f"MKT-{uuid4().hex[:8]}",

        maker_id=maker.id,

        checker_id=checker.id,

        payload={"title": "SLA test plan"},

        status="PENDING_APPROVAL",

        processing_stage="HUMAN_REVIEW_REQUIRED",

        current_version=1,

        current_round=1,

        revision=1,

    )

    version = AuthWorkflowVersion(

        id=uuid4(),

        plan_id=plan.id,

        version_number=1,

        round_number=1,

        payload_snapshot={"title": "SLA test plan"},

        attachment_snapshot=[],

        snapshot_hash="a" * 64,

        submitted_by=maker.id,

    )

    session.add_all([plan, version])

    session.flush()

    snapshot = auth_sla.start_round_snapshot(

        session,

        plan=plan,

        started_at=started_at,

        correlation_id="test-submit",

    )

    session.flush()

    assert snapshot is not None

    return plan, version, snapshot





def test_configuration_starts_unconfigured_and_is_revisioned_with_audit(db_factory):

    admin = _user("ADMIN-1")

    with db_factory() as session:

        session.add(admin)

        session.commit()

        principal = _principal(admin)



        assert auth_sla.get_configuration(session, principal, "read") == {

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

        assert session.scalar(select(func.count(AuthWorkflowSlaConfiguration.id))) == 0



        first = auth_sla.update_configuration(

            session, principal, enabled=False, duration_minutes=24 * 60,

            warning_before_minutes=4 * 60, expected_revision=0,

            change_reason="First explicit configuration", correlation_id="update-1",

        )

        second = auth_sla.update_configuration(

            session, principal, enabled=True, duration_minutes=12 * 60,

            warning_before_minutes=2 * 60, expected_revision=1,

            change_reason="Enable the approved setting", correlation_id="update-2",

        )



        assert first["revision"] == 1

        assert first["enabled"] is False

        assert second["revision"] == 2

        assert second["enabled"] is True

        assert session.scalar(select(func.count(AuthWorkflowSlaConfiguration.id))) == 2

        assert session.scalar(select(func.count(AdminAuditEvent.id))) == 2



        with pytest.raises(ApplicationError) as stale:

            auth_sla.update_configuration(

                session, principal, enabled=False, duration_minutes=60,

                warning_before_minutes=15, expected_revision=1,

                change_reason="Stale write", correlation_id="stale-write",

            )

        assert stale.value.code == "CONFLICT"





def test_configuration_requires_both_admin_role_and_existing_permission(db_factory):

    admin = _user("ADMIN-2")

    with db_factory() as session:

        session.add(admin)

        session.commit()

        unauthorized = _principal(admin, permissions=())

        with pytest.raises(ApplicationError) as failure:

            auth_sla.get_configuration(session, unauthorized, "forbidden")

    assert failure.value.code == "FORBIDDEN"





def test_enabled_round_snapshots_are_immutable_and_read_model_is_read_only(db_factory):

    admin, maker, checker = _user("ADMIN-3"), _user("MAKER-3"), _user("CHECKER-3")

    started = datetime(2026, 10, 11, 10, tzinfo=timezone.utc)

    with db_factory() as session:

        session.add_all([admin, maker, checker])

        session.flush()

        plan, version, snapshot = _seed_round(

            session, admin, started_at=started, maker=maker, checker=checker

        )

        session.commit()



        assert snapshot.configuration_revision == 1

        assert snapshot.warning_at == started + timedelta(minutes=90)

        assert snapshot.due_at == started + timedelta(minutes=120)

        round_count = session.scalar(select(func.count(AuthWorkflowSlaRound.id)))

        current, history = auth_sla.plan_sla_read_model(

            session, plan, [version], now=started + timedelta(minutes=90)

        )

        assert current["status"] == "WARNING"

        assert history[0]["round_number"] == 1

        assert session.scalar(select(func.count(AuthWorkflowSlaRound.id))) == round_count



        close_time = snapshot.due_at + timedelta(seconds=1)

        auth_sla.close_round_snapshot(

            session, plan_id=plan.id, round_number=1, closed_at=close_time

        )

        auth_sla.close_round_snapshot(

            session, plan_id=plan.id, round_number=1,

            closed_at=close_time + timedelta(minutes=1),

        )

        session.flush()

        assert snapshot.closed_at == close_time

        closed, _ = auth_sla.plan_sla_read_model(

            session, plan, [version], now=close_time + timedelta(hours=1)

        )

        assert closed["status"] == "CLOSED_LATE"
        session.commit()
        assert auth_sla.process_due_sla_notifications(
            db_factory, now=close_time + timedelta(hours=2), batch_size=10
        ) == 0





def test_disabled_sla_does_not_create_snapshot(db_factory):

    admin, maker, checker = _user("ADMIN-4"), _user("MAKER-4"), _user("CHECKER-4")

    with db_factory() as session:

        session.add_all([admin, maker, checker])

        session.flush()

        session.add(AuthWorkflowSlaConfiguration(

            id=uuid4(), revision=1, enabled=False, duration_minutes=1440,

            warning_before_minutes=240, changed_by=admin.id, change_reason="Disabled",

        ))

        plan = AuthWorkflowPlan(

            id=uuid4(), code="MKT-DISABLED", maker_id=maker.id, checker_id=checker.id,

            payload={}, status="PENDING_APPROVAL", processing_stage="AI_PENDING",

            current_version=1, current_round=1, revision=1,

        )

        session.add(plan)

        session.flush()

        assert auth_sla.start_round_snapshot(

            session, plan=plan, started_at=datetime.now(timezone.utc),

            correlation_id="disabled-submit",

        ) is None

        assert session.scalar(select(func.count(AuthWorkflowSlaRound.id))) == 0





def test_warning_and_overdue_notifications_are_recipient_scoped_and_idempotent(db_factory):

    admin, maker, checker = _user("ADMIN-5"), _user("MAKER-5"), _user("CHECKER-5")

    started = datetime(2026, 10, 11, 8, tzinfo=timezone.utc)

    with db_factory() as session:

        session.add_all([admin, maker, checker])

        session.flush()

        plan, _, snapshot = _seed_round(

            session, admin, started_at=started, maker=maker, checker=checker

        )

        session.commit()



    warning_at = snapshot.warning_at

    assert auth_sla.process_due_sla_notifications(

        db_factory, now=warning_at, batch_size=10

    ) == 1

    with db_factory() as session:

        notices = session.scalars(select(AuthWorkflowNotification)).all()

        assert [(item.event_type, item.recipient_user_id) for item in notices] == [

            ("SLA_WARNING", checker.id)

        ]



    assert auth_sla.process_due_sla_notifications(

        db_factory, now=warning_at + timedelta(minutes=1), batch_size=10

    ) == 0

    assert auth_sla.process_due_sla_notifications(

        db_factory, now=snapshot.due_at, batch_size=10

    ) == 2

    assert auth_sla.process_due_sla_notifications(

        db_factory, now=snapshot.due_at + timedelta(minutes=1), batch_size=10

    ) == 0



    with db_factory() as session:

        notices = session.scalars(

            select(AuthWorkflowNotification).where(AuthWorkflowNotification.plan_id == plan.id)

        ).all()

        assert {(item.event_type, item.recipient_user_id) for item in notices} == {

            ("SLA_WARNING", checker.id), ("SLA_OVERDUE", maker.id), ("SLA_OVERDUE", checker.id),

        }

        assert session.scalar(select(func.count(AuthWorkflowEvent.id))) == 3





def test_reassigned_checker_gets_immediate_warning_or_overdue_notice(db_factory):

    admin, maker, checker, replacement = (

        _user("ADMIN-6"), _user("MAKER-6"), _user("CHECKER-6"), _user("CHECKER-6B")

    )

    started = datetime(2026, 10, 11, 8, tzinfo=timezone.utc)

    with db_factory() as session:

        session.add_all([admin, maker, checker, replacement])

        session.flush()

        plan, _, snapshot = _seed_round(

            session, admin, started_at=started, maker=maker, checker=checker

        )

        plan.checker_id = replacement.id

        count = auth_sla.notify_reassigned_checker(

            session, plan=plan, now=snapshot.warning_at

        )

        assert count == 1

        plan.checker_id = checker.id

        overdue_count = auth_sla.notify_reassigned_checker(

            session, plan=plan, now=snapshot.due_at

        )

        assert overdue_count == 2

        session.commit()



        notices = session.scalars(

            select(AuthWorkflowNotification).where(AuthWorkflowNotification.plan_id == plan.id)

        ).all()

        assert {(item.event_type, item.recipient_user_id) for item in notices} == {

            ("SLA_WARNING", replacement.id), ("SLA_OVERDUE", maker.id), ("SLA_OVERDUE", checker.id),

        }

def test_stale_warning_scan_is_suppressed_after_overdue_notification(db_factory):
    admin, maker, checker = _user("ADMIN-8"), _user("MAKER-8"), _user("CHECKER-8")
    started = datetime(2026, 10, 11, 8, tzinfo=timezone.utc)
    with db_factory() as session:
        session.add_all([admin, maker, checker])
        session.flush()
        plan, _, snapshot = _seed_round(
            session, admin, started_at=started, maker=maker, checker=checker
        )
        session.commit()

    assert auth_sla.process_due_sla_notifications(
        db_factory, now=snapshot.due_at, batch_size=10
    ) == 2
    # A delayed scan from before the deadline must not emit a late warning
    # after the overdue notification transaction has already committed.
    assert auth_sla.process_due_sla_notifications(
        db_factory, now=snapshot.warning_at, batch_size=10
    ) == 0

    with db_factory() as session:
        notices = session.scalars(
            select(AuthWorkflowNotification).where(
                AuthWorkflowNotification.plan_id == plan.id
            )
        ).all()
        assert {(item.event_type, item.recipient_user_id) for item in notices} == {
            ("SLA_OVERDUE", maker.id), ("SLA_OVERDUE", checker.id),
        }
        events = session.scalars(
            select(AuthWorkflowEvent).where(AuthWorkflowEvent.plan_id == plan.id)
        ).all()
        assert [event.action for event in events] == [
            "SLA_OVERDUE_SENT", "SLA_OVERDUE_SENT",
        ]

def test_first_worker_scan_after_deadline_skips_warning_and_catches_up_overdue(db_factory):
    admin, maker, checker = _user("ADMIN-7"), _user("MAKER-7"), _user("CHECKER-7")
    started = datetime(2026, 10, 11, 8, tzinfo=timezone.utc)
    with db_factory() as session:
        session.add_all([admin, maker, checker])
        session.flush()
        plan, _, snapshot = _seed_round(
            session, admin, started_at=started, maker=maker, checker=checker
        )
        session.commit()

    assert auth_sla.process_due_sla_notifications(
        db_factory, now=snapshot.due_at, batch_size=10
    ) == 2
    with db_factory() as session:
        notices = session.scalars(
            select(AuthWorkflowNotification).where(AuthWorkflowNotification.plan_id == plan.id)
        ).all()
    assert {(item.event_type, item.recipient_user_id) for item in notices} == {
        ("SLA_OVERDUE", maker.id), ("SLA_OVERDUE", checker.id),
    }
