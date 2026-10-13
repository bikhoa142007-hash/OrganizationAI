from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from src.backend.application import approval_configuration
from src.backend.db.models.approval_configuration import (
    AuthWorkflowConfigurationRevision,
    AuthWorkflowRoundConfigurationSnapshot,
)
from src.backend.db.models.auth_workflow import AuthWorkflowPlan
from src.backend.db.models.employee import EmployeeProfile
from src.backend.db.models.role import Role, UserRole
from src.backend.db.models.user import User
from src.backend.application.workflow import ApplicationError


def _person(factory, role: str, label: str) -> tuple[UUID, UUID]:
    suffix = uuid4().hex[:12]
    with factory.begin() as session:
        user = User(
            user_code=f"CFG-{label}-{suffix}",
            username=f"cfg_{label.lower()}_{suffix}",
            email=f"cfg_{label.lower()}_{suffix}@example.test",
            password_hash="synthetic-test-only",
            display_name=f"Synthetic {label}",
            status="ACTIVE",
            employment_status="ACTIVE",
        )
        session.add(user)
        session.flush()
        profile = EmployeeProfile(
            user_code=user.user_code,
            display_name=user.display_name,
            email=user.email,
            department="Marketing",
            employment_status="ACTIVE",
            user_id=user.id,
        )
        session.add(profile)
        session.add(UserRole(
            user_id=user.id,
            role_id=session.scalar(select(Role.id).where(Role.code == role)),
        ))
        return profile.id, user.id


def _create_revision(factory, principal, *, kind, expected_revision, effective_at, value):
    with factory() as session:
        return approval_configuration.create_configuration_revision(
            session,
            principal,
            "synthetic-configuration-test",
            kind=kind,
            expected_revision=expected_revision,
            effective_at=effective_at,
            change_reason="Synthetic fixture for configuration contract tests.",
            value=value,
        )


def test_new_effective_config_only_changes_new_round_snapshot_and_retry_reuses_old(admin_db):
    factory, admin = admin_db
    maker_profile_id, maker_id = _person(factory, "MAKER", "Maker")
    checker_profile_id, checker_id = _person(factory, "CHECKER", "Checker")
    del maker_profile_id, checker_profile_id
    now = datetime.now(timezone.utc)
    effective_v1 = now - timedelta(minutes=5)
    effective_v2 = now + timedelta(days=1)

    _create_revision(
        factory,
        admin,
        kind="checker_assignment",
        expected_revision=None,
        effective_at=effective_v1,
        value={"maker_may_select_other": False, "defaults": [{"department": "Marketing", "checker_id": str(checker_id)}]},
    )
    first_budget = _create_revision(
        factory,
        admin,
        kind="budget",
        expected_revision=None,
        effective_at=effective_v1,
        value={"currency": "VND", "limits": [{"department": "Marketing", "limit_minor_units": "1000000", "active": True}]},
    )

    with factory.begin() as session:
        plan = AuthWorkflowPlan(
            code=f"CFG-PLAN-{uuid4().hex[:10]}",
            maker_id=maker_id,
            checker_id=checker_id,
            payload={"department": "Marketing"},
            status="PENDING_APPROVAL",
            current_version=1,
            current_round=1,
        )
        session.add(plan)
        session.flush()
        plan_id = plan.id
        snapshot_v1 = approval_configuration.capture_round_configuration_snapshot(
            session,
            plan_id=plan.id,
            plan_version=1,
            approval_round=1,
            department_id="Marketing",
            maker_id=maker_id,
            selected_checker_id=checker_id,
            effective_at=effective_v1,
        )
        exported = snapshot_v1.as_dict()
        exported["configurations"]["budget"]["value"]["limits"][0]["limit_minor_units"] = "0"
        assert snapshot_v1.configurations["budget"]["value"]["limits"][0]["limit_minor_units"] == "1000000"

    second_budget = _create_revision(
        factory,
        admin,
        kind="budget",
        expected_revision=1,
        effective_at=effective_v2,
        value={"currency": "VND", "limits": [{"department": "Marketing", "limit_minor_units": "2000000", "active": True}]},
    )
    assert first_budget["revision"] == 1
    assert second_budget["revision"] == 2

    with factory.begin() as session:
        retry_snapshot = approval_configuration.capture_round_configuration_snapshot(
            session,
            plan_id=plan_id,
            plan_version=1,
            approval_round=1,
            department_id="Marketing",
            maker_id=maker_id,
            selected_checker_id=checker_id,
            effective_at=effective_v2,
        )
        assert retry_snapshot.snapshot_hash == snapshot_v1.snapshot_hash
        assert retry_snapshot.configurations["budget"]["revision"] == 1
        assert retry_snapshot.checker_assignment["checker_id"] == str(checker_id)

        snapshot_v2 = approval_configuration.capture_round_configuration_snapshot(
            session,
            plan_id=plan_id,
            plan_version=2,
            approval_round=2,
            department_id="Marketing",
            maker_id=maker_id,
            selected_checker_id=checker_id,
            effective_at=effective_v2,
        )
        assert snapshot_v2.configurations["budget"]["revision"] == 2
        assert snapshot_v2.snapshot_hash != snapshot_v1.snapshot_hash

    with factory() as session:
        loaded = approval_configuration.get_round_configuration_snapshot(
            session, plan_id=plan_id, approval_round=1,
        )
        assert loaded is not None and loaded.snapshot_hash == snapshot_v1.snapshot_hash
        assert session.scalar(select(AuthWorkflowRoundConfigurationSnapshot.id).where(
            AuthWorkflowRoundConfigurationSnapshot.plan_id == plan_id,
            AuthWorkflowRoundConfigurationSnapshot.approval_round == 1,
        )) is not None


