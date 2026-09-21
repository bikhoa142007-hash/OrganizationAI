import pytest
from src.ai_pipeline.adapters import ApprovalPipelineAdapter
from src.ai_pipeline.orchestrator import EvaluationOrchestrator
from src.ai_pipeline.providers.mock import MockVLMProvider
from src.backend.application.workflow import ApprovalWorkflow
from src.backend.repositories.approval import ApprovalRepository
from tests.integration.test_approval_workflow import MAKER, ENGINE, USERS, configuration, submitted

@pytest.fixture
def app(tmp_path):
    repo = ApprovalRepository(tmp_path / "approval.sqlite")
    service = ApprovalWorkflow(repo, configuration(), USERS, evaluator_id=ENGINE)
    yield service
    repo.close()

def test_pipeline_adapter_routes_validated_evidence_to_wp3(app):
    submission = submitted(app)
    adapter = ApprovalPipelineAdapter(app, EvaluationOrchestrator(MockVLMProvider()))
    result = adapter.evaluate_submission(ENGINE, "plan", submission, idempotency_key="pipeline-evaluate")
    assert result["decision"]["outcome"] == "AUTO_APPROVED"
    assert app.get_plan(MAKER, "plan")["plan"]["state"]["plan_status"] == "APPROVED"

def test_pipeline_adapter_failure_keeps_submission_for_checker(app):
    submission = submitted(app)
    adapter = ApprovalPipelineAdapter(app, EvaluationOrchestrator(MockVLMProvider("timeout"), max_retries=1))
    result = adapter.evaluate_submission(ENGINE, "plan", submission, idempotency_key="pipeline-timeout")
    assert result["decision"]["outcome"] == "HUMAN_REVIEW_REQUIRED"
    assert app.get_plan(MAKER, "plan")["plan"]["state"]["plan_status"] == "PENDING_APPROVAL"
