# Scope 1 Phase 1 implementation plan — 2026-10-09

## Goal and status rules

Complete the repository work traceable to `docs/scope-phase-1.md` without
confusing it with the narrower 72-hour Sprint 1 vertical slice in
`docs/sprint-1-deliverables.md`. The Phase 1 baseline remains marked pending
PO/stakeholder confirmation; this plan does not claim that approval. Keep the
Judge Demo SQLite database, restored SQLite backups, Auth PostgreSQL data, old
versions, AI results and audit records intact.

The starting branch was `feature/auth-first-staging`, HEAD was
`93145a0e0828c4a9783dd99ba8d32705627e81e5`, and 11 working-tree files contained
uncommitted VLM extraction changes from the prior turn. Those changes were
preserved on `codex/scope1-phase1-20261009`; additional implementation is still
uncommitted at this checkpoint.
The prior report's PR #17 is stale: GitHub shows PR #17 and PR #19 merged; PR #19
contains the current HEAD. Remote shell access previously failed DNS resolution.

## Repository baseline

- Frontend: React, TypeScript and Vite, managed with npm under `frontend/`.
- Backend: FastAPI, SQLAlchemy and Alembic under `src/backend/` and `alembic/`.
- Auth workflow: PostgreSQL-backed `/api/auth/*` and `/api/workflow/*`; secure
  JWT cookie, database-reloaded active roles and backend permission checks.
- Judge Demo: separate SQLite-backed legacy API and `/demo/*` UI. Do not mix its
  actor header, records or database with Auth workflow work.
- AI: provider adapter, snapshot-based Auth orchestrator, persisted extraction,
  Media/Strategy evaluation, deterministic policy and explicit fail-closed
  configuration. No Mock fallback on Auth production configuration.
- Existing commands: `python -m pytest`, `npm run test --prefix frontend`,
  `npm run typecheck --prefix frontend`, `npm run build --prefix frontend`,
  `npm run test:e2e --prefix frontend`; deployment validator uses Node.
- Existing Alembic chain has seven additive Auth migrations through
  `20261003_07_seed_auth_role_catalog.py`. No employee, role-admin, SLA,
  notification or budget-admin API/screen modules were found in the initial
  inventory. Existing shared pieces include Auth principal/dependencies,
  append-only workflow events, plan/version/round services, private attachment
  storage, audit timeline, frontend Auth shell and service interfaces.
- Python test execution is currently blocked because the repository virtualenv
  interpreter cannot be created by Windows (`The file cannot be accessed by the
  system`); `py -0p` reports no installed Python. Do not alter the environment
  or weaken protections to work around it.
- Render dashboard ownership/service identity and staging DB access are not
  established. The public frontend currently remains on “Đang khôi phục phiên
  đăng nhập…”; API navigation is blocked by the browser. Do not write to the
  live service or database until a service is positively identified as permitted
  staging.

## Progress checkpoint (2026-10-09)

- Frontend Vitest: 10 files / 54 tests passed; typecheck and production build
  passed after fixing issues surfaced by the first run.
- Deployment URL validator: 2 tests passed; `git diff --check` passed; AST
  parsing passed for all 12 changed Python files.
- Backend pytest and Playwright E2E did not start: Windows could not access the
  repository `.venv` Python executable. No runtime/configuration workaround was
  applied.
- Changes at this checkpoint add explicit Checker stale-run recovery (GET is
  read-only), Admin read-only plan visibility and workflow audit, draft-create
  idempotency, and zero-budget validation. They are not deployed.
- Full Phase 1 remains incomplete; see the dated progress report and traceability
  checklist for remaining gaps and external decisions.

## Work packages and dependency order

