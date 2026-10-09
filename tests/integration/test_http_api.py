from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.backend.api.app import create_app
from src.backend.api.dependencies import Settings
from src.backend.demo import MAKER, CHECKER, ENGINE

PNG = b'\x89PNG\r\n\x1a\nsynthetic'


@pytest.fixture
def client(tmp_path, request):
    with TestClient(create_app(Settings('demo', str(tmp_path / 'demo-api.sqlite3'), mock_mode=getattr(request, 'param', 'pass')))) as client:
        yield client


def headers(actor=MAKER, key=None):
    return {'X-Demo-Actor': actor, 'Idempotency-Key': key or uuid4().hex}


def payload(budget='50000000'):
    return dict(title='HTTP campaign', objective='Demo objective', summary='Synthetic strategy',
                department='DEMO-DEPT-01', checker_id=CHECKER, start_date='2026-10-01',
                end_date='2026-10-31', budget_minor_units=budget, currency='VND')


def submitted(client, budget='50000000', plan_id='DEMO-HTTP'):
    draft = client.put(f'/api/plans/{plan_id}/draft', headers=headers(), json={'payload': payload(budget), 'expected_revision': 0})
    assert draft.status_code == 200, draft.text
    uploaded = client.post(f'/api/plans/{plan_id}/attachments', headers=headers(),
                           data={'expected_revision': 1}, files={'file': ('image.png', PNG, 'image/png')})
    assert uploaded.status_code == 200, uploaded.text
    response = client.post(f'/api/plans/{plan_id}/submit', headers=headers(),
                           json={'expected_revision': 2, 'expected_policy_version': 'DEMO-HTTP-2'})
    assert response.status_code == 200, response.text
    return uploaded.json()['attachments'][0]


def evaluate(client, plan_id='DEMO-HTTP', number=1, key=None):
    return client.post(f'/api/plans/{plan_id}/rounds/{number}/evaluate', headers=headers(key=key), json={'expected_revision': 0})


def test_review_replay_private_media_and_locked_snapshot(client):
    attachment = submitted(client)
    result = evaluate(client, key='evaluate-once')
    assert result.status_code == 200, result.text
    assert result.json()['decision']['outcome'] == 'HUMAN_REVIEW_REQUIRED'
    assert evaluate(client, key='evaluate-once').json() == result.json()
    assert evaluate(client).status_code == 409
    history = client.get('/api/plans/DEMO-HTTP', headers=headers()).json()
    assert len(history['versions']) == 1
    assert history['plan']['state']['plan_status'] == 'PENDING_APPROVAL'
    response = client.put('/api/plans/DEMO-HTTP/draft', headers=headers(), json={'payload': {}, 'expected_revision': 4})
    assert response.status_code == 409
    url = '/api/plans/DEMO-HTTP/attachments/' + attachment['attachment_id']
    assert client.get(url).status_code == 401
    assert client.get(url, headers=headers('DEMO-DUAL-01')).status_code == 403
    assert client.get(url, headers=headers(CHECKER)).content == PNG


@pytest.mark.parametrize('client', ['review'], indirect=True)
def test_reject_revise_resubmit_approve_and_preserve_history(client):
    submitted(client, '100000001')
    result = evaluate(client).json()
    assert result['decision']['escalation_category'] == 'AUTHORITY_EXCEEDED'
    url = '/api/plans/DEMO-HTTP/rounds/1/decision'
    body = {'action': 'APPROVED', 'expected_revision': 1, 'reason': None, 'override_reason': None}
    assert client.post(url, headers=headers(), json=body).status_code == 403
    assert client.post(url, headers=headers(CHECKER), json=body).status_code == 422
    body.update(action='REJECTED')
    assert client.post(url, headers=headers(CHECKER), json=body).status_code == 422
    body.update(reason='Reduce budget')
    assert client.post(url, headers=headers(CHECKER), json=body).status_code == 200
    old = client.get('/api/plans/DEMO-HTTP', headers=headers()).json()
    draft = client.put('/api/plans/DEMO-HTTP/draft', headers=headers(),
                       json={'payload': payload('100000002'), 'expected_revision': old['plan']['revision']})
    assert draft.status_code == 200
    response = client.post('/api/plans/DEMO-HTTP/submit', headers=headers(),
                           json={'expected_revision': draft.json()['revision'], 'expected_policy_version': 'DEMO-HTTP-2'})
    assert response.status_code == 200
    assert evaluate(client, number=2).status_code == 200
    body.update(action='APPROVED', override_reason='Checker accepts budget after review')
    url = '/api/plans/DEMO-HTTP/rounds/2/decision'
    assert client.post(url, headers=headers(CHECKER, 'approve-once'), json=body).status_code == 200
    assert client.post(url, headers=headers(CHECKER, 'approve-once'), json=body).status_code == 200
    current = client.get('/api/plans/DEMO-HTTP', headers=headers()).json()
    assert len(current['versions']) == 2
    assert current['versions'][0] == old['versions'][0]
    assert current['records'][:len(old['records'])] == old['records']
    assert current['plan']['state']['plan_status'] == 'APPROVED'


