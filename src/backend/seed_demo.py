"""Idempotent synthetic demo seed through the public application boundary."""
import base64
import os
from pathlib import Path

from src.ai_pipeline.adapters import ApprovalPipelineAdapter
from src.ai_pipeline.orchestrator import EvaluationOrchestrator
from src.ai_pipeline.providers.mock import MockVLMProvider
from src.backend.application.workflow import ApprovalWorkflow
from src.backend.repositories.approval import ApprovalRepository
from src.backend.domain.policy import ApprovalConfiguration
from src.backend.demo import configuration, demo_database, MAKER, CHECKER, ENGINE, PRINCIPALS, DEPARTMENT_CHECKERS

IMAGE = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aT1sAAAAASUVORK5CYII=')


class FactualDemoProvider(MockVLMProvider):
    def analyze_image(self, request):
        raw = super().analyze_image(request)
        raw.update(media_result='REVIEW_REQUIRED', proposed_action='RECOMMEND_HUMAN_REVIEW', escalation_category='FACT_UNCERTAIN')
        raw['evidence_conflicts'] = [dict(conflict_id='demo-kpi-conflict',
                                         description='SYNTHETIC: form KPI 1200; visual evidence 12000; target remains UNRESOLVED.',
                                         evidence_refs=[e['evidence_id'] for e in raw['evidence']])]
        return raw


def seed(path, app_env):
    if app_env != 'demo':
        raise ValueError('Seed requires APP_ENV=demo')
    path = demo_database(path)
    repo = ApprovalRepository(path)
    created, existing = [], []
    try:
        for name, mode, budget in [('auto', 'pass', '50000000'), ('budget', 'pass', '100000001'),
                                   ('review', 'review', '50000000'), ('timeout', 'timeout', '50000000'),
                                   ('facts', 'facts', '50000000'), ('draft', 'draft', '50000000'),
                                   ('approved', 'pass', '50000000'), ('rejected', 'review', '50000000')]:
            config = configuration(auto_approval=name == 'auto')
            workflow = ApprovalWorkflow(repo, config, PRINCIPALS, evaluator_id=ENGINE,
                                        department_checkers=DEPARTMENT_CHECKERS)
            plan_id = 'DEMO-SEED-' + name.upper()
            previous = repo.plan(plan_id)
            if previous is not None:
                if previous['maker_id'] != MAKER:
                    raise ValueError('Existing seed namespace belongs to another Maker')
                existing.append(plan_id)
                first_round = repo.round(plan_id, 1)
                if first_round:
                    # Replay the original seed intent across policy-version changes.
                    # Never rewrite a previously submitted configuration or decision.
                    config = ApprovalConfiguration.from_dict(first_round['configuration'])
                    workflow.configuration = config
            payload = dict(title='Demo ' + name, objective='Synthetic campaign', summary='Demo-only marketing strategy',
                           department='DEMO-DEPT-01', checker_id=CHECKER, start_date='2026-10-01',
                           end_date='2026-10-31', budget_minor_units=budget, currency='VND', kpi_expected='1200')
            plan = workflow.save_draft(MAKER, plan_id, payload, expected_revision=0,
                                      idempotency_key='seed-draft', correlation_id='seed')
            if mode == 'draft':
                if previous is None:
                    created.append(plan_id)
                continue
            plan = workflow.upload_attachment(MAKER, plan_id, IMAGE, 'image/png', expected_revision=plan['revision'],
                                              idempotency_key='seed-upload', correlation_id='seed')
            submission = workflow.submit_plan(MAKER, plan_id, expected_revision=plan['revision'],
                                              expected_policy_version=config.policy.policy_version,
                                              idempotency_key='seed-submit', correlation_id='seed')
            provider = FactualDemoProvider() if mode == 'facts' else MockVLMProvider(mode)
            pipeline = ApprovalPipelineAdapter(workflow, EvaluationOrchestrator(provider))
            workflow.run_evaluation(MAKER, plan_id, submission['round']['number'], 0, pipeline,
                                    idempotency_key='seed-evaluate', correlation_id='seed')
            if name in ('approved', 'rejected'):
                workflow.decide_round(CHECKER, plan_id, 1,
                                      'APPROVED' if name == 'approved' else 'REJECTED',
                                      reason='Synthetic campaign reviewed.' if name == 'approved'
                                      else 'Clarify the campaign strategy and resubmit.', override_reason=None,
                                      expected_revision=1, idempotency_key='seed-human', correlation_id='seed')
            if previous is None:
                created.append(plan_id)
        return {'created': created, 'existing': existing, 'database': str(path)}
    finally:
        repo.close()


if __name__ == '__main__':
    import json
    print(json.dumps(seed(Path(os.getenv('DEMO_DATABASE', 'runtime/demo-organization.sqlite3')), os.getenv('APP_ENV', 'production'))))
