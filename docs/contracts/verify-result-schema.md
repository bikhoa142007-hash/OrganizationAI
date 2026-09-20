# Verify result schema — WP1 / schema version 1

Uses RuntimeOutcome and EscalationCategory from [decision contract](decision-contract.md).
Verify executes the real application path and compares its recorded result with independently owned expected results. This document does not implement a runner.

## Fields

| field | type and invariant |
|---|---|
| case_id | nonblank ID from Role 1 case catalog |
| expected_action | RuntimeOutcome |
| actual_action | RuntimeOutcome or null when application failed to produce a valid outcome |
| expected_category | EscalationCategory or null; null iff expected_action = AUTO_APPROVED |
| actual_category | EscalationCategory or null; when actual_action = HUMAN_REVIEW_REQUIRED a category is required |
| generated_question | EscalationQuestion[] conforming to escalation-question-schema.md; plural contents retain required field name |
| applied_rule_ids | distinct string[] copied from actual engine output, empty only with no valid output |
| started_at | timestamp recorded before invoking application |
| completed_at | timestamp recorded after observation/failure, >= started_at |
| duration_ms | nonnegative integer from monotonic elapsed timer |
| pass | boolean computed by runner, never supplied by fixtures/application |
| schema_version | integer fixed 1 |
| evaluation_id | string or null if unavailable |
| decision_id | string or null if unavailable |
| plan_id | string or null if setup failed |
| plan_version | integer >= 1 or null if setup failed |
| approval_round | integer >= 1 or null if setup failed |
| input_hash | InputHash or null if setup failed |
| policy_version | string or null if unavailable |
| application_invoked | boolean, true only after real adapter invocation |
| application_reference | nonblank route/service-operation identifier or null before invocation |
| correlation_id | nonblank trace ID |
| assertions | array of { assertion_id, passed: boolean, detail: nonblank string } |
| error | null or { code, message }; nonblank sanitized strings |

## Real-path execution contract

Runner ownership: Role 3. Case data and expected outcomes: Role 1. Application/domain engine and validators: Role 2. Runner must use the same submit/evaluate/read-result application boundary used by the UI/service, with normal authorization, snapshotting, persistence and audit enabled. It may use MockVLMProvider through the normal orchestrator with explicit test configuration. It must never replace the Decision Engine, hard-code PASS, reproduce the rules locally to invent actual output or read expected results as the actual result.

Capture the persisted decision/evaluation/questions/audit references from the application. Validate their schemas and cross-record hashes/IDs before comparison. The required generated_question property contains all emitted questions; it is empty for AUTO_APPROVED and nonempty for HUMAN_REVIEW_REQUIRED. For a primary category, at least one question has the same category. actual_category is null for AUTO_APPROVED or absent actual outcome only.

pass is true only if application_invoked is true, error is null, all required assertions are present and true, actual/expected action and category match, and required questions/rules/evidence/audit/state checks pass. Empty assertions never pass. Required assertions include APPLICATION_PATH, SCHEMA_VALID, OUTCOME_MATCH, CATEGORY_MATCH, QUESTION_VALID, RULE_TRACE, AUDIT_TRACE and SNAPSHOT_MATCH. Case-specific assertions additionally check critical business rules. Use monotonic time for duration_ms; wall-clock timestamps provide traceability and must not run backward.

If the application is unavailable, invocation fails, output is invalid/reserved or references do not match, set pass=false, preserve error details and use null actual_action where no valid action exists. Reserved output is a contract violation, not an expected valid Sprint-1 result. Invalid actual output must not be normalized into a successful Human Review result by the runner.

Unauthorized/stale/invalid-submission checks are case-specific application error assertions, not extra RuntimeOutcome values. A pure command-error test belongs in unit/integration/E2E results and is not misrepresented as a successful engine-outcome case. Boundary outcome cases can additionally attempt forbidden mutations and assert their rejection.

No stack or application adapter exists at WP1; runner commands are NOT_AVAILABLE. Future execution must fail visibly when unavailable. Tests may exercise reserved enum rejection, but expected_action cannot be reserved. Do not modify verify/expected-results.json to match observed output.

