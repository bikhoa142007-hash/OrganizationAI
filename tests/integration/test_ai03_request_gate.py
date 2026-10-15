import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from scripts.ai03_request_gate import (
    MAX_INPUT_BYTES,
    MAX_OUTPUT_TOKENS,
    MAX_RESPONSE_BYTES,
    TASK_MODEL_ID,
    TASK_MODEL_VERSION,
    VLM_MODEL_ID,
    VLM_MODEL_VERSION,
    RequestGate,
    build_harness_orchestrator,
)
from src.ai_pipeline.authenticated_orchestrator import AuthenticatedEvaluationOrchestrator
from src.ai_pipeline.providers.base import ProviderAnalysis
from src.ai_pipeline.task_evaluation import STRATEGY_CRITERIA
from src.backend.api.auth import AuthenticatedPrincipal
from src.backend.application import auth_workflow as workflow
from src.backend.application.approval_configuration import create_configuration_revision
from src.backend.application.auth_workflow_ai import unconfigured_approval_configuration
from src.backend.application.role_admin import BUILTIN_PERMISSIONS
from src.backend.db.base import Base
from src.backend.db.models import (
    AuthWorkflowEngineDecision,
    AuthWorkflowEvaluationRun,
    AuthWorkflowPlan,
    AuthWorkflowRoundConfigurationSnapshot,
    AuthWorkflowVersion,
    EmployeeProfile,
    Role,
    RolePermission,
    User,
    UserRole,
)
from src.backend.domain.policy import MediaCompliancePolicy, StrategyRubric
from tests.integration.test_auth_workflow import PNG


def _seed_actors(session):
    roles = {}
    for code in ("MAKER", "CHECKER", "ADMIN"):
        role = Role(
            id=uuid4(), code=code, name=code.title(), description=None,
            is_builtin=True, status="ACTIVE",
        )
        session.add(role)
        session.flush()
        session.add_all(
            RolePermission(role_id=role.id, permission_code=permission)
            for permission in BUILTIN_PERMISSIONS[code]
        )
        roles[code] = role

    actors = {}
    for code, username in (
        ("MAKER", "ai03-synthetic-maker"),
        ("CHECKER", "ai03-synthetic-checker"),
        ("ADMIN", "ai03-synthetic-admin"),
    ):
        user_id = uuid4()
        email = username + "@example.invalid"
        user = User(
            id=user_id, user_code="USR-" + user_id.hex[:12].upper(),
            username=username, email=email, phone=None,
            password_hash="disposable-synthetic-only",
            display_name=username, department="marketing",
            employment_status="ACTIVE", activation_pending=False, status="ACTIVE",
        )
        session.add(user)
        session.flush()
        session.add(UserRole(user_id=user_id, role_id=roles[code].id))
        session.add(EmployeeProfile(
            id=user_id, user_code=user.user_code, display_name=user.display_name,
            email=email, phone=None, department="marketing",
            employment_status="ACTIVE", user_id=user_id,
        ))
        actors[code] = AuthenticatedPrincipal(
            id=user_id, user_code=user.user_code, username=username,
            email=email, phone=None, display_name=username, status="ACTIVE",
            roles=(code,), permissions=BUILTIN_PERMISSIONS[code],
        )
    session.commit()
    return actors


def _round_test_configuration(session, admin, checker):
    now = datetime.now(timezone.utc)
    effective_at = now - timedelta(seconds=5)
    entries = {
        "approval_policy": {
            "enabled": False,
            "media_confidence_threshold": 0.85,
            "feasibility_score_threshold_exclusive": 70,
            "feasibility_confidence_threshold": 0.80,
        },
        "budget": {
            "currency": "VND",
            "limits": [{
                "department": "marketing",
                "limit_minor_units": "100000000",
                "active": True,
            }],
        },
        "media_policy": {
            "policy_id": "AI03-SYNTH-MEDIA",
            "policy_version": "1",
            "status": "ACTIVE",
            "scope_departments": ["marketing"],
            "scope_channels": ["social"],
            "rules": [{
                "rule_id": "AI03-SYNTH-OBSERVATION",
                "severity": "WARNING",
                "description": "The synthetic media must provide an observable detail.",
                "required_evidence_kinds": ["OBSERVATION"],
            }],
        },
        "strategy_rubric": {
            "rubric_id": "AI03-SYNTH-STRATEGY",
            "rubric_version": "1",
            "status": "ACTIVE",
            "criteria": [{
                "criterion_id": criterion_id,
                "label": label,
                "weight": weight,
            } for criterion_id, label, weight in STRATEGY_CRITERIA],
        },
        "checker_assignment": {
            "maker_may_select_other": False,
            "defaults": [{
                "department": "marketing",
                "checker_id": str(checker.id),
            }],
        },
        "authority": {
            "currency": "VND",
            "auto_limit_minor_units": "100000000",
            "allowed_departments": ["marketing"],
            "checker_id": str(checker.id),
            "policy_owner_id": str(admin.id),
            "budget_authority_id": str(admin.id),
            "active": True,
        },
    }
    for kind, value in entries.items():
        create_configuration_revision(
            session, admin, "ai03-synthetic-configuration",
            kind=kind, expected_revision=None, effective_at=effective_at,
            change_reason="Disposable WP-AI-03 synthetic transport test only.",
            value=value,
        )
    return (
        MediaCompliancePolicy.from_dict(entries["media_policy"]),
        StrategyRubric.from_dict(entries["strategy_rubric"]),
    )


