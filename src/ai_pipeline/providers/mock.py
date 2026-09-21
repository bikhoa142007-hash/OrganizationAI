"""Deterministic provider used by demos and automated tests."""

from datetime import datetime, timezone
from typing import Any

from .base import ProviderError, ProviderTimeout, VisualModelProvider


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class MockVLMProvider(VisualModelProvider):
    """Produce stable evidence without case-id or random-result branching.

    ``scenario`` is a test/demo control, not a production decision. Supported
    values are ``pass``, ``review``, ``timeout``, ``error``, ``malformed`` and
    ``unknown_media``.
    """

    def __init__(self, scenario: str = "pass", *, model_version: str = "mock-1"):
        self.scenario = scenario
        self.model_version = model_version

    def health_check(self) -> bool:
        return self.scenario not in {"timeout", "error"}

    def get_model_metadata(self):
        return {"provider": "MOCK_VLM", "model_version": self.model_version}

    def analyze_image(self, request):
        if self.scenario == "timeout":
            raise ProviderTimeout("Mock provider timed out")
        if self.scenario == "error":
            raise ProviderError("Mock provider error")
        if self.scenario == "malformed":
            return {"unexpected": True}

        criteria = tuple(getattr(request.configuration.policy, "criteria", ())) if request.configuration else ()
        if not criteria:
            criteria = (type("Criterion", (), {"criterion_id": "strategy", "maximum_score": 100})(),)
        review = self.scenario in {"review", "unknown_media"}
        score = 70.0 if review else 71.0
        maximum = sum(float(c.maximum_score) for c in criteria)
        scores = []
        remaining = score
        for index, criterion in enumerate(criteria):
            value = min(float(criterion.maximum_score), remaining) if index == len(criteria) - 1 else 0.0
            if index == 0 and len(criteria) > 1:
                value = min(float(criterion.maximum_score), score)
            remaining -= value
            scores.append({
                "criterion_id": criterion.criterion_id,
                "score": value,
                "maximum_score": float(criterion.maximum_score),
                "rationale": "Deterministic mock observation.",
                "evidence_refs": [f"evidence-{a.attachment_id}" for a in request.plan.attachments],
            })
        evidence = [{
            "evidence_id": f"evidence-{attachment.attachment_id}",
            "source_type": "ATTACHMENT",
            "source_ref": attachment.attachment_id,
            "observation": "Mock visual evidence for submitted attachment.",
            "content_hash": attachment.content_hash,
        } for attachment in request.plan.attachments]
        media_result = "REVIEW_REQUIRED" if review or self.scenario == "unknown_media" else "PASS"
        if self.scenario == "unknown_media":
            media_result = "UNKNOWN"
        media_confidence = 0.80 if review else 0.95
        feasibility_confidence = 0.75 if review else 0.90
        proposed = "RECOMMEND_HUMAN_REVIEW" if review else "RECOMMEND_AUTO_APPROVAL"
        return {
            "evaluation_id": request.evaluation_id,
            "plan_id": request.plan_id,
            "plan_version": request.plan_version,
            "approval_round": request.approval_round,
            "run_id": request.run_id,
            "schema_version": 1,
            "input_hash": request.input_hash,
            "policy_version": request.policy_version,
            "provider": "MOCK_VLM",
            "model_version": self.model_version,
            "status": "SUCCEEDED",
            "media_result": media_result,
            "media_findings": [],
            "media_confidence": media_confidence,
            "feasibility_score": score,
            "feasibility_confidence": feasibility_confidence,
            "missing_facts": [],
            "evidence_conflicts": [],
            "evidence": evidence,
            "proposed_action": proposed,
            "escalation_category": "FACT_UNCERTAIN" if review else None,
            "reason": "Mock advisory evaluation.",
            "latency_ms": 0,
            "created_at": _now(),
            "started_at": _now(),
            "completed_at": _now(),
            "agent_errors": [],
            "raw_output_hash": None,
            "reported_model_version": self.model_version,
            "correlation_id": request.correlation_id,
            "criterion_scores": scores,
            "assumptions": [],
        }
