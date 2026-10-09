# Scope 1 Phase 1 traceability checklist — 2026-10-09

Status vocabulary: **Verified** requires current executable/browser evidence;
**Partial** means code exists but acceptance is incomplete; **Gap** means code or
evidence is missing; **Blocked** means an external environment/decision prevents
safe verification. No item is marked complete solely because a route or screen
exists. The source Phase 1 baseline remains pending PO/stakeholder approval.

| Requirement | Source | Current code/evidence found | Gap / next action | Status |
|---|---|---|---|---|
| Guest entry, login/register navigation, session restore/expiry/logout | Scope §§5, 8.1; UC auth; Sprint auth handoff | Frontend tests pass; browser shows login/register after session restoration delay. No credentials submitted. | Diagnose deployed restore delay using staging logs/network after service access is confirmed. | Partial |
| Public registration grants MAKER only | Scope §11.1; Sprint §5 | `src/backend/api/auth.py`, role seeding and Auth tests exist. | Backend authorization tests could not execute; re-run in a working Python environment. | Partial |
| Active principal + backend authorization; multi-role access | Scope §§4–5, 11.1; authority matrix | Cookie session reloads ACTIVE user/roles; protected routes; frontend role-route tests pass. | Backend role escalation, expiry, Origin/CSRF and staging-cookie tests remain unverified. | Partial |
| Maker cannot self-approve; Checker list active and excludes Maker | Scope §§4, 7, 11.3, 11.7 | Service filters ACTIVE CHECKER users and excludes current Maker; regression test added. | Backend test runner blocked; re-run test when Python works. | Partial |
| Maker plan list/search/filter/detail/create/save/update | Scope §§8.3, UC_MKT_01/02 | Auth plans UI and CRUD service exist. | Compare pagination/search/filter and complete field validation to spec. | Partial |
| Draft may be incomplete; submit validates mandatory fields/date/budget/KPI/Checker | Scope §§9, UC_MKT_02/03, BR plan | Draft/submit validation exists; zero budget accepted and negative rejected; create request supports idempotent retries via additive migration. Regression tests added. | Backend and migration tests blocked by Python launcher; re-run and inspect PostgreSQL migration compatibility. | Partial |
| Valid private image upload and immutable submitted attachment snapshot | Scope §9.3, BR files; AGENTS data integrity | Private PNG/JPEG/WebP bytes, size/pixel checks, SHA-256 and snapshot manifests. | Spec lists broader document formats; reconcile accepted image-only workflow with media/AI constraints. Confirm MIME/decode and file-lock tests. | Partial |
| Submit creates immutable Version 1 / Round 1; resubmit increments; old records immutable | Scope §§6, 11.4; AGENTS | Version/round persistence, unique round/run/decision, revision guards and event log. | Run current tests; verify attachments and prior AI results remain unchanged across resubmission. | Partial |
| Assigned Checker review, approve/reject, nonblank rejection, override reason | Scope UC_MKT_04–07, BR decisions | `/api/workflow` decision path, UI review/detail, audit; tests are present. | Verify checker assignment authorization, decision replay and override matrix. | Partial |
| Refresh/GET is read-only; retry idempotent; only active round can decide | Scope BR submission/decision; AGENTS | Removed recovery side effects from plan GET/list; explicit assigned-Checker POST recovers stale current round; draft creation key replays the same plan. Backend regression tests added. | Tests blocked; only draft-create retry is implemented (no notification outbox exists), so notification retry remains a gap. | Partial |
| Employee list/create/update/deactivate and login account lifecycle | Scope features EMP-01..05; UC Admin | No employee/admin API or screen found in initial source inventory; user/role tables exist. | Implement with additive schema/service/API/UI, controlled account reset/lock and audit; verify deactivation Checker reassign rule. | Gap |
| Role create/edit/deactivate and permission assignment | Scope features PER-01..03; authority matrix | Role catalog migration seeds MAKER/CHECKER/ADMIN; no dynamic role admin found. | Implement Admin-only management from canonical permissions; prevent removing required Admin access and audit. | Gap |
| Default Checker configuration and Maker switch choice | Scope APR-04/05, §11.6 | Plan assignment accepts Checker; no explicit default-config module found. | Implement config only after rule source is clear; enforce active role and Maker exclusion. | Gap |
| SLA duration/unit/calendar, due status, warning/overdue alerts and recipient/channel config | Scope SLA-01..05, §§12, 13 | No SLA persistence/service/UI found. | Implement configuration/state without inventing duration; pause pending business configuration. | Gap |
| In-app and email notification events, delivery/retry audit | Scope NOT-01/02, §§11.8, 13 | Append-only events exist; no notification outbox/provider found. | Implement transactional outbox/in-app list; email adapter stays disabled until approved provider/config. | Gap |
| System timeline and audit; internal note | Scope HIS-01..03, §14 | Append-only workflow events plus new Admin-only paginated audit endpoint and read-only UI. Frontend route tests pass. | Current log covers workflow events only; employee/role/config events do not exist; backend test blocked. Internal note remains unlocated. | Partial |
| VLM configured, called, schema-valid, evidence and actual business result | Scope AI-01, §8; `AGENTS.md` §9 | Explicit `LOCAL_VLM` adapter and mock scenarios; extraction v2 adds quality/confidence/evidence metadata. No current hosted call evidenced. | Backend tests blocked; output has no evidence regions/bounding boxes; staging model version and live inference unverified. | Partial |
| Media compliance scoped to submitted snapshot, configured policy, evidence, violations/warnings | Scope AI-02/03, §§8, 12 | Separate evaluator and persisted step results; local ruleset only targets synthetic `Nori Pilot` / `social` scenario. | No approved production policy; out-of-scope media is skipped and must remain Human Review; backend tests/live provider blocked. | Partial |
| Strategy seven-criterion score, confidence, assumptions and evidence | Scope AI-04, §12.4 | Evaluator computes score from seven model-returned criteria; prior local report records valid all-zero results due missing support. | Exact per-plan cause cannot be determined without immutable input snapshot/raw response; do not retune scores without approved rubric/evidence. | Partial |
| Deterministic Budget Rules Engine and immutable budget snapshot | Scope AI-05, BUD-01..04; AGENTS | Deterministic engine exists in policy decision path; no budget configuration admin UI/API found. | Implement versioned budget config and effective selection; no source limit configured and no auto-approval. | Partial |
| Decision Policy Engine and controlled auto-approval; never AI auto-reject | Scope AI-06..09; AGENTS §6 | Deterministic policy and HUMAN_REVIEW fallback exist; default auto-approval disabled. | Test score 70/71, confidence boundaries, budget equality/overage, errors/concurrency; keep off absent approved config. | Partial |
| Admin policy/rubric/budget configuration, snapshots per round | Scope UC_MKT_12, §12.3/12.4, BUD-01..04 | Server env snapshots and policy read page; no authenticated admin configuration endpoints/screens found. | Add backend-managed versioned settings with authorization/audit; environment remains operator-only fallback. | Gap |
| Browser end-to-end through reject, resubmit, approve with two sessions | Scope §§18; user request | Public frontend only displays “Đang khôi phục phiên đăng nhập…”; API URL navigation blocked. | Render ownership and test identities unavailable; do not use real account or write until staging confirmed. | Blocked |
| PostgreSQL compatibility/migration/readiness and deployment verification | Scope §18; deployment docs | Seven Alembic migrations, `render.auth-staging.yaml`, `/api/health/ready` and migration isolation tests. | No live staging DB permission. Confirm disposable PG test first; dashboard unavailable; don't deploy to Judge Demo host. | Blocked |
| Preserve Judge Demo SQLite, backups and current Auth records | User request, Scope §19 | No DB writes or generated plan IDs. Fresh read-only SQLite manifests show `runtime/demo-organization.sqlite3` matches its 5-attachment seed backup; two restore backups have 0 attachment rows. | No PostgreSQL/staging data inspected; local read proves attachment-manifest parity at this checkpoint only. | Partial |
| README, operational guidance, rollback, dated report | AGENTS §§13–16; user request | README and deployment/rollback docs updated; prior report dated 2026-10-03 remains intact. | Add current 2026-10-09 progress report; do not claim scope completion or stale PR state. | Partial |

