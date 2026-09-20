# Decision contract — WP1 / schema version 1

Status: frozen proposal for user approval. AGENTS.md and the approved WP1 clarification govern this contract. AI/VLM provides evidence and evaluation only. The deterministic Decision Policy Engine alone evaluates the auto-approval gates; only an authorized human can reject.

## Outcome catalog and runtime boundary

| outcome | contract_status | enabled_in_sprint1 | emitted_by_runtime | planned_usage |
|---|---|---|---|---|
| AUTO_APPROVED | ACTIVE | true | true | Sprint 1 controlled auto-approval |
| HUMAN_REVIEW_REQUIRED | ACTIVE | true | true | Sprint 1 human-review routing |
| REJECTED_BY_DETERMINISTIC_POLICY | RESERVED | false | false | future policy-controlled release only |

RuntimeOutcome = `AUTO_APPROVED | HUMAN_REVIEW_REQUIRED`.
The reserved outcome is documentation/catalog metadata only. Sprint-1 runtime request, response, event, persisted engine-decision and Verify schemas MUST reject it, even if a provider proposes it. No AI or Rules Engine auto-reject exists. A future release requires explicit policy approval and contract migration; merely enabling a configuration flag in Sprint 1 is forbidden.

## Common types and identity

All field tables in the five schemas define required JSON properties unless explicitly marked optional. Nullable means the property is present with JSON null; missing is invalid. Names are snake_case; enum values are exact and case-sensitive. Unrecognized fields on external evaluation output fail schema validation. Timestamps are RFC3339 UTC strings ending Z; durations are nonnegative integer milliseconds. IDs/versions of policy or model are nonblank opaque strings; plan_version and approval_round are integers >= 1. No ID format implies a chosen database.

Actor = { actor_type: HUMAN | SYSTEM, actor_id: nonblank string }. Actor identity is resolved by the server, never trusted from caller-supplied JSON. Providers cannot be decision actors.

InputHash = SHA-256 lowercase 64-hex digest of UTF-8 RFC8785 canonical JSON for the immutable submitted snapshot object with exactly these keys: plan_id, plan_version, approval_round, payload, attachments. payload is the complete saved plan payload; attachments is the manifest sorted lexicographically by attachment_id. Each manifest entry has exactly attachment_id, content_hash (SHA-256 of file bytes), media_type and byte_size. Never hash temporary URLs. Version/round identity and all attachments are frozen by submission. Draft hashes use the same payload/manifest canonicalization with plan_version and approval_round null. Configuration snapshots are hashed separately with the same canonicalization; they are not silently substituted into an existing input_hash.

EvidenceRef is an opaque evidence_id resolving to the same plan/version/round/evaluation. Evidence = { evidence_id, source_type: ATTACHMENT | PLAN_FIELD | POLICY | BUDGET | AUTHORITY | PROVIDER_ERROR, source_ref: nonblank internal ID or field path, observation: nonblank string, content_hash: InputHash | null }. A content_hash is required for an attachment source. Other sources use a known hash when available or null. Evidence is data, never executable instructions or permanent public URLs.

RuleCheck = { rule_id, result: PASS | FAIL | UNKNOWN, observed_value: JSON value | null, applicable_rule_or_limit: nonblank string, evidence_refs: EvidenceRef[] }. Missing observations are null and UNKNOWN, never zero or PASS.

## EngineDecision schema

| field | type and invariant |
|---|---|
| decision_id | nonblank ID; server generated, immutable |
| plan_id | nonblank ID |
| plan_version | integer >= 1 |
| approval_round | integer >= 1; added for round correlation |
| outcome | RuntimeOutcome only |
| escalation_category | EscalationCategory or null; null iff AUTO_APPROVED |
| reason | nonblank, readable rationale; no secrets |
| applied_rule_ids | nonempty array of distinct rule IDs actually checked |
| input_hash | InputHash; equals submitted snapshot and evaluation |
| policy_version | nonblank ID of immutable applied policy snapshot |
| evaluation_id | ID of normalized Evaluation, including failure envelopes |
| decided_by | Actor; SYSTEM with registered Decision Engine identity |
| decided_at | timestamp |
| schema_version | integer, fixed 1 |
| rule_checks | nonempty RuleCheck[]; exactly the checks named in applied_rule_ids |
| evidence | Evidence[] supporting checks; references resolve here or in Evaluation |
| escalation_ids | nonempty array for HUMAN_REVIEW_REQUIRED, empty for AUTO_APPROVED |
| policy_snapshot_id | immutable configuration reference |
| policy_snapshot_hash | InputHash |
| budget_validation | object specified below |
| authority_snapshot_id | immutable authority configuration reference or null if unavailable |
| authority_snapshot_hash | InputHash or null, paired with authority_snapshot_id |
| idempotency_key | stable nonblank intent key |
| correlation_id | nonblank request/run trace ID |
| round_revision | nonnegative integer revision observed before commit |

