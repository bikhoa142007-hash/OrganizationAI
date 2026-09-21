# Role 1 – Backend – Role 3 integration report

Date: 2026-09-22. Outcome: runnable synthetic demo integrated and verified; not production deployment.

## 1. Baseline and preservation

Baseline commit: `c1288c9ceb49fe16eea5887fc914a9ad50ba1e44`, originating branch `feature/wp5-frontend-verify`. Work performed on requested branch `integration/role1-role3-frontend`; no commit or staging performed.

Initial user changes: modified README.md and requirements.txt; untracked app.py, frontend/, role1-sprint1-v2.1/, src/frontend/, src/verify/, tests/unit/frontend/, tests/unit/verify/. Preserved these components, adding coherent changes to the existing files. Pre-integration copies of README, requirements and frontend source/configuration are in ignored `runtime/integration-baseline/`.

Discovery found one frontend candidate, `frontend/package.json`: React/TypeScript, Vite, npm, React Router, local component state and mock services. No nested Git was found. Backend was Python/SQLite with ApprovalWorkflow, ApprovalRepository, EvaluationOrchestrator and ApprovalPipelineAdapter. No HTTP transport existed. Existing migration_001.sql and workflow transactions were reused. Full inventory and initial test evidence: [audit](../role-integration-audit-2026-09-21.md).

Verified runtimes: Python 3.13.14, Node 24.17.0. Baseline: 88 pytest tests and 84 subtests passed; frontend build/typecheck passed; no frontend test command existed.

## 2. Imported Role 1 files

The existing extracted `role1-sprint1-v2.1/` was used without overwriting it. All numbered business documents, validation-report and package-manifest are under `docs/role1/v2.1/`. Fixture JSON and image bytes are under `tests/fixtures/role1/v2.1/`.

