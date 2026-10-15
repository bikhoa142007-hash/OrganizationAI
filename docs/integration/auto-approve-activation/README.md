# Auto-approve activation package — OrganizationAI

This package contains the user-approved Marketing/social Media policy, the seven-criterion Strategy rubric, and the requested limits. It is configuration data, not executable instructions or a replacement for the backend configuration schema.

## Approved values

- Media policy `ORG-MEDIA-MARKETING-SOCIAL`, version `1.0.0`, exact scope `Marketing` / `social`, with two `WARNING` rules. No wildcard scope or severity escalation.
- Strategy rubric `BA-STRATEGY-7-1.0`, weights `15/15/15/15/15/15/10` as represented in `strategy-rubric.json`.
- Per-plan budget ceiling: VND `10000000`.
- Automatic authority ceiling: VND `5000000`.
- Thresholds: feasibility score strictly greater than `70`; Media confidence at least `0.85`; feasibility confidence at least `0.80`.

## Production configuration — 2026-10-15

The authenticated ADMIN configuration page validated and recorded PostgreSQL revision 1 for each item below, effective 2026-10-15 16:00 Asia/Ho_Chi_Minh:

- `budget`: **EFFECTIVE** — VND 10,000,000 for Marketing.
- `media_policy`: **EFFECTIVE** — `ORG-MEDIA-MARKETING-SOCIAL` 1.0.0, Marketing/social, both approved rules remain `WARNING`. The runtime schema normalizes omitted optional `forbidden_literals` to an empty list; the UI revision stores that empty list explicitly, with no behavior change.
- `strategy_rubric`: **EFFECTIVE** — `BA-STRATEGY-7-1.0`, seven approved criteria and weights.
- `approval_policy`: **DISABLED** — thresholds 0.85 / score >70 / 0.80 are recorded; `enabled=false`.
- `authority`: **DISABLED** — VND 5,000,000 and Marketing scope are recorded, but `checker_id`, `policy_owner_id`, and `budget_authority_id` are null. It must stay disabled.
- `checker_assignment`: **UNCONFIGURED** — no default Checker revision exists.

The employee directory shows three active accounts with the fixed Checker role (`bkhoa`, `smile1`, and `lekhoi`), but their employee department and job title fields are blank. Existing Marketing plans have been assigned to more than one of them, so the directory does not establish a unique Marketing default. No Policy Owner or Budget Authority designation is present in the fixed role catalog.

The backend rejects `approval_policy.enabled=true` before PO sign-off, and the deployed API has no sign-off workflow. Do not bypass the validator or enable authority with null actor IDs. The recorded disabled revisions preserve the approved values while keeping decisions fail-closed. Until the missing identities, Checker default and valid PO sign-off path are established, do not claim auto-approval is active or production pass/fail is verified.

## Model and deployment status

- Render service `organizationai-api` is running code commit `b67a658`. This branch contains configuration documentation; it is not deployed as application code.
- Render's VLM, Media and Strategy remote-inference switches were set to `true` with the model identities/digests recorded in `render-media-strategy.env.example`. `/api/health/ready` confirmed production and PostgreSQL readiness after the Render environment restart.
- `/api/health/ready` does not probe the VLM. No production image or plan inference was sent, so model availability and real-task output remain unverified.
- The activation request remains `configuration_complete=false` until production identities, a Checker assignment and an allowed PO sign-off path are present.

## Verification and fallback

The existing decision-engine tests cover the strict score boundary (71 passes, 70 does not), budget equality and over-limit behavior, low confidence, hard violations, invalid output and error fallback. Targeted verification on 2026-10-15 passed 59 tests and 66 subtests.

The backend requires Media PASS, Media confidence ≥0.85, Strategy score >70, Strategy confidence ≥0.80, an active matching VND budget, an active authority at or below its cap, a configured eligible distinct Checker, no hard violation/conflict/error, and enabled approval policy. Missing configuration, scope mismatch, budget/authority excess, invalid or failed AI output, or any threshold miss must remain on the human-review/Checker path. Equality at the budget ceiling passes; one unit over it does not.