def test_stale_expected_revision_conflicts_without_overwriting_history(admin_db):
    factory, admin = admin_db
    effective = datetime.now(timezone.utc)
    budget = {"currency": "VND", "limits": []}
    first = _create_revision(factory, admin, kind="budget", expected_revision=None, effective_at=effective, value=budget)

    with factory() as session:
        with pytest.raises(ApplicationError, match="revision changed") as error:
            approval_configuration.create_configuration_revision(
                session,
                admin,
                "stale-config-write",
                kind="budget",
                expected_revision=None,
                effective_at=effective + timedelta(seconds=1),
                change_reason="A stale synthetic write.",
                value=budget,
            )
        assert error.value.code == "CONFLICT"

    with factory() as session:
        history = approval_configuration.configuration_history(session, "budget")
        assert history["total"] == 1
        assert history["items"][0]["revision_id"] == first["revision_id"]
        assert history["items"][0]["status"] == "DISABLED"


def test_configuration_revision_orm_update_is_rejected(admin_db):
    factory, admin = admin_db
    created = _create_revision(
        factory,
        admin,
        kind="budget",
        expected_revision=None,
        effective_at=datetime.now(timezone.utc),
        value={"currency": "VND", "limits": []},
    )
    with factory() as session:
        row = session.scalar(select(AuthWorkflowConfigurationRevision).where(
            AuthWorkflowConfigurationRevision.id == UUID(created["revision_id"]),
        ))
        assert row is not None
        row.change_reason = "attempted overwrite"
        with pytest.raises(ValueError, match="immutable"):
            session.flush()


