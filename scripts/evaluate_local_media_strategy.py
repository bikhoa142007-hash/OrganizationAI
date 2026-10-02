"""Run the bounded synthetic Media/Strategy set against local Ollama models."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlsplit

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ai_pipeline.authenticated_orchestrator import PLAN_EVIDENCE_FIELDS
from src.ai_pipeline.providers.base import ProviderError
from src.ai_pipeline.task_evaluation import (
    media_policy_from_json,
    strategy_rubric_from_json,
    validate_media_output,
    validate_strategy_output,
)
from src.ai_pipeline.task_providers import (
    OpenAICompatibleTaskProvider,
    TaskEvaluationRequest,
    TaskModelSettings,
)
from src.shared.validation import canonical_hash


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "tests/fixtures/media_strategy_eval/dataset.json"
DEFAULT_REPORT = ROOT / "docs/integration/media-strategy-evaluation-2026-10-02.json"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
EXPECTED_TEXT_MODEL = "organizationai-qwen3:4b-ctx8192"
EXPECTED_CONTEXT_SIZE = 8192
STRATEGY_CRITERION_STATES = {
    "PRESENT", "PARTIAL", "MISSING", "UNSUPPORTED_TARGET", "NO_BENCHMARK", "CONFLICT",
}


def _dotenv_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value[1:-1]
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("\\'", "'")
    return value


def read_env_file(path: Path) -> dict[str, str]:
    values = {}
    if not path.is_file():
        raise ValueError("The local .env file is required for a pinned evaluation.")
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = _dotenv_value(value)
    return values


def load_dataset(path: Path) -> tuple[dict, list[dict]]:
    dataset = json.loads(path.read_text(encoding="utf-8"))
    if dataset.get("label_status") != "PROPOSED_NOT_HUMAN_APPROVED":
        raise ValueError("Evaluation labels must remain marked as proposed.")
    cases = dataset.get("cases")
    if not isinstance(cases, list) or not 12 <= len(cases) <= 20:
        raise ValueError("The evaluation set must contain between 12 and 20 cases.")
    case_ids = [case.get("case_id") for case in cases]
    if any(not isinstance(case_id, str) or not case_id for case_id in case_ids):
        raise ValueError("Every evaluation case needs a nonblank case_id.")
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("Evaluation case IDs must be unique.")
    if {case.get("split") for case in cases} != {"tune", "holdout"}:
        raise ValueError("The dataset must contain separate tune and holdout cases.")

    media_policy = media_policy_from_json(json.dumps(dataset.get("policy"), ensure_ascii=False))
    strategy_rubric = strategy_rubric_from_json(json.dumps(dataset.get("rubric"), ensure_ascii=False))
    if media_policy is None or strategy_rubric is None:
        raise ValueError("Synthetic policy and rubric snapshots are required.")
    for case in cases:
        if case.get("task") == "MEDIA_COMPLIANCE":
            if case.get("policy_version") != media_policy.policy_version or case.get("rubric_version") is not None:
                raise ValueError(f"{case['case_id']} has a mismatched media policy version.")
        elif case.get("task") == "STRATEGY_EVALUATION":
            if case.get("rubric_version") != strategy_rubric.rubric_version or case.get("policy_version") is not None:
                raise ValueError(f"{case['case_id']} has a mismatched strategy rubric version.")
        else:
            raise ValueError(f"{case['case_id']} has an unsupported task.")
        if not isinstance(case.get("input"), dict) or not isinstance(case.get("expected"), dict):
            raise ValueError(f"{case['case_id']} must separate input and expected labels.")
        if case["task"] == "STRATEGY_EVALUATION":
            states = case["expected"].get("criterion_states")
            expected_criteria = {item.criterion_id for item in strategy_rubric.criteria}
            if not isinstance(states, dict) or set(states) != expected_criteria:
                raise ValueError(f"{case['case_id']} must propose an information-state label for every criterion.")
            if not set(states.values()) <= STRATEGY_CRITERION_STATES:
                raise ValueError(f"{case['case_id']} has an unsupported criterion information-state label.")
    return dataset, cases


def build_task_request(case: dict, policy, rubric) -> TaskEvaluationRequest:
    """Build a provider request from input only; case IDs and expected labels stay out."""
    task = case["task"]
    plan = case["input"]["plan"]
    supplied_evidence = case["input"].get("evidence", [])
    if task == "MEDIA_COMPLIANCE":
        payload = {key: plan.get(key) for key in ("title", "department", "channels")}
        evidence = [dict(item) for item in supplied_evidence]
        return TaskEvaluationRequest(
            task=task, input_hash=canonical_hash(case["input"]),
            plan_payload=payload, evidence=evidence, policy=policy,
        )

    payload = {
        key: plan.get(key) for key in PLAN_EVIDENCE_FIELDS
        if plan.get(key) not in (None, "", [], ())
    }
    evidence = [dict(item) for item in supplied_evidence]
    for field in PLAN_EVIDENCE_FIELDS:
        value = plan.get(field)
        if value in (None, "", [], ()):
            continue
        observation = ", ".join(str(item) for item in value) if isinstance(value, (list, tuple)) else str(value)
        evidence.append({
            "evidence_id": "plan-field:" + field,
            "source_type": "PLAN_FIELD",
            "source_ref": field,
            "observation": observation,
            "content_hash": None,
        })
    return TaskEvaluationRequest(
        task=task, input_hash=canonical_hash(case["input"]),
        plan_payload=payload, evidence=evidence, rubric=rubric,
    )


def _local_root(base_url: str) -> str:
    parsed = urlsplit(base_url)
    if parsed.scheme != "http" or parsed.hostname not in LOCAL_HOSTS or parsed.port != 11434:
        raise ValueError("The evaluator accepts only the local Ollama loopback endpoint on port 11434.")
    return f"http://{parsed.hostname}:{parsed.port}"


def _ollama_json(client: httpx.Client, root: str, path: str, *, body=None) -> dict:
    response = client.get(root + path) if body is None else client.post(root + path, json=body)
    response.raise_for_status()
    value = response.json()
    if not isinstance(value, dict):
        raise ValueError("Ollama returned an invalid metadata response.")
    return value


def _model_preflight(client: httpx.Client, settings, root: str) -> dict:
    tags = _ollama_json(client, root, "/api/tags")
    models = tags.get("models")
    model = next((item for item in models or [] if item.get("name") == settings.model_id), None)
    if model is None:
        raise ValueError("The configured local task model is not present in Ollama.")
    observed_digest = "sha256:" + model.get("digest", "")
    if observed_digest != settings.model_version:
        raise ValueError("The configured model digest does not match the local Ollama tag.")
    metadata = _ollama_json(client, root, "/api/show", body={"model": settings.model_id})
    parameters = metadata.get("parameters") or ""
    context_match = re.search(r"(?m)^\s*num_ctx\s+(\d+)\s*$", parameters)
    if context_match is None or int(context_match.group(1)) != EXPECTED_CONTEXT_SIZE:
        raise ValueError("The task model does not declare the expected 8192-token context.")
    try:
        resident = _ollama_json(client, root, "/api/ps").get("models", [])
    except (httpx.HTTPError, ValueError):
        resident = []
    return {
        "provider": settings.provider,
        "model_id": settings.model_id,
        "configured_model_version": settings.model_version,
        "observed_ollama_digest": observed_digest,
        "context_size": int(context_match.group(1)),
        "remote_access_enabled": settings.allow_remote,
        "initially_loaded": any(item.get("name") == settings.model_id for item in resident),
    }


def _media_missing_evidence(policy, evidence: list[dict]) -> list[dict]:
    available = {item.get("kind") for item in evidence}
    return [
        {"rule_id": rule.rule_id, "evidence_kind": kind}
        for rule in policy.rules
        for kind in rule.required_evidence_kinds
        if kind not in available
    ]


def _references(raw: dict, task: str) -> set[str]:
    refs = set()
    if task == "MEDIA_COMPLIANCE":
        for collection in ("rule_results", "findings", "evidence_conflicts"):
            for item in raw.get(collection, []) if isinstance(raw.get(collection), list) else []:
                refs.update(ref for ref in item.get("evidence_refs", []) if isinstance(ref, str))
    else:
        for item in raw.get("criterion_scores", []) if isinstance(raw.get("criterion_scores"), list) else []:
            refs.update(ref for ref in item.get("evidence_refs", []) if isinstance(ref, str))
        for item in raw.get("evidence_conflicts", []) if isinstance(raw.get("evidence_conflicts"), list) else []:
            refs.update(ref for ref in item.get("evidence_refs", []) if isinstance(ref, str))
    return refs


def _run_case(case, provider, policy, rubric, client: httpx.Client, root: str) -> dict:
    request = build_task_request(case, policy, rubric)
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    before = time.perf_counter()
    output = None
    normalized = None
    error_code = None
    error_reason = None
    validator_error = None
    try:
        analysis = provider.evaluate(request)
        output = analysis.output
        if case["task"] == "MEDIA_COMPLIANCE":
            evidence_map = {item["evidence_id"]: item for item in request.evidence}
            normalized = validate_media_output(
                output, policy, evidence_map,
                required_evidence_missing=_media_missing_evidence(policy, request.evidence),
            )
        else:
            evidence_ids = {item["evidence_id"] for item in request.evidence}
            normalized = validate_strategy_output(output, rubric, evidence_ids)
    except ProviderError as exc:
        error_code = getattr(exc, "code", "PROVIDER_ERROR")
        error_reason = str(exc)
    except (TypeError, ValueError, KeyError) as exc:
        error_code = "INVALID_SCHEMA"
        validator_error = str(exc)
        error_reason = "The raw model output failed local schema or evidence validation."
    except Exception as exc:  # Keep an unforeseen adapter failure sanitized in the report.
        error_code = "PROVIDER_ERROR"
        error_reason = type(exc).__name__
    elapsed = round(time.perf_counter() - before, 3)
    expected = case["expected"]
    result = {
        "case_id": case["case_id"],
        "split": case["split"],
        "task": case["task"],
        "started_at": started_at,
        "elapsed_seconds": elapsed,
        "status": "SUCCEEDED" if normalized is not None else (
            "TIMED_OUT" if error_code in {"PROVIDER_TIMEOUT", "PIPELINE_TIMEOUT"} else "FAILED"
        ),
        "error_code": error_code,
        "error_reason": error_reason,
        "validator_error": validator_error,
        "raw_output_hash": getattr(locals().get("analysis"), "raw_output_hash", None),
        "raw_model_output": output,
        "validated_output": normalized,
    }
    if output is not None:
        refs = _references(output, case["task"])
        result["raw_evidence_refs"] = sorted(refs)
        result["required_evidence_refs_cited"] = sorted(set(expected.get("required_evidence_refs", [])) & refs)
        result["required_evidence_refs_missing"] = sorted(set(expected.get("required_evidence_refs", [])) - refs)
    else:
        result["raw_evidence_refs"] = []
        result["required_evidence_refs_cited"] = []
        result["required_evidence_refs_missing"] = list(expected.get("required_evidence_refs", []))

    if case["task"] == "MEDIA_COMPLIANCE":
        hard_finding = any(
            item.get("severity") == "HARD_VIOLATION"
            for item in (output or {}).get("findings", [])
            if isinstance(item, dict)
        )
        hard_rule_ids = {rule.rule_id for rule in policy.rules if rule.severity == "HARD_VIOLATION"}
        hard_failed_rule = any(
            item.get("rule_id") in hard_rule_ids and item.get("result") == "FAIL"
            for item in (output or {}).get("rule_results", [])
            if isinstance(item, dict)
        )
        actual_outcome = normalized.get("outcome") if normalized else "HUMAN_REVIEW_REQUIRED"
        result["assessment"] = {
            "expected_component_outcome": expected["component_outcome"],
            "actual_component_outcome": actual_outcome,
            "component_outcome_matches_proposed_label": actual_outcome == expected["component_outcome"],
            "hard_violation_expected": expected["hard_violation_expected"],
            "hard_violation_reported": hard_finding or hard_failed_rule,
            "raw_pass_with_hard_violation": (output or {}).get("outcome") == "PASS" and (hard_finding or hard_failed_rule),
            "validator_failed_closed": normalized is None and error_code == "INVALID_SCHEMA",
            "decision_scope": "Media component result only; this evaluator does not make an approval decision.",
        }
    else:
        scores = (normalized or {}).get("criterion_scores", [])
        scores_by_id = {item["criterion_id"]: item for item in scores}
        result["criterion_scores"] = [
            {
                "criterion_id": criterion.criterion_id,
                "weight": criterion.weight,
                "proposed_information_state": expected["criterion_states"][criterion.criterion_id],
                "score": scores_by_id[criterion.criterion_id]["score"] if criterion.criterion_id in scores_by_id else None,
                "rationale": scores_by_id[criterion.criterion_id]["rationale"] if criterion.criterion_id in scores_by_id else None,
                "evidence_refs": scores_by_id[criterion.criterion_id]["evidence_refs"] if criterion.criterion_id in scores_by_id else [],
            }
            for criterion in rubric.criteria
        ]
        actual_conflicts = (normalized or {}).get("evidence_conflicts", [])
        result["assessment"] = {
            "expected_conflict": expected.get("conflict_expected", False),
            "conflict_reported": bool(actual_conflicts),
            "conflict_evidence_refs": sorted({ref for item in actual_conflicts for ref in item["evidence_refs"]}),
            "required_conflict_refs_missing": sorted(
                set(expected.get("conflict_evidence_refs", []))
                - {ref for item in actual_conflicts for ref in item["evidence_refs"]}
            ),
            "required_gap_topics": expected.get("required_gap_topics", []),
            "missing_facts": (normalized or {}).get("missing_facts", []),
            "critical_gaps": (normalized or {}).get("critical_gaps", []),
            "total_score": (normalized or {}).get("total_score"),
            "confidence": (normalized or {}).get("confidence"),
            "confidence_is_calibrated": False,
            "decision_scope": "Strategy assessment only; scores and labels do not authorize approval.",
        }

    try:
        resident = _ollama_json(client, root, "/api/ps").get("models", [])
        result["model_loaded_after_case"] = any(item.get("name") == provider.settings.model_id for item in resident)
        result["runtime_context_length_after_case"] = next(
            (item.get("context_length") for item in resident if item.get("name") == provider.settings.model_id), None
        )
    except (httpx.HTTPError, ValueError):
        result["model_loaded_after_case"] = None
        result["runtime_context_length_after_case"] = None
    return result


def summarize(results: list[dict], rubric) -> dict:
    summary = {}
    for task in ("MEDIA_COMPLIANCE", "STRATEGY_EVALUATION"):
        rows = [item for item in results if item["task"] == task]
        summary[task] = {
            "cases": len(rows),
            "schema_valid": sum(item["status"] == "SUCCEEDED" for item in rows),
            "schema_invalid_or_provider_failed": sum(item["status"] == "FAILED" for item in rows),
            "timeouts": sum(item["status"] == "TIMED_OUT" for item in rows),
            "provider_error_codes": dict(Counter(item["error_code"] for item in rows if item["error_code"])),
            "latency_seconds": [item["elapsed_seconds"] for item in rows],
        }
        if task == "MEDIA_COMPLIANCE":
            summary[task]["proposed_component_label_matches"] = sum(
                item["assessment"]["component_outcome_matches_proposed_label"] for item in rows
            )
            summary[task]["raw_pass_with_hard_violation"] = sum(
                item["assessment"]["raw_pass_with_hard_violation"] for item in rows
            )
            summary[task]["validator_fail_closed"] = sum(
                item["assessment"]["validator_failed_closed"] for item in rows
            )
        else:
            valid_rows = [item for item in rows if item["status"] == "SUCCEEDED"]
            summary[task]["proposed_conflict_label_matches_on_valid_outputs"] = sum(
                item["assessment"]["conflict_reported"] == item["assessment"]["expected_conflict"]
                for item in valid_rows
            )
            by_criterion = {}
            for criterion in rubric.criteria:
                scores = [
                    score for row in rows for score in row.get("criterion_scores", [])
                    if score["criterion_id"] == criterion.criterion_id and score["score"] is not None
                ]
                by_state = {}
                for score in scores:
                    by_state.setdefault(score["proposed_information_state"], []).append(score["score"])
                by_criterion[criterion.criterion_id] = {
                    "weight": criterion.weight,
                    "scored_cases": len(scores),
                    "scores": [score["score"] for score in scores],
                    "evidence_references": [score["evidence_refs"] for score in scores],
                    "scores_by_proposed_information_state": by_state,
                }
            summary[task]["per_criterion"] = by_criterion
    return summary


def run(dataset_path: Path, env_path: Path, report_path: Path, api_base_url: str, split: str) -> dict:
    dataset, cases = load_dataset(dataset_path)
    if split != "all":
        cases = [case for case in cases if case["split"] == split]
    if not cases:
        raise ValueError("No cases matched the requested evaluation split.")
    dotenv = read_env_file(env_path)
    environment = dict(dotenv)

    providers = {}
    for task in ("MEDIA_COMPLIANCE", "STRATEGY_EVALUATION"):
        settings = TaskModelSettings.from_environment(task, environ=environment)
        if not settings.is_configured:
            raise ValueError(f"{task} local provider is not configured: {settings.configuration_error or 'missing settings'}")
        if settings.model_id != EXPECTED_TEXT_MODEL or settings.allow_remote:
            raise ValueError(f"{task} must use the pinned local model with remote access disabled.")
        parsed = urlsplit(api_base_url)
        if parsed.hostname not in LOCAL_HOSTS or parsed.scheme != "http" or parsed.port != 11434:
            raise ValueError("Only local Ollama loopback access on port 11434 is allowed.")
        settings = replace(settings, base_url=api_base_url.rstrip("/"), max_retries=0)
        providers[task] = OpenAICompatibleTaskProvider(settings)
    root = _local_root(api_base_url)
    policy = media_policy_from_json(json.dumps(dataset["policy"], ensure_ascii=False))
    rubric = strategy_rubric_from_json(json.dumps(dataset["rubric"], ensure_ascii=False))

    with httpx.Client(timeout=10) as client:
        preflight = _model_preflight(client, providers["MEDIA_COMPLIANCE"].settings, root)
        if providers["STRATEGY_EVALUATION"].settings.model_version != preflight["observed_ollama_digest"]:
            raise ValueError("Media and Strategy model pins do not match the same local Ollama tag.")
        results = []
        for index, case in enumerate(cases, start=1):
            provider = providers[case["task"]]
            result = _run_case(case, provider, policy, rubric, client, root)
            result["sequence_number"] = index
            result["model_phase"] = "warm" if (index > 1 and result.get("runtime_context_length_after_case")) else "first_or_unloaded"
            results.append(result)

    report = {
        "report_schema": "organizationai.local-media-strategy-evaluation/1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "dataset_id": dataset["dataset_id"],
        "dataset_label_status": dataset["label_status"],
        "split": split,
        "execution": {
            "mode": "REAL_LOCAL_OLLAMA_TEXT_EVALUATORS",
            "calls_are_sequential": True,
            "maximum_model_calls": len(cases),
            "retries_per_case": 0,
            "timeout_seconds_by_task": {
                task: providers[task].settings.timeout_seconds for task in providers
            },
            "image_extraction_measured": False,
            "final_approval_decisions_made": False,
            "auto_approval_enabled": False,
        },
        "policy": {
            "policy_id": policy.policy_id,
            "policy_version": policy.policy_version,
            "scope_departments": list(policy.scope_departments),
            "scope_channels": list(policy.scope_channels),
            "production_policy": False,
        },
        "rubric": {
            "rubric_id": rubric.rubric_id,
            "rubric_version": rubric.rubric_version,
            "weights": {item.criterion_id: item.weight for item in rubric.criteria},
            "production_rubric": False,
        },
        "proposed_criterion_state_legend": dataset.get("criterion_state_legend", {}),
        "model": preflight,
        "summary": summarize(results, rubric),
        "results": results,
        "limitations": [
            "Expected labels are proposed by the task author and have not been approved by a domain reviewer.",
            "Schema evidence-reference validation does not prove that a cited item semantically supports a claim; report entries preserve raw and normalized evidence for review.",
            "Strategy score values are advisory and model-reported confidence is not calibrated probability.",
            "The suite calls Media and Strategy text evaluators directly; VLM image extraction and the PostgreSQL workflow are measured separately.",
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--api-base-url", default="http://127.0.0.1:11434/v1")
    parser.add_argument("--split", choices=("all", "tune", "holdout"), default="all")
    args = parser.parse_args()
    report = run(args.dataset, args.env_file, args.report, args.api_base_url, args.split)
    print(f"Dataset: {report['dataset_id']} ({report['split']}, {len(report['results'])} sequential cases)")
    print(f"Model: {report['model']['model_id']} @ {report['model']['observed_ollama_digest']}; context={report['model']['context_size']}")
    for task, summary in report["summary"].items():
        print(
            f"{task}: valid={summary['schema_valid']}/{summary['cases']}, "
            f"timeouts={summary['timeouts']}, errors={summary['provider_error_codes']}"
        )
    print(f"Report written: {args.report}")


if __name__ == "__main__":
    main()