def test_strict_dto_auth_cors_and_idempotency(client):
    assert client.get('/api/config').status_code == 401
    assert client.get('/api/config', headers=headers(ENGINE)).status_code == 401
    for body in ({'payload': {}, 'expected_revision': 0, 'role': 'ADMIN'},
                 {'payload': {'maker_id': CHECKER}, 'expected_revision': 0},
                 {'payload': {'expected_outcome': 'AUTO_APPROVED'}, 'expected_revision': 0}):
        response = client.put('/api/plans/DEMO-DRAFT/draft', headers=headers(), json=body)
        assert response.status_code == 422
        assert set(response.json()) == {'code', 'message', 'correlation_id', 'http_status'}
    body = {'payload': {}, 'expected_revision': 0}
    first = client.put('/api/plans/DEMO-DRAFT/draft', headers=headers(key='once'), json=body)
    assert first.status_code == 200
    assert client.put('/api/plans/DEMO-DRAFT/draft', headers=headers(key='once'), json=body).json() == first.json()
    assert client.put('/api/plans/DEMO-DRAFT/draft', headers=headers(), json=body).status_code == 409
    body['payload'] = {'title': 'different'}
    assert client.put('/api/plans/DEMO-DRAFT/draft', headers=headers(key='once'), json=body).status_code == 409
    assert client.get('/api/plans', headers=headers('DEMO-DUAL-01')).json() == []
    preflight = client.options('/api/plans', headers={'Origin': 'http://127.0.0.1:5173', 'Access-Control-Request-Method': 'PUT'})
    assert preflight.headers['access-control-allow-origin'] == 'http://127.0.0.1:5173'
    assert 'access-control-allow-origin' not in client.get('/api/health', headers={'Origin': 'https://untrusted.example'}).headers


@pytest.mark.parametrize('mode', ['timeout', 'error', 'malformed'])
def test_provider_failure_does_not_rollback_submission(tmp_path, mode):
    with TestClient(create_app(Settings('demo', str(tmp_path / 'demo-failure.sqlite3'), mock_mode=mode))) as client:
        submitted(client)
        response = evaluate(client)
        assert response.status_code == 200, response.text
        assert response.json()['decision']['outcome'] == 'HUMAN_REVIEW_REQUIRED'
        assert response.json()['evaluation']['status'] != 'SUCCEEDED'
        assert client.get('/api/plans/DEMO-HTTP', headers=headers()).json()['plan']['current_round'] == 1


def test_production_rejects_demo_auth_without_creating_database(tmp_path):
    path = tmp_path / 'demo-production.sqlite3'
    with TestClient(create_app(Settings('production', str(path)))) as client:
        assert client.get('/api/config', headers=headers()).status_code == 401
        assert client.get('/api/plans', headers=headers()).status_code == 401
        assert client.get('/openapi.json').status_code == 200
    assert not path.exists()


def test_verify_replay_and_suite_conflict(client):
    first = client.post('/api/verify/general', json={}, headers=headers(key='verify-once'))
    assert first.status_code == 200
    rows = first.json()['rows']
    assert len(rows) == 4
    assert all(r['passed'] and r['verify_result']['pass'] for r in rows)
    assert [r['actual']['decision']['outcome'] for r in rows].count('AUTO_APPROVED') == 3
    assert [r['actual']['decision']['outcome'] for r in rows].count('HUMAN_REVIEW_REQUIRED') == 1
    assert client.post('/api/verify/general', json={}, headers=headers(key='verify-once')).json() == first.json()
    assert client.post('/api/verify/escalation', json={}, headers=headers(key='verify-once')).status_code == 409


