"""SYNTHETIC input-only Role 1 adapter. Never accepts a case envelope/oracle.

The proposed fixture schema is not a WP contract. Only existing WP fields cross
the provider boundary; opaque source IDs are trace references, never predicates.
"""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json

from src.ai_pipeline.providers.base import VisualModelProvider, ProviderTimeout, ProviderError
from src.backend.domain.models import EvaluationResult
from src.backend.domain.policy import (
    ApprovalConfiguration, PolicySnapshot, Criterion, BudgetConfiguration,
    AuthoritySnapshot, MANDATORY_FIELDS,
)
from src.shared.validation import require, canonical_hash

MODEL = 'role1-mock-adapter-v2.1'
FIELD_MAP = {'name': 'title', 'department_id': 'department', 'budget_vnd': 'budget_minor_units'}
INPUT_FIELDS = {'context', 'plan_snapshot', 'policy_snapshot', 'agent_outputs',
                'unresolved_conflict_count', 'policy_scope_covered', 'agent_error_count', 'input_hash'}
PLAN_FIELDS = {'plan_id', 'code', 'name', 'maker_id', 'department_id', 'checker_id',
               'objective', 'summary', 'target_audience', 'channels', 'kpi_expected',
               'start_date', 'end_date', 'budget_vnd', 'currency', 'notes', 'attachments'}


def exact(value, keys, optional=()):
    require(isinstance(value, dict) and set(keys) <= set(value)
            and set(value) <= set(keys) | set(optional), 'Missing or unknown Role 1 fields')


def amount(value):
    require(type(value) is int and value >= 0, 'VND requires nonnegative integer units')
    return str(value)


def validate_input(data):
    exact(data, INPUT_FIELDS, {'fact_verification', 'evaluation_fixture_hash'})
    exact(data['plan_snapshot'], PLAN_FIELDS)
    exact(data['context'], {'plan_status', 'approval_round_status', 'plan_version', 'approval_round',
                           'round_id', 'run_id', 'correlation_id', 'final_decision_exists', 'checker_active',
                           'checker_has_permission', 'provider_mode', 'submitted_at'})
    exact(data['policy_snapshot'], {'policy_id', 'version', 'data_classification', 'approval_status',
          'mode', 'enabled', 'effective_from', 'effective_to', 'score_threshold', 'score_operator',
          'vlm_confidence_threshold', 'media_confidence_threshold', 'media_confidence_gate_status',
          'strategy_confidence_threshold', 'criteria_weights', 'content_policy_ref', 'limit_snapshot'})
    exact(data['policy_snapshot']['limit_snapshot'], {'id', 'version', 'amount_vnd', 'currency',
          'scope_department_id', 'effective_from', 'effective_to', 'data_classification'})
    for attachment in data['plan_snapshot']['attachments']:
        exact(attachment, {'attachment_id', 'path', 'sha256', 'mime_type', 'size_bytes', 'upload_status'})
    exact(data['agent_outputs'], {'vlm', 'media', 'strategy', 'budget'})
    exact(data['agent_outputs']['vlm'], {'status', 'confidence', 'model_version', 'agent_version',
          'prompt_version', 'description', 'objects', 'quality_flags', 'evidence'})
    exact(data['agent_outputs']['media'], {'status', 'result', 'confidence', 'model_version',
          'agent_version', 'prompt_version', 'policy_version', 'hard_violations', 'warnings', 'evidence_refs'})
    exact(data['agent_outputs']['strategy'], {'status', 'score', 'confidence', 'model_version',
          'agent_version', 'prompt_version', 'criteria', 'assumptions', 'critical_gaps'})
    require(data['context']['provider_mode'] == 'MOCK', 'Only synthetic MOCK inputs supported')
    require(data['plan_snapshot']['currency'] == 'VND', 'Only VND fixture mapping supported')
    amount(data['plan_snapshot']['budget_vnd'])
    require(type(data['policy_scope_covered']) is bool, 'Invalid policy scope')
    facts = data.get('fact_verification')
    if facts is not None:
        exact(facts, {'schema_version', 'verification_status', 'assertion_origin', 'issues'})
        require(facts['schema_version'] == 'role1.fact-verification/1.0-proposed'
                and facts['assertion_origin'] == 'SYNTHETIC_FIXTURE', 'Unknown proposed fixture schema')
        require(facts['verification_status'] in ('UNCERTAIN', 'VERIFIED'), 'Unknown verification status')
        require(bool(facts['issues']) == (facts['verification_status'] == 'UNCERTAIN'), 'Invalid uncertainty')
        refs = {e['evidence_id']: e for e in data['agent_outputs']['vlm']['evidence']}
        for issue in facts['issues']:
            exact(issue, {'issue_id', 'field', 'affected_input_pointer', 'issue_type', 'status',
                         'verified_value', 'sources', 'evidence_refs', 'rationale', 'fixture_rule_ref'})
            require(issue['status'] == 'UNRESOLVED' and issue['verified_value'] is None,
                    'Unresolved issue cannot contain a verified value')
            require(issue['issue_type'] in ('CONFLICTING_VALUES', 'INCOMPLETE_EXTRACTION'), 'Unknown issue type')
            require(issue['evidence_refs'] and set(issue['evidence_refs']) <= set(refs), 'Missing factual evidence')
            require(issue['sources'], 'Missing factual sources')
            normalized = []
            for source in issue['sources']:
                exact(source, {'kind', 'pointer', 'observed_value', 'normalized_value', 'evidence_ref'})
                value = data
                for part in source['pointer'].strip('/').split('/'):
                    value = value[int(part)] if isinstance(value, list) else value[part]
                if source['kind'] == 'VLM_EVIDENCE':
                    require(source['evidence_ref'] in refs and str(source['observed_value']) in str(value),
                            'Factual source does not resolve to observed evidence')
                else:
                    require(source['kind'] == 'PLAN_FIELD' and source['observed_value'] == value,
                            'Factual source does not match submitted form')
                normalized.append(source['normalized_value'])
            if issue['issue_type'] == 'CONFLICTING_VALUES':
                require(len({str(v) for v in normalized}) > 1, 'Conflict needs differing values')
    issues = facts['issues'] if facts else []
    issue_ids = {i['issue_id'] for i in issues}
    for evidence in data['agent_outputs']['vlm']['evidence']:
        require(set(evidence.get('factual_issue_refs', [])) <= issue_ids,
                'Factual evidence lost its issue mapping')
    exact(data['agent_outputs']['budget'], {'engine_version', 'amount_vnd', 'currency', 'limit_vnd',
          'limit_snapshot_id', 'result', 'difference_vnd', 'rule_ids'})
    require(data['unresolved_conflict_count'] == sum(i['issue_type'] == 'CONFLICTING_VALUES' for i in issues),
            'Unresolved conflicts would be lost in mapping')


