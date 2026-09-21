"""Trusted, transport-independent WP3 application boundary.

The host authenticates callers and supplies a server-owned principal ID and role
directory. Never bind these parameters to untrusted HTTP actor/role fields.
Submission commits before evaluation. A server-owned ticket reserves one run;
the pipeline later supplies structured output to evaluate_round (no model I/O).
"""
from dataclasses import replace
from datetime import date, datetime, timezone
from hashlib import sha256
import sqlite3
from uuid import uuid4

from src.backend.domain.models import (
    Actor, AttachmentManifest, AuditEvent, DecisionResult, EvaluationResult,
    HumanDecision, MarketingPlan, State,
)
from src.backend.domain.policy import ApprovalConfiguration
from src.backend.rules.decision import DecisionContext, decide
from src.shared.validation import (
    MinorUnits, ValidationError, canonical_hash, decode, json_value,
)


class ApplicationError(Exception):
    def __init__(self, code, message, correlation_id):
        super().__init__(message)
        self.code, self.message, self.correlation_id = code, message, correlation_id

    def to_dict(self):
        return dict(code=self.code, message=self.message, correlation_id=self.correlation_id)


def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def identifier(prefix):
    return prefix + '-' + uuid4().hex


class ApprovalWorkflow:
    def __init__(self, repository, configuration, principals, *, evaluator_id, provider='MOCK_VLM'):
        self.repository = repository
        self.configuration = configuration
        self.principals = {name: frozenset(roles) for name, roles in principals.items()}
        self.evaluator_id = evaluator_id
        if provider not in ('MOCK_VLM', 'LOCAL_VLM'):
            raise ValueError('Unsupported provider identity')
        self.provider = provider

    @staticmethod
    def _check(condition, code, message, trace):
        if not condition:
            raise ApplicationError(code, message, trace)

    def _authorize(self, actor, role, trace):
        self._check(actor in self.principals, 'UNAUTHENTICATED', 'Authenticated principal required.', trace)
        self._check(role in self.principals[actor], 'FORBIDDEN', 'Role is not authorized.', trace)
        if role == 'EVALUATOR':
            self._check(actor == self.evaluator_id, 'FORBIDDEN', 'Unregistered pipeline.', trace)

    def _plan(self, actor, plan_id, trace, *, edit=False):
        plan = self.repository.plan(plan_id)
        self._check(plan is not None, 'NOT_FOUND', 'Plan not found.', trace)
        if edit:
            self._check(plan['maker_id'] == actor, 'FORBIDDEN', 'Only the owning Maker may edit.', trace)
            self._check(plan['state']['plan_status'] in ('DRAFT', 'REJECTED'),
                        'CONFLICT', 'Submitted content is locked.', trace)
        return plan

    def _command(self, actor, role, plan_id, operation, request, key, trace, action):
        try:
            for value in (actor, plan_id, operation, key, trace):
                decode(str, value)
            self._authorize(actor, role, trace)
            scope = canonical_hash([actor, plan_id, operation, key])
            digest = canonical_hash(request)
            with self.repository.transaction():
                replay = self.repository.replay(scope)
                if replay:
                    self._check(replay[0] == digest, 'CONFLICT', 'Idempotency key reused with different input.', trace)
                    return replay[1]
                result = json_value(action())
                self.repository.remember(scope, digest, result)
                return result
        except ValidationError as exc:
            raise ApplicationError('VALIDATION_ERROR', str(exc), trace) from exc
        except sqlite3.Error as exc:
            code = 'CONFLICT' if isinstance(exc, sqlite3.IntegrityError) and 'UNIQUE constraint' in str(exc) else 'UNAVAILABLE'
            raise ApplicationError(code, 'Atomic operation could not be committed.', trace) from exc

    def _revision(self, actual, expected, trace):
        self._check(type(expected) is int and expected >= 0, 'VALIDATION_ERROR', 'Invalid expected revision.', trace)
        self._check(actual == expected, 'CONFLICT', 'Stale revision.', trace)

    @staticmethod
    def _draft_snapshot(plan):
        return MarketingPlan(plan['plan_id'], None, None, plan['payload'],
                             tuple(AttachmentManifest.from_dict(a) for a in plan['attachments']))

    def _audit(self, plan, action, actor, key, trace, previous, *, snapshot=None,
               config=None, decision=None, human=None, evaluation=None):
        policy = config.policy if config else None
        authority = config.authority if config else None
        budget = decision.budget_validation if decision else None
        event = AuditEvent(
            event_id=identifier('audit'), actor_type='HUMAN', actor_id=actor, action=action,
            entity_id=plan['plan_id'], entity_version=plan['revision'],
            input_hash=(snapshot or self._draft_snapshot(plan)).input_hash,
            policy_version=policy.policy_version if policy else None,
            model_version=evaluation.model_version if evaluation else None,
            reason=(human.reason or human.override_reason or 'Checker approved submission.') if human else action,
            previous_state=State.from_dict(previous) if previous else None,
            new_state=State.from_dict(plan['state']),
            timestamp=human.decided_at if human else now(), schema_version=1,
            plan_id=plan['plan_id'], plan_version=snapshot.plan_version if snapshot else None,
            approval_round=snapshot.approval_round if snapshot else None,
            run_id=evaluation.run_id if evaluation else None,
            evaluation_id=decision.evaluation_id if decision else None,
            decision_id=decision.decision_id if decision else None,
            human_decision_id=human.human_decision_id if human else None,
            correlation_id=trace, idempotency_key=key,
            applied_rule_ids=decision.applied_rule_ids if decision else (), evidence_reference=(),
            policy_snapshot_id=policy.snapshot_id if policy else None,
            policy_snapshot_hash=canonical_hash(policy) if policy else None,
            budget_snapshot_id=budget.configuration_id if budget else None,
            budget_snapshot_hash=budget.configuration_hash if budget else None,
            authority_snapshot_id=authority.snapshot_id if authority else None,
            authority_snapshot_hash=canonical_hash(authority) if authority else None,
            outcome=None, human_action=human.action if human else None,
            override_reason=human.override_reason if human else None,
        )
        self.repository.audit(event)

    def save_draft(self, actor, plan_id, payload, *, expected_revision, idempotency_key, correlation_id):
        def action():
            plan = self.repository.plan(plan_id)
            previous = None
            if plan:
                plan = self._plan(actor, plan_id, correlation_id, edit=True)
                previous = plan['state'].copy()
            else:
                plan = dict(plan_id=plan_id, maker_id=actor, payload={}, attachments=[],
                            revision=0, current_round=0,
                            state=State('DRAFT', None, None).to_dict())
            self._revision(plan['revision'], expected_revision, correlation_id)
            self._check(isinstance(payload, dict), 'VALIDATION_ERROR', 'Payload must be an object.', correlation_id)
            self._check(payload.get('maker_id', actor) == actor, 'FORBIDDEN', 'Maker identity cannot be changed.', correlation_id)
            plan['payload'] = {**payload, 'maker_id': actor}
            self._draft_snapshot(plan)
            plan['revision'] += 1
            self.repository.save_plan(plan)
            self._audit(plan, 'DRAFT_SAVED', actor, idempotency_key, correlation_id, previous)
            return plan
        return self._command(actor, 'MAKER', plan_id, 'save_draft',
                             [payload, expected_revision], idempotency_key, correlation_id, action)

    def upload_attachment(self, actor, plan_id, content, media_type, *, expected_revision,
                          idempotency_key, correlation_id):
        self._check(type(content) is bytes, 'VALIDATION_ERROR', 'Attachment bytes required.', correlation_id)
        digest = sha256(content).hexdigest()
        def action():
            plan = self._plan(actor, plan_id, correlation_id, edit=True)
            self._revision(plan['revision'], expected_revision, correlation_id)
            policy = self.configuration.policy
            signatures = {'image/png': content.startswith(b'\x89PNG\r\n\x1a\n'),
                          'image/jpeg': content.startswith(b'\xff\xd8\xff'),
                          'image/webp': content[:4] == b'RIFF' and content[8:12] == b'WEBP'}
            self._check(media_type in policy.allowed_media_types and signatures.get(media_type, False)
                        and 0 < len(content) <= policy.max_attachment_bytes,
                        'VALIDATION_ERROR', 'Unsupported media, signature or file size.', correlation_id)
            manifest = AttachmentManifest(identifier('attachment'), digest, media_type, len(content))
            self.repository.add_attachment(manifest.attachment_id, plan_id, media_type, content)
            plan['attachments'].append(manifest.to_dict())
            plan['revision'] += 1
            self.repository.save_plan(plan)
            self._audit(plan, 'ATTACHMENT_UPLOADED', actor, idempotency_key, correlation_id, plan['state'])
            return plan
        return self._command(actor, 'MAKER', plan_id, 'upload_attachment',
                             [digest, media_type, expected_revision], idempotency_key, correlation_id, action)

    def _verified_attachments(self, snapshot, trace):
        hashes = []
        for manifest in snapshot.attachments:
            stored = self.repository.attachment(manifest.attachment_id)
            self._check(stored is not None and stored['plan_id'] == snapshot.plan_id
                        and stored['media_type'] == manifest.media_type
                        and len(stored['content']) == manifest.byte_size
                        and sha256(stored['content']).hexdigest() == manifest.content_hash,
                        'CONFLICT', 'Attachment integrity mismatch.', trace)
            hashes.append((manifest.attachment_id, manifest.content_hash))
        return tuple(hashes)

    def _validate_submission(self, snapshot, trace):
        payload, policy = snapshot.payload, self.configuration.policy
        self._check(all(isinstance(payload.get(k), str) and payload[k].strip()
                        for k in policy.mandatory_fields),
                    'VALIDATION_ERROR', 'Required submission fields are missing.', trace)
        checker = payload.get('checker_id')
        self._check(checker != payload.get('maker_id') and 'CHECKER' in self.principals.get(checker, ()),
                    'VALIDATION_ERROR', 'A valid Checker distinct from Maker is required.', trace)
        decode(MinorUnits, payload.get('budget_minor_units'))
        try:
            valid_dates = date.fromisoformat(payload['start_date']) <= date.fromisoformat(payload['end_date'])
        except (ValueError, TypeError):
            valid_dates = False
        self._check(valid_dates, 'VALIDATION_ERROR', 'Invalid campaign dates.', trace)
        self._check(bool(snapshot.attachments) and all(
            a.media_type in policy.allowed_media_types and 0 < a.byte_size <= policy.max_attachment_bytes
            for a in snapshot.attachments), 'VALIDATION_ERROR', 'Valid attachment required.', trace)
        self._verified_attachments(snapshot, trace)

    def submit_plan(self, actor, plan_id, *, expected_revision, expected_policy_version,
                    idempotency_key, correlation_id):
        def action():
            plan = self._plan(actor, plan_id, correlation_id, edit=True)
            self._revision(plan['revision'], expected_revision, correlation_id)
            self._check(expected_policy_version == self.configuration.policy.policy_version,
                        'CONFLICT', 'Stale policy version.', correlation_id)
            number = plan['current_round'] + 1
            snapshot = replace(self._draft_snapshot(plan), plan_version=number, approval_round=number)
            self._validate_submission(snapshot, correlation_id)
            previous = plan['state'].copy()
            plan.update(current_round=number, revision=plan['revision'] + 1,
                        state=State('PENDING_APPROVAL', 'AI_PENDING', 'ACTIVE').to_dict())
            self.repository.save_plan(plan)
            self.repository.append('version', f'{plan_id}:{number}', plan_id, number, snapshot)
            ticket = dict(evaluation_id=identifier('evaluation'), run_id=identifier('run'),
                          correlation_id=correlation_id, created_at=now(), provider=self.provider)
            self.repository.create_round(plan_id, number, self.configuration, ticket)
            self._audit(plan, 'PLAN_SUBMITTED' if number == 1 else 'PLAN_RESUBMITTED', actor,
                        idempotency_key, correlation_id, previous, snapshot=snapshot,
                        config=self.configuration)
            return dict(snapshot=snapshot.to_dict(), input_hash=snapshot.input_hash,
                        round=self.repository.round(plan_id, number), evaluation_ticket=ticket)
        return self._command(actor, 'MAKER', plan_id, 'submit_plan',
                             [expected_revision, expected_policy_version], idempotency_key, correlation_id, action)

    def _active(self, plan_id, number, revision, trace):
        plan = self.repository.plan(plan_id)
        self._check(plan is not None, 'NOT_FOUND', 'Plan not found.', trace)
        self._check(type(number) is int and number > 0, 'VALIDATION_ERROR', 'Invalid round.', trace)
        row = self.repository.round(plan_id, number)
        self._check(row is not None, 'NOT_FOUND', 'Round not found.', trace)
        self._check(plan['current_round'] == number and plan['state']['plan_status'] == 'PENDING_APPROVAL'
                    and row['status'] == 'ACTIVE' and row['final_id'] is None,
                    'CONFLICT', 'Round is no longer active.', trace)
        self._revision(row['revision'], revision, trace)
        body, digest = self.repository.version(plan_id, number)
        snapshot = MarketingPlan.from_dict(body)
        self._check(snapshot.input_hash == digest and canonical_hash(row['configuration']) == row['configuration_hash'],
                    'CONFLICT', 'Stored snapshot integrity mismatch.', trace)
        self._verified_attachments(snapshot, trace)
        return plan, row, snapshot, ApprovalConfiguration.from_dict(row['configuration'])

    def evaluate_round(self, actor, plan_id, number, raw_evaluation, *, expected_revision,
                       expected_policy_version, idempotency_key, correlation_id, suspicious_input=False):
        def action():
            decode(bool, suspicious_input)
            plan, row, snapshot, config = self._active(plan_id, number, expected_revision, correlation_id)
            self._check(expected_policy_version == config.policy.policy_version,
                        'CONFLICT', 'Stale policy version.', correlation_id)
            self._check(row['decision_id'] is None, 'CONFLICT', 'Evaluation already committed.', correlation_id)
            ticket = row['ticket']
            ctx = DecisionContext(
                ticket['evaluation_id'], ticket['run_id'], ticket['provider'], ticket['correlation_id'],
                idempotency_key, now(), 'PENDING_APPROVAL', 'ACTIVE', row['revision'],
                snapshot.input_hash, self._verified_attachments(snapshot, correlation_id),
                tuple(name for name, roles in self.principals.items() if 'CHECKER' in roles), suspicious_input)
            bundle = decide(snapshot, config, raw_evaluation, ctx)
            decision = bundle.decision
            for kind, record_id, record in (
                ('evaluation', bundle.evaluation.evaluation_id, bundle.evaluation),
                ('engine_decision', decision.decision_id, decision),
                *(('escalation', q.escalation_id, q) for q in bundle.escalations),
            ):
                self.repository.append(kind, record_id, plan_id, number, record)
            auto = decision.outcome == 'AUTO_APPROVED'
            if auto:
                self.repository.finalize(plan_id, number, 'engine_decision', decision.decision_id)
            previous = State.from_dict(plan['state'])
            processing = State('PENDING_APPROVAL', 'AI_PROCESSING', 'ACTIVE')
            # These events describe acceptance/validation of pipeline evidence at
            # this boundary, not an invented provider execution or model call.
            started = replace(
                bundle.audit, event_id=identifier('audit'), action='EVALUATION_STARTED',
                actor_id=self.evaluator_id, entity_version=plan['revision'],
                previous_state=previous, new_state=processing, model_version=None,
                decision_id=None, outcome=None, applied_rule_ids=(), evidence_reference=(),
                reason='Structured pipeline output received for evaluation.',
            )
            self.repository.audit(started)
            self.repository.audit(replace(
                started, event_id=identifier('audit'),
                action='EVALUATION_COMPLETED' if bundle.evaluation.status == 'SUCCEEDED' else 'EVALUATION_FAILED',
                previous_state=processing, new_state=processing,
                model_version=bundle.evaluation.model_version,
                reason='Evaluation validated.' if bundle.evaluation.status == 'SUCCEEDED'
                else 'Evaluation failed; deterministic Human Review routing follows.',
            ))
            plan['state'] = bundle.audit.new_state.to_dict()
            plan['revision'] += 1
            self.repository.save_plan(plan)
            self.repository.update_round(plan_id, number, status='CLOSED' if auto else 'ACTIVE',
                                         decision_id=decision.decision_id,
                                         final_id=decision.decision_id if auto else None)
            self.repository.audit(replace(bundle.audit, previous_state=processing,
                                          entity_version=plan['revision']))
            return dict(evaluation=bundle.evaluation, decision=decision, questions=bundle.escalations)
        return self._command(actor, 'EVALUATOR', plan_id, f'evaluate_round:{number}',
                             [raw_evaluation, expected_revision, expected_policy_version, suspicious_input],
                             idempotency_key, correlation_id, action)

    def decide_round(self, actor, plan_id, number, action, *, reason, override_reason,
                     expected_revision, idempotency_key, correlation_id):
        def execute():
            plan, row, snapshot, config = self._active(plan_id, number, expected_revision, correlation_id)
            self._check(actor != plan['maker_id'] and actor == snapshot.payload['checker_id'],
                        'FORBIDDEN', 'Only the assigned Checker may decide.', correlation_id)
            self._check(row['decision_id'] is not None, 'CONFLICT', 'Human Review routing required.', correlation_id)
            routed = DecisionResult.from_dict(self.repository.record('engine_decision', row['decision_id']))
            evaluation = EvaluationResult.from_dict(self.repository.record('evaluation', routed.evaluation_id))
            self._check(routed.outcome == 'HUMAN_REVIEW_REQUIRED', 'CONFLICT', 'Human Review routing required.', correlation_id)
            human = HumanDecision(identifier('human'), plan_id, snapshot.plan_version, number,
                                  action, routed.decision_id, evaluation.evaluation_id,
                                  Actor('HUMAN', actor), reason, override_reason, now(), snapshot.input_hash,
                                  config.policy.policy_version, idempotency_key, correlation_id, row['revision'])
            human.validate_authorization(plan['maker_id'], snapshot.payload['checker_id'], evaluation.proposed_action)
            self.repository.append('human_decision', human.human_decision_id, plan_id, number, human)
            self.repository.finalize(plan_id, number, 'human_decision', human.human_decision_id)
            previous = plan['state'].copy()
            plan['state'] = State(action, None, 'CLOSED').to_dict()
            plan['revision'] += 1
            self.repository.save_plan(plan)
            self.repository.update_round(plan_id, number, status='CLOSED', decision_id=routed.decision_id,
                                         final_id=human.human_decision_id)
            self._audit(plan, 'HUMAN_' + action, actor, idempotency_key, correlation_id, previous,
                        snapshot=snapshot, config=config, decision=routed, human=human, evaluation=evaluation)
            return human
        return self._command(actor, 'CHECKER', plan_id, f'decide_round:{number}',
                             [action, reason, override_reason, expected_revision], idempotency_key, correlation_id, execute)

    def get_plan(self, actor, plan_id, *, correlation_id='read-plan'):
        self._check(actor in self.principals, 'UNAUTHENTICATED', 'Authenticated principal required.', correlation_id)
        with self.repository.transaction():
            plan = self._plan(actor, plan_id, correlation_id)
            self._check(actor == plan['maker_id'] or
                        (actor == plan['payload'].get('checker_id') and 'CHECKER' in self.principals[actor]) or
                        (actor == self.evaluator_id and 'EVALUATOR' in self.principals[actor]),
                        'FORBIDDEN', 'Plan access denied.', correlation_id)
            return self.repository.history(plan_id)

    def get_verify_observation(self, actor, plan_id, number):
        history = self.get_plan(actor, plan_id)
        return dict(application_reference='ApprovalWorkflow.get_verify_observation',
                    plan=history['plan'],
                    records=[r for r in history['records'] if r['body']['approval_round'] == number],
                    versions=[v for v in history['versions'] if v['approval_round'] == number],
                    audit=[e for e in history['audit'] if e['approval_round'] == number])
