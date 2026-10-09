from datetime import datetime, timezone
from decimal import Decimal
import hashlib

import pytest

from src.ai_pipeline.models import EvaluationRequest
from src.ai_pipeline.providers.base import ProviderAnalysis, ProviderError, ProviderTimeout
from src.ai_pipeline.providers.mock import AuthenticatedMockVLMProvider
from src.ai_pipeline.task_evaluation import (
    STRATEGY_CRITERIA,
    media_policy_from_json,
    strategy_rubric_from_json,
)
from src.ai_pipeline.task_providers import TaskModelSettings
from src.ai_pipeline.authenticated_orchestrator import AuthenticatedEvaluationOrchestrator
from src.backend.domain.models import AttachmentManifest, EvaluationResult, MarketingPlan
from src.backend.domain.policy import (
    ApprovalConfiguration,
    Criterion,
    MANDATORY_FIELDS,
    PolicySnapshot,
)
from src.backend.rules.decision import DecisionContext, decide


MEDIA_POLICY_JSON = '''{
  "policy_id":"MEDIA-POLICY-TEST","policy_version":"1","status":"ACTIVE",
  "scope_departments":["marketing"],"scope_channels":["social"],
  "rules":[{"rule_id":"BRAND-LOGO","severity":"HARD_VIOLATION",
    "description":"Check the supplied brand policy.","required_evidence_kinds":["OBSERVATION"]}]
}'''
STRATEGY_RUBRIC_JSON = '''{
  "rubric_id":"BA-RUBRIC-TEST","rubric_version":"1","status":"ACTIVE",
  "criteria":[
    {"criterion_id":"objective","label":"Objective","weight":15},
    {"criterion_id":"audience","label":"Audience","weight":15},
    {"criterion_id":"channel","label":"Channel","weight":15},
    {"criterion_id":"timeline","label":"Timeline","weight":15},
    {"criterion_id":"kpi","label":"KPI","weight":15},
    {"criterion_id":"budget_efficiency","label":"Budget efficiency","weight":15},
    {"criterion_id":"risk_control","label":"Risk control","weight":10}
  ]
}'''


def configuration(*, media_policy=None):
    rubric = strategy_rubric_from_json(STRATEGY_RUBRIC_JSON)
    policy = PolicySnapshot(
        "AUTH-UNCONFIGURED", "AUTH-1", False, MANDATORY_FIELDS,
        tuple(Criterion(item.criterion_id, item.weight) for item in rubric.criteria),
        ("vlm-rev-1",), ("image/png",), 5_000_000,
    )
    return ApprovalConfiguration(policy, (), None, media_policy, rubric)


def request(
    *, extraction_status="COMPLETE", media_policy=None, image_observation=True,
    extraction_confidence=0.97, visual_quality=None,
):
    content = b"synthetic-image-bytes"
    attachment_id = "attachment-1"
    plan = MarketingPlan(
        "plan-1", 1, 1,
        {
            "title": "Test campaign", "objective": "Increase awareness",
            "summary": "Use a landing page and social channel", "department": "marketing",
            "start_date": "2026-10-01", "end_date": "2026-10-15",
            "budget_minor_units": "250000", "currency": "VND",
            "target_audience": "Existing customers", "channels": ["social"],
            "kpi_expected": "Reach 10,000 people", "notes": "",
        },
        (AttachmentManifest(attachment_id, hashlib.sha256(content).hexdigest(), "image/png", len(content)),),
    )
    return EvaluationRequest(
        plan=plan, policy_version="AUTH-1", evaluation_id="eval-1", run_id="run-1",
        correlation_id="trace-1", provider="LOCAL_VLM", model_version="vlm-rev-1",
        configuration=configuration(media_policy=media_policy or media_policy_from_json(MEDIA_POLICY_JSON)),
        metadata={"model_id": "qwen3-vl:4b", "attachment_contents": {attachment_id: content},
                  "fake_extraction_status": extraction_status,
                  "fake_visual_observation": image_observation,
                  "fake_visual_confidence": extraction_confidence,
                  "fake_visual_quality": visual_quality or {"result": "PASS", "findings": []}},
    )