def _completion(model_id, output):
    return httpx.Response(200, json={
        "model": model_id,
        "choices": [{
            "finish_reason": "stop",
            "message": {"content": json.dumps(output), "refusal": None},
        }],
    })


def test_real_source_providers_use_gate_and_application_service_persists_review(tmp_path):
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    wire_requests = []
    gate = RequestGate()

    def synthetic_ollama(request):
        wire_requests.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(200, json={"models": [
                {"name": VLM_MODEL_ID, "digest": VLM_MODEL_VERSION.removeprefix("sha256:")},
                {"name": TASK_MODEL_ID, "digest": TASK_MODEL_VERSION.removeprefix("sha256:")},
            ]})

        body = json.loads(request.content)
        model_id = body["model"]
        user_content = body["messages"][1]["content"]
        if model_id == VLM_MODEL_ID:
            output = {
                "images": [{
                    "image_index": 0,
                    "status": "COMPLETE",
                    "ocr_text": "SYNTHETIC ONLY",
                    "observations": ["Neutral synthetic campaign artwork with a readable label."],
                    "uncertainties": [],
                    "confidence": 0.96,
                    "object_detections": ["abstract geometric shape"],
                    "visual_quality": {"result": "PASS", "findings": []},
                }],
            }
        else:
            supplied = json.loads(user_content)
            if body["response_format"]["json_schema"]["name"] == "media_compliance":
                policy = supplied["content_policy"]
                observation = next(
                    item["evidence_id"] for item in supplied["evidence"]
                    if item["kind"] == "OBSERVATION"
                )
                output = {
                    "policy_id": policy["policy_id"],
                    "policy_version": policy["policy_version"],
                    "outcome": "PASS",
                    "confidence": 0.93,
                    "reason": "Synthetic policy rule was checked against the supplied observation.",
                    "rule_results": [{
                        "rule_id": rule["rule_id"],
                        "result": "PASS",
                        "rationale": "The required synthetic observation is present.",
                        "evidence_refs": [observation],
                    } for rule in policy["rules"]],
                    "findings": [],
                    "evidence_conflicts": [],
                }
            else:
                rubric = supplied["rubric"]
                output = {
                    "rubric_id": rubric["rubric_id"],
                    "rubric_version": rubric["rubric_version"],
                    "total_score": 71,
                    "confidence": 0.82,
                    "criterion_scores": [{
                        "criterion_id": item["criterion_id"],
                        "score": 71,
                        "rationale": "The synthetic plan field supports this advisory assessment.",
                        "evidence_refs": ["plan-field:objective"],
                    } for item in rubric["criteria"]],
                    "assumptions": [],
                    "missing_facts": [],
                    "critical_gaps": [],
                    "evidence_conflicts": [],
                    "reason": "Synthetic strategy assessment.",
                }
        return _completion(model_id, output)

    orchestrator, providers = build_harness_orchestrator(
        gate, inner_transport=httpx.MockTransport(synthetic_ollama)
    )
    with providers["client"] as client:
        assert isinstance(orchestrator, AuthenticatedEvaluationOrchestrator)
        assert providers["visual"].delegate._client is client
        assert providers["media"].delegate._client is client
        assert providers["strategy"].delegate._client is client
        assert providers["media_settings"].max_retries == 0
        assert providers["strategy_settings"].max_retries == 0
        assert providers["media_settings"].max_output_tokens == MAX_OUTPUT_TOKENS
        assert providers["media_settings"].max_response_bytes == MAX_RESPONSE_BYTES
        assert providers["media_settings"].max_input_bytes == MAX_INPUT_BYTES

        with factory() as session:
            actors = _seed_actors(session)
            media_policy, strategy_rubric = _round_test_configuration(
                session, actors["ADMIN"], actors["CHECKER"]
            )
            base_configuration = unconfigured_approval_configuration(
                providers["visual"],
                media_policy=media_policy,
                strategy_rubric=strategy_rubric,
                media_model_snapshot=providers["media_settings"].public_snapshot(),
                strategy_model_snapshot=providers["strategy_settings"].public_snapshot(),
                visual_model_snapshot=providers["visual"].get_model_metadata(),
            )
            payload = {
                "title": "Synthetic campaign pipeline",
                "objective": "Measure interest in a fictional product.",
                "summary": "A synthetic plan used only to test the local approval pipeline.",
                "department": "marketing",
                "start_date": "2026-10-15",
                "end_date": "2026-11-15",
                "budget_minor_units": "50000000",
                "currency": "VND",
                "target_audience": "Synthetic sample audience",
                "channels": ["social"],
                "kpi_expected": ["Synthetic engagement count"],
            }
            correlation_id = "ai03-synthetic-transport-test"
            draft = workflow.create_plan(
                session, actors["MAKER"], payload, actors["CHECKER"].id,
                correlation_id, idempotency_key="ai03-synthetic-case",
            )
            plan_id = __import__("uuid").UUID(draft["id"])
            uploaded = workflow.upload_attachment(
                session, actors["MAKER"], plan_id, "synthetic-only.png",
                "image/png", PNG, draft["revision"], correlation_id,
            )
            submitted = workflow.submit_plan(
                session, actors["MAKER"], plan_id, uploaded["revision"],
                correlation_id, provider_name="LOCAL_VLM",
                model_version=VLM_MODEL_VERSION, model_id=VLM_MODEL_ID,
                configuration=base_configuration,
            )
            assert submitted["status"] == "PENDING_APPROVAL"
            result = workflow.evaluate_submission(
                session, plan_id, 1, orchestrator, correlation_id,
            )
            assert result["processing_stage"] == "HUMAN_REVIEW_REQUIRED"

        with factory() as verify_session:
            plan = verify_session.get(AuthWorkflowPlan, plan_id)
            version = verify_session.scalar(select(AuthWorkflowVersion).where(
                AuthWorkflowVersion.plan_id == plan_id,
                AuthWorkflowVersion.round_number == 1,
            ))
            round_snapshot = verify_session.scalar(select(AuthWorkflowRoundConfigurationSnapshot).where(
                AuthWorkflowRoundConfigurationSnapshot.plan_id == plan_id,
                AuthWorkflowRoundConfigurationSnapshot.approval_round == 1,
            ))
            run = verify_session.scalar(select(AuthWorkflowEvaluationRun).where(
                AuthWorkflowEvaluationRun.plan_id == plan_id,
                AuthWorkflowEvaluationRun.round_number == 1,
            ))
            decision = verify_session.scalar(select(AuthWorkflowEngineDecision).where(
                AuthWorkflowEngineDecision.plan_id == plan_id,
                AuthWorkflowEngineDecision.round_number == 1,
            ))

    try:
        assert plan.status == "PENDING_APPROVAL"
        assert plan.processing_stage == "HUMAN_REVIEW_REQUIRED"
        assert version.version_number == 1 and version.snapshot_hash == run.input_hash
        assert round_snapshot.snapshot_hash
        assert round_snapshot.checker_assignment["status"] == "CONFIGURED"
        assert round_snapshot.checker_assignment["source"] == "DEFAULT"
        assert round_snapshot.checker_assignment["checker_id"] == str(actors["CHECKER"].id)
        assert round_snapshot.checker_assignment["configuration_revision_id"]
        assert run.status == "SUCCEEDED" and run.retried is False
        assert run.visual_extraction["model_revision"] == VLM_MODEL_VERSION
        assert run.media_evaluation["model_revision"] == TASK_MODEL_VERSION
        assert run.strategy_evaluation["model_revision"] == TASK_MODEL_VERSION
        assert run.visual_extraction["status"] == "SUCCEEDED"
        assert run.media_evaluation["status"] == "SUCCEEDED"
        assert run.strategy_evaluation["status"] == "SUCCEEDED"
        assert all(len(getattr(run, key)["raw_output_hash"]) == 64 for key in (
            "visual_extraction", "media_evaluation", "strategy_evaluation",
        ))
        assert run.evaluation["status"] == "SUCCEEDED"
        assert run.evaluation["feasibility_score"] == 71
        assert run.evaluation["evidence_conflicts"] == []
        assert run.evaluation["proposed_action"] == "RECOMMEND_AUTO_APPROVAL"
        assert decision.outcome == "HUMAN_REVIEW_REQUIRED"
        assert decision.decision["budget_validation"]["result"] == "PASS"
        snapshot = gate.snapshot()
        assert snapshot["request_count"] == 6
        assert snapshot["inference_post_count"] == 3
        assert [item["provider"] for item in snapshot["sent_requests"]] == [
            "VLM", "VLM", "MEDIA", "MEDIA", "STRATEGY", "STRATEGY",
        ]
        assert all(item["server_completion_known"] for item in snapshot["sent_requests"])
        assert len(wire_requests) == 6
    finally:
        engine.dispose()
