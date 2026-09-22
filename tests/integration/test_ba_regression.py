import json
from pathlib import Path

import pytest

from src.verify.runner import execute_input, compare_observation

FIXTURES = Path(__file__).parents[1] / 'fixtures/ba/v2.1'
CASES = json.loads((FIXTURES / 'ground-truth-cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_ba_application_regression(case):
    observation = execute_input(case['input'], FIXTURES)
    assert not compare_observation(observation, case['expected'])
    evaluation = observation['evaluation']
    assert evaluation['status'] == 'SUCCEEDED'
    assert evaluation['feasibility_score'] == case['input']['agent_outputs']['strategy']['score']
    assert evaluation['media_confidence'] == case['input']['agent_outputs']['media']['confidence']
    if 'fact_verification' in case['input']:
        assert observation['decision']['escalation_category'] == 'FACT_UNCERTAIN'
        assert observation['final_decision'] is None
        for issue in case['input']['fact_verification']['issues']:
            assert issue['issue_id'] in json.dumps(evaluation, ensure_ascii=False)
            assert issue['field'] in json.dumps(evaluation, ensure_ascii=False)


def test_verify_inputs_against_separate_oracle():
    inputs = json.loads((FIXTURES / 'verify-inputs.json').read_text(encoding='utf-8'))
    actuals = {c['id']: execute_input(c['input'], FIXTURES) for c in inputs}
    expected = json.loads((FIXTURES / 'verify-expected-results.json').read_text(encoding='utf-8'))
    for case in expected:
        assert not compare_observation(actuals[case['id']], case['expected'])