def settings(task):
    prefix = "media" if task == "MEDIA_COMPLIANCE" else "strategy"
    return TaskModelSettings(
        task=task, provider="OPENAI_COMPATIBLE_CHAT_COMPLETIONS",
        base_url=f"http://localhost:8000/v1/{prefix}", model_id=f"{prefix}-model",
        model_version=f"{prefix}-rev-1", api_key="secret", allow_remote=False,
        timeout_seconds=2, max_output_tokens=1024, max_response_bytes=4096,
        max_input_bytes=4096, max_retries=0,
        prompt_version=f"{prefix}-prompt-v1", schema_version=f"{prefix}-schema-v1",
    )


class FakeExtractionProvider:
    output_kind = "VISUAL_EXTRACTION"

    def get_model_metadata(self):
        return {"provider": "LOCAL_VLM", "model_id": "qwen3-vl:4b", "model_version": "vlm-rev-1"}

    def health_check(self):
        return True

    def analyze_image(self, _request):
        return ProviderAnalysis(
            output={"images": [{
                "image_index": 0,
                "status": _request.metadata["fake_extraction_status"],
                "ocr_text": "Summer offer",
                "observations": (["Blue logo in top left"]
                                 if _request.metadata["fake_visual_observation"] else []),
                "uncertainties": (["Small disclaimer text is unreadable"]
                                  if _request.metadata["fake_extraction_status"] == "PARTIAL" else []),
                "confidence": _request.metadata["fake_visual_confidence"],
                "object_detections": ["logo", "banner"],
                "visual_quality": _request.metadata["fake_visual_quality"],
            }]},
            model_revision="vlm-rev-1", reported_model_id="qwen3-vl:4b",
        )


class RetryOnceExtractionProvider(FakeExtractionProvider):
    def __init__(self):
        self.calls = 0

    def analyze_image(self, request):
        self.calls += 1
        if self.calls == 1:
            raise ProviderTimeout()
        return super().analyze_image(request)


class FakeTaskProvider:
    def __init__(self, task, *, fail=None, score=71):
        self.settings = settings(task)
        self.task = task
        self.fail = fail
        self.score = score
        self.calls = 0
        self.last_evidence = ()

    def evaluate(self, task_request):
        self.calls += 1
        self.last_evidence = task_request.evidence
        if self.fail == "timeout":
            raise ProviderTimeout()
        if self.fail == "error":
            raise RuntimeError("secret response must not leak")
        if self.task == "MEDIA_COMPLIANCE":
            observations = [item for item in task_request.evidence
                           if item.get("kind") == "OBSERVATION"]
            evidence_ref = (observations[0]["evidence_id"] if observations
                            else next(item["evidence_id"] for item in task_request.evidence))
            outcome = "PASS" if observations else "REVIEW_REQUIRED"
            output = {
                "policy_id": task_request.policy.policy_id,
                "policy_version": task_request.policy.policy_version,
                "outcome": outcome, "confidence": 0.93,
                "reason": "The configured policy check is supported by extraction evidence.",
                "rule_results": [{"rule_id": "BRAND-LOGO", "result": "PASS" if observations else "UNKNOWN",
                                  "rationale": "Observation matches the supplied rule." if observations else "Required visual evidence is missing.",
                                  "evidence_refs": [evidence_ref]}],
                "findings": [], "evidence_conflicts": [],
            }
            if self.fail == "invalid_policy_reference":
                output["policy_id"] = "UNTRUSTED-POLICY"
            return ProviderAnalysis(
                output=output, model_revision=self.settings.model_version,
                reported_model_id=self.settings.model_id,
                raw_output_hash=hashlib.sha256(b"fake-media-output").hexdigest(),
            )
        refs = ["plan-field:objective"]
        score = Decimal(str(self.score))
        output = {
            "rubric_id": task_request.rubric.rubric_id,
            "rubric_version": task_request.rubric.rubric_version,
            "total_score": float(score), "confidence": 0.82,
            "criterion_scores": [{
                "criterion_id": criterion_id, "score": float(score), "rationale": "Grounded in plan evidence.",
                "evidence_refs": refs,
            } for criterion_id, _label, _weight in STRATEGY_CRITERIA],
            "assumptions": [], "missing_facts": [], "critical_gaps": [],
            "evidence_conflicts": [], "reason": "Advisory score from the submitted plan.",
        }
        if self.fail == "mismatched_total":
            output["total_score"] = float(score) + 0.01
        return ProviderAnalysis(
            output=output, model_revision=self.settings.model_version,
            reported_model_id=self.settings.model_id,
            raw_output_hash=hashlib.sha256(b"fake-strategy-output").hexdigest(),
        )


