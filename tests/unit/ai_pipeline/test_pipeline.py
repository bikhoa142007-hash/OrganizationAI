import pytest
from src.ai_pipeline.models import EvaluationRequest
from src.ai_pipeline.orchestrator import EvaluationOrchestrator
from src.ai_pipeline.providers.base import ProviderError
from src.ai_pipeline.providers.mock import MockVLMProvider
from src.backend.domain.models import AttachmentManifest, MarketingPlan
from src.backend.domain.policy import ApprovalConfiguration, AuthoritySnapshot, BudgetConfiguration, Criterion, PolicySnapshot

def config():
    return ApprovalConfiguration(
        PolicySnapshot("policy-1", "POLICY-1", True, ("title","maker_id","checker_id","department","objective","summary","start_date","end_date","budget_minor_units","currency"), (Criterion("total",100),), ("mock-1",), ("image/png",), 100000),
        (BudgetConfiguration("budget-1","VND",0,"10000","marketing",True),),
        AuthoritySnapshot("authority-1","VND","10000",("marketing",),"checker","owner","budget",True))

def request():
    plan = MarketingPlan("plan",1,1,{"title":"Campaign"},(AttachmentManifest("image","a"*64,"image/png",10),))
    return EvaluationRequest(plan,"POLICY-1","evaluation-1","run-1","trace-1",configuration=config(),model_version="mock-1")

def test_mock_provider_is_deterministic():
    one=EvaluationOrchestrator(MockVLMProvider()).evaluate(request()); two=EvaluationOrchestrator(MockVLMProvider()).evaluate(request())
    assert one.evaluation["input_hash"] == two.evaluation["input_hash"]
    assert one.evaluation["criterion_scores"] == two.evaluation["criterion_scores"]
    assert one.evaluation["proposed_action"] == "RECOMMEND_AUTO_APPROVAL"

def test_timeout_retries_and_fails_closed():
    result=EvaluationOrchestrator(MockVLMProvider("timeout"),max_retries=2).evaluate(request())
    assert result.attempts == 3
    assert result.evaluation["status"] == "TIMED_OUT"
    assert result.evaluation["proposed_action"] is None

@pytest.mark.parametrize("scenario",["error","malformed","unknown_media"])
def test_invalid_provider_result_fails_closed(scenario):
    result=EvaluationOrchestrator(MockVLMProvider(scenario),max_retries=2).evaluate(request())
    assert result.attempts == (3 if scenario=="error" else 1)
    assert result.evaluation["status"] == "FAILED"
    assert result.evaluation["escalation_category"] == "FACT_UNCERTAIN"

def test_retry_success_is_bounded():
    class RetryProvider(MockVLMProvider):
        def __init__(self): super().__init__(); self.calls=0
        def analyze_image(self, request):
            self.calls += 1
            if self.calls == 1: raise ProviderError("transient")
            return super().analyze_image(request)
    provider=RetryProvider()
    result=EvaluationOrchestrator(provider,max_retries=1).evaluate(request())
    assert result.attempts == 2 and result.retried is True
    assert result.evaluation["status"] == "SUCCEEDED"

def test_schema_and_correlation_fail_closed_without_retry():
    class Bad(MockVLMProvider):
        def analyze_image(self, request):
            value = super().analyze_image(request)
            value.pop("media_confidence")
            return value
    result = EvaluationOrchestrator(Bad(), max_retries=3).evaluate(request())
    assert result.attempts == 1
    assert result.evaluation["agent_errors"][0]["code"] == "INVALID_SCHEMA"

def test_input_hash_mismatch_fails_closed():
    class WrongHash(MockVLMProvider):
        def analyze_image(self, request):
            value = super().analyze_image(request)
            value["input_hash"] = "b" * 64
            return value
    result = EvaluationOrchestrator(WrongHash(), max_retries=0).evaluate(request())
    assert result.evaluation["agent_errors"][0]["code"] in {"CORRELATION_MISMATCH", "INPUT_HASH_MISMATCH"}

