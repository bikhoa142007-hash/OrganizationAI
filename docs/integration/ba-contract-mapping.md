# BA v2.1 -> WP1/WP2 mapping

Implementation: src/verify/ba_adapter.py. Execution: src/verify/runner.py.
Fixture schema status: **PROPOSED_FIXTURE_SCHEMA**. The JSON proposal is not the
official WP schema. Shared domain decoders reject missing and unknown fields.

| BA source | Existing backend | Handling |
| --- | --- | --- |
| name | payload.title | Preserve text |
| budget_vnd | payload.budget_minor_units | Require nonnegative integer; exact decimal string, VND precision 0 |
| department_id | payload.department | Explicit field map; budget scope uses configured department |
| maker_id/checker_id | trusted workflow principals / payload | Test directory is synthetic; HTTP does not accept maker_id and validates assigned Checker |
| sha256 | content_hash | Compare source bytes; upload through workflow calculates authoritative hash |
| mime_type | media_type | Workflow checks MIME allowlist and signature |
| size_bytes | byte_size | Compare actual bytes; workflow computes stored size |
| attachment_id/path | server attachment_id | Source ID only joins evidence to uploaded bytes; filename only locates fixture; never decides outcome |
| agent_outputs.vlm.evidence | EvaluationResult.evidence | ATTACHMENT source points to newly uploaded ID/hash; observation retains OCR, confidence, bbox and factual source metadata |
| fact_verification.issues, CONFLICTING_VALUES | evidence_conflicts | Preserve issue ID, field, source values, pointers, verified_value=null, unresolved status, rationale and evidence references |
| fact_verification.issues, INCOMPLETE_EXTRACTION | missing_facts | Full structured issue serialized into existing string field; original evidence remains resolvable |
| VLM/media/strategy model, prompt, agent versions and confidence | evidence provenance | Separate raw versions/confidences retained; known normalized adapter model is role1-mock-adapter-v2.1 |
| strategy criteria score/weight | criterion_scores score/maximum_score | Decimal(score) * weight / 100; maximum=weight. Total checked against original strategy score by engine; scores never adjusted to pass |
| strategy evidence_refs | PLAN_FIELD Evidence | Resolve plan fields into submitted payload; unknown reference fails |
| hard_violations/warnings | media_findings | HARD_VIOLATION with original rule ID; ordinary warning has null rule; preserve refs |
| policy_scope_covered=false | rule-backed media finding and POLICY evidence | POLICY_SCOPE_MISSING warning with snapshot reference; source fixture media REVIEW_REQUIRED remains unchanged |
| agent_outputs.budget result | not used for final arithmetic | Engine selects active budget snapshot and compares submitted amount itself |
| input.context IDs/status | fresh workflow identity | New run/plan/version/round via application; fixture IDs are not trusted database identity |
| input_hash/evaluation_fixture_hash | source provenance only | Backend recomputes WP snapshot hash; never substitutes BA source hash |
| expected.route/category/reason | runner assertion only | Provider accepts only input, rejects whole case envelope/expected/case_id fields |

## Runtime rule evidence used for BA assertions

| BA reason | Required actual evidence |
| --- | --- |
| MEDIA_REVIEW_REQUIRED | MEDIA_PASS check failed |
| UNRESOLVED_CONFLICT | Persisted evidence_conflicts and failed NO_EVIDENCE_CONFLICT |
| VLM_LOW_CONFIDENCE | Original VLM confidence in preserved provenance below .85; not an added WP gate |
| POLICY_SCOPE_MISSING | Persisted rule-backed policy-scope finding |
| BUDGET_LIMIT_EXCEEDED | Failed deterministic BUDGET_LIMIT |
| HARD_VIOLATION | Failed NO_HARD_VIOLATION |

The engine retains AUTHORITY_EXCEEDED > POLICY_OUT_OF_SCOPE > FACT_UNCERTAIN
for independently established failures. Factual-only media review is no longer
misclassified as a policy failure. Hard or rule-backed findings still preserve
policy precedence, covered by mixed-trigger tests.

Runner executes draft -> upload -> submit -> orchestrator/provider -> evaluate ->
get_verify_observation, then reads the oracle. It validates persisted schema,
version/input hash, evaluation linkage, questions and audit before asserting.
All five Verify rows also expose the WP1 field shape with timings and required
assertions. GT hard-category exceptions are documented separately.

Fixtures are synthetic, effective-period snapshots for test simulation. They are
not selected as live company configuration and are not loaded by normal plan API
routes. Expected files never influence provider/engine inputs.
