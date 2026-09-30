"""Finite-retry orchestration that never decides approval outcomes."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime, timezone

from .models import EvaluationRequest, PipelineResult
from .providers.base import (
    ProviderAnalysis,
    ProviderConfigurationError,
    ProviderError,
    ProviderNonRetryableError,
    ProviderTimeout,
    VisualModelProvider,
)
from .validation import EvidenceValidationError, safe_raw_hash, validate_evidence
from .vlm_extraction import (
    ExtractionValidationError,
    common_evidence,
    failed_extraction,
    utc_now,
    validate_and_bind_extraction,
)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class EvaluationOrchestrator:
    def __init__(self, provider: VisualModelProvider, *, timeout_seconds: float = 10.0,
                 max_retries: int = 1):
        if timeout_seconds <= 0 or max_retries < 0:
            raise ValueError("Invalid timeout/retry configuration")
        self.provider = provider
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def evaluate(self, request: EvaluationRequest) -> PipelineResult:
        if getattr(self.provider, "output_kind", "EVALUATION") == "VISUAL_EXTRACTION":
            return self._evaluate_visual_extraction(request)

        attempts = 0
        last_error = None
        raw_hash = None
        while attempts <= self.max_retries:
            attempts += 1
            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(self.provider.analyze_image, request)
            try:
                raw = future.result(timeout=self.timeout_seconds)
                executor.shutdown(wait=True)
                raw_hash = safe_raw_hash(raw)
                return PipelineResult(validate_evidence(raw, request), attempts, attempts > 1)
            except FutureTimeout as exc:
                future.cancel()
                executor.shutdown(wait=False, cancel_futures=True)
                last_error = ("PROVIDER_TIMEOUT", "Provider timed out.")
            except EvidenceValidationError as exc:
                executor.shutdown(wait=True)
                last_error = (exc.code, "Provider evidence failed schema validation.")
                break
            except ProviderTimeout:
                executor.shutdown(wait=True)
                last_error = ("PROVIDER_TIMEOUT", "Provider timed out.")
            except ProviderError:
                executor.shutdown(wait=True)
                last_error = ("PROVIDER_ERROR", "Provider execution failed.")
            except Exception:
                executor.shutdown(wait=True)
                last_error = ("PROVIDER_ERROR", "Provider execution failed.")
        code, message = last_error or ("PROVIDER_ERROR", "Provider execution failed.")
        return PipelineResult(self._failure(request, code, message, raw_hash), attempts, attempts > 1)

    def _evaluate_visual_extraction(self, request: EvaluationRequest) -> PipelineResult:
        started_at = utc_now()
        attempts = 0
        last_code = "PROVIDER_ERROR"
        last_raw_hash = None
        while attempts <= self.max_retries:
            attempts += 1
            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(self.provider.analyze_image, request)
            try:
                provider_result = future.result(timeout=self.timeout_seconds)
                executor.shutdown(wait=True)
                if not isinstance(provider_result, ProviderAnalysis):
                    raise ProviderNonRetryableError(
                        "Provider returned an invalid response.", code="INVALID_PROVIDER_RESPONSE"
                    )
                last_raw_hash = provider_result.raw_output_hash
                completed_at = utc_now()
                extraction = validate_and_bind_extraction(
                    provider_result.output,
                    request,
                    model_id=(request.metadata.get("model_id")
                              or self.provider.get_model_metadata().get("model_id")),
                    model_revision=provider_result.model_revision,
                    reported_model_id=provider_result.reported_model_id,
                    raw_output_hash=provider_result.raw_output_hash,
                    started_at=started_at,
                    completed_at=completed_at,
                )
                evaluation = self._failure(
                    request,
                    "MISSING_REQUIRED_EVALUATORS",
                    "Media Compliance and Strategy evaluators are not configured.",
                    provider_result.raw_output_hash,
                )
                evaluation["reason"] = (
                    "Image extraction completed; required Media Compliance and Strategy "
                    "evaluations are unavailable, so Checker review is required."
                )
                evaluation["agent_errors"] = [{
                    "component": "evaluation",
                    "code": "MISSING_REQUIRED_EVALUATORS",
                    "message": "Media Compliance and Strategy evaluators are not configured.",
                }]
                evaluation["evidence"] = common_evidence(extraction)
                return PipelineResult(
                    evaluation, attempts, attempts > 1, visual_extraction=extraction
                )
            except FutureTimeout:
                future.cancel()
                executor.shutdown(wait=False, cancel_futures=True)
                last_code = "PROVIDER_TIMEOUT"
            except ExtractionValidationError as exc:
                executor.shutdown(wait=True)
                last_code = exc.code
                break
            except ProviderTimeout as exc:
                executor.shutdown(wait=True)
                last_code = exc.code
            except ProviderConfigurationError as exc:
                executor.shutdown(wait=True)
                last_code = exc.code
                break
            except ProviderNonRetryableError as exc:
                executor.shutdown(wait=True)
                last_code = exc.code
                break
            except ProviderError as exc:
                executor.shutdown(wait=True)
                last_code = exc.code
            except Exception:
                executor.shutdown(wait=True)
                last_code = "PROVIDER_ERROR"

        completed_at = utc_now()
        extraction = failed_extraction(
            request,
            model_id=(request.metadata.get("model_id")
                      or self.provider.get_model_metadata().get("model_id")),
            error_code=last_code,
            raw_output_hash=last_raw_hash,
            started_at=started_at,
            completed_at=completed_at,
        )
        message = "Image extraction failed; Checker review is required."
        evaluation = self._failure(request, last_code, message, last_raw_hash)
        return PipelineResult(
            evaluation, attempts, attempts > 1, visual_extraction=extraction
        )

    @staticmethod
    def fail_closed(request: EvaluationRequest, code: str, message: str) -> PipelineResult:
        """Create the same validated failure envelope for orchestration-level faults."""
        extraction = None
        if request.provider == "LOCAL_VLM":
            extraction = failed_extraction(
                request,
                model_id=request.metadata.get("model_id"),
                error_code=code,
            )
        return PipelineResult(
            EvaluationOrchestrator._failure(request, code, message),
            attempts=0,
            retried=False,
            visual_extraction=extraction,
        )

    run = evaluate

    @staticmethod
    def _failure(request, code, message, raw_hash=None):
        now = _now()
        return {
            "evaluation_id": request.evaluation_id,
            "plan_id": request.plan_id,
            "plan_version": request.plan_version,
            "approval_round": request.approval_round,
            "run_id": request.run_id,
            "schema_version": 1,
            "input_hash": request.input_hash,
            "policy_version": request.policy_version,
            "provider": request.provider,
            "model_version": request.model_version,
            "status": "TIMED_OUT" if code == "PROVIDER_TIMEOUT" else "FAILED",
            "media_result": None,
            "media_findings": [],
            "media_confidence": None,
            "feasibility_score": None,
            "feasibility_confidence": None,
            "missing_facts": [],
            "evidence_conflicts": [],
            "evidence": [],
            "proposed_action": None,
            "escalation_category": "FACT_UNCERTAIN",
            "reason": "Evaluation failed closed; deterministic engine must route Human Review.",
            "latency_ms": 0,
            "created_at": now,
            "started_at": now,
            "completed_at": now,
            "agent_errors": [{"component": "provider", "code": code, "message": message}],
            "raw_output_hash": raw_hash,
            "reported_model_version": None,
            "correlation_id": request.correlation_id,
            "criterion_scores": [],
            "assumptions": [],
        }