def make_orchestrator(*, media=None, strategy=None, timeout_seconds=20):
    return AuthenticatedEvaluationOrchestrator(
        FakeExtractionProvider(), media_provider=media, strategy_provider=strategy,
        timeout_seconds=timeout_seconds,
    )


def test_authenticated_orchestrator_reuses_extraction_and_builds_weighted_strategy_result():
    media, strategy = FakeTaskProvider("MEDIA_COMPLIANCE"), FakeTaskProvider("STRATEGY_EVALUATION")
    updates = []
    result = make_orchestrator(media=media, strategy=strategy).evaluate(
        request(), on_step=lambda name, state: updates.append((name, state["status"])),
    )

    assert result.media_evaluation["status"] == "SUCCEEDED"
    assert result.strategy_evaluation["status"] == "SUCCEEDED"
    assert result.media_evaluation["raw_output_hash"] == hashlib.sha256(b"fake-media-output").hexdigest()
    assert result.strategy_evaluation["raw_output_hash"] == hashlib.sha256(b"fake-strategy-output").hexdigest()
    assert result.evaluation["status"] == "SUCCEEDED"
    assert result.evaluation["feasibility_score"] == 71
    assert len(result.evaluation["criterion_scores"]) == 7
    assert EvaluationResult.from_dict(result.evaluation).feasibility_score == 71
    assert media.calls == strategy.calls == 1
    assert {item["kind"] for item in media.last_evidence} >= {
        "OBJECT_DETECTION", "VISUAL_QUALITY",
    }
    assert ("media_evaluation", "PROCESSING") in updates
    assert ("strategy_evaluation", "SUCCEEDED") in updates


def test_unconfigured_media_does_not_fake_pass_and_keeps_strategy_result():
    strategy = FakeTaskProvider("STRATEGY_EVALUATION")
    result = make_orchestrator(strategy=strategy).evaluate(request())

    assert result.media_evaluation["status"] == "NOT_CONFIGURED"
    assert result.media_evaluation["result"] is None
    assert result.strategy_evaluation["status"] == "SUCCEEDED"
    assert result.evaluation["status"] == "FAILED"
    assert result.evaluation["media_result"] is None
    assert result.evaluation["agent_errors"][0]["code"] == "MEDIA_NOT_CONFIGURED"
    assert strategy.calls == 1


def test_out_of_scope_media_skips_provider_and_aggregate_attempts_sum_actual_stage_calls():
    media_policy = media_policy_from_json(MEDIA_POLICY_JSON.replace('"marketing"', '"nori pilot"'))
    visual = RetryOnceExtractionProvider()
    media = FakeTaskProvider("MEDIA_COMPLIANCE")
    strategy = FakeTaskProvider("STRATEGY_EVALUATION")
    result = AuthenticatedEvaluationOrchestrator(
        visual, media_provider=media, strategy_provider=strategy,
    ).evaluate(request(media_policy=media_policy))

    assert result.visual_extraction["status"] == "SUCCEEDED"
    assert visual.calls == 2
    assert result.media_evaluation["status"] == "REVIEW_REQUIRED"
    assert result.media_evaluation["attempts"] == 0
    assert result.media_evaluation["retried"] is False
    assert result.media_evaluation["raw_output_hash"] is None
    assert media.calls == 0
    assert result.strategy_evaluation["status"] == "SUCCEEDED"
    assert result.strategy_evaluation["attempts"] == 1
    assert result.strategy_evaluation["retried"] is False
    assert strategy.calls == 1
    assert result.evaluation["status"] == "FAILED"
    assert result.evaluation["feasibility_score"] is None
    assert result.strategy_evaluation["result"]["feasibility_score"] == 71
    assert result.attempts == 3
    assert result.retried is True


