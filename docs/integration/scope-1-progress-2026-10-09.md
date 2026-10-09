# Scope 1 Phase 1 progress — 2026-10-09

## Status

**PARTIAL — not ready to claim Scope 1 complete.** This report follows the broad
Phase 1 baseline in `docs/scope-phase-1.md`; it does not substitute the narrower
Sprint 1 vertical slice for Phase 1. The source spec still says pending
PO/stakeholder confirmation. No business requirements or approval state were
changed here.

Work is on local branch `codex/scope1-phase1-20261009`, started from
`93145a0e0828c4a9783dd99ba8d32705627e81e5`. The prior uncommitted VLM work was
preserved. This checkpoint has not been deployed, committed, pushed, or opened as
a PR. Existing PRs #17 and #19 are merged; the old report's Draft PR #17 status
is stale.

## Work completed in this checkpoint

- Removed stale-evaluation recovery side effects from plan list/detail GETs.
  Recovery is an explicit, replay-safe POST limited to the assigned Checker and
  the active approval round. Tests assert that reads do not change state.
- Added read-only Admin access to all plan metadata/details and an Admin-only,
  paginated workflow audit endpoint/page. Admin-only users cannot create,
  change, decide, or download another participant's attachment through these
  changes.
- Added an optional draft-creation idempotency key, request hash, unique index,
  and additive Alembic migration `20261009_08`. A retry with the same key and
  same request returns the same draft; key reuse with different input conflicts.
- Aligned budget validation with the non-negative Phase 1 rule: zero is valid;
  negative values are rejected.
- Added frontend/backend/migration regression tests for these behaviors,
  Checker selection, Admin access/audit, draft retries, recovery and budget.
- Continued the Local VLM extraction v2 adapter work: structured confidence,
  object and technical-quality evidence; Mock VLM pass/review/error coverage;
  Human Review routing for low confidence, invalid output, timeout, or quality
  review. This is source code and test coverage, not evidence of current hosted
  inference.
- Updated README and local AI/workflow documentation. Created a separate
  Scope 1 plan/checklist; the existing `tasks/plan.md` and `tasks/todo.md` were
  not overwritten.

## Verification evidence

| Check | Result |
|---|---|
| `npm run test --prefix frontend` | PASS — 10 files, 54 tests |
| `npm run typecheck --prefix frontend` | PASS |
| `npm run build --prefix frontend` | PASS — Vite production build |
| `node --test deployment/validate_frontend.test.mjs` | PASS — 2 tests |
| Python AST parse | PASS — 12 changed Python files parsed with bundled runtime; no project imports executed |
| `git diff --check` | PASS |
| `.venv\Scripts\python.exe -m pytest -q` | BLOCKED before test collection: Windows reports `Unable to create process using '"C:\Users\Khoa Bi\VS Studio\repos\OrganizationAI\.venv\Scripts\python.exe" -m pytest -q': The file cannot be accessed by the system.` `DATABASE_URL` was absent. |
| `npm run test:e2e --prefix frontend` | BLOCKED before browser tests: Playwright's webServer cannot start the same repository `.venv` interpreter. Its config points to a unique `runtime/demo-e2e-<timestamp>.sqlite3`; no new E2E database or plan was produced. |
| Local model / PostgreSQL / Render staging | NOT RUN — no model call, PostgreSQL access, or deployment was made in this checkpoint. |

The first frontend run exposed one audit test timing assertion and one generic
TypeScript return inference error; both were fixed, then the complete frontend
suite, typecheck and build passed.

## Current Scope trace