def payload_from_input(data):
    validate_input(data)
    return {FIELD_MAP.get(k, k): amount(v) if k == 'budget_vnd' else deepcopy(v)
            for k, v in data['plan_snapshot'].items() if k not in ('attachments', 'plan_id', 'code')}


def configuration_from_input(data):
    validate_input(data)
    p = data['policy_snapshot']
    require(p['data_classification'] == 'SYNTHETIC', 'Not a demo policy')
    require((p['score_threshold'], p['score_operator'], p['media_confidence_threshold'],
             p['strategy_confidence_threshold']) == (70, '>', .85, .8), 'Fixture changes frozen gates')
    limit = p['limit_snapshot']
    checker = data['plan_snapshot']['checker_id']
    return ApprovalConfiguration(
        PolicySnapshot(p['policy_id'], p['version'], p['enabled'], MANDATORY_FIELDS,
                       tuple(Criterion(k, v) for k, v in p['criteria_weights'].items()),
                       (MODEL,), ('image/png', 'image/jpeg', 'image/webp'), 5_000_000),
        (BudgetConfiguration(limit['id'], 'VND', 0, amount(limit['amount_vnd']),
                             limit['scope_department_id'], True),),
        AuthoritySnapshot('DEMO-AUTHORITY-V2', 'VND', amount(limit['amount_vnd']),
                          (limit['scope_department_id'],), checker, 'DEMO-ADMIN-01', checker, True),
    )