def test_one_successful_step_is_retained_when_the_other_provider_fails():
    media, strategy = FakeTaskProvider("MEDIA_COMPLIANCE"), FakeTaskProvider("STRATEGY_EVALUATION", fail="error")
    persisted = {}
    result = make_orchestrator(media=media, strategy=strategy).evaluate(
        request(), on_step=lambda name, value: persisted.__setitem__(name, value),
    )

    assert persisted["media_evaluation"]["status"] == "SUCCEEDED"
    assert result.media_evaluation["result"]["outcome"] == "PASS"
    assert result.strategy_evaluation["status"] == "FAILED"
    assert result.evaluation["status"] == "FAILED"
    assert "secret response" not in str(result.evaluation)


def test_invalid_policy_reference_and_weighted_total_are_step_failures():
    media = FakeTaskProvider("MEDIA_COMPLIANCE", fail="invalid_policy_reference")
    strategy = FakeTaskProvider("STRATEGY_EVALUATION", fail="mismatched_total")
    result = make_orchestrator(media=media, strategy=strategy).evaluate(request())

    assert result.media_evaluation["status"] == "FAILED"
    assert result.media_evaluation["error_code"] == "INVALID_SCHEMA"
    assert result.strategy_evaluation["status"] == "FAILED"
    assert result.strategy_evaluation["error_code"] == "INVALID_SCHEMA"
    assert result.evaluation["status"] == "FAILED"


def test_media_pass_with_hard_violation_fails_closed_through_decision_engine():
    submitted = request()
    media = FakeTaskProvider("MEDIA_COMPLIANCE")
    original_evaluate = media.evaluate

    def contradictory_evaluate(task_request):
        analysis = original_evaluate(task_request)
        output = dict(analysis.output)
        output["outcome"] = "PASS"
        output["rule_results"] = [
            {**output["rule_results"][0], "result": "FAIL"}
        ]
        output["findings"] = [{
            "finding_id": "hard-violation-1",
            "severity": "HARD_VIOLATION",
            "description": "A configured hard policy rule failed.",
            "rule_id": "BRAND-LOGO",
            "evidence_refs": ["ev-image-1"],
        }]
        return ProviderAnalysis(
            output=output,
            model_revision=analysis.model_revision,
            reported_model_id=analysis.reported_model_id,
            raw_output_hash=analysis.raw_output_hash,
        )

    media.evaluate = contradictory_evaluate
    result = make_orchestrator(
        media=media, strategy=FakeTaskProvider("STRATEGY_EVALUATION"),
    ).evaluate(submitted)

    assert result.media_evaluation["status"] == "FAILED"
    assert result.media_evaluation["error_code"] == "INVALID_SCHEMA"
    assert result.media_evaluation["result"] is None
    assert result.evaluation["status"] == "FAILED"

    context = DecisionContext(
        evaluation_id="eval-1", run_id="run-1", provider="LOCAL_VLM",
        correlation_id="trace-1", idempotency_key="synthetic-intent",
        decided_at="2026-10-02T00:00:00Z", plan_status="PENDING_APPROVAL",
        approval_round_status="ACTIVE", round_revision=0,
        expected_input_hash=submitted.plan.input_hash,
        verified_attachment_hashes=((
            "attachment-1", hashlib.sha256(b"synthetic-image-bytes").hexdigest(),
        ),), valid_checker_ids=("checker-1",), suspicious_input=False,
    )
    decision = decide(
        submitted.plan, submitted.configuration, result.evaluation, context,
    ).decision
    assert decision.outcome == "HUMAN_REVIEW_REQUIRED"
    assert "EVAL_VALID" in decision.reason_codes


def test_partial_extraction_uncertainty_blocks_auto_recommendation():
    media, strategy = FakeTaskProvider("MEDIA_COMPLIANCE"), FakeTaskProvider("STRATEGY_EVALUATION")
    result = make_orchestrator(media=media, strategy=strategy).evaluate(request(extraction_status="PARTIAL"))

    assert result.evaluation["status"] == "SUCCEEDED"
    assert result.evaluation["proposed_action"] == "RECOMMEND_HUMAN_REVIEW"
    assert result.evaluation["missing_facts"]
    assert result.visual_extraction["status"] == "PARTIAL"


def test_low_visual_confidence_routes_to_human_review_even_when_other_agents_pass():
    result = make_orchestrator(
        media=FakeTaskProvider("MEDIA_COMPLIANCE"),
        strategy=FakeTaskProvider("STRATEGY_EVALUATION"),
    ).evaluate(request(extraction_confidence=0.84))

    assert result.visual_extraction["confidence"] == 0.84
    assert result.evaluation["status"] == "SUCCEEDED"
    assert result.evaluation["proposed_action"] == "RECOMMEND_HUMAN_REVIEW"
    assert any("confidence" in item.lower() for item in result.evaluation["missing_facts"])


