from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, Uuid, select
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine

from src.backend.api.auth import AuthenticatedPrincipal
from src.backend.application import workflow_retry
from src.backend.application.workflow import ApplicationError
from src.backend.db.base import Base
from src.backend.db.models.auth_workflow import (
    AuthWorkflowDecision,
    AuthWorkflowEvaluationRun,
    AuthWorkflowEvent,
    AuthWorkflowNotification,
    AuthWorkflowPlan,
    AuthWorkflowVersion,
)


class RetryHarnessRun(Base):
    __tablename__ = "test_retry_harness_runs"
    __table_args__ = (
        UniqueConstraint("plan_id", "round_number", "attempt_number"),
        UniqueConstraint("plan_id", "round_number", "retry_idempotency_key"),
    )

    id: Mapped[object] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    plan_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), ForeignKey("auth_workflow_plans.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    run_id: Mapped[str] = mapped_column(String(100), nullable=False)
    evaluation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(200), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(160), nullable=True)
    model_digest: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_revision: Mapped[str | None] = mapped_column(String(160), nullable=True)
    policy_version: Mapped[str] = mapped_column(String(160), nullable=False)
    policy_snapshot_id: Mapped[str] = mapped_column(String(160), nullable=False)
    policy_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    retried: Mapped[bool] = mapped_column(nullable=False)
    evaluation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    visual_extraction: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    media_evaluation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    strategy_evaluation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    retry_parent_run_id: Mapped[object | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    retry_idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    retry_request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_disposition: Mapped[str | None] = mapped_column(String(16), nullable=True)


class RetryHarnessEngineDecision(Base):
    __tablename__ = "test_retry_harness_engine_decisions"
    __table_args__ = (UniqueConstraint("evaluation_run_id"),)

    id: Mapped[object] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    plan_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), ForeignKey("auth_workflow_plans.id"), nullable=False)
    evaluation_run_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), ForeignKey("test_retry_harness_runs.id"), nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    decision_id: Mapped[str] = mapped_column(String(100), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    decision: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@pytest.fixture
def session(monkeypatch):
    monkeypatch.setattr(workflow_retry, "AuthWorkflowEvaluationRun", RetryHarnessRun)
    monkeypatch.setattr(workflow_retry, "AuthWorkflowEngineDecision", RetryHarnessEngineDecision)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        yield db
    Base.metadata.drop_all(engine)
    engine.dispose()


def principal(role: str, user_id=None) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        id=user_id or uuid4(),
        user_code=f"{role}-1",
        username=f"{role.lower()}-1",
        email=None,
        phone=None,
        display_name=f"{role.title()} One",
        status="ACTIVE",
        roles=(role,),
        permissions=(),
    )


def add_retryable_round(session, checker_id, failure_code="PROVIDER_ERROR"):
    plan = AuthWorkflowPlan(
        code=f"MKT-{uuid4().hex[:12]}",
        maker_id=uuid4(),
        checker_id=checker_id,
        payload={},
        status="PENDING_APPROVAL",
        processing_stage="HUMAN_REVIEW_REQUIRED",
        current_version=1,
        current_round=1,
        revision=7,
    )
    session.add(plan)
    session.flush()
    version = AuthWorkflowVersion(
        plan_id=plan.id,
        version_number=1,
        round_number=1,
        payload_snapshot={"summary": "frozen"},
        attachment_snapshot=[],
        snapshot_hash="a" * 64,
        submitted_by=plan.maker_id,
    )
    session.add(version)
    session.flush()
    run = RetryHarnessRun(
        id=uuid4(),
        plan_id=plan.id,
        version_number=1,
        round_number=1,
        run_id="RUN-original",
        evaluation_id="EVAL-original",
        idempotency_key="submit-key",
        correlation_id="corr-original",
        input_hash="a" * 64,
        provider="LOCAL_VLM",
        model_id="model-fixed",
        model_version="v1",
        model_digest="sha256:pinned-model",
        model_revision="task-revision-4",
        policy_version="POLICY-1",
        policy_snapshot_id="SNAPSHOT-1",
        policy_snapshot_hash="b" * 64,
        policy_snapshot={"budget_limit": 900000, "rubric_revision": "r4"},
        status="FAILED",
        attempts=1,
        retried=False,
        evaluation={"status": "FAILED", "agent_errors": [{"code": failure_code}]},
        visual_extraction=None,
        media_evaluation=None,
        strategy_evaluation=None,
        failure_reason=failure_code,
        started_at=datetime(2026, 10, 12, 8, tzinfo=timezone.utc),
        completed_at=datetime(2026, 10, 12, 8, 1, tzinfo=timezone.utc),
        created_at=datetime(2026, 10, 12, 8, tzinfo=timezone.utc),
        attempt_number=1,
        retry_parent_run_id=None,
        retry_idempotency_key=None,
        retry_request_hash=None,
        result_disposition="APPLIED",
    )
    session.add(run)
    session.flush()
    session.add(RetryHarnessEngineDecision(
        id=uuid4(),
        plan_id=plan.id,
        evaluation_run_id=run.id,
        round_number=1,
        decision_id="DEC-review-original",
        outcome="HUMAN_REVIEW_REQUIRED",
        decision={"reason": failure_code},
        created_at=datetime(2026, 10, 12, 8, 1, tzinfo=timezone.utc),
    ))
    session.commit()
    return plan, version, run


