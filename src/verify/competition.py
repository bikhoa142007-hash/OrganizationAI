"""Synthetic, evidence-backed four-case Verify suite for judges and CLI users."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from time import monotonic, perf_counter
from typing import Any, Callable
from uuid import uuid4

from src.ai_pipeline.adapters import ApprovalPipelineAdapter
from src.ai_pipeline.orchestrator import EvaluationOrchestrator
from src.ai_pipeline.providers.mock import MockVLMProvider
from src.backend.application.workflow import ApprovalWorkflow
from src.backend.domain.policy import (
    ApprovalConfiguration,
    AuthoritySnapshot,
    BudgetConfiguration,
    Criterion,
    MANDATORY_FIELDS,
    MediaCompliancePolicy,
    MediaPolicyRule,
    PolicySnapshot,
    STRATEGY_CRITERIA,
    StrategyCriterion,
    StrategyRubric,
)
from src.backend.repositories.approval import ApprovalRepository
from src.shared.validation import require
from src.verify.observation import validate_observation


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures"
CASE_FILE = PROJECT_ROOT / "tests" / "fixtures" / "verify" / "competition-cases.json"
ATTACHMENT_ROOT = (FIXTURE_ROOT / "ba" / "v2.1" / "images").resolve()
CASE_TIMEOUT_SECONDS = 20
TOTAL_TIMEOUT_SECONDS = 90
MAKER = "VERIFY-MAKER"
CHECKER = "VERIFY-CHECKER"
EVALUATOR = "VERIFY-EVALUATOR"
CASE_IDS = ("TC01", "TC02", "TC03", "TC04")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _load_cases() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    document = json.loads(CASE_FILE.read_text(encoding="utf-8"))
    require(document.get("suite_version") == "VERIFY-1.0", "Unknown Verify fixture version")
    configuration = document.get("configuration")
    require(isinstance(configuration, dict), "Verify configuration is missing")
    cases = document.get("cases")
    require(isinstance(cases, list) and len(cases) == 4, "Verify must define exactly four cases")
    case_ids = [case.get("id") for case in cases]
    require(case_ids == ["TC01", "TC02", "TC03", "TC04"], "Verify cases are not in the required order")
    for case in cases:
        require(set(case) == {"id", "name", "input", "expected"}, "Invalid Verify case shape")
        require(case["input"]["provider_scenario"] in {"pass", "missing_evidence", "timeout"},
                "Unsupported Verify provider scenario")
    return configuration, cases


def _approval_configuration(fixture: dict[str, Any]) -> ApprovalConfiguration:
    strategy_criteria = tuple(
        Criterion(criterion_id, weight)
        for criterion_id, _label, weight in STRATEGY_CRITERIA
    )
    policy = PolicySnapshot(
        "VERIFY-POLICY-1",
        "VERIFY-1.0",
        fixture["auto_approval_enabled"],
        MANDATORY_FIELDS,
        strategy_criteria,
        ("mock-1",),
        ("image/png", "image/jpeg", "image/webp"),
        5_000_000,
    )
    budget = BudgetConfiguration(
        "VERIFY-BUDGET-1", "VND", 0, fixture["budget_limit_minor_units"], "marketing", True
    )
    authority = AuthoritySnapshot(
        "VERIFY-AUTHORITY-1",
        "VND",
        fixture["auto_approval_limit_minor_units"],
        ("marketing",),
        CHECKER,
        "VERIFY-ADMIN",
        "VERIFY-BUDGET-AUTHORITY",
        True,
    )
    return ApprovalConfiguration(
        policy,
        (budget,),
        authority,
        media_policy=MediaCompliancePolicy(
            "VERIFY-MEDIA-1",
            "1",
            "ACTIVE",
            ("marketing",),
            ("social",),
            (MediaPolicyRule(
                "VERIFY-EVIDENCE-1",
                "WARNING",
                "Synthetic media evidence check.",
                ("OBSERVATION",),
            ),),
        ),
        strategy_rubric=StrategyRubric(
            "VERIFY-RUBRIC-1",
            "1",
            "ACTIVE",
            tuple(
                StrategyCriterion(criterion_id, label, weight)
                for criterion_id, label, weight in STRATEGY_CRITERIA
            ),
        ),
    )


class _MissingEvidenceMockProvider(MockVLMProvider):
    """A valid provider response with no visual evidence; it cannot imply PASS."""

    def __init__(self):
        super().__init__("pass")

    def analyze_image(self, request):
        result = super().analyze_image(request)
        result.update(
            media_result="REVIEW_REQUIRED",
            media_confidence=0.95,
            evidence=[],
            missing_facts=["Required media evidence is missing."],
            proposed_action="RECOMMEND_HUMAN_REVIEW",
            escalation_category="FACT_UNCERTAIN",
            reason="Required media evidence is missing; no compliance pass was inferred.",
        )
        return result


def _provider_for(scenario: str) -> MockVLMProvider:
    if scenario == "missing_evidence":
        return _MissingEvidenceMockProvider()
    return MockVLMProvider(scenario)


def _execute_case(case: dict[str, Any], configuration: dict[str, Any], run_id: str) -> dict[str, Any]:
    case_id = case["id"]
    correlation_id = f"verify-{run_id}-{case_id}"
    plan_id = f"VERIFY-{case_id}-{uuid4().hex[:12]}"
    payload = deepcopy(case["input"]["plan"])
    attachments = payload.pop("attachments")
    payload.update({"maker_id": MAKER, "checker_id": CHECKER})
    repository = ApprovalRepository(":memory:")
    try:
        approval_configuration = _approval_configuration(configuration)
        workflow = ApprovalWorkflow(
            repository,
            approval_configuration,
            {MAKER: {"MAKER"}, CHECKER: {"CHECKER"}, EVALUATOR: {"EVALUATOR"}},
            evaluator_id=EVALUATOR,
        )
        plan = workflow.save_draft(
            MAKER,
            plan_id,
            payload,
            expected_revision=0,
            idempotency_key=f"{correlation_id}:draft",
            correlation_id=correlation_id,
        )
        for index, attachment in enumerate(attachments):
            path = (FIXTURE_ROOT / attachment["path"]).resolve()
            require(path.is_relative_to(ATTACHMENT_ROOT), "Verify attachment path is outside the fixture image set")
            content = path.read_bytes()
            plan = workflow.upload_attachment(
                MAKER,
                plan_id,
                content,
                attachment["media_type"],
                expected_revision=plan["revision"],
                idempotency_key=f"{correlation_id}:attachment:{index}",
                correlation_id=correlation_id,
            )
        submission = workflow.submit_plan(
            MAKER,
            plan_id,
            expected_revision=plan["revision"],
            expected_policy_version=approval_configuration.policy.policy_version,
            idempotency_key=f"{correlation_id}:submit",
            correlation_id=correlation_id,
        )
        provider = _provider_for(case["input"]["provider_scenario"])
        pipeline = ApprovalPipelineAdapter(
            workflow,
            EvaluationOrchestrator(provider, timeout_seconds=8, max_retries=0),
        )
        pipeline.evaluate_submission(
            EVALUATOR,
            plan_id,
            submission,
            idempotency_key=f"{correlation_id}:evaluate",
            correlation_id=correlation_id,
        )

        observation = workflow.get_verify_observation(MAKER, plan_id, 1)
        decision = next(record["body"] for record in observation["records"] if record["kind"] == "engine_decision")
        evaluation = next(record["body"] for record in observation["records"] if record["kind"] == "evaluation")
        questions = [record["body"] for record in observation["records"] if record["kind"] == "escalation"]
        actual = {
            "application_reference": observation["application_reference"],
            "plan": observation["plan"],
            "decision": decision,
            "evaluation": evaluation,
            "versions": observation["versions"],
            "audit": observation["audit"],
            "questions": questions,
        }
        validate_observation(actual)
        final = repository.connection.execute(
            "SELECT kind FROM wp3_finals WHERE plan_id=?", (plan_id,)
        ).fetchone()
        actual.update({
            "final_decision": "APPROVED" if final and final["kind"] == "engine_decision" else None,
            "decision_source": "AI_AUTO_APPROVAL" if final else None,
        })
        return actual
    finally:
        repository.close()


def _compare(case: dict[str, Any], actual: dict[str, Any] | None) -> list[dict[str, Any]]:
    expected = case["expected"]
    if actual is None:
        return [{"name": "workflow_execution", "passed": False, "expected": "actual workflow observation", "actual": None}]

    checks = [
        ("decision_outcome", expected["outcome"], actual["decision"]["outcome"]),
        ("plan_status", expected["plan_status"], actual["plan"]["state"]["plan_status"]),
        ("evaluation_status", expected["evaluation_status"], actual["evaluation"]["status"]),
        ("media_result", expected["media_result"], actual["evaluation"]["media_result"]),
        ("escalation_category", expected["escalation_category"], actual["decision"]["escalation_category"]),
        ("decision_source", expected["decision_source"], actual["decision_source"]),
    ]
    assertions = [
        {"name": name, "expected": wanted, "actual": got, "passed": wanted == got}
        for name, wanted, got in checks
    ]
    audit_actions = {event["action"] for event in actual["audit"]}
    assertions.append({
        "name": "audit_actions",
        "expected": expected["audit_actions"],
        "actual": sorted(audit_actions),
        "passed": set(expected["audit_actions"]) <= audit_actions,
    })
    if "failed_rule_ids" in expected:
        failed_rules = {check["rule_id"] for check in actual["decision"]["rule_checks"] if check["result"] != "PASS"}
        assertions.append({
            "name": "failed_rule_ids",
            "expected": expected["failed_rule_ids"],
            "actual": sorted(failed_rules),
            "passed": set(expected["failed_rule_ids"]) <= failed_rules,
        })
    if "media_evidence_count" in expected:
        evidence_count = len(actual["evaluation"]["evidence"])
        assertions.append({
            "name": "media_evidence_count",
            "expected": expected["media_evidence_count"],
            "actual": evidence_count,
            "passed": expected["media_evidence_count"] == evidence_count,
        })
    if "reason_contains" in expected:
        reason = (actual["decision"]["reason"] + " " + actual["evaluation"]["reason"]).casefold()
        needle = expected["reason_contains"].casefold()
        assertions.append({
            "name": "reason_contains",
            "expected": expected["reason_contains"],
            "actual": actual["decision"]["reason"],
            "passed": needle in reason,
        })
    if "agent_error_codes" in expected:
        error_codes = {error["code"] for error in actual["evaluation"]["agent_errors"]}
        assertions.append({
            "name": "agent_error_codes",
            "expected": expected["agent_error_codes"],
            "actual": sorted(error_codes),
            "passed": set(expected["agent_error_codes"]) <= error_codes,
        })
    return assertions


def _failure_row(case: dict[str, Any], run_id: str, reason: str) -> dict[str, Any]:
    timestamp = _utc_now()
    return {
        "case_id": case["id"],
        "case_name": case["name"],
        "input": deepcopy(case["input"]),
        "expected": deepcopy(case["expected"]),
        "actual": None,
        "assertions": [{"name": "case_execution", "expected": "completed within deadline", "actual": reason, "passed": False}],
        "status": "FAIL",
        "reason": reason,
        "started_at": timestamp,
        "completed_at": timestamp,
        "duration_ms": 0,
    }


def run_competition_suite(
    *,
    run_id: str | None = None,
    on_case_started: Callable[[str], None] | None = None,
    on_case_completed: Callable[[dict[str, Any]], None] | None = None,
    total_timeout_seconds: int = TOTAL_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Run TC01-TC04 sequentially; PASS is computed only from actual observations."""
    configuration, cases = _load_cases()
    run_id = run_id or f"VERIFY-{uuid4()}"
    started_at = _utc_now()
    started = monotonic()
    deadline = started + total_timeout_seconds
    rows: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        if monotonic() >= deadline:
            reason = f"Verify exceeded the {total_timeout_seconds}-second total deadline."
            for pending in cases[index:]:
                row = _failure_row(pending, run_id, reason)
                rows.append(row)
                if on_case_completed:
                    on_case_completed(row)
            break
        if on_case_started:
            on_case_started(case["id"])
        case_started_at = _utc_now()
        case_started = perf_counter()
        actual = None
        failure_reason = None
        try:
            actual = _execute_case(case, configuration, run_id)
        except Exception as exc:
            failure_reason = str(exc) or type(exc).__name__
        duration_ms = max(0, int((perf_counter() - case_started) * 1000))
        assertions = _compare(case, actual)
        if failure_reason:
            assertions.append({
                "name": "workflow_execution",
                "expected": "workflow completes and persists observation",
                "actual": failure_reason,
                "passed": False,
            })
        if duration_ms > CASE_TIMEOUT_SECONDS * 1000:
            assertions.append({
                "name": "case_timeout",
                "expected": f"<= {CASE_TIMEOUT_SECONDS}s",
                "actual": f"{duration_ms}ms",
                "passed": False,
            })
        row = {
            "case_id": case["id"],
            "case_name": case["name"],
            "input": deepcopy(case["input"]),
            "expected": deepcopy(case["expected"]),
            "actual": actual,
            "assertions": assertions,
            "status": "PASS" if assertions and all(assertion["passed"] for assertion in assertions) else "FAIL",
            "reason": failure_reason or next((item["actual"] for item in assertions if not item["passed"]), None),
            "started_at": case_started_at,
            "completed_at": _utc_now(),
            "duration_ms": duration_ms,
        }
        rows.append(row)
        if on_case_completed:
            on_case_completed(row)

    completed_at = _utc_now()
    try:
        commit_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=1,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        commit_sha = None
    return {
        "run_id": run_id,
        "suite": "competition",
        "suite_version": "VERIFY-1.0",
        "status": "COMPLETED" if len(rows) == 4 else "ERROR",
        "environment": "SYNTHETIC_TEST",
        "provider_mode": "MOCK_VLM (external calls disabled)",
        "timezone": "Asia/Ho_Chi_Minh",
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_ms": max(0, int((monotonic() - started) * 1000)),
        "commit_sha": commit_sha,
        "configuration": deepcopy(configuration),
        "completed_cases": len(rows),
        "passed_cases": sum(row["status"] == "PASS" for row in rows),
        "failed_cases": sum(row["status"] != "PASS" for row in rows),
        "rows": rows,
    }


