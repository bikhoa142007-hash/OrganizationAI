"""Bounded Ollama verification with synthetic data and no application database."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
import httpx
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.ai_pipeline.models import EvaluationRequest
from src.ai_pipeline.orchestrator import EvaluationOrchestrator
from src.ai_pipeline.providers.base import ProviderError, ProviderNonRetryableError
from src.ai_pipeline.providers.ollama_identity import verify_ollama_model_digest
from src.ai_pipeline.providers.openai_provider import LocalVLMProvider, _validate_base_url
from src.ai_pipeline.task_evaluation import (
    MEDIA_OUTPUT_SCHEMA, MEDIA_PROMPT_VERSION, MEDIA_SCHEMA_VERSION, MEDIA_SYSTEM_PROMPT,
    STRATEGY_OUTPUT_SCHEMA, STRATEGY_PROMPT_VERSION, STRATEGY_SCHEMA_VERSION,
    STRATEGY_SYSTEM_PROMPT, PolicyOutputConflictError, STRATEGY_CRITERIA,
    validate_media_output, validate_strategy_output,
)
from src.ai_pipeline.task_providers import (
    OpenAICompatibleTaskProvider, SUPPORTED_PROTOCOL, TaskEvaluationRequest, TaskModelSettings,
)
from src.ai_pipeline.vlm_extraction import (
    OUTPUT_JSON_SCHEMA as VLM_OUTPUT_SCHEMA, PROMPT_VERSION as VLM_PROMPT_VERSION,
    SCHEMA_VERSION as VLM_SCHEMA_VERSION, SYSTEM_PROMPT as VLM_SYSTEM_PROMPT,
)
from src.backend.domain.models import AttachmentManifest, MarketingPlan
from src.backend.domain.policy import MediaCompliancePolicy, MediaPolicyRule, StrategyCriterion, StrategyRubric
from src.shared.validation import canonical_hash
OUT_DIR = ROOT / "docs/integration/evidence/scope1-c-20261012"
OUT_FILE = OUT_DIR / "real-inference-post-contract-20261012.json"
SOURCE_FILES = (
    "scripts/ai_scope1/run_local_task_inference.py",
    "src/ai_pipeline/providers/ollama_identity.py",
    "src/ai_pipeline/providers/openai_provider.py",
    "src/ai_pipeline/task_providers.py",
    "src/ai_pipeline/task_evaluation.py",
    "src/ai_pipeline/authenticated_orchestrator.py",
    "src/ai_pipeline/vlm_extraction.py",
    "src/ai_pipeline/orchestrator.py",
    "tests/unit/ai_pipeline/test_ollama_model_identity.py",
    "tests/unit/ai_pipeline/test_task_output_conflicts.py",
    "tests/unit/ai_pipeline/test_task_evaluations.py",
    "tests/unit/ai_pipeline/test_task_providers.py",
    "tests/unit/ai_pipeline/test_authenticated_orchestrator.py",
)
SHA = re.compile(r"^sha256:[0-9a-f]{64}$")

def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def fingerprint() -> dict[str, Any]:
    hashes = {name: digest((ROOT / name).read_bytes()) for name in SOURCE_FILES}
    try:
        source_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
            check=True, capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        source_sha = None
    return {"source_sha": source_sha, "source_fingerprint": canonical_hash(hashes),
            "source_files_sha256": hashes}

def root_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    return base[:-3] if base.endswith("/v1") else base

def inventory(client: httpx.Client, base_url: str, model_id: str) -> dict[str, Any] | None:
    response = client.get(root_url(base_url) + "/api/tags", timeout=5)
    if response.status_code != 200:
        raise RuntimeError("LOCAL_MODEL_INVENTORY_UNAVAILABLE")
    models = response.json().get("models")
    if not isinstance(models, list):
        raise RuntimeError("LOCAL_MODEL_INVENTORY_INVALID")
    found = next((item for item in models if isinstance(item, dict) and item.get("name") == model_id), None)
    if found is None:
        return {"model_id": model_id, "present": False}
    details = found.get("details") if isinstance(found.get("details"), dict) else {}
    context = None
    try:
        show = client.post(root_url(base_url) + "/api/show", json={"name": model_id}, timeout=5)
        params = show.json().get("parameters", "") if show.status_code == 200 else ""
        match = re.search(r"(?m)^num_ctx\s+(\d+)\s*$", params) if isinstance(params, str) else None
        context = int(match.group(1)) if match else None
    except (httpx.HTTPError, ValueError, AttributeError):
        pass
    return {"model_id": model_id, "present": True, "digest": found.get("digest"),
            "size_bytes": found.get("size"), "parameter_size": details.get("parameter_size"),
            "quantization": details.get("quantization_level"), "family": details.get("family"),
            "base_context_length": details.get("context_length"), "configured_num_ctx": context}

def runtime_version() -> str | None:
    try:
        r = subprocess.run(["ollama", "--version"], check=True, capture_output=True, text=True, timeout=5)
        return (r.stdout or r.stderr).strip()[:120]
    except (OSError, subprocess.SubprocessError):
        return None

def hardware() -> str | None:
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
                            "--format=csv,noheader"], check=True, capture_output=True, text=True, timeout=5)
        return r.stdout.strip()[:300]
    except (OSError, subprocess.SubprocessError):
        return None

def settings_for(task: str, args: argparse.Namespace) -> TaskModelSettings:
    media = task == "MEDIA_COMPLIANCE"
    prefix = "AUTH_WORKFLOW_MEDIA" if media else "AUTH_WORKFLOW_STRATEGY"
    prompt = MEDIA_PROMPT_VERSION if media else STRATEGY_PROMPT_VERSION
    schema = MEDIA_SCHEMA_VERSION if media else STRATEGY_SCHEMA_VERSION
    return TaskModelSettings.from_environment(task, {
        prefix + "_PROVIDER": SUPPORTED_PROTOCOL, prefix + "_BASE_URL": args.base_url,
        prefix + "_MODEL": args.task_model_id, prefix + "_MODEL_VERSION": args.task_model_digest,
        prefix + "_IDENTITY_MODE": "OLLAMA_TAG_DIGEST",
        prefix + "_ALLOW_REMOTE": "false", prefix + "_TIMEOUT_SECONDS": str(args.timeout_seconds),
        prefix + "_MAX_OUTPUT_TOKENS": "2048", prefix + "_MAX_RESPONSE_BYTES": "262144",
        prefix + "_MAX_INPUT_BYTES": "1048576", prefix + "_MAX_RETRIES": "0",
        prefix + "_REASONING_EFFORT": "none", prefix + "_PROMPT_VERSION": prompt,
        prefix + "_SCHEMA_VERSION": schema,
    })

def make_plan(complete: bool) -> dict[str, Any]:
    if not complete:
        return {"title": "Synthetic incomplete campaign", "department": "Synthetic Lab",
                "objective": "Promote a fictional weekend workshop.",
                "summary": "A short synthetic social post is proposed.",
                "channels": ["social"], "currency": "VND"}
    return {"title": "Synthetic neighborhood workshop campaign", "department": "Synthetic Lab",
        "objective": "Reach 120 registrations for a fictional weekend workshop.",
        "summary": "Synthetic prior exercise: 200 impressions, 40 clicks, 8 registrations.",
        "start_date": "2026-11-01", "end_date": "2026-11-14",
        "budget_minor_units": "1200000", "currency": "VND",
        "target_audience": "Adults in a fictional district interested in weekend workshops.",
        "channels": ["social"], "kpi_expected": "120 registrations and 90 attendees by 2026-11-14.",
        "notes": "Synthetic risk controls: cap daily spend; stop above 10000 VND per registration; check accessibility."}

def evidence_for_plan(payload: dict[str, Any], include_missing: bool) -> list[dict[str, str]]:
    fields = ("title", "objective", "summary", "department", "start_date", "end_date",
              "budget_minor_units", "currency", "target_audience", "channels", "kpi_expected", "notes")
    output = []
    for field in fields:
        value = payload.get(field)
        if value in (None, "", []):
            if include_missing:
                output.append({"evidence_id": "plan-field:" + field, "kind": "PLAN_FIELD",
                               "text": f"Synthetic submission did not provide {field}."})
            continue
        text = ", ".join(str(x) for x in value) if isinstance(value, list) else str(value)
        output.append({"evidence_id": "plan-field:" + field, "kind": "PLAN_FIELD", "text": text})
    return output

def media_policy() -> MediaCompliancePolicy:
    return MediaCompliancePolicy(policy_id="C-SYNTH-MEDIA-1", policy_version="1.0", status="ACTIVE",
        scope_departments=("Synthetic Lab",), scope_channels=("social",), rules=(MediaPolicyRule(
            rule_id="NO-GUARANTEED-RESULT", severity="HARD_VIOLATION",
            description="Do not make an exact guaranteed-result claim.",
            required_evidence_kinds=("OCR_TEXT",), forbidden_literals=("GUARANTEED RESULT",)),))

def strategy_rubric() -> StrategyRubric:
    return StrategyRubric(rubric_id="C-SYNTH-STRATEGY-7", rubric_version="1.0", status="ACTIVE",
        criteria=tuple(StrategyCriterion(criterion_id=i, label=label, weight=weight)
                       for i, label, weight in STRATEGY_CRITERIA))

def validate_task_output(task: str, analysis: Any, request: TaskEvaluationRequest, config: Any) -> dict[str, Any]:
    if task == "MEDIA_COMPLIANCE":
        refs = {item["evidence_id"]: {"kind": item["kind"], "observation": item["text"]}
                for item in request.evidence}
        return validate_media_output(analysis.output, config, refs)
    refs = {item["evidence_id"]: item.get("kind") for item in request.evidence}
    return validate_strategy_output(analysis.output, config, refs)

def scripted_checks(task: str, case_id: str, normalized: dict[str, Any]) -> dict[str, bool]:
    if task == "MEDIA_COMPLIANCE":
        hard = sum(x["severity"] == "HARD_VIOLATION" for x in normalized["findings"])
        return {"expected_policy_outcome": normalized["outcome"] ==
                ("REVIEW_REQUIRED" if case_id == "media-marker" else "PASS"),
                "hard_violation_grounding": hard > 0 if case_id == "media-marker" else hard == 0,
                "no_evidence_conflicts": not normalized["evidence_conflicts"]}
    scores = normalized["criterion_scores"]
    cited = len(scores) == 7 and all(item["evidence_refs"] for item in scores)
    if case_id == "strategy-complete":
        return {"all_criteria_scored_and_cited": cited,
                "score_above_70": normalized["feasibility_score"] > 70,
                "no_material_gaps": not normalized["missing_facts"] and not normalized["critical_gaps"],
                "no_conflicts": not normalized["evidence_conflicts"],
                "score_not_zero": normalized["feasibility_score"] > 0}
    return {"all_criteria_scored_and_cited": cited,
            "incomplete_case_surfaces_gaps": bool(normalized["missing_facts"] or normalized["critical_gaps"]),
            "missing_facts_not_called_conflicts": not normalized["evidence_conflicts"],
            "score_not_zero": normalized["feasibility_score"] > 0}

def run_task_case(task: str, case_id: str, args: argparse.Namespace, client: httpx.Client) -> dict[str, Any]:
    started = time.monotonic()
    complete = case_id not in {"strategy-incomplete"}
    payload = make_plan(complete)
    evidence = evidence_for_plan(payload, include_missing=not complete)
    if task == "MEDIA_COMPLIANCE":
        ocr = "Register for a fictional workshop this weekend."
        if case_id == "media-marker":
            ocr += " GUARANTEED RESULT"
        evidence.append({"evidence_id": "synthetic-image-ocr-1", "kind": "OCR_TEXT", "text": ocr})
        config = media_policy()
    else:
        config = strategy_rubric()
    request = TaskEvaluationRequest(
        task=task,
        input_hash=canonical_hash({"case_id": case_id, "plan": payload, "evidence": evidence}),
        plan_payload=payload,
        evidence=evidence,
        policy=config if task == "MEDIA_COMPLIANCE" else None,
        rubric=config if task == "STRATEGY_EVALUATION" else None,
    )
    settings = settings_for(task, args)
    provider = OpenAICompatibleTaskProvider(settings, client=client)
    result: dict[str, Any] = {
        "case_id": case_id, "task": task, "expected": (
            "REVIEW_REQUIRED" if case_id == "media-marker" else
            "PASS" if task == "MEDIA_COMPLIANCE" else
            "GAPS_REPORTED" if case_id == "strategy-incomplete" else "NO_MATERIAL_GAPS"
        ),
        "prompt_version": settings.prompt_version, "schema_version": settings.schema_version,
        "timeout_seconds": settings.timeout_seconds, "max_retries": settings.max_retries,
    }
    try:
        analysis = provider.evaluate(request)
        normalized = validate_task_output(task, analysis, request, config)
        result.update({
            "provider_call": "SUCCEEDED", "schema_valid": True, "policy_valid": True,
            "model_id_reported": analysis.reported_model_id,
            "model_digest_verified": analysis.model_revision,
            "output_sha256": analysis.raw_output_hash,
            "checks": scripted_checks(task, case_id, normalized),
        })
        if task == "MEDIA_COMPLIANCE":
            result["observed"] = normalized["outcome"]
            result["hard_violation_count"] = sum(
                item["severity"] == "HARD_VIOLATION" for item in normalized["findings"])
            result["warning_count"] = sum(item["severity"] == "WARNING" for item in normalized["findings"])
            result["evidence_conflict_count"] = len(normalized["evidence_conflicts"])
        else:
            result["observed"] = "GAPS_REPORTED" if (
                normalized["missing_facts"] or normalized["critical_gaps"]) else "NO_MATERIAL_GAPS"
            result["feasibility_score"] = normalized["feasibility_score"]
            result["confidence"] = normalized["confidence"]
            result["criterion_count"] = len(normalized["criterion_scores"])
            result["all_criteria_cited"] = all(x["evidence_refs"] for x in normalized["criterion_scores"])
            result["assumption_count"] = len(normalized["assumptions"])
            result["missing_fact_count"] = len(normalized["missing_facts"])
            result["critical_gap_count"] = len(normalized["critical_gaps"])
            result["evidence_conflict_count"] = len(normalized["evidence_conflicts"])
    except PolicyOutputConflictError as exc:
        result.update({"provider_call": "SUCCEEDED", "schema_valid": True,
                       "policy_valid": False, "error_code": "POLICY_OUTPUT_CONFLICT",
                       "policy_conflict_reason": str(exc)})
    except ProviderError as exc:
        result.update({"provider_call": "FAILED", "schema_valid": False,
                       "policy_valid": False, "error_code": getattr(exc, "code", "PROVIDER_ERROR")})
    except (TypeError, ValueError):
        result.update({"provider_call": "SUCCEEDED", "schema_valid": False,
                       "policy_valid": False, "error_code": "INVALID_SCHEMA_OR_OUTPUT"})
    result["latency_ms"] = round((time.monotonic() - started) * 1000)
    result["scripted_quality_pass"] = bool(result.get("checks")) and all(result["checks"].values())
    result["expected_result_pass"] = result.get("observed") == result["expected"]
    return result

def synthetic_png() -> bytes:
    import struct
    import zlib
    width, height = 64, 32
    raw = b"".join(b"\x00" + b"\xff\xff\xff" * width for _ in range(height))
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">2I5B", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))

def run_visual_preflight(args: argparse.Namespace) -> dict[str, Any]:
    content = synthetic_png()
    content_hash = digest(content)
    attachment = AttachmentManifest(
        attachment_id="synthetic-attachment-c-1", content_hash=content_hash,
        media_type="image/png", byte_size=len(content))
    plan = MarketingPlan(
        plan_id="SYNTH-C-001", plan_version=1, approval_round=1,
        payload=make_plan(True), attachments=(attachment,))
    request = EvaluationRequest(
        plan=plan, policy_version="C-SYNTH-POLICY-1",
        evaluation_id="SYNTH-EVAL-C-1", run_id="SYNTH-RUN-C-1",
        correlation_id="SYNTH-CORR-C-1", provider="LOCAL_VLM",
        model_version=args.visual_model_digest,
        metadata={"model_id": args.visual_model_id,
                  "attachment_contents": {attachment.attachment_id: content}})
    calls: list[dict[str, str]] = []
    def record_request(request):
        calls.append({"method": request.method, "path": request.url.path})
    client = httpx.Client(trust_env=False, event_hooks={"request": [record_request]})
    started = time.monotonic()
    try:
        provider = LocalVLMProvider(
            model=args.visual_model_id, model_version=args.visual_model_digest,
            base_url=args.base_url, allow_remote=False, timeout_seconds=args.timeout_seconds,
            max_output_tokens=1536, max_response_bytes=262144, max_input_bytes=1048576,
            client=client)
        result = EvaluationOrchestrator(
            provider, timeout_seconds=args.timeout_seconds, max_retries=0).evaluate(request)
        extraction = result.visual_extraction or {}
        error_codes = [item.get("code") for item in result.evaluation.get("agent_errors", [])]
        return {
            "provider": "LOCAL_VLM", "status": extraction.get("status"),
            "error_code": extraction.get("error_code") or (error_codes[0] if error_codes else None),
            "image_sha256": content_hash, "image_bytes": len(content),
            "image_request_sent": any(item["path"].endswith("/chat/completions") for item in calls),
            "runtime_requests": calls, "attempts": result.attempts, "max_retries": 0,
            "prompt_version": VLM_PROMPT_VERSION, "schema_version": VLM_SCHEMA_VERSION,
            "expected_digest": args.visual_model_digest,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "persistence": "NOT_RUN", "application_routing": "NOT_RUN",
        }
    finally:
        client.close()

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:11434/v1")
    parser.add_argument("--task-model-id", required=True)
    parser.add_argument("--task-model-digest", required=True)
    parser.add_argument("--visual-model-id", required=True)
    parser.add_argument("--visual-model-digest", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.timeout_seconds <= 45:
        parser.error("--timeout-seconds must be between 1 and 45")
    if not SHA.fullmatch(args.task_model_digest) or not SHA.fullmatch(args.visual_model_digest):
        parser.error("Model digests must use sha256:<64 lowercase hex characters>")
    endpoint_error = _validate_base_url(args.base_url, allow_remote=False)
    if endpoint_error:
        parser.error("Only a local model endpoint is permitted")
    started_at = now()
    evidence: dict[str, Any] = {
        "run_started_at": started_at,
        "scope": "synthetic local inference; serial concurrency=1; no retry; no app database",
        "endpoint_fingerprint": hashlib.sha256(args.base_url.encode("utf-8")).hexdigest(),
        "timeout_seconds_per_inference": args.timeout_seconds,
        "max_retries": 0,
        "runtime_version": runtime_version(),
        "hardware": hardware(),
        "prompt_schema": {
            "visual": {"prompt": VLM_PROMPT_VERSION, "schema": VLM_SCHEMA_VERSION},
            "media": {"prompt": MEDIA_PROMPT_VERSION, "schema": MEDIA_SCHEMA_VERSION},
            "strategy": {"prompt": STRATEGY_PROMPT_VERSION, "schema": STRATEGY_SCHEMA_VERSION},
        },
        "source": fingerprint(),
        "models": {},
        "gates": {},
        "cases": [],
        "limitations": [
            "Synthetic development fixtures only; no independent holdout was available.",
            "Results do not estimate general model accuracy.",
            "This harness does not invoke application database persistence or full app routing.",
        ],
    }
    try:
        with httpx.Client(trust_env=False) as client:
            try:
                response = client.get(args.base_url.rstrip("/") + "/models", timeout=5)
                listed = []
                if response.status_code == 200:
                    data = response.json().get("data", [])
                    if isinstance(data, list):
                        listed = [item.get("id") for item in data
                                  if isinstance(item, dict) and isinstance(item.get("id"), str)]
                connection = response.status_code == 200
                connection_error = None if connection else "LOCAL_PROVIDER_HTTP_ERROR"
            except (httpx.HTTPError, ValueError):
                listed, connection, connection_error = [], False, "LOCAL_PROVIDER_UNAVAILABLE"
            evidence["gates"]["provider_connection"] = {
                "status": "PASS" if connection else "BLOCKED",
                "openai_compatible_models_endpoint": connection,
                "task_model_list_contains_configured_id": args.task_model_id in listed,
                "visual_model_list_contains_configured_id": args.visual_model_id in listed,
                "error_code": connection_error,
            }
            for kind, model_id, expected in (
                ("task", args.task_model_id, args.task_model_digest),
                ("visual", args.visual_model_id, args.visual_model_digest),
            ):
                try:
                    found = inventory(client, args.base_url, model_id)
                except (httpx.HTTPError, RuntimeError, ValueError):
                    found = None
                actual = found.get("digest") if found else None
                identity_ok = bool(
                    found and found.get("present") and isinstance(actual, str)
                    and ("sha256:" + actual.removeprefix("sha256:").lower()) == expected
                )
                evidence["models"][kind] = {
                    **(found or {"model_id": model_id, "present": False}),
                    "expected_digest": expected,
                    "identity_valid": identity_ok,
                }
            task_ok = evidence["models"]["task"]["identity_valid"]
            visual_ok = evidence["models"]["visual"]["identity_valid"]
            evidence["gates"]["model_identity"] = {
                "status": "PASS" if task_ok and visual_ok else "FAIL",
                "task_model": "PASS" if task_ok else "FAIL",
                "visual_model": "PASS" if visual_ok else "FAIL",
                "digest_pin_changed": False,
            }
            if task_ok and connection:
                for task, case_id in (
                    ("MEDIA_COMPLIANCE", "media-clean"),
                    ("MEDIA_COMPLIANCE", "media-marker"),
                    ("STRATEGY_EVALUATION", "strategy-complete"),
                    ("STRATEGY_EVALUATION", "strategy-incomplete"),
                ):
                    evidence["cases"].append(run_task_case(task, case_id, args, client))
            else:
                evidence["gates"]["real_task_inference"] = {
                    "status": "BLOCKED", "reason": "Provider connection or task-model digest gate failed.",
                    "cases_run": 0,
                }
        visual = run_visual_preflight(args)
        evidence["visual_preflight"] = visual
        evidence["gates"]["visual_real_inference"] = {
            "status": "PASS" if visual.get("status") == "SUCCEEDED" and not visual.get("error_code")
            else "BLOCKED" if visual.get("error_code") == "MODEL_DIGEST_MISMATCH"
            else "FAIL",
            "image_sent": visual.get("image_request_sent", False),
            "error_code": visual.get("error_code"),
        }
        if evidence["cases"]:
            evidence["gates"]["task_schema_validity"] = {
                "status": "PASS" if all(item.get("schema_valid") for item in evidence["cases"]) else "FAIL",
                "valid_cases": sum(bool(item.get("schema_valid")) for item in evidence["cases"]),
                "total_cases": len(evidence["cases"]),
            }
            evidence["gates"]["scripted_policy_quality"] = {
                "status": "PASS" if all(item.get("scripted_quality_pass")
                                         and item.get("expected_result_pass")
                                         for item in evidence["cases"]) else "FAIL",
                "passing_cases": sum(bool(item.get("scripted_quality_pass")
                                           and item.get("expected_result_pass"))
                                     for item in evidence["cases"]),
                "total_cases": len(evidence["cases"]),
            }
            evidence["gates"]["real_task_inference"] = {
                "status": "PASS" if all(item.get("provider_call") == "SUCCEEDED"
                                         for item in evidence["cases"]) else "FAIL",
                "cases_run": len(evidence["cases"]),
            }
        else:
            evidence["gates"].setdefault("task_schema_validity", {"status": "BLOCKED", "cases_run": 0})
            evidence["gates"].setdefault("scripted_policy_quality", {"status": "BLOCKED", "cases_run": 0})
        evidence["gates"]["pipeline_persistence_and_routing"] = {
            "status": "NOT_RUN", "reason": "Harness-only verification; no temporary DB or full application wiring."
        }
        evidence["gates"]["independent_holdout"] = {"status": "NOT_RUN", "cases": 0}
        evidence["gates"]["unit_contract_tests"] = {
            "status": "PENDING", "command": "pytest -q tests/unit/ai_pipeline"
        }
    except Exception as exc:
        evidence["harness_error"] = type(exc).__name__
    evidence["run_completed_at"] = now()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "evidence_file": str(OUT_FILE),
        "gates": evidence["gates"],
        "models": evidence["models"],
        "cases": [{"case_id": x["case_id"], "provider_call": x["provider_call"],
                   "schema_valid": x["schema_valid"], "scripted_quality_pass": x["scripted_quality_pass"]}
                  for x in evidence["cases"]],
    }, indent=2))
    return 0 if not evidence.get("harness_error") else 2

if __name__ == "__main__":
    raise SystemExit(main())