| WP | Scope | Exit evidence | Dependencies |
|---|---|---|---|
| 0. Baseline and traceability | Re-read authoritative docs, inspect clean/diff state, map feature IDs to code/tests/gaps, distinguish Phase 1 from Sprint 1 and record conflicts. | Dedicated plan/checklist and dated progress report; no old plan overwritten. | None |
| 1. Auth and access | Verify guest routing, login/session restore/expiry/logout, Maker-only public registration, multi-role navigation, active Checker selection excluding the Maker, API authorization, Origin/CSRF/CORS, and Maker self-approval protection. Fix only evidenced gaps. | Backend/frontend tests plus browser evidence where safe; no test uses live DB. | WP0 |
| 2. Maker–Checker workflow | Verify draft, validation, private uploads, submit snapshot, immutable versions/rounds, assignment, decision idempotency/concurrency, rejection reason, resubmission, history and non-mutating GET/refresh. Fix code and regression tests. | Isolated DB tests cover required rules; frontend flow/typecheck/build. | WP1 |
| 3. Employee, account and role administration | Implement the Phase 1 employee/account lifecycle and role/permission administration by extending existing identity schema/services; enforce Admin-only backend policies and audit all changes. Resolve exact role-permission matrix from the authority document, not assumptions. | Additive migration tests, authorization negatives, audit evidence, UI tests. | WP1; authority matrix |
| 4. Checker settings, SLA and notifications | Implement configured default Checker behavior, SLA configuration/state/warnings and in-app/email notification contracts/retry status. Do not invent SLA durations, send external email, or treat ACTIVE as online. | Deterministic tests with configured values; no external message sent without approved provider/config. | WP2; WP3; PO decisions for values/provider |
| 5. Audit/history and configuration | Complete immutable timeline and administrative policy/budget/rubric configuration with per-round snapshots and audited changes. Keep notes optional if Should. | Tests prove history append-only and old snapshots unchanged. | WP2–WP4 |
| 6. AI pipeline | Independently verify VLM extraction, Media Compliance, Strategy, Budget Rules and Decision Engine. Diagnose scope mismatch and Strategy zero from snapshots/input/evidence; fix technical defects only. Preserve fail-closed behavior and keep auto-approval off without approved config. | Isolated fixture tests; real-model claims only with real provider evidence; versioned contracts and snapshots. | WP2; approved policy/rubric/budget needed for business acceptance |
| 7. Integration and staging | Run isolated suites and PostgreSQL compatibility tests only against a disposable test DB. Inspect Render dashboard read-only; deploy only if service is certainly authorized staging and all gates pass. | Record deployed commit, real URLs, readiness, migrations and browser smoke. | WP1–WP6; DB/service access |
| 8. Handoff | Review diff/secrets, run repository gates, update README and dated evidence report, commit/push and create/update draft PR if shell access permits. Include rollback preserving DB and old data. | Accurate PARTIAL/BLOCKED status and reproducible next actions. | WP0–WP7 |

## Known scope conflicts and decision gates

1. `docs/scope-phase-1.md` is a broad Phase 1 baseline but explicitly “chờ
   PO/Stakeholder xác nhận”. `AGENTS.md` and Sprint 1 defer full administration,
   SLA, production email and several settings to later work. The user explicitly
   requests Scope 1, so implement precise Phase 1 behaviors where they are
   specified; never claim Sprint 1 deferral means the Phase 1 feature is done.
2. `docs/integration/ba-conflict-report.md` records an earlier BA conflict
   resolution that prohibited another production gate. Current Scope Phase 1
   BR-AI-09/10 and AGENTS.md require the separate Local VLM confidence/quality
   Human Review gate. Current authorized behavior follows the newer explicit
   user/repository requirements; report the conflict and keep the extraction
   threshold configurable/versioned rather than silently reusing Media policy.
3. VLM spec requests evidence regions; current extraction v2 returns text,
   object labels, confidence and quality, but no bounding boxes. Do not fabricate
   coordinates; record this as a precise contract gap pending implementation or
   PO clarification if the chosen runtime cannot provide reliable coordinates.
4. SLA periods, employee administration capabilities, exact role permissions,
   approved notification provider, media policies, strategy rubric and budget
   authority require business/operations data not present in the repository.
   Build safe configuration primitives where values are specified; keep unset
   values disabled/fail-closed and document required decisions.

## Verification and data rules

- Read test fixtures and env isolation before invoking backend tests. Refuse any
  test configuration that resolves `DATABASE_URL` to live Render. Use SQLite
  temp DB for logic and a disposable PostgreSQL database for compatibility.
- Frontend: Vitest, typecheck, Vite production build, E2E only against its own
  isolated DB. Browser verification of deployed staging is read-only until an
  authorized synthetic account/Checker and unique test are provided.
- AI: record whether a provider was configured, actually called, schema-valid,
  and business-accepted as four distinct facts. Mock output is isolated test
  evidence only.
- Do not reset, truncate, downgrade, reseed, delete, or recreate existing DBs,
  backups, attachments, plans, versions, evaluations or audit records.
- Do not log credentials. Do not request passwords or a full database URL.
- Recheck `git diff --check`, changed-file inventory and secret patterns before
  commit. Never force-push or merge. If remote/Dashboard access is blocked, leave
  deployment untouched and report the exact missing operator action.
