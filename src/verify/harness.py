"""Execute Verify cases through the real submission and evaluation workflow."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Callable, Iterable

from src.ai_pipeline.adapters import ApprovalPipelineAdapter
from src.ai_pipeline.orchestrator import EvaluationOrchestrator
from src.ai_pipeline.providers.mock import MockVLMProvider
from src.backend.application.workflow import ApprovalWorkflow
from src.backend.domain.policy import ApprovalConfiguration, AuthoritySnapshot, BudgetConfiguration, Criterion, PolicySnapshot
from src.backend.repositories.approval import ApprovalRepository


MAKER = "demo-maker"
CHECKER = "demo-checker"
ENGINE = "demo-evaluator"


@dataclass(frozen=True)
class VerifyCase:
    case_id: str
    description: str
    scenario: str
    expected_outcome: str
    expected_category: str | None


@dataclass(frozen=True)
class VerifyObservation:
    case_id: str
    expected_outcome: str
    actual_outcome: str | None
    expected_category: str | None
    actual_category: str | None
    escalation_question: str | None
    passed: bool
    duration_ms: int
    error: str | None = None
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def default_verify_cases() -> tuple[VerifyCase, ...]:
    return (
        VerifyCase("TEST_ONLY-A01", "Compliant campaign at budget limit", "pass", "AUTO_APPROVED", None),
        VerifyCase("TEST_ONLY-A02", "Compliant campaign below budget limit", "pass", "AUTO_APPROVED", None),
        VerifyCase("TEST_ONLY-A03", "Boundary score above 70", "pass", "AUTO_APPROVED", None),
        VerifyCase("TEST_ONLY-A04", "Low-confidence evidence", "review", "HUMAN_REVIEW_REQUIRED", "POLICY_OUT_OF_SCOPE"),
        VerifyCase("TEST_ONLY-A05", "Provider review signal", "review", "HUMAN_REVIEW_REQUIRED", "POLICY_OUT_OF_SCOPE"),
    )


def demo_configuration() -> ApprovalConfiguration:
    policy = PolicySnapshot(
        "demo-policy", "DEMO-1", True,
        ("title", "maker_id", "checker_id", "department", "objective", "summary",
         "start_date", "end_date", "budget_minor_units", "currency"),
        (Criterion("strategy", 100),), ("mock-1",), ("image/png",), 1_000_000,
    )
    budget = BudgetConfiguration("demo-budget", "VND", 0, "10000", "demo-marketing", True)
    authority = AuthoritySnapshot("demo-authority", "VND", "10000", ("demo-marketing",),
                                  CHECKER, "demo-policy-owner", "demo-budget-authority", True)
    return ApprovalConfiguration(policy, (budget,), authority)


def _payload(budget: str = "10000") -> dict[str, Any]:
    return {
        "title": "Demo marketing plan", "maker_id": MAKER, "checker_id": CHECKER,
        "department": "demo-marketing", "objective": "Reach qualified customers",
        "summary": "A test-only campaign for the WP5 verify harness.",
        "start_date": "2026-10-01", "end_date": "2026-10-31",
        "budget_minor_units": budget, "currency": "VND",
    }


class VerifyHarness:
    """Run every case through a fresh SQLite workflow and compute PASS from output."""

    def __init__(self, *, case_loader: Callable[[], Iterable[VerifyCase]] = default_verify_cases,
                 configuration_factory: Callable[[], ApprovalConfiguration] = demo_configuration):
        self.case_loader = case_loader
        self.configuration_factory = configuration_factory

    def run_all(self) -> list[dict[str, Any]]:
        return [observation.to_dict() for observation in (self.run_case(case) for case in self.case_loader())]

    def run_case(self, case: VerifyCase) -> VerifyObservation:
        started = perf_counter()
        timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        repo = ApprovalRepository(":memory:")
        try:
            config = self.configuration_factory()
            workflow = ApprovalWorkflow(repo, config,
                                        {MAKER: {"MAKER"}, CHECKER: {"CHECKER"}, ENGINE: {"EVALUATOR"}},
                                        evaluator_id=ENGINE)
            workflow.save_draft(MAKER, case.case_id, _payload(), expected_revision=0,
                                idempotency_key=f"verify-draft-{case.case_id}", correlation_id=f"verify-{case.case_id}")
            draft = workflow.upload_attachment(MAKER, case.case_id, b"\x89PNG\r\n\x1a\nTEST", "image/png",
                                                expected_revision=1, idempotency_key=f"verify-upload-{case.case_id}",
                                                correlation_id=f"verify-{case.case_id}")
            submission = workflow.submit_plan(MAKER, case.case_id, expected_revision=draft["revision"],
                                               expected_policy_version=config.policy.policy_version,
                                               idempotency_key=f"verify-submit-{case.case_id}", correlation_id=f"verify-{case.case_id}")
            adapter = ApprovalPipelineAdapter(workflow, EvaluationOrchestrator(MockVLMProvider(case.scenario)))
            result = adapter.evaluate_submission(ENGINE, case.case_id, submission,
                                                  idempotency_key=f"verify-evaluate-{case.case_id}")
            decision = result["decision"]
            actual = decision.get("outcome") if isinstance(decision, dict) else decision.outcome
            category = (decision.get("escalation_category") if isinstance(decision, dict)
                        else decision.escalation_category)
            first_question = result["questions"][0] if result["questions"] else None
            question = ((first_question.get("question") if isinstance(first_question, dict)
                         else first_question.question) if first_question else None)
            passed = actual == case.expected_outcome and category == case.expected_category
            error = None if passed else f"Expected {case.expected_outcome}/{case.expected_category}, got {actual}/{category}."
            return VerifyObservation(case.case_id, case.expected_outcome, actual, case.expected_category,
                                     category, question, passed, int((perf_counter() - started) * 1000), error, timestamp)
        except Exception as exc:  # a failed case is a visible FAIL row, never a synthetic PASS
            return VerifyObservation(case.case_id, case.expected_outcome, None, case.expected_category, None,
                                     None, False, int((perf_counter() - started) * 1000), str(exc), timestamp)
        finally:
            repo.close()