class Role1MockProvider(VisualModelProvider):
    def __init__(self, data, attachment_bindings):
        validate_input(data)
        self.data = deepcopy(data)
        self.bindings = deepcopy(attachment_bindings)

    def health_check(self):
        return True

    def get_model_metadata(self):
        return {'provider': 'MOCK_VLM', 'model_version': MODEL}

    def analyze_image(self, request):
        data = self.data
        outputs = data['agent_outputs']
        for part in ('vlm', 'media', 'strategy'):
            require(outputs[part]['model_version'] == f'mock-{part}-fixture-v2', 'Unknown source model')
            if outputs[part]['status'] == 'TIMED_OUT':
                raise ProviderTimeout('Synthetic timeout')
            if outputs[part]['status'] != 'SUCCEEDED':
                raise ProviderError('Synthetic provider failure')
        require(data['agent_error_count'] == 0, 'Unmapped agent errors')
        evidence = []
        for e in outputs['vlm']['evidence']:
            exact(e, {'evidence_id', 'attachment_id', 'attachment_sha256', 'plan_version',
                      'source_type', 'bbox_normalized', 'observed_text', 'confidence', 'evidence_origin'}, {'fact_verification_status', 'factual_issue_refs', 'is_complete', 'extraction_mode'})
            attachment = self.bindings[e['attachment_id']]
            require(attachment['content_hash'] == e['attachment_sha256'], 'Source image hash mismatch')
            require(any(a.attachment_id == attachment['attachment_id'] and a.content_hash == attachment['content_hash']
                        for a in request.plan.attachments), 'Evidence outside submitted snapshot')
            evidence.append(dict(evidence_id=e['evidence_id'], source_type='ATTACHMENT',
                                 source_ref=attachment['attachment_id'], observation=json.dumps(e, ensure_ascii=False),
                                 content_hash=attachment['content_hash']))
        criteria = []
        for c in outputs['strategy']['criteria']:
            exact(c, {'id', 'score', 'weight', 'reason', 'evidence_refs'})
            for ref in c['evidence_refs']:
                field = FIELD_MAP.get(ref.removeprefix('plan.'), ref.removeprefix('plan.'))
                require(field in request.plan.payload, 'Unknown criterion source')
                if not any(e['evidence_id'] == ref for e in evidence):
                    evidence.append(dict(evidence_id=ref, source_type='PLAN_FIELD', source_ref=field,
                                         observation=str(request.plan.payload[field]), content_hash=None))
            criteria.append(dict(criterion_id=c['id'], score=float(Decimal(str(c['score'])) * Decimal(c['weight']) / 100),
                                 maximum_score=c['weight'], rationale=c['reason'], evidence_refs=c['evidence_refs']))
        media = outputs['media']
        findings = [dict(finding_id=f'hard-{i}', severity='HARD_VIOLATION', description=v,
                         rule_id=v, evidence_refs=media['evidence_refs']) for i, v in enumerate(media['hard_violations'])]
        findings += [dict(finding_id=f'warning-{i}', severity='WARNING', description=v,
                          rule_id=None, evidence_refs=media['evidence_refs']) for i, v in enumerate(media['warnings'])]
        if not data['policy_scope_covered']:
            evidence.append(dict(evidence_id='fixture-policy-scope', source_type='POLICY',
                                 source_ref=request.configuration.policy.snapshot_id,
                                 observation='Synthetic configured media policy scope is missing.', content_hash=None))
            findings.append(dict(finding_id='policy-scope', severity='WARNING', description='Policy scope missing',
                                 rule_id='POLICY_SCOPE_MISSING', evidence_refs=['fixture-policy-scope']))
        conflicts, missing = [], list(outputs['strategy']['critical_gaps'])
        for issue in data.get('fact_verification', {}).get('issues', []):
            description = json.dumps(issue, ensure_ascii=False)
            if issue['issue_type'] == 'CONFLICTING_VALUES':
                conflicts.append(dict(conflict_id=issue['issue_id'], description=description,
                                      evidence_refs=issue['evidence_refs']))
            else:
                missing.append(description)
        # Keep VLM confidence separate from media confidence, without inventing a gate.
        evidence.append(dict(evidence_id='fixture-provenance', source_type='PLAN_FIELD', source_ref='summary',
                             observation=json.dumps({k: {f: outputs[k][f] for f in ('model_version', 'agent_version', 'prompt_version', 'confidence')}
                                                     for k in ('vlm', 'media', 'strategy')}, ensure_ascii=False), content_hash=None))
        now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        raw = dict(evaluation_id=request.evaluation_id, plan_id=request.plan_id, plan_version=request.plan_version,
                   approval_round=request.approval_round, run_id=request.run_id, schema_version=1,
                   input_hash=request.input_hash, policy_version=request.policy_version, provider='MOCK_VLM',
                   model_version=MODEL, status='SUCCEEDED', media_result=media['result'], media_findings=findings,
                   media_confidence=media['confidence'], feasibility_score=outputs['strategy']['score'],
                   feasibility_confidence=outputs['strategy']['confidence'], missing_facts=missing,
                   evidence_conflicts=conflicts, evidence=evidence,
                   proposed_action='RECOMMEND_HUMAN_REVIEW', escalation_category='FACT_UNCERTAIN',
                   reason='Synthetic advisory evidence; only the deterministic engine decides.',
                   latency_ms=0, created_at=now, started_at=now, completed_at=now, agent_errors=[],
                   raw_output_hash=canonical_hash({'agent_outputs': outputs, 'fact_verification': data.get('fact_verification')}), reported_model_version=MODEL, correlation_id=request.correlation_id,
                   criterion_scores=criteria, assumptions=outputs['strategy']['assumptions'])
        return EvaluationResult.from_dict(raw).to_dict()