def test_round_snapshot_is_mapped_to_the_immutable_evaluator_and_policy_configuration():
    from src.backend.application.approval_configuration import (
        RoundConfigurationSnapshot,
        apply_round_configuration_snapshot,
        canonical_configuration_hash,
    )
    from src.backend.domain.policy import (
        ApprovalConfiguration,
        AuthoritySnapshot,
        BudgetConfiguration,
        Criterion,
        MANDATORY_FIELDS,
        PolicySnapshot,
        STRATEGY_CRITERIA,
        StrategyCriterion,
        StrategyRubric,
    )

    media_value = {
        "policy_id": "SNAPSHOT-MEDIA",
        "policy_version": "media-r4",
        "status": "ACTIVE",
        "scope_departments": ["Marketing"],
        "scope_channels": ["social"],
        "rules": [{
            "rule_id": "LOGO-CHECK",
            "severity": "WARNING",
            "description": "Check the logo placement.",
            "required_evidence_kinds": ["OBSERVATION"],
            "forbidden_literals": [],
        }],
    }
    rubric_value = {
        "rubric_id": "SNAPSHOT-STRATEGY",
        "rubric_version": "strategy-r5",
        "status": "ACTIVE",
        "criteria": [
            {"criterion_id": key, "label": label, "weight": weight}
            for key, label, weight in STRATEGY_CRITERIA
        ],
    }
    approval_value = {
        "enabled": False,
        "media_confidence_threshold": 0.9,
        "feasibility_score_threshold_exclusive": 75,
        "feasibility_confidence_threshold": 0.85,
    }
    budget_value = {
        "currency": "VND",
        "limits": [{
            "department": "Marketing", "limit_minor_units": "75000000", "active": True,
        }],
    }
    authority_value = {
        "currency": "VND", "auto_limit_minor_units": "70000000",
        "allowed_departments": ["Marketing"], "checker_id": None,
        "policy_owner_id": None, "budget_authority_id": None, "active": True,
    }
    checker_id = uuid4()
    values = {
        "approval_policy": ("DISABLED", approval_value),
        "budget": ("EFFECTIVE", budget_value),
        "media_policy": ("EFFECTIVE", media_value),
        "strategy_rubric": ("EFFECTIVE", rubric_value),
        "authority": ("EFFECTIVE", authority_value),
        "checker_assignment": ("UNCONFIGURED", None),
    }
    resolutions = {}
    for kind, (status, value) in values.items():
        revision_id = str(uuid4()) if value is not None else None
        resolutions[kind] = {
            "kind": kind, "status": status,
            "revision_id": revision_id, "revision": 4 if value is not None else None,
            "effective_at": "2026-10-12T12:00:00.000000Z" if value is not None else None,
            "configuration_hash": canonical_configuration_hash(value) if value is not None else None,
            "value": value,
        }
    round_snapshot = RoundConfigurationSnapshot(
        plan_id=uuid4(), plan_version=1, approval_round=1,
        effective_at=datetime.now(timezone.utc), configurations=resolutions,
        checker_assignment={"checker_id": str(checker_id), "eligible": True},
        snapshot_hash="synthetic-snapshot-hash", snapshot_id=uuid4(),
    )
    base = ApprovalConfiguration(
        policy=PolicySnapshot(
            "BASE-POLICY", "base-1", True, MANDATORY_FIELDS,
            tuple(Criterion(key, weight) for key, _label, weight in STRATEGY_CRITERIA),
            ("visual-model-rev-1",), ("image/png",), 5_000_000,
        ),
        budgets=(BudgetConfiguration("BASE-BUDGET", "VND", 0, "100000000", "Marketing", True),),
        authority=AuthoritySnapshot(
            "BASE-AUTHORITY", "VND", "100000000", ("Marketing",),
            str(checker_id), str(checker_id), str(checker_id), True,
        ),
        strategy_rubric=StrategyRubric(
            "BASE-RUBRIC", "base-1", "ACTIVE",
            tuple(StrategyCriterion(key, label, weight) for key, label, weight in STRATEGY_CRITERIA),
        ),
        media_model_snapshot={"identity_mode": "GENERIC_OPAQUE_REVISION"},
        strategy_model_snapshot={"model_id": "task-model"},
        visual_model_snapshot={"model_id": "visual-model"},
    )

    applied = apply_round_configuration_snapshot(base, round_snapshot)

    assert applied.policy.auto_approval_policy_enabled is False
    assert applied.policy.feasibility_threshold == 75
    assert applied.policy.media_confidence_threshold == 0.9
    assert applied.policy.feasibility_confidence_threshold == 0.85
    assert applied.policy.snapshot_id == resolutions["approval_policy"]["revision_id"]
    assert applied.media_policy.policy_id == "SNAPSHOT-MEDIA"
    assert applied.strategy_rubric.rubric_version == "strategy-r5"
    assert applied.budgets[0].limit_minor_units == "75000000"
    assert applied.budgets[0].configuration_id == resolutions["budget"]["revision_id"]
    assert applied.authority.auto_limit_minor_units == "70000000"
    assert applied.authority.snapshot_id == resolutions["authority"]["revision_id"]
    assert applied.visual_model_snapshot == base.visual_model_snapshot
    assert applied.strategy_model_snapshot == base.strategy_model_snapshot