| Capability | Status | Evidence / remaining work |
|---|---|---|
| Login, registration, session restore and role routes | PARTIAL | Frontend route tests pass. Unauthenticated public `/` eventually reaches login; `/register` renders after a delay. No credentials were entered, and staging session/network behavior is not diagnosed. |
| Employee/account lifecycle and Admin role/permission management | GAP | No employee CRUD or dynamic role/permission administration exists. Static MAKER/CHECKER/ADMIN catalog is present. Requires integration with the actual identity/authority matrix and additive migrations, audit, API and UI. |
| Maker plan list/detail/create/save, private image upload and workflow | PARTIAL | Existing workflow plus the changes above. Backend rules, migration, replay/concurrency and attachment-lock tests could not run in this Windows environment. Search/filter coverage and format expectations still need reconciliation. |
| Version/round immutability, Checker decision/rejection/resubmission | PARTIAL | Existing persisted versions, rounds and decision guards; regression tests present. Backend suite and two-session browser reject/resubmit/approve flow were not executable here. |
| Default Checker settings | GAP | Assignment UI exists; an Admin-managed default and effective configuration snapshot are not implemented. |
| SLA and notifications | GAP | No SLA configuration/due-state/warning service or in-app notification outbox is implemented. Do not invent durations or send email without an approved provider. |
| Audit/history | PARTIAL | Existing append-only workflow events plus new Admin-only workflow audit list. Employee/role/config events and internal note are not implemented. |
| Local VLM | PARTIAL | Adapter/mock/schema code and tests are present, but Python tests could not execute and the current deployment was not called. Extraction v2 has no evidence regions/bounding boxes. Self-reported confidence is not calibrated. |
| Media Compliance | PARTIAL | Separate snapshot-based evaluator exists. Local smoke policy is synthetic and only scoped to department `Nori Pilot` / channel `social`; unmatched plans are `MEDIA_POLICY_OUT_OF_SCOPE` and correctly go to Human Review. There is no approved company policy or current staging result. |
| Strategy Feasibility | PARTIAL | Seven-criterion evaluator retains schema-valid model scores. The 2026-10-02 synthetic local run recorded all seven scores as zero because the model supplied no supported evidence for the criteria; these are model outputs, not calibrated truth. Exact cause for any other plan requires that plan's immutable input snapshot and raw response, which were not inspected. Do not raise scores by tuning against unapproved labels. |
| Deterministic budget and controlled auto-approval | PARTIAL | Deterministic engine and fail-closed policy exist; zero budget validation was corrected. No approved company budget/policy config is available, so auto-approval remains disabled. Backend boundary tests did not run. |
| Admin policy/rubric/budget configuration and per-round config audit | GAP | Operator environment is not a substitute for versioned Admin configuration UI/API and audited snapshots. |
| PostgreSQL migration compatibility and staging workflow | BLOCKED | The new migration is additive, but migration tests could not run. Render Dashboard ownership/service identity and authorized test users are unconfirmed; no live DB was accessed or deployment attempted. |

### AI findings retained from prior evidence

- The 2026-10-02 synthetic evaluator explicitly labels expected outputs
  `PROPOSED_NOT_HUMAN_APPROVED`; the seven BA criterion point values remain
  unlabelled. Strategy v5 valid tune outputs returned all-zero criterion scores.
- The recorded successful real local pipeline case
  `4999312c-770e-489c-bc68-9176a6ed8c27` was Checker-approved with score `0.0`;
  two other local synthetic cases failed closed. A hard-marker Media response
  that said PASS while also reporting a hard violation was rejected as invalid
  schema. A truncated VLM response caused extraction failure and Strategy
  invalid schema. Those were observed model-quality failures with Human Review
  fallback, not successful business evaluations.
- The older `docs/integration/ba-conflict-report.md` says not to add a separate
  VLM confidence gate, while the current Phase 1/AGENTS requirements explicitly
  require the Local VLM confidence/quality gate. Current code follows the
  explicit current task requirements and preserves the earlier decision as a
  documented conflict for PO review.

## Data and environment protection

- No database write, migration execution, seed/reset, model inference, plan
  creation, or live account action occurred in this checkpoint. No new plan,
  run, decision, user, or deployment IDs were generated.
- Read-only SQLite inspection used `mode=ro` and `PRAGMA query_only=ON`. The
  current `runtime/demo-organization.sqlite3` and its restored seed backup each
  contain five attachment rows and have matching canonical manifest fingerprint
  `a84a8584d1fa6403038a27ef4cdac4b0ff0ccca8b26297c98d86b6a39384fe8a`; the two
  older restore backups have zero attachment rows. This checkpoint fingerprint
  is a fresh comparison of current file to seed backup, not a claim about
  PostgreSQL or the historical pre-session state.
- The test shell had no `DATABASE_URL`. No password or database URL was printed.
- Public frontend: [OrganizationAI](https://organizationai-frontend.onrender.com).
  The Render Dashboard session was unauthenticated, so service ownership and
  staging identity remain unknown. Do not deploy to either public service until
  the operator confirms the exact staging service and impact.

## Next safe work package

1. Run backend unit/integration/migration tests and Playwright E2E in a working
   isolated Python environment; do not alter or repair the blocked `.venv` as a
   workaround.
2. Implement employee/account and static-role administration only after mapping
   the canonical authority matrix; then add audited Checker/SLA/notification and
   policy/budget configuration using approved values.
3. Re-run the Local VLM v2 smoke against an explicitly isolated local model and
   test DB. Preserve scores and route unsupported/invalid results to Checker.
4. Obtain staging service identity and disposable PG access before a two-user
   Maker/Checker browser workflow or migration compatibility run.
5. Before deployment, review and commit the branch, push it and create/update a
   draft PR if remote access works. Roll back application code through the
   deployment history; retain additive schema and all DB records (no downgrade,
   reset or deletion).
