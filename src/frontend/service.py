"""Transport-neutral facade for the WP5 user interface.

All mutations go through the existing WP3 workflow.  This module only turns
trusted workflow responses into small dictionaries suitable for a web UI.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from src.ai_pipeline.adapters import ApprovalPipelineAdapter


REQUIRED_FIELDS = (
    "title", "maker_id", "checker_id", "department", "objective", "summary",
    "start_date", "end_date", "budget_minor_units", "currency",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def validate_plan_form(payload: Mapping[str, Any], attachment_count: int = 0) -> dict[str, Any]:
    """Return deterministic field errors without invoking the workflow."""
    errors: dict[str, str] = {}
    for field in REQUIRED_FIELDS:
        value = payload.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors[field] = "This field is required."
    try:
        if payload.get("start_date") and payload.get("end_date"):
            if payload["start_date"] > payload["end_date"]:
                errors["end_date"] = "End date must be on or after start date."
    except TypeError:
        errors["start_date"] = "Use ISO date format (YYYY-MM-DD)."
    try:
        if payload.get("budget_minor_units") is not None and int(payload["budget_minor_units"]) < 0:
            errors["budget_minor_units"] = "Budget cannot be negative."
    except (TypeError, ValueError):
        errors["budget_minor_units"] = "Budget must be a whole number."
    if attachment_count < 1:
        errors["attachments"] = "At least one image attachment is required."
    return {"valid": not errors, "errors": errors}


class FrontendService:
    """Small UI-facing facade around ``ApprovalWorkflow`` and the AI adapter."""

    def __init__(self, workflow, pipeline: ApprovalPipelineAdapter, *, maker_id: str, checker_id: str,
                 evaluator_id: str):
        self.workflow = workflow
        self.pipeline = pipeline
        self.maker_id = maker_id
        self.checker_id = checker_id
        self.evaluator_id = evaluator_id

    def save_draft(self, plan_id: str, payload: Mapping[str, Any], revision: int = 0) -> dict:
        body = dict(payload)
        body.setdefault("maker_id", self.maker_id)
        return self.workflow.save_draft(
            self.maker_id, plan_id, body, expected_revision=revision,
            idempotency_key=f"ui-draft-{uuid4().hex}", correlation_id=f"ui-{uuid4().hex}",
        )

    def upload(self, plan_id: str, content: bytes, media_type: str, revision: int) -> dict:
        return self.workflow.upload_attachment(
            self.maker_id, plan_id, content, media_type, expected_revision=revision,
            idempotency_key=f"ui-upload-{uuid4().hex}", correlation_id=f"ui-{uuid4().hex}",
        )

    def submit_and_evaluate(self, plan_id: str, revision: int) -> dict:
        submission = self.workflow.submit_plan(
            self.maker_id, plan_id, expected_revision=revision,
            expected_policy_version=self.workflow.configuration.policy.policy_version,
            idempotency_key=f"ui-submit-{uuid4().hex}", correlation_id=f"ui-{uuid4().hex}",
        )
        return self.pipeline.evaluate_submission(
            self.evaluator_id, plan_id, submission,
            idempotency_key=f"ui-evaluate-{uuid4().hex}",
            correlation_id=submission["evaluation_ticket"]["correlation_id"],
        )

    def human_decide(self, plan_id: str, number: int, action: str, *, reason: str | None = None,
                     override_reason: str | None = None, revision: int) -> dict:
        decision = self.workflow.decide_round(
            self.checker_id, plan_id, number, action, reason=reason,
            override_reason=override_reason, expected_revision=revision,
            idempotency_key=f"ui-human-{uuid4().hex}", correlation_id=f"ui-{uuid4().hex}",
        )
        return _jsonable(decision)

    def history(self, plan_id: str) -> dict:
        return _jsonable(self.workflow.get_plan(self.maker_id, plan_id))

    def result_view(self, evaluation_result: Mapping[str, Any]) -> dict[str, Any]:
        """Normalize dataclasses/dicts to fields required by the result screen."""
        result = _jsonable(evaluation_result)
        decision = result.get("decision", {})
        evaluation = result.get("evaluation", {})
        questions = result.get("questions", [])
        return {
            "outcome": decision.get("outcome"),
            "escalation_category": decision.get("escalation_category"),
            "escalation_questions": [q.get("question") for q in questions],
            "explanation": decision.get("reason") or evaluation.get("reason"),
            "rule_checks": decision.get("rule_checks", []),
            "evidence": evaluation.get("evidence", []) + decision.get("evidence", []),
            "confidence": {
                "media": evaluation.get("media_confidence"),
                "feasibility": evaluation.get("feasibility_confidence"),
            },
            "provider": evaluation.get("provider"),
            "model_version": evaluation.get("model_version"),
            "timestamp": evaluation.get("completed_at") or _now(),
            "plan_id": evaluation.get("plan_id"),
            "version": evaluation.get("plan_version"),
            "approval_round": evaluation.get("approval_round"),
            "correlation_id": evaluation.get("correlation_id") or decision.get("correlation_id"),
            "evaluation": evaluation,
            "decision": decision,
        }


def audit_rows(history: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Map persisted audit events to stable table columns."""
    rows = []
    for event in history.get("audit", []):
        body = event.get("body", event)
        previous = body.get("previous_state") or {}
        resulting = body.get("new_state") or {}
        rows.append({
            "action": body.get("action"), "actor": body.get("actor_id"),
            "timestamp": body.get("timestamp"), "plan_id": body.get("plan_id") or body.get("entity_id"),
            "version": body.get("plan_version"), "input_hash": body.get("input_hash"),
            "previous_state": previous.get("plan_status"),
            "resulting_state": resulting.get("plan_status"), "reason": body.get("reason"),
            "correlation_id": body.get("correlation_id"),
            "run_id": body.get("run_id"), "decision_id": body.get("decision_id"),
        })
    return rows
