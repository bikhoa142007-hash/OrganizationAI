# Sprint 1 authorization, validation and workflow audit

Date: 2026-09-22. Branch: `fix/rbac-workflow-validation`. Starting tree was clean on
`refactor/role-names`. Changes remain unstaged; no commit, push, merge or deployment.

## Sources and repository inventory

Read AGENTS.md, the current scope (`docs/scope-phase-1.md`) and sprint strategy
(`docs/sprint-1-deliverables.md`), active BA authority/approval/escalation material,
decision contract, integration mappings/conflicts, API/OpenAPI, workflow, seeds,
frontend actor/client/screens and HTTP/domain/frontend/browser tests.
The Vietnamese filenames referenced by AGENTS are absent; existing integration
conflict documentation already identifies these current equivalents. Archives and
fixture provenance were not promoted to runtime authority or rewritten.

Python/FastAPI, pip requirements, standard-library SQLite, repeatable
`migration_001.sql`; React/TypeScript/Vite with npm and its existing lockfile.
No migration or dependency change is needed. Reused ApprovalWorkflow,
ApprovalRepository transactions/idempotency/final guard, Decision Policy Engine,
MockVLMProvider, API error envelope, API service adapters, existing screen components,
Vitest and Playwright. The separate Streamlit frontend remains a local legacy demo.

## Findings and exact automatic-approval cause

