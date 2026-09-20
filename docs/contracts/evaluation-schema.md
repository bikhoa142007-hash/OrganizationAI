# Evaluation schema — WP1 / schema version 1

Normative types: [decision contract](decision-contract.md). This is a normalized application-owned evaluation envelope. It cannot finalize approval/rejection. Raw provider output is untrusted; schema validation precedes all use.

## Fields

| field | type and invariant |
|---|---|
| evaluation_id | nonblank ID, unique per evaluation attempt |
| plan_id | nonblank ID |
| plan_version | integer >= 1 |
| approval_round | integer >= 1 |
| run_id | nonblank orchestrator run ID |
| schema_version | integer fixed 1 |
| input_hash | InputHash, matches immutable submitted snapshot |
| policy_version | nonblank ID, same applied snapshot as engine decision |
| provider | LOCAL_VLM or MOCK_VLM; selected by approved local configuration |
| model_version | nonblank known model ID on success; null only in failure envelope if unavailable/untrusted |
| status | SUCCEEDED, FAILED or TIMED_OUT |
| media_result | PASS or REVIEW_REQUIRED on success; null on failure |
| media_findings | array of { finding_id, severity: HARD_VIOLATION or WARNING, description, rule_id: string or null, evidence_refs: EvidenceRef[] }; IDs/descriptions nonblank |
| media_confidence | number in [0,1] on success; null on failure |
| feasibility_score | number in [0,100] on success; null on failure |
| feasibility_confidence | number in [0,1] on success; null on failure |
| missing_facts | string[] of nonblank facts; empty if none |
| evidence_conflicts | array of { conflict_id, description, evidence_refs: EvidenceRef[] }; unresolved conflicts only |
| evidence | Evidence[]; internal references, no permanent public URLs |
| proposed_action | RECOMMEND_AUTO_APPROVAL or RECOMMEND_HUMAN_REVIEW on success; null on failure |
| escalation_category | EscalationCategory or null; evaluation's advisory primary category, not final engine authority |
| reason | nonblank explanation, uncertainty and assumptions stated honestly |
| latency_ms | nonnegative integer measured by orchestrator |
| created_at | timestamp of immutable normalized envelope |
| started_at | timestamp of attempt start |
| completed_at | timestamp of completion/failure/timeout, >= started_at |
| agent_errors | array of { component, code, message }; nonblank sanitized strings |
| raw_output_hash | InputHash or null if no output was received |
| reported_model_version | sanitized untrusted provider-reported string or null |
| correlation_id | nonblank trace ID |
| criterion_scores | array of { criterion_id, score, maximum_score, rationale, evidence_refs }; score/maximum_score nonnegative numbers, score <= maximum_score |
| assumptions | string[]; unsupported assumptions cannot be represented as established facts |

Each property is required, including empty arrays and explicitly nullable properties. Provider outputs missing required expected fields, containing unknown model versions, unparseable data, nonfinite/out-of-range values, unknown enums or incorrect snapshot identifiers are failures. A provider cannot choose the trusted plan/version/round/hash/configuration identity: the orchestrator checks it against the submitted request.

## Success and failure semantics

SUCCEEDED requires non-null model_version, media_result, both confidence values, feasibility_score and proposed_action; agent_errors is empty. Evidence references must resolve. Feasibility criterion aggregation is declared by the immutable policy; the orchestrator validates the declared total rather than rewriting it. No default score or confidence may fill a missing field. A successful evaluation may still require Human Review because of low confidence, missing facts, conflicts, hard violations or policy gates.

RECOMMEND_AUTO_APPROVAL is advisory and can only be proposed when evaluation-side gates pass with no material uncertainty; escalation_category must then be null. It does not assert a budget/authority PASS. RECOMMEND_HUMAN_REVIEW requires a category and reason. The engine independently computes outcome and category from validated evidence and deterministic configuration; it ignores any attempt to output a final outcome.

FAILED or TIMED_OUT requires at least one agent_errors entry and null media_result, media_confidence, feasibility_score, feasibility_confidence and proposed_action. Preserve trustworthy partial evidence/findings only; never use them to bypass failure. Set escalation_category = FACT_UNCERTAIN. Use error codes such as PROVIDER_TIMEOUT, PROVIDER_ERROR, INVALID_SCHEMA, UNKNOWN_MODEL, INPUT_MISMATCH or EVIDENCE_CONFLICT. A configured known model may remain in model_version after a timeout; an unavailable/untrusted model is null and its sanitized reported value remains in reported_model_version. Never fabricate a trusted model version.

The orchestrator, not a malformed provider response, constructs a complete failure envelope with trusted IDs/hash/policy and sanitized error metadata. It persists this envelope so EngineDecision.evaluation_id is always resolvable even when no valid AI output exists. Retain a raw-output hash where available; do not put raw media, credentials or arbitrary provider response bodies in audit.

## Provider boundary and resilience

VisualModelProvider defines analyzeImage(), healthCheck() and getModelMetadata(); implementations required later are LocalVLMProvider and MockVLMProvider. Only attachments from this version snapshot may be analyzed. Local inference is the approved integration mode; external transmission requires explicit approved configuration. Mock provider is visibly identified and must cover pass, review-required and timeout/error cases.

The orchestrator owns finite configured timeout/retry bounds, health/metadata validation and failure handling. Exact durations/model/runtime are NOT_SELECTED at WP1; valid configuration is required before execution. No unbounded retry and no automatic resubmission. New attempts have new run_id/evaluation_id and preserve prior envelopes; the input_hash remains unchanged for the same snapshot. Provider latency is measured, not estimated by the model.

For the same plan/version/round, Decision, Evaluation, Questions and Audit must agree on input_hash, policy_version and evaluation_id where applicable. Budget and authority calculations live in the engine contract, never in final LLM arithmetic.