The [46-entry import manifest](role1-import-manifest.json) lists every source, destination and both SHA-256 hashes. Fixtures and expected results are byte-identical. Imported Markdown has relative links rebased where necessary; differing document hashes are explicit. Existing scope-phase-1.md, sprint-1-deliverables.md and docs/contracts/* were not overwritten.

## 3. Exclusions and provenance

Diffs, changes-v2.1.json, historical regression/mapping status and legacy PDF/README are archived under `docs/role1/archive/v2.1/`, excluded from application inputs. The original validator remains in the extracted source package and must run there; relocated documents do not pretend to be its original layout. Dependencies, build outputs, runtime DBs, actual runtime reports and Playwright screenshots remain ignored. No secret or environment file was staged.

Original package validation: 192/192 artifact checks passed. Original NOT_VERIFIED/NOT_RUN compatibility labels were preserved as historical facts; they are not backend execution evidence.

## 4. Contract mapping and engine correction

Detailed [mapping matrix](role1-contract-mapping.md) and [conflict report](role1-conflict-report.md) describe each translation. VND uses exact integer minor units; attachment identity/hash comes from backend-uploaded bytes; agent evidence retains source and issue provenance. Weighted strategy criteria use Decimal. Proposed fact_verification maps into existing missing_facts/evidence_conflicts/evidence, with strict unknown/missing field rejection. No frozen contract or outcome catalog was extended.

The runner performs draft → upload → submit → orchestrator/provider → persist → get_verify_observation before reading the expected oracle. Expected/category/case metadata is not passed into the input adapter or decision rules.

Decision MEDIA_PASS still fails for REVIEW_REQUIRED. Its failure category is factual when unresolved facts exist without a hard/rule-backed media finding; independent policy and authority failures retain priority. GT-007/008/009 and VERIFY-A04 now produce FACT_UNCERTAIN with retained evidence and questions. Outcomes remain AUTO_APPROVED and HUMAN_REVIEW_REQUIRED; no AI rejection was introduced.

## 5. Backend changes

FastAPI is a transport around existing workflow methods. DTOs, errors and actor dependencies are separate from domain types. Errors include code, message, correlation_id and http_status. Mutations use Idempotency-Key and expected revision. Added authorized plan list/private attachment reads and orchestration entry point; committed evaluation replay uses persisted results.

X-Demo-Actor resolves only server-owned principals in APP_ENV=demo. Public role/maker overrides and the internal evaluator are rejected. Production denies demo auth. Checker assignment remains configured on the server. CORS uses explicit environment origins. Attachments require authorization and are returned with no-store/nosniff; the frontend uses temporary blob URLs.

## 6. Frontend integration

App uses one real API service/client with VITE_API_BASE_URL; original mocks remain unused references. Maker can save incomplete drafts, upload, submit, see results and revise rejected plans. Submitted snapshots are read-only. Checker can approve/reject with required rejection/override reasons. Detail/history show rounds, versions, evidence, factual conflicts and private media. Loading, network errors and revision conflicts have explicit handling. Processing polls persisted state; unsupported Stop/Undo were removed. Verify dashboard runs actual five-case application evaluation.

## 7. HTTP endpoints

All paths below use `/api`. See [generated OpenAPI](openapi.json) and [request examples](api-examples.md).

| Method | Path | Purpose |
| --- | --- | --- |
| GET | /health | Health |
| GET | /config | Server-owned demo configuration |
| GET | /plans | Authorized list with pagination |
| PUT | /plans/{id}/draft | Create/update with revision and idempotency |
| GET | /plans/{id} | Detail/history |
| POST | /plans/{id}/attachments | Multipart upload |
| GET | /plans/{id}/attachments/{attachment_id} | Authorized private media |
| POST | /plans/{id}/submit | Immutable version/round |
| POST | /plans/{id}/rounds/{n}/evaluate | Initial evaluation/replay |
| POST | /plans/{id}/rounds/{n}/decision | Checker decision |
| GET | /plans/{id}/rounds/{n}/observation | Demo observation |
| POST | /verify/{suite} | Demo general/escalation suites |

## 8. Database and seed

No schema change or new migration required. Existing migration_001.sql is applied by ApprovalRepository. Submission and final decisions retain existing transaction, revision and idempotency protections. Prior versions/results/audit are preserved.

Seed command `python -m src.backend.seed_demo` is restricted to APP_ENV=demo and demo-*.sqlite3. Synthetic actors: DEMO-MAKER-01, DEMO-CHECKER-01, DEMO-ADMIN-01, DEMO-DUAL-01, plus internal evaluator. DEMO-HTTP-1 policy uses synthetic 100m VND limit, separate from Role 1 and old Streamlit demo policy. Five scenarios: AUTO, BUDGET, REVIEW, TIMEOUT, FACTS. Running twice produced five new records then zero new/five existing, without deleting records.

## 9. Executed verification

Commands use `.venv/Scripts/python.exe` at root; npm commands run in frontend unless stated otherwise.

| Command/check | Actual result |
| --- | --- |
| Baseline python -m pytest -q | 88 passed, 84 subtests passed |
| Baseline npm run build / npm run typecheck | Passed |
| python tools/validate_package.py (original Role 1 directory) | 192/192 artifact checks |
| python -m pip install -r requirements.txt | Passed |
| npm install --prefix frontend | Up to date; 114 packages audited, zero vulnerabilities |
| python -m pytest -q | 123 passed, 84 subtests passed; 2 dependency deprecation warnings |
| python -m src.verify.runner --suite ground-truth --output runtime/role1-ground-truth-actual.json | 15/15 acceptance assertions |
| python -m src.verify.runner --suite verify --output runtime/role1-verify-actual.json | 5/5 |
| npm run test | 4 passed in 2 files |
| npm run build | Strict TypeScript and Vite passed, 40 modules |
| npm run test:e2e | 4 passed in 10.0s |
| git diff --check | Passed; normal CRLF normalization warnings |
| Live GET :8010/api/health, :5173/, :8010/openapi.json | ok / HTTP 200 / generated schema saved |
| Live authorized GET :8010/api/plans | Five persisted seed scenarios |

No standalone lint/formatter is configured; no nonexistent lint pass is claimed. Browser E2E covers auto-approve/history, budget review → reject → revise → V2/R2 with V1 unchanged, factual uncertainty/Verify, and Checker approval with override/audit. Screenshots remain in ignored frontend/test-results/. Existing tests cover authorization, immutable snapshots, concurrency, failures and idempotent decisions.

## 10. Per-case actual regression

[Durable results](role1-regression-results.json) include execution times and original actual-report hashes. Full persisted observations are in runtime/role1-ground-truth-actual.json and runtime/role1-verify-actual.json.

| Case | Actual outcome | Actual primary category | Assertions |
| --- | --- | --- | --- |
| GT-001 | AUTO_APPROVED | null | PASS |
| GT-002 | AUTO_APPROVED | null | PASS |
| GT-003 | AUTO_APPROVED | null | PASS |
| GT-004 | AUTO_APPROVED | null | PASS |
| GT-005 | AUTO_APPROVED | null | PASS |
| GT-006 | AUTO_APPROVED | null | PASS |
| GT-007 | HUMAN_REVIEW_REQUIRED | FACT_UNCERTAIN | PASS |
| GT-008 | HUMAN_REVIEW_REQUIRED | FACT_UNCERTAIN | PASS |
| GT-009 | HUMAN_REVIEW_REQUIRED | FACT_UNCERTAIN | PASS |
| GT-010 | HUMAN_REVIEW_REQUIRED | POLICY_OUT_OF_SCOPE | PASS |
| GT-011 | HUMAN_REVIEW_REQUIRED | POLICY_OUT_OF_SCOPE | PASS |
| GT-012 | HUMAN_REVIEW_REQUIRED | AUTHORITY_EXCEEDED | PASS |
| GT-013 | HUMAN_REVIEW_REQUIRED | AUTHORITY_EXCEEDED | PASS |
| GT-014 | HUMAN_REVIEW_REQUIRED | POLICY_OUT_OF_SCOPE | PASS |
| GT-015 | HUMAN_REVIEW_REQUIRED | POLICY_OUT_OF_SCOPE | PASS |
| VERIFY-A01 | AUTO_APPROVED | null | PASS |
| VERIFY-A02 | AUTO_APPROVED | null | PASS |
| VERIFY-A03 | AUTO_APPROVED | null | PASS |
| VERIFY-A04 | HUMAN_REVIEW_REQUIRED | FACT_UNCERTAIN | PASS |
| VERIFY-A05 | HUMAN_REVIEW_REQUIRED | AUTHORITY_EXCEEDED | PASS |

GT-014/015 caveat: original expected category is null for Human Review. Acceptance verifies hard-rule evidence, pending state, questions and no final rejection; actual category is POLICY_OUT_OF_SCOPE. Expected fixtures were not changed. Those two rows do not claim full WP Verify category compatibility and do not emit fabricated VerifyResult rows.

## 11. Open decisions

Production identity provider, real company limits/policy, actual local VLM deployment, a VLM-only confidence gate, kill-switch semantics and other Role 1 proposed policy questions remain owner decisions. They do not block the explicitly authorized synthetic demo. Completion of the GT-014/015 category oracle remains with Role 1; no category was invented on its behalf.

## 12. Known limitations and assumptions

- HTTP demo uses explicit mock inference; existing local adapter is not certified here against a running real model. No external inference enabled.
- Demo actors are a simulation, not production authentication. Production integration needs a real trusted identity adapter.
- Verify HTTP replay cache is process-local; workflow mutation idempotency is database-backed. Verify UI state lasts the current page session.
- UI lists the first 100 authorized plans; API pagination exists.
- Committed evaluation cannot be rerun. An unevaluated submitted round can continue; no new manual-retry policy is introduced.
- Demo servers use 8010/5173 because 8000 is owned by an unrelated process; that process was not stopped. Default client fallback remains 8000, so README explicitly sets VITE_API_BASE_URL.

## 13. Changed files

Tracked modifications: README.md, requirements.txt, src/backend/application/workflow.py, src/backend/repositories/approval.py, src/backend/rules/decision.py.

New backend: src/backend/api/{app,dependencies,errors,schemas}.py; src/backend/demo.py; src/backend/seed_demo.py; .env.example.

New Verify: src/verify/role1_adapter.py, runner.py, observation.py. Existing src/verify modules preserved.

Frontend modified: package.json, package-lock.json; src/App.tsx; src/components/AppShell.tsx; src/routes/AppRoutes.tsx; src/pages/{PlanFormPage,ReviewQueuePage,ProcessingPage,AuditTimelinePage,VerifyDashboardPage,LandingPage}.tsx; src/styles.css. New: src/services/api/{client,index}.ts and client.test.ts; src/pages/{PlansPage,PlanDetailPage,integration.test}.tsx; src/components/DemoActor.tsx; src/test-setup.ts; vitest.config.ts; playwright.config.ts; e2e/workflow.spec.ts; .env.example. See the original frontend backup to distinguish integration additions from the initially untracked user frontend.

Tests added: tests/integration/test_http_api.py, test_demo_seed.py, test_role1_regression.py; tests/unit/verify/test_role1_mapping.py; tests/fixtures/role1/v2.1/*.

Documentation: docs/integration/*; docs/role1/v2.1/*; docs/role1/archive/v2.1/*; docs/role-integration-audit-2026-09-21.md; tasks/plan.md; tasks/todo.md. Role 1 imports are individually enumerated in the manifest. Existing app.py, src/frontend and their tests were preserved.

## 14. Run and rollback handoff

Use the verified PowerShell setup/seed/backend/frontend/test commands in [README](../../README.md). Current demo: http://127.0.0.1:5173; backend http://127.0.0.1:8010/api/health; Swagger http://127.0.0.1:8010/docs. Exported OpenAPI was fetched from this running server.

To roll back, first save current work and stop only the integration's own servers. Compare README, requirements and frontend files with runtime/integration-baseline/; restore only integration hunks after checking for newer user changes. Reverse only the three tracked backend integration diffs relative to the recorded commit. Review integration-only added files individually before removing them; never delete the pre-existing untracked directories wholesale. Keep or separately archive demo databases/audit and source package; there was no schema migration to reverse. Do not use git reset --hard or git clean. No commits or external deployment need reverting.

Next safe package: obtain owner-approved production identity/model/policy decisions if production work is desired. Sprint demo acceptance is met with the explicitly recorded oracle limitation; production readiness is not claimed.
