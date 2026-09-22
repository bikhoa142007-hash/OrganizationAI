"""Execute BA fixtures through WP3/WP4 before loading the assertion oracle."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4
from time import perf_counter
from src.backend.application.workflow import now
from src.verify.observation import validate_observation, contract_result

from src.ai_pipeline.adapters import ApprovalPipelineAdapter
from src.ai_pipeline.orchestrator import EvaluationOrchestrator
from src.backend.application.workflow import ApprovalWorkflow
from src.backend.repositories.approval import ApprovalRepository
from src.shared.validation import require
from src.verify.ba_adapter import payload_from_input, configuration_from_input, BAMockProvider

FIXTURES = Path(__file__).resolve().parents[2] / 'tests/fixtures/ba/v2.1'


def execute_input(data, fixture_root=FIXTURES):
    payload = payload_from_input(data)
    config = configuration_from_input(data)
    repo = ApprovalRepository(':memory:')
    maker, checker, engine = payload['maker_id'], payload['checker_id'], 'DEMO-EVALUATOR-01'
    workflow = ApprovalWorkflow(repo, config, {maker: {'MAKER'}, checker: {'CHECKER'}, engine: {'EVALUATOR'}}, evaluator_id=engine)
    plan_id = 'DEMO-' + uuid4().hex
    try:
        plan = workflow.save_draft(maker, plan_id, payload, expected_revision=0,
                                   idempotency_key='draft', correlation_id='ba-run')
        bindings = {}
        for item in data['plan_snapshot']['attachments']:
            # Source path is only a locator. Identity and hash come from upload.
            path = (Path(fixture_root) / 'images' / Path(item['path']).name).resolve()
            require(path.parent == (Path(fixture_root) / 'images').resolve(), 'Invalid fixture path')
            content = path.read_bytes()
            require(len(content) == item['size_bytes'] and sha256(content).hexdigest() == item['sha256'],
                    'Fixture bytes do not match source manifest')
            plan = workflow.upload_attachment(maker, plan_id, content, item['mime_type'],
                                             expected_revision=plan['revision'], idempotency_key='upload-' + str(len(bindings)),
                                             correlation_id='ba-run')
            bindings[item['attachment_id']] = plan['attachments'][-1]
        submission = workflow.submit_plan(maker, plan_id, expected_revision=plan['revision'],
                                          expected_policy_version=config.policy.policy_version,
                                          idempotency_key='submit', correlation_id='ba-run')
        pipeline = ApprovalPipelineAdapter(workflow, EvaluationOrchestrator(BAMockProvider(data, bindings), max_retries=0))
        pipeline.evaluate_submission(engine, plan_id, submission, idempotency_key='evaluate')
        observed = workflow.get_verify_observation(maker, plan_id, 1)
        decision = next(r['body'] for r in observed['records'] if r['kind'] == 'engine_decision')
        evaluation = next(r['body'] for r in observed['records'] if r['kind'] == 'evaluation')
        final = repo.connection.execute('SELECT kind FROM wp3_finals WHERE plan_id=?', (plan_id,)).fetchone()
        return dict(application_reference=observed['application_reference'], plan=observed['plan'],
                    decision=decision, evaluation=evaluation, versions=observed['versions'], audit=observed['audit'],
                    questions=[r['body'] for r in observed['records'] if r['kind'] == 'escalation'],
                    final_decision='APPROVED' if final and final['kind'] == 'engine_decision' else None,
                    decision_source='AI_AUTO_APPROVAL' if final else None)
    finally:
        repo.close()


def compare_observation(actual, expected):
    try:
        validate_observation(actual)
    except ValueError as exc:
        return ['Invalid persisted observation: ' + str(exc)]
    checks = {'route': actual['decision']['outcome'], 'business_status': actual['plan']['state']['plan_status'],
              'processing_stage': actual['plan']['state']['processing_stage'],
              'final_decision': actual['final_decision'], 'decision_source': actual['decision_source']}
    errors = [f'{key}: expected {expected[key]}, observed {value}' for key, value in checks.items() if expected[key] != value]
    # BA explicitly leaves category null for hard-violation cases. WP1 requires
    # a non-null review category; null is unspecified here, not a runtime change.
    if expected['primary_category'] is not None and actual['decision']['escalation_category'] != expected['primary_category']:
        errors.append('Primary category mismatch')
    evaluation = actual['evaluation']
    failed = {c['rule_id'] for c in actual['decision']['rule_checks'] if c['result'] != 'PASS'}
    observed_codes = {
        'MEDIA_REVIEW_REQUIRED': 'MEDIA_PASS' in failed,
        'UNRESOLVED_CONFLICT': bool(evaluation['evidence_conflicts']) and 'NO_EVIDENCE_CONFLICT' in failed,
        'BUDGET_LIMIT_EXCEEDED': 'BUDGET_LIMIT' in failed,
        'HARD_VIOLATION': 'NO_HARD_VIOLATION' in failed,
        'POLICY_SCOPE_MISSING': any(f['rule_id'] == 'POLICY_SCOPE_MISSING' for f in evaluation['media_findings']),
        'VLM_LOW_CONFIDENCE': any(e['evidence_id'] == 'fixture-provenance' and
                                  json.loads(e['observation'])['vlm']['confidence'] < .85
                                  for e in evaluation['evidence']),
    }
    for code in expected['required_reason_codes']:
        if not observed_codes.get(code, False):
            errors.append('Missing mapped reason evidence: ' + code)
    if evaluation['status'] != 'SUCCEEDED':
        errors.append('Fixture evidence failed to map to a successful evaluation')
    serialized = json.dumps(evaluation, ensure_ascii=False)
    explanation = expected.get('explanation_requirements', {})
    for key in ('affected_fields', 'issue_types', 'required_evidence_refs', 'required_factual_issue_refs'):
        for token in explanation.get(key, []):
            if token not in serialized:
                errors.append('Lost explanation trace: ' + token)
    if actual['plan']['payload']['checker_id'] != expected['assigned_checker_id']:
        errors.append('Assigned Checker mismatch')
    if expected['question_required'] and not actual['questions']:
        errors.append('Missing escalation question')
    return errors


def run_suite(suite='verify'):
    filename = 'verify-inputs.json' if suite == 'verify' else 'ground-truth-cases.json'
    inputs = json.loads((FIXTURES / filename).read_text(encoding='utf-8'))
    rows = []
    for case in inputs:
        started_at, started = now(), perf_counter()
        try:
            actual = execute_input(case['input'])
            rows.append(dict(case_id=case['id'], actual=actual, error=None))
        except Exception as exc:
            rows.append(dict(case_id=case['id'], actual=None, error=str(exc)))
        rows[-1].update(started_at=started_at, completed_at=now(), duration_ms=max(0, int((perf_counter() - started) * 1000)))
    # Oracle access happens only after application execution, never in the provider.
    oracle_file = 'verify-expected-results.json' if suite == 'verify' else filename
    expected = {c['id']: c['expected'] for c in json.loads((FIXTURES / oracle_file).read_text(encoding='utf-8'))}
    for row in rows:
        row['expected'] = expected[row['case_id']]
        row['differences'] = compare_observation(row['actual'], row['expected']) if row['actual'] else [row['error']]
        row['passed'] = not row['differences']
        row['verify_result'] = contract_result(row)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--suite', choices=('verify', 'ground-truth'), default='verify')
    parser.add_argument('--output', type=Path, default=Path('runtime/ba-actual.json'))
    args = parser.parse_args()
    require(FIXTURES.resolve() not in args.output.resolve().parents, 'Cannot overwrite fixtures')
    rows = run_suite(args.suite)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'passed': sum(r['passed'] for r in rows), 'total': len(rows), 'output': str(args.output)}))
    raise SystemExit(0 if all(r['passed'] for r in rows) else 1)


if __name__ == '__main__':
    main()
