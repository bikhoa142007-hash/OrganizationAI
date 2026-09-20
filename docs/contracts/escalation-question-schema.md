# Escalation question schema — WP1 / schema version 1

Uses [common types and taxonomy](decision-contract.md). Questions turn blocked auto-approval into a specific request to an authorized human. A question or answer never directly approves or rejects a plan.

## Fields

| field | type and invariant |
|---|---|
| escalation_id | nonblank unique ID |
| category | EscalationCategory; exact enum from decision contract |
| disputed_or_missing_fact | nonblank description of the fact, rule scope or authority issue |
| observed_value | JSON scalar/object/array or null when unavailable; no fabricated defaults |
| applicable_rule_or_limit | nonblank rule/limit description; explicitly state unavailable configuration |
| evidence_reference | EvidenceRef[]; may be empty only if no evidence exists, explained in reason |
| question | nonblank, actionable and specific to this case |
| answer_options | array of { option_id, label }; at least two distinct nonblank options including defer/request clarification |
| target_authority | { role: CHECKER or POLICY_OWNER or BUDGET_AUTHORITY, actor_id: string or null }; null actor means assignment unresolved and cannot authorize a decision |
| created_at | timestamp |
| schema_version | integer fixed 1 |
| plan_id | nonblank ID |
| plan_version | integer >= 1 |
| approval_round | integer >= 1 |
| evaluation_id | nonblank ID of normalized evaluation |
| decision_id | nonblank ID of linked HUMAN_REVIEW_REQUIRED routing record |
| input_hash | InputHash |
| policy_version | nonblank applied policy ID |
| applied_rule_ids | nonempty distinct string[] of triggered rule IDs |
| reason | nonblank rationale for routing and authority selection |

## Generation and handling

Generate at least one question for every triggered category, retaining all material issues and rule/evidence references. The engine decision's escalation_category identifies the primary category according to deterministic precedence; other questions preserve secondary categories. All question IDs are listed in EngineDecision.escalation_ids. Allocate routing/question IDs together and persist consistently before presenting them.

FACT_UNCERTAIN example: “The provider timed out and media compliance is unknown. Can you inspect the attached version, or request clarification?” Observed value is null, with provider-error evidence when available. Options may be “Record manual inspection” and “Defer/request clarification”; neither is automatic approval.

POLICY_OUT_OF_SCOPE example: “No active budget policy uniquely matches this plan. Which approved policy applies, or should review remain pending?” Never invent a limit.

AUTHORITY_EXCEEDED example: “The submitted budget exceeds the recorded delegated limit. Can an authorized budget reviewer assess it, or should review remain pending?” Include actual validated budget/currency/limit evidence, not model estimates.

Answer records use { answer_id, escalation_id, option_id, actor: Actor, reason, answered_at }. reason is nonblank; actor is authenticated HUMAN. Validate option membership and authority server-side, preserve the original question and append the answer/audit. A human's final approve/reject remains a separate HumanDecision with actor, reason/override_reason and timestamp. Answers cannot edit an immutable submitted snapshot; Maker changes require rejection and a new version/round.

POLICY_OWNER and BUDGET_AUTHORITY denote configured human remits, not a new dynamic role builder, delegation system or multi-level approval feature. The assigned Checker remains the single approval path and must possess the required authority to finalize. Missing assignment retains Human Review; a question must never grant its recipient permissions.

