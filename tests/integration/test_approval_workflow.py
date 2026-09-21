"""WP3 application-path tests use real SQLite transactions and WP2 rules."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
import sqlite3

import pytest

from src.backend.application.workflow import ApprovalWorkflow, ApplicationError
from src.backend.repositories.approval import ApprovalRepository
from src.backend.domain.policy import (
    ApprovalConfiguration, PolicySnapshot, BudgetConfiguration, AuthoritySnapshot, Criterion,
)


MAKER = 'maker'
CHECKER = 'checker'
ENGINE = 'pipeline'
IMAGE = b'\x89PNG\r\n\x1a\nsynthetic-test-media'
USERS = {MAKER: ('MAKER',), CHECKER: ('CHECKER',),
         'other': ('CHECKER',), ENGINE: ('EVALUATOR',)}


def configuration():
    return ApprovalConfiguration(
        PolicySnapshot('policy-1', 'POLICY-1', True,
                       ('title', 'maker_id', 'checker_id', 'department', 'objective',
                        'summary', 'start_date', 'end_date', 'budget_minor_units', 'currency'),
                       (Criterion('total', 100),), ('mock-1',), ('image/png',), 100000),
        (BudgetConfiguration('budget-1', 'VND', 0, '10000', 'marketing', True),),
        AuthoritySnapshot('authority-1', 'VND', '10000', ('marketing',),
                          CHECKER, 'policy-owner', 'budget-owner', True),
    )


def payload(**changes):
    return dict(title='Campaign', checker_id=CHECKER, department='marketing',
                objective='Reach customers', summary='Campaign overview',
                start_date='2026-10-01', end_date='2026-10-31',
                budget_minor_units='10000', currency='VND', **changes)


@pytest.fixture
def app(tmp_path):
    repo = ApprovalRepository(tmp_path / 'approval.sqlite')
    service = ApprovalWorkflow(repo, configuration(), USERS, evaluator_id=ENGINE)
    yield service
    repo.close()


def save(app, data=None, revision=0, key='save'):
    return app.save_draft(MAKER, 'plan', payload() if data is None else data,
                          expected_revision=revision, idempotency_key=key, correlation_id='trace')


def submitted(app):
    draft = save(app)
    draft = app.upload_attachment(MAKER, 'plan', IMAGE, 'image/png',
                                  expected_revision=draft['revision'],
                                  idempotency_key='upload', correlation_id='trace')
    return app.submit_plan(MAKER, 'plan', expected_revision=draft['revision'],
                           expected_policy_version='POLICY-1',
                           idempotency_key='submit', correlation_id='trace')


def evaluation(submission, review=False):
    snapshot, ticket = submission['snapshot'], submission['evaluation_ticket']
    attachment = snapshot['attachments'][0]
    now = ticket['created_at']
    return dict(
        evaluation_id=ticket['evaluation_id'], run_id=ticket['run_id'],
        plan_id='plan', plan_version=snapshot['plan_version'],
        approval_round=snapshot['approval_round'], input_hash=submission['input_hash'],
        policy_version='POLICY-1', provider='MOCK_VLM', model_version='mock-1',
        schema_version=1, status='SUCCEEDED', media_result='PASS', media_findings=[],
        media_confidence=.7 if review else .9, feasibility_score=71,
        feasibility_confidence=.9, missing_facts=[], evidence_conflicts=[],
        evidence=[dict(evidence_id='image-evidence', source_type='ATTACHMENT',
                       source_ref=attachment['attachment_id'], observation='Image inspected',
                       content_hash=attachment['content_hash'])],
        proposed_action='RECOMMEND_HUMAN_REVIEW' if review else 'RECOMMEND_AUTO_APPROVAL',
        escalation_category='FACT_UNCERTAIN' if review else None,
        reason='Structured test evaluation', latency_ms=1, created_at=now,
        started_at=now, completed_at=now, agent_errors=[], raw_output_hash=None,
        reported_model_version=None, correlation_id=ticket['correlation_id'],
        criterion_scores=[dict(criterion_id='total', score=71, maximum_score=100,
                               rationale='Test assessment', evidence_refs=['image-evidence'])],
        assumptions=[],
    )


def evaluate(app, submission, raw=None, key='evaluate'):
    return app.evaluate_round(ENGINE, 'plan', submission['snapshot']['approval_round'],
                              evaluation(submission, review=True) if raw is None else raw,
                              expected_revision=0, expected_policy_version='POLICY-1',
                              idempotency_key=key, correlation_id='evaluation-trace')


def human(app, action='REJECTED', reason='Revise objective', override_reason=None,
          actor=CHECKER, key='human', round_number=1, revision=1):
    return app.decide_round(actor, 'plan', round_number, action,
                            reason=reason, override_reason=override_reason,
                            expected_revision=revision, idempotency_key=key,
                            correlation_id='human-trace')


def assert_error(code, operation):
    with pytest.raises(ApplicationError) as exc:
        operation()
    assert exc.value.code == code
    assert exc.value.correlation_id


def test_incomplete_draft_and_invalid_submission(app):
    draft = save(app, {})
    assert draft['state']['plan_status'] == 'DRAFT'
    assert draft['payload'] == {'maker_id': MAKER}
    assert_error('VALIDATION_ERROR', lambda: app.submit_plan(
        MAKER, 'plan', expected_revision=1, expected_policy_version='POLICY-1',
        idempotency_key='submit', correlation_id='trace'))
    observation = app.get_plan(MAKER, 'plan')
    assert observation['versions'] == []
    assert len(observation['audit']) == 1


def test_submission_snapshot_replay_and_lock(app):
    first = submitted(app)
    replay = app.submit_plan(MAKER, 'plan', expected_revision=2,
                             expected_policy_version='POLICY-1',
                             idempotency_key='submit', correlation_id='retry-trace')
    assert replay == first
    assert first['snapshot']['plan_version'] == first['snapshot']['approval_round'] == 1
    assert first['round']['status'] == 'ACTIVE'
    assert first['snapshot']['attachments'][0]['content_hash'] == sha256(IMAGE).hexdigest()
    assert_error('CONFLICT', lambda: save(app, revision=3, key='locked-edit'))
    assert_error('CONFLICT', lambda: app.submit_plan(
        MAKER, 'plan', expected_revision=3, expected_policy_version='POLICY-1',
        idempotency_key='second-submit', correlation_id='trace'))
    first['snapshot']['payload']['title'] = 'Mutated response'
    observation = app.get_plan(MAKER, 'plan')
    assert observation['versions'][0]['payload']['title'] == 'Campaign'
    assert len(observation['rounds']) == 1
    assert len(observation['audit']) == 3


def test_rejection_resubmission_preserves_history(app):
    first = submitted(app)
    evaluate(app, first)
    assert_error('VALIDATION_ERROR', lambda: human(app, reason='  '))
    decision = human(app)
    assert human(app) == decision
    before = app.get_plan(MAKER, 'plan')
    assert before['plan']['state']['plan_status'] == 'REJECTED'
    edited = save(app, {**payload(), 'title': 'Revised campaign'},
                  revision=before['plan']['revision'], key='revise')
    second = app.submit_plan(MAKER, 'plan', expected_revision=edited['revision'],
                             expected_policy_version='POLICY-1',
                             idempotency_key='resubmit', correlation_id='round-2')
    after = app.get_plan(MAKER, 'plan')
    assert second['snapshot']['plan_version'] == second['snapshot']['approval_round'] == 2
    assert second['input_hash'] != first['input_hash']
    assert after['versions'][0] == before['versions'][0]
    assert after['rounds'][0] == before['rounds'][0]
    assert after['records'] == before['records']
    assert after['audit'][:len(before['audit'])] == before['audit']
    assert [r['status'] for r in after['rounds']] == ['CLOSED', 'ACTIVE']


def test_checker_authorization_override_and_final_replay(app):
    submission = submitted(app)
    evaluate(app, submission)
    assert_error('FORBIDDEN', lambda: human(app, actor=MAKER))
    assert_error('FORBIDDEN', lambda: human(app, actor='other'))
    assert_error('VALIDATION_ERROR', lambda: human(app, action='APPROVED', reason=None))
    result = human(app, action='APPROVED', reason=None, override_reason='Evidence verified')
    assert human(app, action='APPROVED', reason=None, override_reason='Evidence verified') == result
    assert_error('CONFLICT', lambda: human(app, key='another'))
    observation = app.get_plan(CHECKER, 'plan')
    assert observation['plan']['state']['plan_status'] == 'APPROVED'
    assert observation['rounds'][0]['status'] == 'CLOSED'
    assert len([r for r in observation['records'] if r['kind'] == 'human_decision']) == 1


def test_audit_metadata_and_correlation(app):
    submission = submitted(app)
    routed = evaluate(app, submission)
    decision = human(app)
    events = app.get_plan(MAKER, 'plan')['audit']
    final = events[-1]
    assert final['human_decision_id'] == decision['human_decision_id']
    assert final['decision_id'] == routed['decision']['decision_id']
    assert final['input_hash'] == submission['input_hash']
    assert final['correlation_id'] == 'human-trace'
    assert final['idempotency_key'] == 'human'
    assert final['policy_snapshot_id'] == 'policy-1'
    assert final['actor_id'] == CHECKER
    assert final['timestamp'] == decision['decided_at']
    assert final['human_action'] == 'REJECTED'
    assert final['outcome'] is None


def test_audit_failure_rolls_back_submission_and_allows_retry(app):
    save(app)
    app.upload_attachment(MAKER, 'plan', IMAGE, 'image/png', expected_revision=1,
                          idempotency_key='upload', correlation_id='trace')
    app.repository.connection.execute("""CREATE TRIGGER fail_submission
        BEFORE INSERT ON wp3_audit WHEN json_extract(NEW.body, '$.action') = 'PLAN_SUBMITTED'
        BEGIN SELECT RAISE(ABORT, 'injected audit failure'); END""")
    assert_error('UNAVAILABLE', lambda: app.submit_plan(
        MAKER, 'plan', expected_revision=2, expected_policy_version='POLICY-1',
        idempotency_key='submit', correlation_id='trace'))
    observation = app.get_plan(MAKER, 'plan')
    assert observation['versions'] == observation['rounds'] == []
    assert observation['plan']['state']['plan_status'] == 'DRAFT'
    app.repository.connection.execute('DROP TRIGGER fail_submission')
    result = app.submit_plan(MAKER, 'plan', expected_revision=2,
                             expected_policy_version='POLICY-1',
                             idempotency_key='submit', correlation_id='trace')
    assert result['snapshot']['plan_version'] == 1


@pytest.mark.parametrize('scenario,category', [
    ('auto', None), ('confidence', 'FACT_UNCERTAIN'),
    ('budget', 'AUTHORITY_EXCEEDED'), ('policy', 'POLICY_OUT_OF_SCOPE'),
    ('invalid', 'FACT_UNCERTAIN'), ('timeout', 'FACT_UNCERTAIN'),
])
def test_real_engine_path_and_escalation_questions(app, scenario, category):
    if scenario == 'policy':
        app.configuration = replace(app.configuration, policy=replace(
            app.configuration.policy, auto_approval_policy_enabled=False))
    if scenario == 'budget':
        app.configuration = replace(app.configuration, budgets=(replace(
            app.configuration.budgets[0], limit_minor_units='9999'),))
    submission = submitted(app)
    raw = evaluation(submission, review=scenario == 'confidence')
    if scenario == 'invalid':
        raw.pop('media_confidence')
    if scenario == 'timeout':
        raw.update(status='TIMED_OUT', model_version=None, media_result=None,
                   media_confidence=None, feasibility_score=None, feasibility_confidence=None,
                   proposed_action=None, escalation_category='FACT_UNCERTAIN', criterion_scores=[],
                   agent_errors=[dict(component='provider', code='TIMEOUT', message='Provider timed out')])
    result = evaluate(app, submission, raw)
    assert result['decision']['outcome'] == ('AUTO_APPROVED' if category is None else 'HUMAN_REVIEW_REQUIRED')
    assert result['decision']['escalation_category'] == category
    assert evaluate(app, submission, raw) == result
    observed = app.get_verify_observation(ENGINE, 'plan', 1)
    assert observed['application_reference'] == 'ApprovalWorkflow.get_verify_observation'
    assert len([r for r in observed['records'] if r['kind'] == 'evaluation']) == 1
    if category:
        assert observed['plan']['state']['plan_status'] == 'PENDING_APPROVAL'
        assert any(q['category'] == category for q in result['questions'])
        for question in result['questions']:
            assert question['observed_value']
            assert question['applicable_rule_or_limit']
            assert len(question['answer_options']) >= 2
            assert 'plan' in question['question']
            assert question['evidence_reference'] or 'No trustworthy evidence' in question['reason']
    else:
        assert observed['plan']['state']['plan_status'] == 'APPROVED'
        assert result['questions'] == []
        assert_error('CONFLICT', lambda: human(app))


@pytest.mark.parametrize('change', [
    {'checker_id': MAKER}, {'checker_id': 'missing'}, {'title': ' '},
    {'budget_minor_units': '-1'}, {'start_date': 'invalid'},
    {'start_date': '2026-11-01'},
])
def test_invalid_submission_has_no_partial_writes(app, change):
    save(app, {**payload(), **change})
    app.upload_attachment(MAKER, 'plan', IMAGE, 'image/png', expected_revision=1,
                          idempotency_key='upload', correlation_id='trace')
    assert_error('VALIDATION_ERROR', lambda: app.submit_plan(
        MAKER, 'plan', expected_revision=2, expected_policy_version='POLICY-1',
        idempotency_key='submit', correlation_id='trace'))
    assert app.get_plan(MAKER, 'plan')['versions'] == []


def test_stale_policy_revision_and_idempotency_conflict(app):
    save(app)
    assert_error('CONFLICT', lambda: save(app, {'title': 'Changed'}))
    assert_error('CONFLICT', lambda: save(app, revision=0, key='stale-edit'))
    app.upload_attachment(MAKER, 'plan', IMAGE, 'image/png', expected_revision=1,
                          idempotency_key='upload', correlation_id='trace')
    assert_error('CONFLICT', lambda: app.submit_plan(
        MAKER, 'plan', expected_revision=2, expected_policy_version='OLD',
        idempotency_key='submit', correlation_id='trace'))
    assert_error('UNAUTHENTICATED', lambda: app.get_plan('missing', 'plan'))
    assert_error('FORBIDDEN', lambda: app.get_plan('other', 'plan'))
    assert_error('FORBIDDEN', lambda: save(app, {'maker_id': 'other'}, revision=2, key='spoof'))


def test_locked_upload_and_invalid_media(app):
    first = submitted(app)
    assert_error('CONFLICT', lambda: app.upload_attachment(
        MAKER, 'plan', IMAGE, 'image/png', expected_revision=3,
        idempotency_key='locked-upload', correlation_id='trace'))
    assert_error('FORBIDDEN', lambda: app.evaluate_round(
        MAKER, 'plan', 1, evaluation(first), expected_revision=0,
        expected_policy_version='POLICY-1', idempotency_key='spoof', correlation_id='trace'))


def test_invalid_media_does_not_create_attachment(app):
    save(app)
    assert_error('VALIDATION_ERROR', lambda: app.upload_attachment(
        MAKER, 'plan', b'<script>invalid</script>', 'image/png', expected_revision=1,
        idempotency_key='upload', correlation_id='trace'))
    assert app.get_plan(MAKER, 'plan')['plan']['attachments'] == []


def test_database_protects_history_and_single_active_round(app):
    submission = submitted(app)
    connection = app.repository.connection
    for statement in ("UPDATE wp3_records SET body='{}'", 'DELETE FROM wp3_records',
                      'DELETE FROM wp3_audit', 'DELETE FROM wp3_attachments',
                      "UPDATE wp3_rounds SET configuration='{}'", 'DELETE FROM wp3_rounds'):
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(statement)
    with pytest.raises(sqlite3.IntegrityError):
        app.repository.create_round('plan', 2, configuration(), submission['evaluation_ticket'])
    assert len(app.get_plan(MAKER, 'plan')['rounds']) == 1


def test_decision_audit_failure_rolls_back_final_and_replay_claim(app):
    submission = submitted(app)
    evaluate(app, submission)
    before = app.get_plan(MAKER, 'plan')
    app.repository.connection.execute("""CREATE TRIGGER fail_human BEFORE INSERT ON wp3_audit
        WHEN json_extract(NEW.body, '$.action') = 'HUMAN_REJECTED'
        BEGIN SELECT RAISE(ABORT, 'injected audit failure'); END""")
    assert_error('UNAVAILABLE', lambda: human(app))
    assert app.get_plan(MAKER, 'plan') == before
    app.repository.connection.execute('DROP TRIGGER fail_human')
    assert human(app)['action'] == 'REJECTED'


def test_concurrent_decisions_on_separate_connections_have_one_winner(app, tmp_path):
    from threading import Barrier
    submission = submitted(app)
    evaluate(app, submission)
    barrier = Barrier(2)
    def worker(key):
        repo = ApprovalRepository(tmp_path / 'approval.sqlite')
        service = ApprovalWorkflow(repo, configuration(), USERS, evaluator_id=ENGINE)
        try:
            barrier.wait(timeout=10)
            return human(service, key=key)['action']
        except ApplicationError as exc:
            return exc.code
        finally:
            repo.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, ('one', 'two')))
    assert sorted(results) == ['CONFLICT', 'REJECTED']
    history = app.get_plan(MAKER, 'plan')
    assert len([r for r in history['records'] if r['kind'] == 'human_decision']) == 1
    assert len([a for a in history['audit'] if a['action'] == 'HUMAN_REJECTED']) == 1


def test_restart_retains_idempotency_and_history(app, tmp_path):
    submission = submitted(app)
    before = app.get_plan(MAKER, 'plan')
    repo = ApprovalRepository(tmp_path / 'approval.sqlite')
    restarted = ApprovalWorkflow(repo, configuration(), USERS, evaluator_id=ENGINE)
    try:
        assert restarted.get_plan(MAKER, 'plan') == before
        assert restarted.submit_plan(MAKER, 'plan', expected_revision=2,
                                     expected_policy_version='POLICY-1', idempotency_key='submit',
                                     correlation_id='restart') == submission
    finally:
        repo.close()


def test_evaluation_lifecycle_audit_and_configuration_snapshot(app):
    submission = submitted(app)
    # Live policy changes cannot silently alter an already submitted round.
    app.configuration = replace(configuration(), policy=replace(
        configuration().policy, auto_approval_policy_enabled=False))
    result = evaluate(app, submission, evaluation(submission))
    assert result['decision']['outcome'] == 'AUTO_APPROVED'
    events = app.get_plan(MAKER, 'plan')['audit']
    assert [e['action'] for e in events[-3:]] == [
        'EVALUATION_STARTED', 'EVALUATION_COMPLETED', 'AUTO_APPROVED']
    assert all(e['run_id'] == submission['evaluation_ticket']['run_id'] for e in events[-3:])
    assert all(e['actor_type'] == 'SYSTEM' for e in events[-3:])


def test_failed_evaluation_is_audited_without_rolling_back_submission(app):
    submission = submitted(app)
    evaluate(app, submission, {'broken': True})
    history = app.get_plan(MAKER, 'plan')
    assert len(history['versions']) == 1
    assert [e['action'] for e in history['audit'][-3:]] == [
        'EVALUATION_STARTED', 'EVALUATION_FAILED', 'ENGINE_ROUTED']
    assert history['plan']['state']['processing_stage'] == 'HUMAN_REVIEW_REQUIRED'


def test_suspicious_input_cannot_auto_approve(app):
    submission = submitted(app)
    result = app.evaluate_round(
        ENGINE, 'plan', 1, evaluation(submission), expected_revision=0,
        expected_policy_version='POLICY-1', idempotency_key='evaluate',
        correlation_id='trace', suspicious_input=True)
    assert result['decision']['outcome'] == 'HUMAN_REVIEW_REQUIRED'
    assert 'INPUT_INTEGRITY' in [r['rule_id'] for r in result['decision']['rule_checks']
                                 if r['result'] != 'PASS']


@pytest.mark.parametrize('same_key', [False, True])
def test_concurrent_submissions_are_atomic(app, tmp_path, same_key):
    from threading import Barrier
    save(app)
    app.upload_attachment(MAKER, 'plan', IMAGE, 'image/png', expected_revision=1,
                          idempotency_key='upload', correlation_id='trace')
    barrier = Barrier(2)
    def worker(key):
        repo = ApprovalRepository(tmp_path / 'approval.sqlite')
        service = ApprovalWorkflow(repo, configuration(), USERS, evaluator_id=ENGINE)
        try:
            barrier.wait(timeout=10)
            return service.submit_plan(MAKER, 'plan', expected_revision=2,
                                       expected_policy_version='POLICY-1',
                                       idempotency_key=key, correlation_id='race')
        except ApplicationError as exc:
            return exc.code
        finally:
            repo.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, ('same', 'same' if same_key else 'different')))
    if same_key:
        assert results[0] == results[1]
    else:
        assert sum(isinstance(result, dict) for result in results) == 1
        assert 'CONFLICT' in results
    history = app.get_plan(MAKER, 'plan')
    assert len(history['versions']) == len(history['rounds']) == 1
    assert len([a for a in history['audit'] if a['action'] == 'PLAN_SUBMITTED']) == 1


def test_failed_engine_commit_preserves_submission_and_can_retry(app):
    submission = submitted(app)
    before = app.get_plan(MAKER, 'plan')
    app.repository.connection.execute("""CREATE TRIGGER fail_engine BEFORE INSERT ON wp3_audit
        WHEN json_extract(NEW.body, '$.action') = 'AUTO_APPROVED'
        BEGIN SELECT RAISE(ABORT, 'injected engine audit failure'); END""")
    assert_error('UNAVAILABLE', lambda: evaluate(app, submission, evaluation(submission)))
    assert app.get_plan(MAKER, 'plan') == before
    app.repository.connection.execute('DROP TRIGGER fail_engine')
    assert evaluate(app, submission, evaluation(submission))['decision']['outcome'] == 'AUTO_APPROVED'


def test_stale_evaluation_and_old_round_cannot_mutate_resubmission(app):
    submission = submitted(app)
    assert_error('CONFLICT', lambda: app.evaluate_round(
        ENGINE, 'plan', 1, evaluation(submission), expected_revision=0,
        expected_policy_version='OLD', idempotency_key='stale', correlation_id='trace'))
    evaluate(app, submission)
    human(app)
    draft = app.get_plan(MAKER, 'plan')['plan']
    second = app.submit_plan(MAKER, 'plan', expected_revision=draft['revision'],
                             expected_policy_version='POLICY-1', idempotency_key='resubmit',
                             correlation_id='second')
    before = app.get_plan(MAKER, 'plan')
    assert_error('CONFLICT', lambda: evaluate(app, submission, key='late-evaluation'))
    assert_error('CONFLICT', lambda: human(app, key='late-decision'))
    assert app.get_plan(MAKER, 'plan') == before
    assert second['snapshot']['approval_round'] == 2


def test_draft_update_and_upload_replay_are_atomic(app):
    first = save(app, {'title': 'Incomplete'})
    updated = save(app, revision=first['revision'], key='complete')
    uploaded = app.upload_attachment(MAKER, 'plan', IMAGE, 'image/png',
                                     expected_revision=updated['revision'], idempotency_key='upload',
                                     correlation_id='trace')
    assert app.upload_attachment(MAKER, 'plan', IMAGE, 'image/png',
                                 expected_revision=updated['revision'], idempotency_key='upload',
                                 correlation_id='retry') == uploaded
    assert len(uploaded['attachments']) == 1
    assert len(app.get_plan(MAKER, 'plan')['audit']) == 3


def test_dual_role_maker_still_cannot_self_approve(app):
    app.principals[MAKER] = frozenset(('MAKER', 'CHECKER'))
    submission = submitted(app)
    evaluate(app, submission)
    assert_error('FORBIDDEN', lambda: human(app, actor=MAKER))


def test_unassigned_maker_cannot_change_draft(app):
    app.principals['other-maker'] = frozenset(('MAKER',))
    save(app)
    assert_error('FORBIDDEN', lambda: app.save_draft(
        'other-maker', 'plan', payload(), expected_revision=1,
        idempotency_key='steal', correlation_id='trace'))


def test_application_error_wire_shape(app):
    try:
        save(app, {'title': 'Draft'}, key=' ')
    except ApplicationError as exc:
        assert exc.to_dict() == dict(code='VALIDATION_ERROR', message='Blank string', correlation_id='trace')
    else:
        pytest.fail('Blank idempotency key accepted')