## Acceptance evidence checklist

- [ ] Inventory source files and map implementation/test locations per row.
- [ ] Confirm auth guest/login/register/restore/logout in local browser/test.
- [ ] Confirm Maker/Checker role isolation and negative API access tests.
- [ ] Confirm draft→submit V1/R1, reject reason, resubmit V2/R2, approve; old
      version/run/audit unchanged; GET and refresh have no side effects.
- [ ] Cover active Checker filters, no self-approval, required form/KPI/date/file
      validation, concurrent/replayed decisions and attachment snapshot locks.
- [ ] Implement and test employee/account/role administration with additive
      migrations, permission checks and audit.
- [ ] Implement configurable Checker defaults, SLA, in-app notification and
      email adapter safely; record unresolved business/provider values.
- [ ] Validate VLM extraction separately from Media and Strategy; preserve
      raw score/confidence and distinguish configured/called/schema-valid/accepted.
- [ ] Validate deterministic budget and decision boundaries with isolated tests.
- [x] Run frontend suite/typecheck/build and URL validator; current results pass.
- [ ] Run isolated backend suite, E2E and migration compatibility; backend
      interpreter cannot start in this Windows environment.
- [ ] Verify Render dashboard service identity before any deployment; verify
      actual deployed commit and browser flow only on approved staging.
- [ ] Recheck data preservation read-only; no live test data unless authorized
      test identities/service are confirmed and each generated ID is recorded.
- [x] Review diff and secrets, commit/push and open draft PR #20; no force-push
      or merge.
- [x] Update progress report and mark every unresolved row PARTIAL/BLOCKED.