def retry(session, checker, plan, evaluate_run, *, key="retry-key", version=1, revision=7):
    return workflow_retry.request_manual_evaluation_retry(
        session,
        checker,
        plan.id,
        1,
        expected_plan_version=version,
        expected_round_revision=revision,
        idempotency_key=key,
        correlation_id="corr-retry",
        orchestrator=object(),
        evaluate_run=evaluate_run,
    )


def test_retry_appends_a_new_run_after_claim_without_locking_during_evaluation(session):
    checker = principal("CHECKER")
    plan, _version, original = add_retryable_round(session, checker.id, "PROVIDER_TIMEOUT")
    snapshots = []
    decisions = []

    def evaluate_run(db, plan_id, evaluation_run_id, orchestrator, correlation_id):
        assert not db.in_transaction()
        retry_run = db.get(RetryHarnessRun, evaluation_run_id)
        assert retry_run.status == "PENDING"
        assert retry_run.result_disposition is None
        assert retry_run.attempt_number == 2
        assert retry_run.retry_parent_run_id == original.id
        assert retry_run.retry_idempotency_key == "retry-key"
        assert retry_run.input_hash == original.input_hash
        assert retry_run.policy_snapshot == original.policy_snapshot
        assert retry_run.model_digest == original.model_digest
        assert retry_run.model_revision == original.model_revision
        assert orchestrator is not None
        snapshots.append(retry_run.policy_snapshot.copy())
        retry_run.status = "TIMED_OUT"
        retry_run.failure_reason = "PROVIDER_TIMEOUT"
        retry_run.result_disposition = "APPLIED"
        retry_run.completed_at = datetime.now(timezone.utc)
        decision = RetryHarnessEngineDecision(
            id=uuid4(), plan_id=plan_id, evaluation_run_id=retry_run.id,
            round_number=1, decision_id="DEC-review-retry", outcome="HUMAN_REVIEW_REQUIRED",
            decision={"reason": "PROVIDER_TIMEOUT"}, created_at=datetime.now(timezone.utc),
        )
        db.add(decision)
        db.commit()
        decisions.append(decision.decision_id)

    response = retry(session, checker, plan, evaluate_run)

    assert response["attempt_number"] == 2
    assert response["run_status"] == "TIMED_OUT"
    assert response["result_disposition"] == "APPLIED"
    assert response["decision_id"] == "DEC-review-retry"
    assert response["processing_stage"] == "HUMAN_REVIEW_REQUIRED"
    assert snapshots == [original.policy_snapshot]
    assert decisions == ["DEC-review-retry"]
    assert session.get(RetryHarnessRun, original.id).failure_reason == "PROVIDER_TIMEOUT"
    assert session.get(AuthWorkflowPlan, plan.id).revision == 7
    assert session.query(AuthWorkflowEvent).count() == 1
    assert session.query(AuthWorkflowNotification).count() == 0


