"""PostgreSQL migration helpers used only by the isolated notification runner."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from uuid import NAMESPACE_URL, uuid5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

from src.backend.db.models import (
    AuthWorkflowEvent,
    AuthWorkflowNotification,
    AuthWorkflowPlan,
    AuthWorkflowVersion,
    Role,
    User,
    UserRole,
)

EXPECTED_HEAD = "20261011_11"
LEGACY_HEAD = "20261010_10"
NOTIFICATION_TABLE = "auth_workflow_notifications"


def _run_id() -> str:
    run_id = os.environ.get("NOTIFICATION_VERIFICATION_RUN_ID", "").strip()
    if len(run_id) != 32 or any(char not in "0123456789abcdef" for char in run_id.lower()):
        raise RuntimeError("The notification runner must provide its unique synthetic run id.")
    return run_id.lower()


def _revision(session: Session) -> str:
    return session.scalar(text("SELECT version_num FROM alembic_version"))


def _verify_schema(engine, *, empty: bool) -> dict:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert NOTIFICATION_TABLE in tables
    columns = {column["name"]: column for column in inspector.get_columns(NOTIFICATION_TABLE)}
    required_columns = {
        "id", "recipient_user_id", "plan_id", "event_key", "event_type",
        "title", "message", "version_number", "round_number", "read_at", "created_at",
    }
    assert required_columns <= set(columns)
    assert columns["recipient_user_id"]["nullable"] is False
    assert columns["plan_id"]["nullable"] is False
    assert columns["event_key"]["nullable"] is False

    foreign_keys = inspector.get_foreign_keys(NOTIFICATION_TABLE)
    foreign_key_map = {
        tuple(item["constrained_columns"]): (item["referred_table"], tuple(item["referred_columns"]),
                                              (item.get("options") or {}).get("ondelete"))
        for item in foreign_keys
    }
    assert foreign_key_map[("recipient_user_id",)] == ("users", ("id",), "RESTRICT")
    assert foreign_key_map[("plan_id",)] == ("auth_workflow_plans", ("id",), "RESTRICT")

    indexes = {item["name"]: item for item in inspector.get_indexes(NOTIFICATION_TABLE)}
    assert indexes["ix_auth_workflow_notifications_recipient_created"]["column_names"] == [
        "recipient_user_id", "created_at",
    ]
    assert indexes["ix_auth_workflow_notifications_recipient_unread"]["column_names"] == [
        "recipient_user_id", "read_at",
    ]
    unique_constraints = {item["name"]: item for item in inspector.get_unique_constraints(NOTIFICATION_TABLE)}
    assert unique_constraints["uq_auth_workflow_notifications_event_key"]["column_names"] == ["event_key"]
    checks = {item["name"]: item["sqltext"] for item in inspector.get_check_constraints(NOTIFICATION_TABLE)}
    assert "ck_auth_workflow_notifications_event_type" in checks
    assert all(event in checks["ck_auth_workflow_notifications_event_type"] for event in (
        "PLAN_SUBMITTED", "PLAN_APPROVED", "PLAN_AUTO_APPROVED", "PLAN_REJECTED",
    ))

    with engine.connect() as connection:
        revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        user_count = connection.scalar(text("SELECT count(*) FROM users"))
        plan_count = connection.scalar(text("SELECT count(*) FROM auth_workflow_plans"))
        notification_count = connection.scalar(text(f"SELECT count(*) FROM {NOTIFICATION_TABLE}"))
        postgres_version = connection.scalar(text("SHOW server_version"))
    assert revision == EXPECTED_HEAD, revision
    if empty:
        assert user_count == plan_count == notification_count == 0
    return {
        "status": "PASS",
        "revision": revision,
        "table": NOTIFICATION_TABLE,
        "columns": sorted(required_columns),
        "foreign_keys": [
            {"columns": list(columns), "target": value[0], "target_columns": list(value[1]), "ondelete": value[2]}
            for columns, value in sorted(foreign_key_map.items())
        ],
        "indexes": sorted(indexes),
        "unique_constraints": sorted(unique_constraints),
        "check_constraints": sorted(checks),
        "users": user_count,
        "plans": plan_count,
        "notifications": notification_count,
        "postgres_version": postgres_version,
    }


def _synthetic_state(factory: sessionmaker[Session], run_id: str) -> dict:
    marker = run_id[:10].upper()
    maker_id = uuid5(NAMESPACE_URL, f"organizationai:{run_id}:maker")
    checker_id = uuid5(NAMESPACE_URL, f"organizationai:{run_id}:checker")
    plan_id = uuid5(NAMESPACE_URL, f"organizationai:{run_id}:plan")
    with factory() as session:
        users = session.scalars(select(User).where(User.id.in_((maker_id, checker_id))).order_by(User.user_code)).all()
        assignments = session.execute(
            select(User.user_code, Role.code)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(User.id.in_((maker_id, checker_id)))
            .order_by(User.user_code, Role.code)
        ).all()
        plan = session.get(AuthWorkflowPlan, plan_id)
        versions = session.scalars(
            select(AuthWorkflowVersion).where(AuthWorkflowVersion.plan_id == plan_id)
            .order_by(AuthWorkflowVersion.version_number)
        ).all()
        events = session.scalars(
            select(AuthWorkflowEvent).where(AuthWorkflowEvent.plan_id == plan_id)
            .order_by(AuthWorkflowEvent.sequence_number)
        ).all()
        return {
            "users": [{
                "id": str(user.id), "user_code": user.user_code, "username": user.username,
                "email": user.email, "display_name": user.display_name,
                "status": user.status, "employment_status": user.employment_status,
            } for user in users],
            "role_assignments": [list(row) for row in assignments],
            "plan": None if plan is None else {
                "id": str(plan.id), "code": plan.code, "maker_id": str(plan.maker_id),
                "checker_id": str(plan.checker_id), "payload": plan.payload,
                "status": plan.status, "processing_stage": plan.processing_stage,
                "current_version": plan.current_version, "current_round": plan.current_round,
                "revision": plan.revision,
            },
            "versions": [{
                "id": str(item.id), "version": item.version_number, "round": item.round_number,
                "payload": item.payload_snapshot, "attachments": item.attachment_snapshot,
                "snapshot_hash": item.snapshot_hash, "submitted_by": str(item.submitted_by),
            } for item in versions],
            "events": [{
                "id": str(item.id), "sequence": item.sequence_number, "action": item.action,
                "status_before": item.status_before, "status_after": item.status_after,
                "details": item.details,
            } for item in events],
        }


def _seed_revision_10(engine, factory, run_id: str) -> dict:
    marker = run_id[:10].upper()
    maker_id = uuid5(NAMESPACE_URL, f"organizationai:{run_id}:maker")
    checker_id = uuid5(NAMESPACE_URL, f"organizationai:{run_id}:checker")
    plan_id = uuid5(NAMESPACE_URL, f"organizationai:{run_id}:plan")
    version_id = uuid5(NAMESPACE_URL, f"organizationai:{run_id}:version")
    event_id = uuid5(NAMESPACE_URL, f"organizationai:{run_id}:event")
    payload = {
        "title": f"Synthetic revision 10 preservation {marker}",
        "objective": "Synthetic fixture created at revision 20261010_10.",
        "summary": "Existing data must remain unchanged after the notification migration.",
        "department": "marketing",
    }
    with factory.begin() as session:
        assert _revision(session) == LEGACY_HEAD
        assert NOTIFICATION_TABLE not in inspect(engine).get_table_names()
        roles = {item.code: item for item in session.scalars(select(Role).where(Role.code.in_(("MAKER", "CHECKER"))))}
        assert set(roles) == {"MAKER", "CHECKER"}
        for user_id, role, name in (
            (maker_id, roles["MAKER"], "Synthetic legacy Maker"),
            (checker_id, roles["CHECKER"], "Synthetic legacy Checker"),
        ):
            user = User(
                id=user_id,
                user_code=f"PG{marker}{'M' if role.code == 'MAKER' else 'C'}",
                username=f"pg_{run_id[:10]}_{role.code.lower()}",
                email=f"pg_{run_id[:10]}_{role.code.lower()}@example.invalid",
                phone=None,
                password_hash="synthetic-not-authenticated",
                display_name=name,
                status="ACTIVE",
            )
            session.add(user)
            session.flush()
            session.add(UserRole(user_id=user_id, role_id=role.id))
        session.add(AuthWorkflowPlan(
            id=plan_id,
            code=f"PG-LEGACY-{marker}",
            maker_id=maker_id,
            checker_id=checker_id,
            payload=payload,
            creation_idempotency_key=f"synthetic:{run_id}",
            creation_request_hash=hashlib.sha256(run_id.encode()).hexdigest(),
            status="PENDING_APPROVAL",
            processing_stage="HUMAN_REVIEW_REQUIRED",
            current_version=1,
            current_round=1,
            revision=1,
        ))
        session.flush()
        session.add(AuthWorkflowVersion(
            id=version_id,
            plan_id=plan_id,
            version_number=1,
            round_number=1,
            payload_snapshot=payload,
            attachment_snapshot=[],
            snapshot_hash=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
            submitted_by=maker_id,
        ))
        session.flush()
        session.add(AuthWorkflowEvent(
            id=event_id,
            plan_id=plan_id,
            actor_id=maker_id,
            actor_type="HUMAN",
            sequence_number=1,
            action="SUBMITTED",
            status_before="DRAFT",
            status_after="PENDING_APPROVAL",
            details={"version": 1, "round": 1, "synthetic": True},
        ))
    state = _synthetic_state(factory, run_id)
    assert len(state["users"]) == 2 and state["plan"] is not None
    assert len(state["versions"]) == len(state["events"]) == 1
    return {"status": "PASS", "revision": LEGACY_HEAD, "preserved_state": state}


def _verify_revision_11(engine, factory, run_id: str) -> dict:
    schema = _verify_schema(engine, empty=False)
    state = _synthetic_state(factory, run_id)
    assert len(state["users"]) == 2 and state["plan"] is not None
    assert len(state["versions"]) == len(state["events"]) == 1
    assert schema["notifications"] == 0
    return {
        **schema,
        "preserved_state": state,
        "preserved_records": ["users", "user_roles", "auth_workflow_plans", "auth_workflow_versions", "auth_workflow_events"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("verify-empty", "seed-revision-10", "verify-revision-11"))
    args = parser.parse_args()
    from scripts.postgres_test_target import verify_runner_provisioned_database

    database_url = verify_runner_provisioned_database(os.environ)
    engine = create_engine(database_url, pool_pre_ping=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    try:
        if args.mode == "verify-empty":
            result = _verify_schema(engine, empty=True)
        elif args.mode == "seed-revision-10":
            result = _seed_revision_10(engine, factory, _run_id())
        else:
            result = _verify_revision_11(engine, factory, _run_id())
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