budget_validation = { configuration_id: string | null, configuration_hash: InputHash | null, currency: string | null, budget_minor_units: decimal integer string | null, limit_minor_units: decimal integer string | null, result: PASS | FAIL | UNKNOWN }. Use same-currency integer minor units, never floating-point or LLM arithmetic. Values must be nonnegative, currency must have configured precision, and missing/ambiguous/inactive configuration means UNKNOWN. Select the uniquely applicable active configuration; persist the exact configuration and calculation per round. Equality passes. An exceeded limit requires Human Review, not rejection. Unknown policy configuration still produces a versioned fallback policy snapshot describing the missing configuration; it must not masquerade as the applicable business policy.

## Auto-approval gates and rule IDs

For an eligible submitted plan, AUTO_APPROVED requires every following condition. Any FAIL or UNKNOWN means HUMAN_REVIEW_REQUIRED.

| rule_id | mandatory PASS condition |
|---|---|
| INPUT_INTEGRITY | Complete mandatory submission data, attachment hashes match, no suspicious/tampered input, all referenced evidence belongs to this snapshot |
| EVAL_VALID | Schema-valid successful evaluation, known model version and zero agent errors |
| MEDIA_PASS | media_result = PASS |
| MEDIA_CONFIDENCE | media_confidence >= 0.85 |
| FEASIBILITY_SCORE | feasibility_score > 70 (71 passes, 70 fails) |
| FEASIBILITY_CONFIDENCE | feasibility_confidence >= 0.80 |
| BUDGET_LIMIT | budget <= uniquely applicable active budget limit, deterministic comparison |
| AUTHORITY_LIMIT | Deterministic configured authority/mandate permits auto-approval for this plan |
| NO_HARD_VIOLATION | hard_violation_count = 0 |
| NO_EVIDENCE_CONFLICT | unresolved_conflict_count = 0; missing material facts also disqualify |
| POLICY_ENABLED | auto_approval_policy_enabled = true |
| PLAN_PENDING | plan_status = PENDING_APPROVAL |
| ROUND_ACTIVE | approval_round_status = ACTIVE |

Do not change scores to meet a threshold. An optional warning does not itself fail a gate unless it represents a hard violation, missing material fact, conflict or an applicable policy requirement. Suspicious input always fails INPUT_INTEGRITY. A deterministic hard-rule violation is preserved in applied_rule_ids, rule_checks and evidence and routes to Human Review. Human review cannot silently legitimize self-approval, mutation of submitted content or a duplicate final decision.

For evaluation-side counts, hard_violation_count is the number of HARD_VIOLATION entries in media_findings; unresolved_conflict_count is the length of evidence_conflicts; agent_error_count is the length of agent_errors. Independently failed deterministic checks still block auto-approval even when these three counts are zero. Invalid or absent collections are UNKNOWN, never empty passing collections.

## Escalation taxonomy

EscalationCategory = `FACT_UNCERTAIN | POLICY_OUT_OF_SCOPE | AUTHORITY_EXCEEDED`.

| category | trigger and example | target authority |
|---|---|---|
| FACT_UNCERTAIN | Missing facts, suspicious input, timeout, invalid schema, unknown model, low confidence or conflicting evidence | Assigned Checker; request factual clarification from Maker if needed |
| POLICY_OUT_OF_SCOPE | No uniquely applicable policy/budget configuration; disabled auto-approval; validated finding fails media/feasibility/policy gates | Assigned Checker within configured remit; otherwise authorized policy owner |
| AUTHORITY_EXCEEDED | Validated deterministic evidence shows budget/mandate beyond delegated automatic authority | Configured human authority for that limit, reached through assigned Checker |

