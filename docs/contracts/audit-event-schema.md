# Audit event schema — WP1 / schema version 1

Uses [common types](decision-contract.md). Events are append-only and record significant business, evaluation and decision actions. Audit records are not an alternative decision engine.

## Fields

| field | type and invariant |
|---|---|
| event_id | nonblank unique ID |
| actor_type | HUMAN or SYSTEM |
| actor_id | nonblank authenticated user/service identity |
| action | enum listed below |
| entity_id | nonblank affected plan/entity ID |
| entity_version | nonnegative integer domain revision; distinct from submitted plan_version |
| input_hash | InputHash of corresponding draft/submitted snapshot; null only when no trustworthy input exists (e.g. pre-lookup access denial) |
| policy_version | nonblank policy ID or null before selection |
| model_version | nonblank validated model ID or null for non-model/failed unknown-model actions |
| reason | nonblank sanitized explanation |
| previous_state | state object or null for creation/non-state actions |
| new_state | state object or null for non-state actions |
| timestamp | server timestamp |
| schema_version | integer fixed 1 |
| plan_id | nonblank ID or null only when unknown |
| plan_version | integer >= 1 or null before first submission |
| approval_round | integer >= 1 or null before first submission |
| run_id | string or null for non-evaluation actions |
| evaluation_id | string or null before evaluation |
| decision_id | string or null before engine routing/decision |
| human_decision_id | string or null except Checker final decision |
| correlation_id | nonblank trace ID |
| idempotency_key | nonblank stable key for mutating actions; null for non-mutating observations |
| applied_rule_ids | distinct string[]; empty when no rule checked |
| evidence_reference | EvidenceRef[]; internal IDs only |
| policy_snapshot_id | string or null before selection |
| policy_snapshot_hash | InputHash or null, paired with policy_snapshot_id |
| budget_snapshot_id | string or null when no applicable configuration |
| budget_snapshot_hash | InputHash or null, paired with budget_snapshot_id |
| authority_snapshot_id | string or null when unavailable |
| authority_snapshot_hash | InputHash or null, paired with authority_snapshot_id |
| outcome | RuntimeOutcome or null for non-engine actions |
| human_action | APPROVED, REJECTED or null; separate from outcome |
| override_reason | nonblank string when override occurred, otherwise null |

State object = { plan_status: DRAFT | PENDING_APPROVAL | APPROVED | REJECTED, processing_stage: AI_PENDING | AI_PROCESSING | HUMAN_REVIEW_REQUIRED | AI_AUTO_APPROVED | AI_PROCESSING_FAILED | null, approval_round_status: ACTIVE | CLOSED | null }. A transient AI_PROCESSING_FAILED observation must still lead to Human Review; it is never rejection.

Action enum: DRAFT_SAVED, ATTACHMENT_UPLOADED, PLAN_SUBMITTED, EVALUATION_STARTED, EVALUATION_COMPLETED, EVALUATION_FAILED, ENGINE_ROUTED, AUTO_APPROVED, HUMAN_APPROVED, HUMAN_REJECTED, ESCALATION_ANSWERED, PLAN_RESUBMITTED, ACCESS_DENIED, RETRY_REQUESTED. No automatic-rejection action exists in Sprint 1.

## Integrity and privacy

Engine events require plan_id, plan_version, approval_round, input_hash, policy_version, policy snapshot ID/hash, evaluation_id, decision_id, outcome, rule IDs and matching actor. AUTO_APPROVED additionally requires the applied budget/authority snapshots; missing configuration can only appear on Human Review with an explanatory rule check. The reserved outcome is forbidden in the outcome field and any state transition.

Human events require human_decision_id, human_action, authenticated HUMAN actor, round/version and input/configuration trace. They reference the preceding routing decision; a rejected plan is attributable to HUMAN_REJECTED, never an engine outcome. Rejection and override reason constraints are the same as HumanDecision. Answers record their answer_id/escalation_id as entity_id/evidence correlation via the application record, without embedding the answer's sensitive contents.

Submission and final decisions commit their state, immutable records and audit atomically. Audit persistence failure cannot produce an unaudited success. Retry may append a distinct attempt event, but cannot duplicate a final decision event or notification intent; use stable event identity for the same committed effect. Events must retain referential links to immutable versions, evaluations and configuration snapshots across resubmission.

Audit access is authorized server-side. Never store secrets, raw credentials, full provider prompts/output, raw media, unnecessary personal data or permanent public attachment URLs. Store hashes and protected internal evidence references. Unknown model identity remains null with a reason and linked failure evaluation; do not invent a known model version. No stack-specific logging sink, retention engine or migration is introduced by WP1.