def _format_behavior(value: Any) -> str:
    if value is None:
        return "—"
    return str(value)


def _print_report(run: dict[str, Any], output: Path) -> None:
    headers = ("Tình huống", "Kết quả kỳ vọng", "Kết quả thực tế", "PASS/FAIL", "Thời lượng")
    rows = []
    for row in run["rows"]:
        expected = row["expected"]["outcome"]
        actual = row["actual"]["decision"]["outcome"] if row["actual"] else row["reason"]
        rows.append((row["case_id"], expected, _format_behavior(actual), row["status"], f"{row['duration_ms']} ms"))
    widths = [max(len(headers[i]), *(len(str(row[i])) for row in rows)) for i in range(len(headers))]
    print(" | ".join(headers[i].ljust(widths[i]) for i in range(len(headers))))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(" | ".join(str(row[i]).ljust(widths[i]) for i in range(len(headers))))
    print(f"run_id={run['run_id']}")
    print(f"environment={run['environment']} provider_mode={run['provider_mode']}")
    print(f"started_at={run['started_at']} completed_at={run['completed_at']} timestamp_timezone=UTC display_timezone=Asia/Ho_Chi_Minh")
    print(f"duration_ms={run['duration_ms']} pass={run['passed_cases']} fail={run['failed_cases']}")
    print(f"commit_sha={run['commit_sha'] or 'unavailable'}")
    print(f"report={output}")


def main() -> int:
    # Windows PowerShell may launch Python with a legacy code page that cannot
    # print the Vietnamese case names in the terminal report.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Run the four synthetic OrganizationAI Verify cases.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    run = run_competition_suite()
    output = args.output or Path("runtime") / "verify" / f"verify-{run['run_id']}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    _print_report(run, output)
    return 0 if run["status"] == "COMPLETED" and run["failed_cases"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