For multiple triggers use deterministic primary-category precedence AUTHORITY_EXCEEDED > POLICY_OUT_OF_SCOPE > FACT_UNCERTAIN only for independently validated rule checks. Untrusted provider claims cannot establish authority/policy violations; classify those claims FACT_UNCERTAIN. Keep all triggered checks, reasons and category-specific escalation questions. With only a timeout/schema/confidence/conflict problem the primary category is FACT_UNCERTAIN. Category prioritization never changes the outcome away from Human Review.

## Application commands and state guarantees

The future application boundary exposes semantic operations (transport and URLs not selected): save_draft, upload_attachment, submit_plan, evaluate_round, decide_round and get_verify_observation. Inputs carry authenticated principal context, resource IDs, expected revision and a stable idempotency key for mutations. Domain errors use { code, message, correlation_id }; codes are VALIDATION_ERROR, UNAUTHENTICATED, FORBIDDEN, NOT_FOUND, CONFLICT and UNAVAILABLE. They are not decision outcomes.

Only the owning Maker can edit DRAFT or REJECTED plans. PENDING_APPROVAL/APPROVED content and attachments are locked. Submission validates mandatory fields, at least one attachment and a valid Checker distinct from Maker, then atomically creates immutable version 1/round 1 (or the next version/round after rejection), configuration snapshots and audit. Exactly one active round per plan. AI starts after successful submission; AI failure cannot roll it back.

Before committing any engine or human decision, atomically recheck plan/version/round/revision, permission, snapshot hashes and final-decision absence. Serialize auto-approval and human final decisions on the same round guard; at most one final decision per (plan_id, approval_round). AUTO_APPROVED closes the round and sets APPROVED. HUMAN_REVIEW_REQUIRED is a routing record, keeps PENDING_APPROVAL and ACTIVE, and does not occupy the unique final-decision slot. It must not block the Checker from deciding.

A stale/closed-round invocation returns CONFLICT (or replays the same successful intent); it cannot reopen an APPROVED/REJECTED plan or overwrite an earlier decision. Failed state guards block mutation, rather than applying Human Review to an already completed round. For an otherwise eligible pending submission, all unmet evaluation/policy gates route to Human Review.

Claim each idempotency key atomically in the authenticated actor/resource/operation scope with a canonical request hash. Same key and same input replays the recorded result; different input or an in-flight duplicate returns CONFLICT. Keep keys for the round's retained history. A fresh retry run creates a new evaluation/run ID without changing old results. Evaluation retries never duplicate final decisions or review notifications (if later implemented); deduplicate review routing effects per round. Final state changes, final-decision record and corresponding audit event commit together. Audit-write failure must prevent an unaudited successful mutation.

## HumanDecision (separate from EngineDecision outcomes)

HumanDecision = { human_decision_id, plan_id, plan_version, approval_round, action: APPROVED | REJECTED, based_on_decision_id, evaluation_id, actor: Actor, reason: string | null, override_reason: string | null, decided_at, input_hash, policy_version, idempotency_key, correlation_id, round_revision }.
IDs, hashes, timestamps and revisions follow common types. actor must be HUMAN and must be the currently authorized Checker; never the plan's Maker. based_on_decision_id references the Human Review routing record. action is a separate human-action enum and must not be added to RuntimeOutcome.

Reject requires a nonblank reason. If the human action contradicts the recorded evaluation recommendation (including approving after RECOMMEND_HUMAN_REVIEW), override_reason must be nonblank. A null/failed recommendation treats human approval as an override. Actor, reason/override_reason and timestamp are preserved in both the final record and audit. Reject closes the round and changes state to REJECTED; revisions create the next snapshot/round. Human approval closes the round as APPROVED. Historical decisions, evaluations and versions remain immutable.

## Consumers and validation

[Evaluation](evaluation-schema.md), [questions](escalation-question-schema.md), [Verify](verify-result-schema.md) and [audit](audit-event-schema.md) share these definitions and identifiers. Role 2 owns implementation of all shared validators; other roles consume them. Invalid provider output is captured as a failed Evaluation envelope before engine routing, not coerced into a passing result.