Most backend ownership and assigned-checker checks already existed. Inconsistency
came from unconditional frontend navigation/create/edit controls, the review client
building a queue from all visible plans (including a Maker's own), and assignment
validation living only in the HTTP draft route. The generic domain accepted weak
submission content and any nonnegative budget. Department membership was unchecked.
Human decisions checked round state before assignment, producing a state conflict
for an unauthorized Checker on a closed round instead of a permission denial.

`src/backend/demo.py:configuration()` previously constructed an enabled policy
with a literal `True`. `Settings.mock_mode` defaulted to `pass`.
`createApiServices().plan.submitPlan()` submitted then invoked `/evaluate`.
`evaluate_round()` called `decide()` and finalized on `AUTO_APPROVED`.
The provider was not directly writing final decisions: all deterministic gates were
used, but the shared demo enabled them by default and did not clearly explain that
mock PASS could lead to an engine final decision. Seed `auto` used that same policy.

## Canonical roles and permissions

The single canonical matrix is [03-authority-matrix](../role1/v2.1/03-authority-matrix.md).
It covers screens, record reads/creates/edits, submit/review/approve/reject/escalate,
policy, audit, Verify and actor management. Runtime roles are MAKER, CHECKER, ADMIN
and internal EVALUATOR. CHECKER is the single human Approver. A dual-role actor
still cannot self-approve. No separate Judge/Auditor/Approver runtime role exists.
BA and Frontend Developer are project responsibilities only.

All authenticated demo actors may read policy and run isolated Verify fixtures.
Admin has neither a global record bypass nor a runtime policy editor. That is a
Sprint limitation, now stated explicitly instead of implying unimplemented powers.

## Before / after workflow

Before: DRAFT -> submit -> PENDING_APPROVAL/AI_PENDING -> mock PASS + enabled gates
-> APPROVED/AI_AUTO_APPROVED. Review failures already stayed pending for Checker.

After: new HTTP plans use disabled `DEMO-HTTP-2`; submit still creates the immutable
version/round, evaluation yields evidence and HUMAN_REVIEW_REQUIRED, and the
assigned Checker commits APPROVED or REJECTED. Rejection allows editing and the
next version/round. There are no new states, auto-rejection or reopen operations.

The required controlled-auto demo remains ONLY as the explicitly configured
`DEMO-SEED-AUTO` with `DEMO-HTTP-AUTO-1`. All original gates and audit evidence
remain mandatory. Old submitted configurations and final decisions are preserved;
seed replay reuses the first round's original policy across configuration upgrades.

Same successful intent replays; a new or opposite decision on a closed round
conflicts. Existing transaction/concurrency and unique final slot remain intact.
AI failure does not roll back submission. Verify uses a separate in-memory DB and
cannot decide any live plan, even when its test result is PASS.

## Validation and endpoints

Draft payload is now a typed extra-forbidden DTO. The domain also allows only
known payload fields and compatible types. HTTP callers cannot set maker_id,
status, decision actor, roles or audit metadata. Server assigns the Maker.

Incomplete drafts remain allowed. Supplied department/checker/currency references
are validated at save time as well as submission, preventing an unauthorized
Checker nomination from granting draft visibility. A supplied Checker requires a complete valid department/Checker pair; an empty draft may omit both. Department directory and Checker
assignment are trusted host configuration, distinct from auto-approval budget scope.

Submission requires nonblank mandatory fields, a valid separate Checker and image,
positive integer VND budget, actual ISO calendar dates and end >= start. Placeholder
checks normalize whitespace/case and reject exact known values (`test`, `tbd`,
`todo`, `n/a`, `na`, `null`, `undefined`, `placeholder`, `lorem ipsum`, `abc`, `asdf`,
`xxx`, `123`, `đang cập nhật`) and text without a letter in title/objective/summary.
No arbitrary minimum text length is introduced. This conservative check does not
claim to establish business truth or detect every possible meaningless sentence.

| Endpoint | Enforcement / change |
|---|---|
| GET /api/health | Public health only; unchanged |
| GET /api/config | Known demo actor; reports roles, directory and new policy snapshot |
| GET /api/plans | Existing owner/assigned record filtering |
| PUT /api/plans/{id}/draft | Maker + ownership/state/revision; typed payload and directory validation |
| GET /api/plans/{id} | Existing owner/assigned reads; includes scoped audit/history |
| POST /api/plans/{id}/attachments | Existing owner/state/revision, private upload validation/hash |
| GET /api/plans/{id}/attachments/{attachment} | Existing record permission and attachment membership |
| POST /api/plans/{id}/submit | New semantic checks; snapshot/transaction/locking retained |
| POST /api/plans/{id}/rounds/{n}/evaluate | Existing readable-record permission; server evaluator; default policy now routes review |
| POST /api/plans/{id}/rounds/{n}/decision | Role and assignment before state check; active/evaluated round and reasons required |
| GET /api/plans/{id}/rounds/{n}/observation | Existing record access; no extra Verify permission bypass |
| GET /api/reviews | New: CHECKER only, assigned non-own pending Human Review rows; server pagination |
| POST /api/verify/{suite} | Existing known demo actor, isolated fixtures, idempotent run; no live decision |

401/403/404/409/422 structured error envelopes retained. OpenAPI regenerated from
FastAPI. No HTTP endpoint permits enabling auto-approval or editing policy.

## Frontend and documentation

Shell waits for server identity/roles and fails closed; displays current actor and
roles. Create/edit routes require MAKER, review route requires CHECKER; links match.
Edit controls also require ownership. Backend remains the authority for direct calls.
Review queue uses `/reviews`. Form has Vietnamese labels/help, units, required and
optional indicators, configured read-only department/Checker and no prefilled
business narrative. API errors add actionable guidance for 401/403/409/422.
Result/review evidence explicitly labels AI recommendation; final human decision
has its own label. Verify explains its isolated historical fixtures.

Updated README, canonical authority matrix, frontend UI_FLOW, API examples,
OpenAPI, deployment runbook and existing BA conflict report. This report records
the audit and walkthrough; it is not a second authorization matrix.

## Conflict decisions

| Source / conflicting statement | Implemented decision and rationale | Remaining owner decision |
|---|---|---|
| AGENTS obsolete document paths | Use available scope/sprint equivalents; correct README links | Repository owner may align AGENTS references |
| AGENTS/strategy require controlled auto demo; observed shared demo auto-finalizes | Preserve explicit enabled seed, disable new HTTP default | PO must approve any future broader enablement |
| BA authority matrix implied Admin config/audit powers | Document actual read-only config/isolated Verify; no new global read or admin editor | Future authorized admin work package |
| Frozen BA GT-006 expects zero budget valid; current request requires positive | Public/default workflow minimum is 1 VND. Isolated BA runner explicitly uses historical minimum 0; fixture/oracle unchanged | BA owner may issue a new fixture version aligned to current input rules |
| Disabled policy + factual errors | Retain existing category precedence: POLICY_OUT_OF_SCOPE may be primary; preserve all factual evidence | No taxonomy change in this task |
| Completed naming refactor vs legacy paths/model IDs | Runtime roles are never BA/Frontend Developer. Stable `role1` fixture paths and model/schema IDs retain provenance | No naming rollback |

## Verification

Final executed results:

| Command | Result |
|---|---|
| `.venv/Scripts/python.exe -m pytest -q` | 179 passed, 84 subtests passed; two existing FastAPI/Starlette deprecation warnings |
| `npm run test` (frontend) | 16 passed across 3 files |
| `npm run build` (frontend) | TypeScript and Vite production build passed |
| `npm run test:e2e` (frontend) | 5 Playwright scenarios passed; page errors checked, review screenshot visually inspected |
| `git diff --check` | Passed; Git reports only repository CRLF conversion notices |
| JSON parse + OpenAPI assertions | Passed; typed extra-forbidden DraftPayload and /api/reviews present |
| Modified YAML validation | Not applicable: no YAML changed |

Independent review closed the incomplete department/Checker pair loophole.
Whitespace-only reason/override HTTP regressions confirmed that the existing
shared Contract decoder already rejects blank strings; no duplicate validator added.
Final searches found no obsolete Role1/Role3 labels in runtime Python/React source.
Retained lower-case fixture paths/model/schema identifiers are provenance, not roles.
Only Decision Policy Engine outcomes or explicit human decisions finalize live
rounds. UI mock services are not used by the API service provider. The canonical
matrix is updated in place; other docs link to it instead of defining a rival matrix.

 Existing tooling has no
configured root formatter/lint or frontend lint script; `git diff --check`, Python
suite, TypeScript production build, Vitest and Playwright are the applicable gates.
Python uses `.venv/Scripts/python.exe -m pytest`; its Windows Store base requires
execution outside this session's sandbox. No environment/dependency replacement.

## Manual public-demo checklist (after a separately authorized deployment)

1. Wait for the free Render backend cold start. Confirm HTTPS frontend/API and
   configured CORS still work; no public URL is changed by this work.
2. Select DEMO-MAKER-01. Save an incomplete draft. Try blank/placeholder submission,
   zero budget and reversed dates; expect actionable validation, no new version.
3. Fill realistic synthetic content, dates and positive VND budget; attach a valid
   image and submit. Expect pending Human Review, V1/Round 1, AI recommendation,
   locked content and no final decision despite mock PASS.
4. Confirm Maker has no Review Queue and direct `/review` denies access. Direct
   API self-decision returns 403; missing/unknown actor returns 401.
5. Select DEMO-DUAL-01: no access to the other Maker's plan or media, empty queue.
   Select DEMO-CHECKER-01: assigned plan appears, create/edit unavailable.
6. Reject with reason (and override reason when contradicting recommendation).
   Return as Maker, revise and resubmit: V2/Round 2, prior evidence/decision unchanged.
7. Approve a separate pending plan as assigned Checker. Confirm human decision
   actor/time and a single HUMAN_APPROVED audit event. Repeat/new opposite decisions
   must replay or conflict, never create another final decision.
8. Inspect DEMO-SEED-AUTO and its explicit enabled snapshot separately. Inspect
   budget, review, timeout and factual cases; risky evidence stays available for review.
9. Run Verify: evidence/PASS relates only to fixture runs. Inspect plan audit for
   draft, upload, submit, evaluation, routing and human decision old/new states/reasons.
10. After ephemeral restart, only deterministic seed data is restored: eight scenarios.
    User-created plans are temporary. Shared actor selection is not real-user authentication.

## Remaining limitations and next safe work

No production identity provider, real-user isolation, account administration,
policy editor, manual escalation action, multi-level approval, retry of committed
AI evaluations, real external inference or permanent SQLite storage is added.
Record access is plan-level and includes history for the current assigned Checker. The public demo fixes a single Checker and exposes no reassignment operation; round-specific historical access grants would require a separate design before enabling reassignment. The UI lists the first 100 records; API pagination exists. The legacy Streamlit demo
and frozen Verify fixtures retain their own explicit synthetic policies. Public
hosting has not been deployed or manually verified by this task.

Next safe work: inspect the unstaged diff and run the checklist locally; deploy only
under separate authorization. Production identity/company policies remain owner decisions.


## Changed files / work packages

- Backend: `src/backend/api/app.py`, `schemas.py`, `dependencies.py`;
  `application/workflow.py`, `repositories/approval.py`, `demo.py`, `seed_demo.py`.
- Historical Verify configuration: `src/verify/runner.py`.
- Frontend shell/identity: `components/AppShell.tsx`, `components/DemoActor.tsx`,
  `routes/AppRoutes.tsx`; API adapters `services/api/index.ts`, `client.ts`.
- Screens: `LandingPage`, `PlansPage`, `PlanFormPage`, `PlanDetailPage`, `ResultPage`,
  `VerifyDashboardPage`. ReviewQueue uses the corrected service without a redesign.
- Tests: `tests/integration/test_rbac_validation.py`, `test_http_api.py`,
  `test_demo_seed.py`, `tests/unit/test_deployment.py`, frontend
  `pages/authorization.test.tsx`, `services/api/client.test.ts`, `e2e/workflow.spec.ts`.
- Documentation: README, deployment/README, frontend/UI_FLOW, canonical BA authority
  matrix, integration API examples/OpenAPI, BA conflict report and this audit report.

Assumptions: synthetic demo directory is the only public assignment source; positive
budget applies to current application input; historical Verify stays isolated;
controlled auto-approval remains a specifically enabled demonstration only.