def test_evaluator_exception_is_persisted_as_failed_human_review(session):
    checker = principal("CHECKER")
    plan, _version, original = add_retryable_round(session, checker.id)

    def raise_provider_error(*_args):
        raise RuntimeError("provider transport failed")

    response = retry(session, checker, plan, raise_provider_error)
    retry_run = session.query(RetryHarnessRun).filter_by(plan_id=plan.id, attempt_number=2).one()

    assert response["run_status"] == "FAILED"
    assert response["processing_stage"] == "HUMAN_REVIEW_REQUIRED"
    assert response["decision_id"] is None
    assert retry_run.failure_reason == "RETRY_EVALUATOR_ERROR"
    assert retry_run.result_disposition == "APPLIED"
    assert retry_run.evaluation["agent_errors"] == [{"code": "RETRY_EVALUATOR_ERROR"}]
    assert session.get(AuthWorkflowPlan, plan.id).revision == 8
    assert session.get(RetryHarnessRun, original.id).failure_reason == "PROVIDER_ERROR"
    assert session.query(AuthWorkflowEvent).count() == 2
    assert session.query(AuthWorkflowNotification).count() == 0


@pytest.mark.parametrize("failure_code", [
    "INVALID_SCHEMA", "INVALID_PROVIDER_RESPONSE", "PROVIDER_UNAVAILABLE", "RATE_LIMITED",
])
def test_allowlisted_transient_failure_allows_one_manual_retry(session, failure_code):
    checker = principal("CHECKER")
    plan, _version, _run = add_retryable_round(session, checker.id, failure_code)

    first = retry(session, checker, plan, lambda *_args: None, key="schema-retry-1")
    assert first["attempt_number"] == 2
    with pytest.raises(ApplicationError) as error:
        retry(session, checker, plan, lambda *_args: pytest.fail("must not evaluate"), key="schema-retry-2")

    assert error.value.code == "CONFLICT"
    assert session.query(RetryHarnessRun).filter_by(plan_id=plan.id).count() == 2


def test_retry_evaluator_preserves_only_allowlisted_failure_code(session):
    checker = principal("CHECKER")
    plan, _version, _run = add_retryable_round(session, checker.id)

    def raise_snapshot_error(*_args):
        raise ApplicationError("CONFIG_SNAPSHOT_MISMATCH", "private provider detail", "corr-retry")

    response = retry(session, checker, plan, raise_snapshot_error)
    retry_run = session.query(RetryHarnessRun).filter_by(plan_id=plan.id, attempt_number=2).one()

    assert response["run_status"] == "FAILED"
    assert response["processing_stage"] == "HUMAN_REVIEW_REQUIRED"
    assert retry_run.failure_reason == "CONFIG_SNAPSHOT_MISMATCH"
    assert retry_run.evaluation["agent_errors"] == [{"code": "CONFIG_SNAPSHOT_MISMATCH"}]
    assert "private provider detail" not in str(retry_run.evaluation)


def test_retry_idempotency_replays_one_attempt_without_a_second_evaluation(session):
    checker = principal("CHECKER")
    plan, _version, _run = add_retryable_round(session, checker.id)
    calls = []

    def evaluate_run(_db, _plan_id, retry_run_id, _orchestrator, _correlation_id):
        calls.append(retry_run_id)

    first = retry(session, checker, plan, evaluate_run, key="same-key")
    replay = retry(session, checker, plan, evaluate_run, key="same-key")

    assert replay["run_id"] == first["run_id"]
    assert replay["attempt_number"] == first["attempt_number"] == 2
    assert len(calls) == 1
    assert session.get(RetryHarnessRun, calls[0]).run_id == first["run_id"]
    assert session.query(RetryHarnessRun).filter_by(plan_id=plan.id).count() == 2
    assert session.query(AuthWorkflowEvent).count() == 1


def test_retry_idempotency_key_cannot_be_reused_for_another_request(session):
    checker = principal("CHECKER")
    plan, _version, _run = add_retryable_round(session, checker.id)

    retry(session, checker, plan, lambda *_args: None, key="same-key")
    with pytest.raises(ApplicationError) as error:
        retry(session, checker, plan, lambda *_args: None, key="same-key", revision=8)

    assert error.value.code == "IDEMPOTENCY_CONFLICT"