def test_verify_escalation_suite_runs_three_routine_and_two_review_cases(client):
    response = client.post('/api/verify/escalation', json={}, headers=headers(key='verify-escalation'))
    assert response.status_code == 200, response.text
    rows = response.json()['rows']
    assert len(rows) == 5
    assert all(row['passed'] for row in rows)
    assert [row['actual']['decision']['outcome'] for row in rows].count('AUTO_APPROVED') == 3
    review_rows = [row for row in rows if row['actual']['decision']['outcome'] == 'HUMAN_REVIEW_REQUIRED']
    assert len(review_rows) == 2
    fact_case = next(row for row in review_rows if row['actual']['decision']['escalation_category'] == 'FACT_UNCERTAIN')
    assert fact_case['actual']['questions'][0]['question'].strip()
    assert fact_case['actual']['evaluation']['evidence']
    assert all(row['started_at'] <= row['completed_at'] and row['duration_ms'] >= 0 for row in rows)


def test_verify_regression_catalog_runs_all_fifteen_synthetic_cases(client):
    response = client.post('/api/verify/regression', json={}, headers=headers(key='verify-regression'))
    assert response.status_code == 200, response.text
    rows = response.json()['rows']
    assert len(rows) == 15
    assert all(row['passed'] for row in rows)
    assert {row['expected']['primary_category'] for row in rows if row['expected']['primary_category']} == {
        'FACT_UNCERTAIN', 'POLICY_OUT_OF_SCOPE', 'AUTHORITY_EXCEEDED',
    }
    assert all(row['data_classification'].startswith('SYNTHETIC') for row in rows)


def test_new_plan_input_uses_mock_provider_and_real_policy_engine_for_budget_rules(client):
    decisions = []
    plan_ids = []
    budget_results = []
    cases = (
        ('Autumn community campaign', '50000000', 'PASS'),
        ('Winter store opening campaign', '150000000', 'FAIL'),
    )
    for title, budget, expected_budget_result in cases:
        plan_id = str(uuid4())
        plan_ids.append(plan_id)
        custom_payload = {**payload(budget), 'title': title, 'objective': 'Measure qualified customer interest.'}
        draft = client.put(f'/api/plans/{plan_id}/draft', headers=headers(), json={
            'payload': custom_payload, 'expected_revision': 0,
        })
        assert draft.status_code == 200, draft.text
        uploaded = client.post(f'/api/plans/{plan_id}/attachments', headers=headers(),
                               data={'expected_revision': draft.json()['revision']},
                               files={'file': ('custom.png', PNG, 'image/png')})
        assert uploaded.status_code == 200, uploaded.text
        submission = client.post(f'/api/plans/{plan_id}/submit', headers=headers(), json={
            'expected_revision': uploaded.json()['revision'],
            'expected_policy_version': 'DEMO-HTTP-2',
        })
        assert submission.status_code == 200, submission.text

        result = evaluate(client, plan_id=plan_id)
        assert result.status_code == 200, result.text
        body = result.json()
        assert body['evaluation']['provider'] == 'MOCK_VLM'
        assert body['evaluation']['model_version'] == 'mock-1'
        assert body['decision']['outcome'] == 'HUMAN_REVIEW_REQUIRED'
        assert body['decision']['plan_id'] == plan_id
        rule_results = {item['rule_id']: item['result'] for item in body['decision']['rule_checks']}
        assert rule_results['BUDGET_LIMIT'] == expected_budget_result
        budget_results.append(rule_results['BUDGET_LIMIT'])
        decisions.append(body['decision']['outcome'])

        history = client.get(f'/api/plans/{plan_id}', headers=headers()).json()
        assert history['plan']['payload']['title'] == title
        assert history['versions'][0]['payload']['title'] == title

    assert len(set(plan_ids)) == 2
    assert decisions == ['HUMAN_REVIEW_REQUIRED', 'HUMAN_REVIEW_REQUIRED']
    assert budget_results == ['PASS', 'FAIL']


def test_invalid_upload_and_submission_leave_draft(client):
    assert client.put('/api/plans/DEMO-INVALID/draft', headers=headers(), json={'payload': {}, 'expected_revision': 0}).status_code == 200
    response = client.post('/api/plans/DEMO-INVALID/attachments', headers=headers(),
                           data={'expected_revision': 1}, files={'file': ('fake.png', b'not png', 'image/png')})
    assert response.status_code == 422
    response = client.post('/api/plans/DEMO-INVALID/submit', headers=headers(),
                           json={'expected_revision': 1, 'expected_policy_version': 'DEMO-HTTP-2'})
    assert response.status_code == 422
    history = client.get('/api/plans/DEMO-INVALID', headers=headers()).json()
    assert history['plan']['state']['plan_status'] == 'DRAFT'
    assert history['versions'] == []
