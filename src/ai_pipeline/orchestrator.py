"""Finite-retry orchestration that never decides approval outcomes."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime, timezone

from .models import EvaluationRequest, PipelineResult
from .providers.base import ProviderError, ProviderTimeout, VisualModelProvider
from .validation import EvidenceValidationError, safe_raw_hash, validate_evidence


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

    run = evaluate

    def _failure(self, request, code, message, raw_hash=None):
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
