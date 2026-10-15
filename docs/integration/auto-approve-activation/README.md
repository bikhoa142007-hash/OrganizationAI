# Auto-approve activation package — OrganizationAI

This package contains the user-approved Marketing/social Media policy, the current seven-criterion Strategy rubric, and the requested limits. It is configuration data, not executable instructions or a replacement for the backend configuration schema.

## Approved values

- Media policy `ORG-MEDIA-MARKETING-SOCIAL`, version `1.0.0`, status `ACTIVE`, exact scope `Marketing` / `social`, with two `WARNING` rules. No wildcard scope or severity escalation.
- Strategy rubric `BA-STRATEGY-7-1.0`, weights `15/15/15/15/15/15/15/10` as represented in `strategy-rubric.json`.
- Per-plan budget ceiling: VND `10000000`.
- Automatic authority ceiling: VND `5000000`.
- Thresholds: feasibility score strictly greater than `70`; Media confidence at least `0.85`; feasibility confidence at least `0.80`.

## Backend and deployment behavior

The deployed backend supports `AUTH_WORKFLOW_MEDIA_POLICY_JSON` and `AUTH_WORKFLOW_STRATEGY_RUBRIC_JSON` as base configuration. Revisioned PostgreSQL configuration takes precedence for each approval round, including an explicitly disabled revision. Round snapshots remain immutable.

The approved activation request has `checker_id`, `policy_owner_id`, and `budget_authority_id` unset. The live configuration endpoint requires an authenticated `ADMIN` session and returned `401 UNAUTHENTICATED` during the prior verification. Therefore the effective Checker assignment and authority identities have not been verified or written. Do not infer identities from an Admin account or from test fixtures.

The current approval-policy validator rejects `enabled=true` with `Auto-approval cannot be enabled before PO sign-off.` The deployed schema has no sign-off field; do not bypass the validator or write around it. Auto-approval stays fail-closed until an authorized sign-off path and the live identities/configuration are verified.

Budget equality uses `<=` the configured budget ceiling; auto authority uses `<=` its own ceiling. A plan from an unconfigured department, one without a matching active Checker/authority, over either ceiling, outside the Media scope, with an incomplete/invalid AI result, or below any confidence/score threshold must route to Checker.

## Model and test limits

The environment example pins the previously verified Ollama identities and leaves endpoint URLs blank. Verify the current runtime digests before deployment; do not reuse old digests. No real production inference or positive production auto-approval was performed as part of creating this package.

The request JSON is retained as an input record only. It is not a backend runtime schema and `configuration_complete=false` until production identities, revisioned config, and an allowed PO sign-off path are present.

## Render rollout — 2026-10-15

- Saved the approved `AUTH_WORKFLOW_MEDIA_POLICY_JSON` to Render service `organizationai-api`; its value matches `media-policy.approved.json`. Render reported a successful service restart and `/api/health/ready` returned `status=ok`, `environment=production`, `auth_database=postgresql`.
- `AUTH_WORKFLOW_STRATEGY_RUBRIC_JSON` on Render matches `BA-STRATEGY-7-1.0` and its seven weights.
- Render is running code commit `b67a658`; this documentation branch has not been deployed as code. The environment policy is only the base configuration: an effective PostgreSQL `media_policy` revision, including a disabled revision, takes precedence.
- `/api/workflow/configuration` still returns `401 UNAUTHENTICATED` without an ADMIN session, so effective assignments, limits, authority and approval-policy revisions could not be verified. No database revisions were written, no model inference was sent, and auto-approval was not enabled.
