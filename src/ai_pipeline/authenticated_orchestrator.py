"""Authenticated workflow orchestration for VLM extraction plus two independent agents."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from collections.abc import Mapping
from datetime import datetime, timezone
import time
from typing import Callable

from src.ai_pipeline.models import EvaluationRequest, PipelineResult
from src.ai_pipeline.orchestrator import EvaluationOrchestrator
from src.ai_pipeline.providers.base import (
    ProviderAnalysis,
    ProviderConfigurationError,
    ProviderError,
    ProviderNonRetryableError,
    ProviderTimeout,
)
from src.ai_pipeline.task_evaluation import validate_media_output, validate_strategy_output
from src.ai_pipeline.task_providers import OpenAICompatibleTaskProvider, TaskEvaluationRequest
from src.ai_pipeline.vlm_extraction import common_evidence, failed_extraction, utc_now
from src.backend.domain.policy import ApprovalConfiguration
from src.shared.validation import canonical_hash


PLAN_EVIDENCE_FIELDS = (
    "title", "objective", "summary", "department", "start_date", "end_date",
    "budget_minor_units", "currency", "target_audience", "channels", "kpi_expected", "notes",
)


def initial_evaluation_step(task, input_hash, configuration, settings):
    """Create a durable status envelope before provider work begins."""
    media = task == "MEDIA_COMPLIANCE"
    step_key = "media_evaluation" if media else "strategy_evaluation"
    agent_config = configuration.media_policy if media else configuration.strategy_rubric
    configured_snapshot = (
        configuration.media_model_snapshot if media else configuration.strategy_model_snapshot
    )
    settings_snapshot = (
        settings.public_snapshot() if hasattr(settings, "public_snapshot")
        else settings if isinstance(settings, dict) else {}
    )
    setting_ready = settings.is_configured if hasattr(settings, "is_configured") else bool(
        settings_snapshot.get("provider") and settings_snapshot.get("model_id")
        and settings_snapshot.get("model_version") and settings_snapshot.get("endpoint_fingerprint")
    )
    config_active = agent_config is not None and agent_config.status == "ACTIVE"
    error_code = (settings.configuration_error if hasattr(settings, "configuration_error")
                  else settings_snapshot.get("configuration_error"))
    if configured_snapshot is not None and settings_snapshot and configured_snapshot != settings_snapshot:
        error_code = "CONFIG_SNAPSHOT_MISMATCH"
    status = "FAILED" if error_code else "PENDING" if setting_ready and config_active else "NOT_CONFIGURED"
    if error_code:
        reason = "The task policy or provider configuration is invalid; Checker review is required."
    elif not config_active:
        reason = "Chưa có chính sách nội dung Media đang hoạt động." if media else "Chưa có rubric Strategy đang hoạt động."
    elif not setting_ready and not error_code:
        reason = "Chưa cấu hình provider, endpoint, model ID và model version cho bước này."
    else:
        reason = None
    model_config_hash = settings_snapshot.get("configuration_hash")
    domain_snapshot = agent_config.to_dict() if agent_config is not None else None
    configuration_hash = canonical_hash({
        "model_configuration_hash": model_config_hash,
        "task_configuration": domain_snapshot,
    })
    return {
        "step": "MEDIA_COMPLIANCE" if media else "STRATEGY_EVALUATION",
        "status": status,
        "provider": settings_snapshot.get("provider"),
        "model_id": settings_snapshot.get("model_id"),
        "model_version": settings_snapshot.get("model_version"),
        "prompt_version": settings_snapshot.get("prompt_version"),
        "schema_version": settings_snapshot.get("schema_version"),
        "configuration_id": getattr(agent_config, "policy_id", None)
        or getattr(agent_config, "rubric_id", None),
        "configuration_version": getattr(agent_config, "policy_version", None)
        or getattr(agent_config, "rubric_version", None),
        "input_hash": input_hash,
        "raw_output_hash": None,
        "configuration_hash": configuration_hash,
        "started_at": None,
        "completed_at": None,
        "latency_ms": None,
        "attempts": 0,
        "retried": False,
        "result": None,
        "error_code": error_code,
        "reason": reason,
    }


class AuthenticatedEvaluationOrchestrator:
    """Run one extractor and independent text agents without making a decision."""

    supports_step_updates = True

    def __init__(
        self,
        visual_provider,
        *,
        media_provider=None,
        strategy_provider=None,
        timeout_seconds=180,
        visual_max_retries=1,
    ):
        if timeout_seconds <= 0 or visual_max_retries < 0:
            raise ValueError("Invalid authenticated pipeline deadline/retry configuration")
        self.visual_provider = visual_provider
        self.media_provider = media_provider
        self.strategy_provider = strategy_provider
        self.timeout_seconds = timeout_seconds
        self.visual_max_retries = visual_max_retries

    def fail_closed(self, request: EvaluationRequest, code: str, message: str) -> PipelineResult:
        failure = EvaluationOrchestrator.fail_closed(request, code, message)
        extraction = failure.visual_extraction or failed_extraction(
            request, model_id=request.metadata.get("model_id"), error_code=code,
        )
        configuration = request.configuration
        media = initial_evaluation_step(
            "MEDIA_COMPLIANCE", request.input_hash, configuration,
            getattr(self.media_provider, "settings", None),
        )
        strategy = initial_evaluation_step(
            "STRATEGY_EVALUATION", request.input_hash, configuration,
            getattr(self.strategy_provider, "settings", None),
        )
        for stage in (media, strategy):
            if stage["status"] in {"PENDING", "PROCESSING"}:
                stage.update({
                    "status": "FAILED", "error_code": code,
                    "reason": "The pipeline could not complete; Checker review is required.",
                    "completed_at": utc_now(),
                })
        evaluation = failure.evaluation
        evaluation["agent_errors"] = [{
            "component": "orchestrator", "code": code,
            "message": "The pipeline could not complete; Checker review is required.",
        }]
        return PipelineResult(
            evaluation, attempts=0, retried=False, visual_extraction=extraction,
            media_evaluation=media, strategy_evaluation=strategy,
        )

    def evaluate(self, request: EvaluationRequest, *, on_step: Callable | None = None) -> PipelineResult:
        started = time.monotonic()
        deadline = started + self.timeout_seconds
        configuration = request.configuration
        if not isinstance(configuration, ApprovalConfiguration):
            return self._failed(request, "POLICY_SNAPSHOT_INVALID", "The saved evaluation configuration is invalid.")

        media_settings = getattr(self.media_provider, "settings", None)
        strategy_settings = getattr(self.strategy_provider, "settings", None)
        media_step = initial_evaluation_step(
            "MEDIA_COMPLIANCE", request.input_hash, configuration, media_settings,
        )
        strategy_step = initial_evaluation_step(
            "STRATEGY_EVALUATION", request.input_hash, configuration, strategy_settings,
        )
        self._emit(on_step, "media_evaluation", media_step)
        self._emit(on_step, "strategy_evaluation", strategy_step)

        visual_budget = min(self.timeout_seconds, self._remaining(deadline))
        provider_timeout = getattr(self.visual_provider, "timeout_seconds", 10)
        visual_timeout = min(provider_timeout + 2, visual_budget / (self.visual_max_retries + 1))
        if visual_timeout <= 0:
            visual_result = EvaluationOrchestrator.fail_closed(
                request, "PIPELINE_TIMEOUT", "The evaluation exceeded its total deadline."
            )
        else:
            visual_result = EvaluationOrchestrator(
                self.visual_provider,
                timeout_seconds=visual_timeout,
                max_retries=self.visual_max_retries,
            ).evaluate(request)
        extraction = visual_result.visual_extraction
        if extraction is None:
            # Auth Media/Strategy never consume a legacy combined MOCK evaluation envelope.
            visual_errors = visual_result.evaluation.get("agent_errors") or []
            extraction_error = (visual_errors[0].get("code") if visual_errors else None)
            extraction = failed_extraction(
                request,
                model_id=request.metadata.get("model_id"),
                error_code=extraction_error or "INVALID_PROVIDER_CONFIGURATION",
            )

        image_evidence = self._image_evidence(extraction)
        plan_evidence = self._plan_evidence(request)
        all_evidence = image_evidence + plan_evidence
        contract_evidence = [
            {key: value for key, value in item.items() if key != "kind"}
            for item in all_evidence
        ]
        error_records = []

        media_policy = configuration.media_policy
        if media_step["status"] == "FAILED":
            pass
        elif media_step["status"] == "NOT_CONFIGURED":
            media_step["error_code"] = "MEDIA_NOT_CONFIGURED"
        elif extraction.get("status") == "FAILED":
            self._complete_failed(media_step, "EXTRACTION_FAILED", "Image extraction failed; Media Compliance cannot evaluate this round.")
        elif not media_policy.applies_to(request.plan.payload):
            media_step.update({
                "status": "REVIEW_REQUIRED",
                "started_at": utc_now(),
                "completed_at": utc_now(),
                "result": {
                    "outcome": "REVIEW_REQUIRED",
                    "confidence": None,
                    "reason": "The submitted department or channel is outside the configured media policy scope.",
                    "findings": [],
                    "rule_results": [],
                    "evidence_conflicts": [],
                    "missing_evidence": [],
                },
                "reason": "The configured media policy does not cover this plan.",
            })
            self._emit(on_step, "media_evaluation", media_step)
        else:
            missing_evidence = self._missing_media_evidence(media_policy, image_evidence)
            task_request = TaskEvaluationRequest(
                "MEDIA_COMPLIANCE", request.input_hash,
                self._media_plan_payload(request), image_evidence, policy=media_policy,
            )
            media_step = self._run_step(
                "MEDIA_COMPLIANCE", self.media_provider, task_request, media_step,
                deadline, lambda output, refs: validate_media_output(
                    output, media_policy, refs, required_evidence_missing=missing_evidence,
                ),
                {item["evidence_id"]: item.get("kind") for item in image_evidence}, on_step,
            )

        # Strategy depends on the submitted plan snapshot and receives extraction evidence when available.
        rubric = configuration.strategy_rubric
        if strategy_step["status"] == "FAILED":
            pass
        elif strategy_step["status"] == "NOT_CONFIGURED":
            strategy_step["error_code"] = "STRATEGY_NOT_CONFIGURED"
        else:
            task_request = TaskEvaluationRequest(
                "STRATEGY_EVALUATION", request.input_hash,
                {key: request.plan.payload.get(key) for key in PLAN_EVIDENCE_FIELDS
                 if request.plan.payload.get(key) not in (None, "", [])},
                all_evidence, rubric=rubric,
            )
            strategy_step = self._run_step(
                "STRATEGY_EVALUATION", self.strategy_provider, task_request, strategy_step,
                deadline, lambda output, refs: validate_strategy_output(output, rubric, refs),
                {item["evidence_id"]: item.get("kind") for item in all_evidence}, on_step,
            )

        errors = []
        if extraction.get("status") == "FAILED":
            errors.append({
                "component": "visual_extraction",
                "code": extraction.get("error_code") or "PROVIDER_ERROR",
                "message": "Image extraction failed; Checker review is required.",
            })
        errors.extend(self._agent_errors(media_step, strategy_step))
        visual_model_version = extraction.get("model_revision") or request.model_version
        if not isinstance(visual_model_version, str) or not visual_model_version.strip():
            errors.append({
                "component": "visual_extraction", "code": "UNKNOWN_MODEL",
                "message": "Image extraction did not provide a pinned model version.",
            })
        if (visual_model_version and
                visual_model_version not in configuration.policy.known_model_versions):
            if not any(item["code"] == "UNKNOWN_MODEL" for item in errors):
                errors.append({
                    "component": "visual_extraction", "code": "UNKNOWN_MODEL",
                    "message": "Image extraction model version is not present in the applied configuration.",
                })
        self._emit(on_step, "media_evaluation", media_step)
        self._emit(on_step, "strategy_evaluation", strategy_step)

        if errors:
            first = errors[0]
            envelope = EvaluationOrchestrator._failure(request, first["code"], first["message"])
            envelope["agent_errors"] = errors
            envelope["evidence"] = contract_evidence
            envelope["raw_output_hash"] = canonical_hash({
                "media": media_step, "strategy": strategy_step,
            })
            envelope["latency_ms"] = max(0, int((time.monotonic() - started) * 1_000))
            return PipelineResult(
                envelope,
                attempts=visual_result.attempts + media_step["attempts"] + strategy_step["attempts"],
                retried=visual_result.retried or media_step["retried"] or strategy_step["retried"],
                visual_extraction=extraction,
                media_evaluation=media_step,
                strategy_evaluation=strategy_step,
            )

        media_output = media_step["result"]
        strategy_output = strategy_step["result"]
        uncertainty = self._extraction_uncertainties(extraction)
        missing_facts = list(uncertainty)
        missing_facts.extend(strategy_output["missing_facts"])
        missing_facts.extend(strategy_output["critical_gaps"])
        missing_facts.extend(
            f"Policy rule {item['rule_id']} needs {item['evidence_kind']} evidence, which extraction did not provide."
            for item in media_output["missing_evidence"]
        )
        conflicts = media_output["evidence_conflicts"] + strategy_output["evidence_conflicts"]
        hard_violations = any(item["severity"] == "HARD_VIOLATION" for item in media_output["findings"])
        auto_recommendation = (
            media_output["outcome"] == "PASS"
            and media_output["confidence"] >= configuration.policy.media_confidence_threshold
            and strategy_output["feasibility_score"] > configuration.policy.feasibility_threshold
            and strategy_output["confidence"] >= configuration.policy.feasibility_confidence_threshold
            and not hard_violations and not conflicts and not missing_facts
            and extraction.get("status") == "SUCCEEDED"
        )
        recommendation = "RECOMMEND_AUTO_APPROVAL" if auto_recommendation else "RECOMMEND_HUMAN_REVIEW"
        if recommendation == "RECOMMEND_AUTO_APPROVAL":
            category = None
            reason = "Media and Strategy checks meet their configured evaluation thresholds; the deterministic engine still applies budget, authority, policy, and state gates."
        else:
            category = "FACT_UNCERTAIN" if missing_facts or conflicts else "POLICY_OUT_OF_SCOPE"
            reason = "Checker review is required because one or more evaluation, evidence, or policy conditions were not met."

        now = utc_now()
        evaluation = {
            "evaluation_id": request.evaluation_id,
            "plan_id": request.plan_id,
            "plan_version": request.plan_version,
            "approval_round": request.approval_round,
            "run_id": request.run_id,
            "schema_version": 1,
            "input_hash": request.input_hash,
            "policy_version": request.policy_version,
            "provider": request.provider,
            "model_version": visual_model_version,
            "status": "SUCCEEDED",
            "media_result": media_output["outcome"],
            "media_findings": media_output["findings"],
            "media_confidence": media_output["confidence"],
            "feasibility_score": strategy_output["feasibility_score"],
            "feasibility_confidence": strategy_output["confidence"],
            "missing_facts": list(dict.fromkeys(missing_facts)),
            "evidence_conflicts": conflicts,
            "evidence": contract_evidence,
            "proposed_action": recommendation,
            "escalation_category": category,
            "reason": reason,
            "latency_ms": max(0, int((time.monotonic() - started) * 1_000)),
            "created_at": now,
            "started_at": now,
            "completed_at": now,
            "agent_errors": [],
            "raw_output_hash": canonical_hash({"media": media_step, "strategy": strategy_step}),
            "reported_model_version": extraction.get("reported_model_id"),
            "correlation_id": request.correlation_id,
            "criterion_scores": [
                {key: value for key, value in item.items() if key != "weight"}
                for item in strategy_output["criterion_scores"]
            ],
            "assumptions": strategy_output["assumptions"],
        }
        return PipelineResult(
            evaluation,
            attempts=visual_result.attempts + media_step["attempts"] + strategy_step["attempts"],
            retried=visual_result.retried or media_step["retried"] or strategy_step["retried"],
            visual_extraction=extraction,
            media_evaluation=media_step,
            strategy_evaluation=strategy_step,
        )

    def _run_step(self, task, provider, task_request, step, deadline, validate, evidence, on_step):
        settings = provider.settings
        step["status"] = "PROCESSING"
        step["started_at"] = utc_now()
        self._emit(on_step, self._step_key(task), step)
        started = time.monotonic()
        last_code = "PROVIDER_ERROR"
        attempts = 0
        raw_hash = None
        while attempts <= settings.max_retries:
            remaining = self._remaining(deadline)
            if remaining <= 0:
                last_code = "PIPELINE_TIMEOUT"
                break
            attempts += 1
            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(provider.evaluate, task_request)
            try:
                output = future.result(timeout=min(remaining, settings.timeout_seconds))
                executor.shutdown(wait=True)
                if not isinstance(output, ProviderAnalysis) or not isinstance(output.output, Mapping):
                    raise ProviderNonRetryableError("Provider returned an invalid response.", code="INVALID_SCHEMA")
                if (output.model_revision != settings.model_version
                        or output.reported_model_id != settings.model_id):
                    raise ProviderNonRetryableError(
                        "Task provider identity did not match the pinned configuration.",
                        code="UNKNOWN_MODEL",
                    )
                raw_hash = output.raw_output_hash
                normalized = validate(output.output, evidence)
                step.update({
                    "status": "SUCCEEDED",
                    "result": normalized,
                    "error_code": None,
                    "reason": normalized.get("reason"),
                })
                break
            except FutureTimeout:
                future.cancel()
                executor.shutdown(wait=False, cancel_futures=True)
                last_code = "PROVIDER_TIMEOUT" if self._remaining(deadline) > 0 else "PIPELINE_TIMEOUT"
            except (ProviderConfigurationError, ProviderNonRetryableError) as exc:
                executor.shutdown(wait=True)
                last_code = exc.code
                if isinstance(exc, ProviderConfigurationError) or exc.code not in {"INVALID_SCHEMA", "INVALID_PROVIDER_RESPONSE"}:
                    break
            except ProviderTimeout as exc:
                executor.shutdown(wait=True)
                last_code = exc.code
            except ProviderError as exc:
                executor.shutdown(wait=True)
                last_code = exc.code
            except ValueError:
                executor.shutdown(wait=True)
                last_code = "INVALID_SCHEMA"
            except Exception:
                executor.shutdown(wait=True)
                last_code = "PROVIDER_ERROR"
            if attempts > settings.max_retries:
                break

        if step["status"] != "SUCCEEDED":
            step.update({
                "status": "TIMED_OUT" if last_code in {"PROVIDER_TIMEOUT", "PIPELINE_TIMEOUT"} else "FAILED",
                "result": None,
                "error_code": last_code,
                "reason": "Evaluation could not be completed; Checker review is required.",
            })
        step["attempts"] = attempts
        step["retried"] = attempts > 1
        step["raw_output_hash"] = raw_hash
        step["completed_at"] = utc_now()
        step["latency_ms"] = max(0, int((time.monotonic() - started) * 1_000))
        self._emit(on_step, self._step_key(task), step)
        return step

    @staticmethod
    def _step_key(task):
        return "media_evaluation" if task == "MEDIA_COMPLIANCE" else "strategy_evaluation"

    @staticmethod
    def _emit(callback, name, value):
        if callback:
            callback(name, dict(value))

    @staticmethod
    def _remaining(deadline):
        return max(0, deadline - time.monotonic())

    @staticmethod
    def _complete_failed(step, code, reason):
        step.update({
            "status": "FAILED", "error_code": code, "reason": reason,
            "started_at": utc_now(), "completed_at": utc_now(), "latency_ms": 0,
        })

    @staticmethod
    def _image_evidence(extraction):
        result = []
        for attachment in extraction.get("attachments", []):
            for evidence in attachment.get("evidence", []):
                result.append({
                    "evidence_id": evidence["evidence_id"],
                    "kind": evidence["kind"],
                    "source_type": "ATTACHMENT",
                    "source_ref": evidence["source_attachment_id"],
                    "observation": evidence["text"],
                    "content_hash": evidence["source_content_hash"],
                })
        return result

    @staticmethod
    def _plan_evidence(request):
        result = []
        for field in PLAN_EVIDENCE_FIELDS:
            value = request.plan.payload.get(field)
            if value in (None, "", [], ()):
                continue
            if isinstance(value, (list, tuple)):
                observation = ", ".join(str(item) for item in value)
            else:
                observation = str(value)
            result.append({
                "evidence_id": "plan-field:" + field,
                "source_type": "PLAN_FIELD",
                "source_ref": field,
                "observation": observation,
                "content_hash": None,
            })
        return result

    @staticmethod
    def _media_plan_payload(request):
        return {
            field: request.plan.payload.get(field)
            for field in ("title", "department", "channels")
        }

    @staticmethod
    def _missing_media_evidence(policy, evidence):
        kinds = {item["kind"] for item in evidence}
        return [
            {"rule_id": rule.rule_id, "evidence_kind": kind}
            for rule in policy.rules
            for kind in rule.required_evidence_kinds
            if kind not in kinds
        ]

    @staticmethod
    def _extraction_uncertainties(extraction):
        return [item["text"] for attachment in extraction.get("attachments", [])
                for item in attachment.get("uncertainties", [])]

    @staticmethod
    def _agent_errors(media, strategy):
        errors = []
        for step in (media, strategy):
            if step["status"] in {"NOT_CONFIGURED", "FAILED", "TIMED_OUT", "REVIEW_REQUIRED"}:
                code = step["error_code"] or ("MEDIA_POLICY_OUT_OF_SCOPE"
                       if step["step"] == "MEDIA_COMPLIANCE" else "STRATEGY_REVIEW_REQUIRED")
                errors.append({
                    "component": step["step"].lower(),
                    "code": code,
                    "message": step.get("reason") or "Agent evaluation requires Checker review.",
                })
        return errors

    @staticmethod
    def _failed(request, code, message):
        envelope = EvaluationOrchestrator._failure(request, code, message)
        return PipelineResult(envelope, 0, False)