def test_only_one_manual_retry_is_allowed_for_each_round(session):
    checker = principal("CHECKER")
    plan, _version, _run = add_retryable_round(session, checker.id)

    retry(session, checker, plan, lambda *_args: None, key="first-retry")
    with pytest.raises(ApplicationError) as error:
        retry(session, checker, plan, lambda *_args: None, key="second-retry")

    assert error.value.code == "CONFLICT"
    assert session.query(RetryHarnessRun).filter_by(plan_id=plan.id).count() == 2


@pytest.mark.parametrize("failure_code", [
    "POLICY_OUTPUT_CONFLICT",
    "MODEL_DIGEST_MISMATCH",
    "UNKNOWN_MODEL",
    "MODEL_IDENTITY_UNVERIFIED",
    "MODEL_NOT_FOUND",
    "MODEL_CONFIGURATION_CHANGED",
    "EVALUATOR_RUBRIC_UNSUPPORTED",
    "CONFIG_SNAPSHOT_MISMATCH",
])
def test_retry_rejects_nonrecoverable_fail_closed_results(session, failure_code):
    checker = principal("CHECKER")
    plan, _version, _run = add_retryable_round(session, checker.id, failure_code)

    with pytest.raises(ApplicationError) as error:
        retry(session, checker, plan, lambda *_args: None)

    assert error.value.code == "CONFLICT"
    assert session.query(RetryHarnessRun).filter_by(plan_id=plan.id).count() == 1


def test_retry_rejects_mixed_retryable_and_integrity_failure_codes(session):
    checker = principal("CHECKER")
    plan, _version, run = add_retryable_round(session, checker.id, "PROVIDER_ERROR")
    run.evaluation = {
        "status": "FAILED",
        "agent_errors": [{"code": "PROVIDER_ERROR"}, {"code": "SNAPSHOT_INTEGRITY"}],
    }
    session.commit()

    with pytest.raises(ApplicationError) as error:
        retry(session, checker, plan, lambda *_args: pytest.fail("must not evaluate"))

    assert error.value.code == "CONFLICT"
    assert session.query(RetryHarnessRun).filter_by(plan_id=plan.id).count() == 1


def test_retry_rejects_valid_human_review_and_final_checker_decision(session):
    checker = principal("CHECKER")
    plan, _version, run = add_retryable_round(session, checker.id, "LOW_CONFIDENCE")
    run.status = "SUCCEEDED"
    run.evaluation = {"status": "SUCCEEDED", "score": 65}
    session.add(AuthWorkflowDecision(
        plan_id=plan.id,
        round_number=1,
        checker_id=checker.id,
        action="REJECTED",
        reason="Human reviewed",
        override_reason=None,
    ))
    session.commit()

    with pytest.raises(ApplicationError) as error:
        retry(session, checker, plan, lambda *_args: pytest.fail("must not evaluate"))

    assert error.value.code == "CONFLICT"
    assert session.query(RetryHarnessRun).filter_by(plan_id=plan.id).count() == 1


def test_retry_requires_the_assigned_checker_and_current_plan_revision(session):
    assigned = principal("CHECKER")
    other_checker = principal("CHECKER")
    maker = principal("MAKER")
    plan, _version, _run = add_retryable_round(session, assigned.id)

    for caller in (other_checker, maker):
        with pytest.raises(ApplicationError) as error:
            retry(session, caller, plan, lambda *_args: pytest.fail("must not evaluate"))
        assert error.value.code == "FORBIDDEN"

    with pytest.raises(ApplicationError) as stale:
        retry(session, assigned, plan, lambda *_args: pytest.fail("must not evaluate"), revision=6)
    assert stale.value.code == "CONFLICT"
    assert session.query(RetryHarnessRun).filter_by(plan_id=plan.id).count() == 1


def test_retry_storage_columns_are_integrated_in_production_run_model():
    mapped_columns = {column.key for column in AuthWorkflowEvaluationRun.__table__.columns}
    assert {
        "attempt_number", "retry_parent_run_id", "retry_idempotency_key",
        "retry_request_hash", "result_disposition",
    } <= mapped_columns
    workflow_retry._require_retry_storage("test-correlation")
