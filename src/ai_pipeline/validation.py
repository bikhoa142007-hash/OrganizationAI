"""Fail-closed validation at the untrusted provider boundary."""

from collections.abc import Mapping

from src.backend.domain.models import EvaluationResult
from src.shared.validation import ValidationError, canonical_hash


class EvidenceValidationError(ValueError):
    def __init__(self, code: str, message: str = "Provider evidence is invalid"):
        super().__init__(message)
        self.code = code


def validate_evidence(raw, request):
    """Return a normalized contract dict or raise without coercing bad data.

    The existing contract decoder rejects missing/unknown fields, enum errors,
    malformed collections and non-finite values. This function adds trusted
    request correlation and evidence completeness checks before WP3 sees data.
    """
    if not isinstance(raw, Mapping):
        raise EvidenceValidationError("INVALID_SCHEMA")
    try:
        result = EvaluationResult.from_dict(raw)
    except (ValidationError, TypeError, ValueError, OverflowError) as exc:
        raise EvidenceValidationError("INVALID_SCHEMA") from exc
    expected = {
        "evaluation_id": request.evaluation_id,
        "run_id": request.run_id,
        "plan_id": request.plan_id,
        "plan_version": request.plan_version,
        "approval_round": request.approval_round,
        "input_hash": request.input_hash,
        "policy_version": request.policy_version,
        "provider": request.provider,
        "correlation_id": request.correlation_id,
    }
    actual = {key: getattr(result, key) for key in expected}
    if actual != expected:
        raise EvidenceValidationError("CORRELATION_MISMATCH")
    if result.input_hash != request.plan.input_hash:
        raise EvidenceValidationError("INPUT_HASH_MISMATCH")
    if result.status == "SUCCEEDED":
        attachment_ids = {a.attachment_id for a in request.plan.attachments}
        observed = {e.source_ref for e in result.evidence if e.source_type == "ATTACHMENT"}
        if not result.evidence or not attachment_ids.issubset(observed):
            raise EvidenceValidationError("MISSING_EVIDENCE")
        if result.media_result not in {"PASS", "REVIEW_REQUIRED"}:
            raise EvidenceValidationError("UNKNOWN_MEDIA_STATUS")
        for value in (result.media_confidence, result.feasibility_confidence):
            if value is None or not 0 <= value <= 1:
                raise EvidenceValidationError("INVALID_CONFIDENCE")
    return result.to_dict()


def safe_raw_hash(raw):
    try:
        return canonical_hash(raw)
    except (ValidationError, TypeError, ValueError):
        return None
