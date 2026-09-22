from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest

from src.shared.validation import ValidationError
from src.verify.ba_adapter import payload_from_input, validate_input
from src.verify.runner import execute_input, FIXTURES

CASES = json.loads((FIXTURES / 'ground-truth-cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('field', ['expected', 'expected_category', 'case_id', 'unknown_field'])
def test_oracle_and_unknown_fields_rejected(field):
    data = deepcopy(CASES[0]['input'])
    data[field] = 'AUTO_APPROVED'
    with pytest.raises(ValidationError):
        payload_from_input(data)


def test_missing_fact_mapping_cannot_silently_pass():
    data = deepcopy(CASES[6]['input'])
    del data['fact_verification']
    with pytest.raises(ValidationError, match='Factual evidence lost'):
        validate_input(data)
    data = deepcopy(CASES[6]['input'])
    data['fact_verification']['issues'][0]['verified_value'] = 123
    with pytest.raises(ValidationError):
        validate_input(data)
    data = deepcopy(CASES[6]['input'])
    data['fact_verification']['issues'][0]['evidence_refs'] = ['missing-ref']
    with pytest.raises(ValidationError):
        validate_input(data)


def test_image_bytes_hash_and_reference_are_checked(tmp_path):
    shutil.copytree(FIXTURES / 'images', tmp_path / 'images')
    data = deepcopy(CASES[0]['input'])
    path = tmp_path / 'images' / Path(data['plan_snapshot']['attachments'][0]['path']).name
    path.write_bytes(b'\x89PNG\r\n\x1a\nchanged')
    with pytest.raises(ValidationError, match='bytes'):
        execute_input(data, tmp_path)
    data = deepcopy(CASES[0]['input'])
    data['agent_outputs']['vlm']['evidence'][0]['attachment_sha256'] = 'a' * 64
    actual = execute_input(data)
    assert actual['evaluation']['status'] == 'FAILED'
    assert actual['decision']['outcome'] == 'HUMAN_REVIEW_REQUIRED'


def test_ids_and_filename_do_not_select_outcome(tmp_path):
    data = deepcopy(CASES[6]['input'])
    original = execute_input(data)
    (tmp_path / 'images').mkdir()
    attachment = data['plan_snapshot']['attachments'][0]
    shutil.copyfile(FIXTURES / 'images' / Path(attachment['path']).name, tmp_path / 'images' / 'renamed.png')
    attachment['path'] = 'images/renamed.png'
    data['plan_snapshot'].update(plan_id='arbitrary', code='unrelated', name='Different title')
    data['context'].update(round_id='other', run_id='other', correlation_id='other')
    actual = execute_input(data, tmp_path)
    assert actual['decision']['outcome'] == original['decision']['outcome']
    assert actual['decision']['escalation_category'] == original['decision']['escalation_category']


def test_independent_policy_and_authority_failures_keep_precedence():
    data = deepcopy(CASES[6]['input'])
    data['agent_outputs']['media']['hard_violations'] = ['TEST-HARD-RULE']
    assert execute_input(data)['decision']['escalation_category'] == 'POLICY_OUT_OF_SCOPE'
    data['policy_snapshot']['limit_snapshot']['amount_vnd'] = 1
    assert execute_input(data)['decision']['escalation_category'] == 'AUTHORITY_EXCEEDED'


def test_unknown_source_model_cannot_be_hidden_by_adapter():
    data = deepcopy(CASES[0]['input'])
    data['agent_outputs']['vlm']['model_version'] = 'unregistered-model'
    actual = execute_input(data)
    assert actual['evaluation']['status'] == 'FAILED'
    assert actual['decision']['outcome'] == 'HUMAN_REVIEW_REQUIRED'
