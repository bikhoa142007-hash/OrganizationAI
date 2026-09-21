"""Small adapter from the orchestrator to the existing WP3 application API."""

from .models import EvaluationRequest


class ApprovalPipelineAdapter:
    def __init__(self, workflow, orchestrator):
        self.workflow = workflow
        self.orchestrator = orchestrator

    def evaluate_submission(self, actor, plan_id, submission, *, idempotency_key,
                            correlation_id=None):
        ticket = submission["evaluation_ticket"]
        round_data = submission["round"]
        snapshot = self.workflow.repository.version(plan_id, round_data["number"])[0]
        from src.backend.domain.models import MarketingPlan
        from src.backend.domain.policy import ApprovalConfiguration
        plan = MarketingPlan.from_dict(snapshot)
        config = ApprovalConfiguration.from_dict(round_data["configuration"])
        request = EvaluationRequest(
            plan=plan,
            policy_version=config.policy.policy_version,
            evaluation_id=ticket["evaluation_id"],
            run_id=ticket["run_id"],
            correlation_id=correlation_id or ticket["correlation_id"],
            provider=ticket["provider"],
            configuration=config,
            model_version=(config.policy.known_model_versions[0]
                           if config.policy.known_model_versions else None),
        )
        result = self.orchestrator.evaluate(request)
        return self.workflow.evaluate_round(
            actor, plan_id, round_data["number"], result.evaluation,
            expected_revision=round_data["revision"],
            expected_policy_version=request.policy_version,
            idempotency_key=idempotency_key,
            correlation_id=request.correlation_id,
        )