def test_visual_confidence_at_threshold_remains_eligible_for_other_auto_approval_gates():
    result = make_orchestrator(
        media=FakeTaskProvider("MEDIA_COMPLIANCE"),
        strategy=FakeTaskProvider("STRATEGY_EVALUATION"),
    ).evaluate(request(extraction_confidence=0.85))

    assert result.evaluation["proposed_action"] == "RECOMMEND_AUTO_APPROVAL"


def test_visual_quality_review_routes_to_checker_and_retains_findings():
    result = make_orchestrator(
        media=FakeTaskProvider("MEDIA_COMPLIANCE"),
        strategy=FakeTaskProvider("STRATEGY_EVALUATION"),
    ).evaluate(request(visual_quality={
        "result": "REVIEW_REQUIRED", "findings": ["The campaign text is too blurred to inspect."],
    }))

    assert result.visual_extraction["attachments"][0]["visual_quality"]["result"] == "REVIEW_REQUIRED"
    assert result.evaluation["proposed_action"] == "RECOMMEND_HUMAN_REVIEW"
    assert any("blurred" in item.lower() for item in result.evaluation["missing_facts"])


def test_score_exactly_seventy_and_missing_media_evidence_require_checker_review():
    media = FakeTaskProvider("MEDIA_COMPLIANCE")
    strategy = FakeTaskProvider("STRATEGY_EVALUATION", score=70)
    result = make_orchestrator(media=media, strategy=strategy).evaluate(request())
    assert result.evaluation["feasibility_score"] == 70
    assert result.evaluation["proposed_action"] == "RECOMMEND_HUMAN_REVIEW"

    media, strategy = FakeTaskProvider("MEDIA_COMPLIANCE"), FakeTaskProvider("STRATEGY_EVALUATION")
    missing = make_orchestrator(media=media, strategy=strategy).evaluate(
        request(image_observation=False),
    )
    assert missing.media_evaluation["status"] == "SUCCEEDED", (
        missing.media_evaluation["error_code"], missing.media_evaluation["reason"]
    )
    assert missing.media_evaluation["result"]["outcome"] == "REVIEW_REQUIRED"
    assert missing.media_evaluation["result"]["missing_evidence"]
    assert missing.evaluation["proposed_action"] == "RECOMMEND_HUMAN_REVIEW"


def test_authenticated_mock_vlm_is_extraction_only_and_supports_review_timeout_and_error():
    submitted = request()
    passed = AuthenticatedMockVLMProvider("pass").analyze_image(submitted)
    reviewed = AuthenticatedMockVLMProvider("review").analyze_image(submitted)
    assert isinstance(passed, ProviderAnalysis)
    assert passed.output["images"][0]["status"] == "COMPLETE"
    assert passed.output["images"][0]["confidence"] == 0.95
    assert passed.output["images"][0]["object_detections"]
    assert passed.output["images"][0]["visual_quality"]["result"] == "PASS"
    assert reviewed.output["images"][0]["status"] == "PARTIAL"
    assert reviewed.output["images"][0]["uncertainties"]
    assert reviewed.output["images"][0]["confidence"] < 0.85
    assert reviewed.output["images"][0]["visual_quality"]["result"] == "REVIEW_REQUIRED"
    with pytest.raises(ProviderTimeout):
        AuthenticatedMockVLMProvider("timeout").analyze_image(submitted)
    with pytest.raises(ProviderError):
        AuthenticatedMockVLMProvider("error").analyze_image(submitted)


def test_timeout_is_recorded_as_execution_failure_and_retries_are_bounded():
    media = FakeTaskProvider("MEDIA_COMPLIANCE", fail="timeout")
    result = make_orchestrator(media=media, strategy=FakeTaskProvider("STRATEGY_EVALUATION")).evaluate(request())

    assert result.media_evaluation["status"] == "TIMED_OUT"
    assert result.media_evaluation["error_code"] == "PROVIDER_TIMEOUT"
    assert result.evaluation["media_result"] is None