def test_round_snapshot_mapping_rejects_a_value_hash_mismatch():
    from src.backend.application.approval_configuration import (
        ConfigurationValidationError,
        RoundConfigurationSnapshot,
        apply_round_configuration_snapshot,
    )
    from src.backend.domain.policy import ApprovalConfiguration, PolicySnapshot, Criterion, MANDATORY_FIELDS, STRATEGY_CRITERIA

    base = ApprovalConfiguration(
        policy=PolicySnapshot(
            "BASE-POLICY", "base-1", False, MANDATORY_FIELDS,
            tuple(Criterion(key, weight) for key, _label, weight in STRATEGY_CRITERIA),
            ("visual-model-rev-1",), ("image/png",), 5_000_000,
        ),
        budgets=(), authority=None,
    )
    resolutions = {kind: {
        "kind": kind, "status": "UNCONFIGURED", "revision_id": None,
        "revision": None, "effective_at": None, "configuration_hash": None,
        "value": None,
    } for kind in approval_configuration.CONFIGURATION_KINDS}
    resolutions["budget"] = {
        "kind": "budget", "status": "EFFECTIVE", "revision_id": str(uuid4()),
        "revision": 1, "effective_at": "2026-10-12T12:00:00.000000Z",
        "configuration_hash": "0" * 64,
        "value": {"currency": "VND", "limits": [{
            "department": "Marketing", "limit_minor_units": "100", "active": True,
        }]},
    }
    snapshot = RoundConfigurationSnapshot(
        plan_id=uuid4(), plan_version=1, approval_round=1,
        effective_at=datetime.now(timezone.utc), configurations=resolutions,
        checker_assignment={"eligible": True}, snapshot_hash="synthetic",
    )

    with pytest.raises(ConfigurationValidationError, match="hash"):
        apply_round_configuration_snapshot(base, snapshot)


def test_unsupported_active_rubric_is_not_fabricated_as_a_supported_baseline():
    from src.backend.application.approval_configuration import (
        RoundConfigurationSnapshot,
        apply_round_configuration_snapshot,
        canonical_configuration_hash,
    )
    from src.backend.domain.policy import (
        ApprovalConfiguration,
        Criterion,
        MANDATORY_FIELDS,
        PolicySnapshot,
        STRATEGY_CRITERIA,
    )

    approval_value = {
        "enabled": False,
        "media_confidence_threshold": 0.85,
        "feasibility_score_threshold_exclusive": 70,
        "feasibility_confidence_threshold": 0.8,
    }
    rubric_value = {
        "rubric_id": "CUSTOM-SNAPSHOT",
        "rubric_version": "custom-1",
        "status": "ACTIVE",
        "criteria": [{
            "criterion_id": key,
            "label": label,
            "weight": 40 if key == "risk_control" else 10,
        } for key, label, _weight in STRATEGY_CRITERIA],
    }
    values = {
        "approval_policy": ("DISABLED", approval_value),
        "strategy_rubric": ("EFFECTIVE", rubric_value),
    }
    resolutions = {}
    for kind in approval_configuration.CONFIGURATION_KINDS:
        status, value = values.get(kind, ("UNCONFIGURED", None))
        resolutions[kind] = {
            "kind": kind,
            "status": status,
            "revision_id": str(uuid4()) if value is not None else None,
            "revision": 1 if value is not None else None,
            "effective_at": "2026-10-12T12:00:00.000000Z" if value is not None else None,
            "configuration_hash": canonical_configuration_hash(value) if value is not None else None,
            "value": value,
        }
    snapshot = RoundConfigurationSnapshot(
        plan_id=uuid4(), plan_version=1, approval_round=1,
        effective_at=datetime.now(timezone.utc), configurations=resolutions,
        checker_assignment={"eligible": True}, snapshot_hash="synthetic-custom-rubric",
    )
    base = ApprovalConfiguration(
        policy=PolicySnapshot(
            "BASE-POLICY", "base-1", True, MANDATORY_FIELDS,
            tuple(Criterion(key, weight) for key, _label, weight in STRATEGY_CRITERIA),
            ("visual-model-rev-1",), ("image/png",), 5_000_000,
        ),
        budgets=(), authority=None, strategy_rubric=None,
    )

    applied = apply_round_configuration_snapshot(base, snapshot)

    assert applied.strategy_rubric is None
    assert {item.criterion_id: item.maximum_score for item in applied.policy.criteria} == {
        key: weight for key, _label, weight in STRATEGY_CRITERIA
    }
