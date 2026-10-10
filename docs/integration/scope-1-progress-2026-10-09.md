# Scope 1 Phase 1 progress — 2026-10-09

## Status

**PARTIAL — not ready to claim Scope 1 complete.** This report follows the broad
Phase 1 baseline in `docs/scope-phase-1.md`; it does not substitute the narrower
Sprint 1 vertical slice for Phase 1. The source spec still says pending
PO/stakeholder confirmation. No business requirements or approval state were
changed here.

Work is on local branch `codex/scope1-phase1-20261009`, started from
`93145a0e0828c4a9783dd99ba8d32705627e81e5`. The prior uncommitted VLM work was
preserved. The implementation checkpoint is commit `199e97f`, pushed to the
branch. Draft PR [#20](https://github.com/bikhoa142007-hash/OrganizationAI/pull/20)
is open against `main` and has no merge conflicts. It has not been deployed or
merged. Existing PRs #17 and #19 are merged; the old report's Draft PR #17 status
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
5. Continue review in draft PR #20. Before any deployment, confirm the exact
   authorized staging service and disposable PostgreSQL access, then run all
   blocked gates. Roll back application code through deployment history; retain
   additive schema and all DB records (no downgrade, reset or deletion).

## Verify dashboard delta — 2026-10-09

After the checkpoint above, the local Judge Verify interface and runner were
extended without touching Auth/PostgreSQL or the restored Judge Demo database:

- `general` now selects 4 cases; `escalation` runs the 5-case Verify input set;
  `regression` exposes all 15 synthetic ground-truth cases.
- Every runner case uses a fresh in-memory ApprovalWorkflow. Only the case
  `input` enters execution; the runner reads expected output after processing.
- The UI shows expected/actual, input, evidence, question context and evidence
  references, policy/model versions, audit IDs and timestamps. It links judges
  to the public demo Maker form for a new synthetic plan.
- Removed the canned Verify mock PASS dataset. Mock mode is labeled as synthetic
  and not real inference evidence. README and fixture/measurement docs describe
  the suites and their current holdout limitation.
- Added API suite tests and frontend Verify/mock-service tests. Final frontend
  checks: Vitest 12 files/58 tests, typecheck, and production build all pass.
- Backend pytest and browser E2E remain blocked. A separate Python 3.12 test
  environment was created, but dependency installation failed at package-index
  DNS resolution for `rfc8785`; E2E then failed before browser startup with
  `ModuleNotFoundError: No module named 'rfc8785'`. Docker daemon access remains
  denied. No Verify backend result or E2E database was produced.

See [the full dated traceability and review](scope-1-review-2026-10-09.md) for
history/remote caveats, migration and recovery findings, and remaining gates.

## Unblock and verification follow-up — 2026-10-09

- Reconfirmed the blockers are independent: `pypi.org` and `github.com` do not
  resolve; the isolated Python 3.12 environment has no `pytest` because the
  dependency install stopped at DNS; Docker CLI exists but access to the
  Desktop Engine named pipe is denied. No registry, sandbox or permissions
  were changed.
- Read-only GitHub lookup still fails DNS, so no fetch was possible. Local
  `HEAD` remains `6ba137c`; the working tree remains uncommitted.
- Added a custom-plan API regression test using random UUIDs, unrelated titles,
  and budgets on both sides of the deterministic limit. It asserts `BUDGET_LIMIT`
  changes from PASS to FAIL while identifying the evaluation provider as
  `MOCK_VLM`. The test is authored but not executed.
- Drafted `.github/workflows/verify.yml` for review. It would run backend pytest,
  all 3 Verify suites with per-case expected/actual output artifacts, frontend
  tests/typecheck/build, Judge Demo browser E2E, and Auth browser E2E plus
  Alembic migration against an ephemeral PostgreSQL service. It has not been
  pushed or activated.
- Static Python AST parsing and `git diff --check` pass. Backend pytest and the
  Verify runtime commands remain blocked by missing dependencies. Judge Demo
  E2E previously stopped before browser startup at missing `rfc8785`; Auth E2E
  and PostgreSQL migration were not run because no isolated PostgreSQL service
  was available.
- The 15-case catalog was used during development and remains a regression
  catalog, not an independent holdout. No independent source/curator has been
  selected; do not report holdout performance. No real VLM or Auth text model
  inference occurred; Verify and the proposed CI E2E use explicitly mocked
  providers.

## Later test-environment update — 2026-10-09

This section supersedes the earlier missing-dependency status above. The user
installed dependencies in `.venv-test-20261009`; using that exact interpreter,
`pip check` passed and `pytest 9.1.1` / `rfc8785 0.1.4` imported successfully.
`DATABASE_URL`, `TEST_POSTGRESQL_DATABASE_URL`, and `DEMO_DATABASE` were unset
for backend pytest and Verify. `pytest.ini` points at `tests`; no dotenv loader
is configured in the test path. Migration tests use temporary SQLite and the
Verify runners use independent in-memory repositories.

- Full backend pytest collected 302 cases and passed the first 38. It then
  stalled entering `tests/integration/test_auth_api.py::test_login_by_user_code_sets_http_only_cookie_and_me_returns_database_roles`.
  A minimal `TestClient` reproduction localized the stall to AnyIO's Windows
  Proactor `socket.socketpair()` / `accept()` path. No assertion failure was
  observed; the full suite is incomplete in this app sandbox.
- Focused `tests/unit/verify` completed: **11 passed**, including the test that
  changes IDs, title, run metadata and attachment filename without changing
  outcome, and tests that reject oracle fields in execution input.
- The three runtime suites completed: **general 4/4, escalation 5/5, regression
  15/15**. Per-case expected/actual values, source hashes, provider provenance
  and differences are in [the Verify run report](verify-run-2026-10-09.md).
  A further two-case custom synthetic input used a new plan and newly generated
  PNG outside the fixture catalog; contradictory route labels in the title did
  not steer the result, while the deterministic budget rule did. VLM, Media
  and Strategy outputs were still mock; no real model was invoked.
- Judge Demo Playwright seeded only its configured temporary SQLite file, then
  could not reach `127.0.0.1:8008`: Playwright reported `connect EACCES` on the
  local health-check. Browser tests did not start. Auth E2E and PostgreSQL
  migration remain unrun. No local PostgreSQL client/server binaries were
  found; Docker CLI exists but Docker Desktop's Linux Engine named pipe returns
  permission denied.
- `.github/workflows/verify.yml` remains an uncommitted, unactivated review
  draft for isolated CI PostgreSQL migration/Auth E2E. A YAML parser is not
  installed here, so it has only had manual review. It has not been pushed.

No migration or live database was used. The 15-case regression set remains a
development set, not an independent holdout. No external source or independent
curator is available in this run, so no holdout result is claimed. No
administration or SLA scope was expanded.

## Auth regression follow-up — 2026-10-09

The user reported an external PowerShell full-suite baseline using
`.venv-test-20261009`: **2 failed, 300 passed, 84 subtests passed, 1 warning**.
This is user-reported evidence from before the fixes, not a run performed here.

1. `test_local_vlm_extraction_persists_separately_and_missing_evaluators_route_checker`
   supplied only five fields per image. `visual-extraction-schema-v2` requires
   eight, including `confidence`, `object_detections`, and `visual_quality`.
   Exact-key validation correctly produced `status=FAILED` and
   `error_code=INVALID_SCHEMA`; the old success fixture was stale. The fixture
   now supplies valid v2 fields and retains its assertions that extraction
   succeeds while unconfigured Media/Strategy evaluators yield
   `HUMAN_REVIEW_REQUIRED`. A separate parameterized unit test removes each
   required v2 field and asserts fail-closed extraction with no evidence.
2. `test_non_workflow_role_cannot_create_and_submission_requires_attachment`
   expected Admin list access to return 403, while the current read-only Admin
   contract allows listing and detail reads. The test was split: an expanded
   Admin test now checks read access and denials for private attachment bytes,
   create, edit, submit, approve, reject, and recovery; the Maker attachment
   test independently asserts submission without an attachment returns 422
   and the plan remains `DRAFT`.
   No API authorization changed. The stale authority matrix was corrected to
   describe the already-implemented read-only contract.

Post-change verification performed in this Codex sandbox:

| Command / gate | Result |
|---|---|
| Focused VLM unit tests: missing v2 fields and existing invalid-schema cases | **PASS 12/12** using `.venv-test-20261009`; DB URL variables unset. |
| Focused Auth workflow regressions (VLM integration, Admin contract, Maker missing attachment) | **INCOMPLETE**: collected 3, then stalled before the first test body while entering Starlette `TestClient`; interrupted after 30 seconds. |
| Full backend pytest, `-q -o faulthandler_timeout=30` | **INCOMPLETE**: 38 tests completed, then stalled entering `test_auth_api::test_login_by_user_code_sets_http_only_cookie_and_me_returns_database_roles`. Faulthandler located the block in Windows Proactor `socketpair()` / `accept()` during AnyIO portal startup. No post-change Auth integration assertion ran. |

Run the focused Auth regressions first, then the entire backend suite, from an
external PowerShell session where local `TestClient` sockets are available:

```powershell
$py = (Resolve-Path '.venv-test-20261009\Scripts\python.exe').Path
Remove-Item Env:DATABASE_URL,Env:TEST_POSTGRESQL_DATABASE_URL,Env:DEMO_DATABASE -ErrorAction SilentlyContinue
& $py -m pytest -q -o faulthandler_timeout=30 `
  tests/integration/test_auth_workflow.py::test_local_vlm_extraction_persists_separately_and_missing_evaluators_route_checker `
  tests/integration/test_auth_workflow.py::test_admin_can_read_workflow_plans_but_cannot_mutate_or_recover `
  tests/integration/test_auth_workflow.py::test_maker_submission_requires_attachment
if ($LASTEXITCODE -ne 0) { throw 'Focused Auth workflow regressions failed' }
& $py -m pytest -q -o faulthandler_timeout=30
```

The reported Starlette warning did not prompt a dependency change. No live DB,
commit, push, merge, deploy, sandbox change, or permission escalation occurred.

## User-run backend verification update — 2026-10-09

The user reports that, after the Auth regression fixes, they ran the complete
backend suite from PowerShell outside the Codex sandbox using
`.venv-test-20261009`:

```text
305 passed, 1 warning, 84 subtests passed in 59.20s
```

This is explicitly user-run evidence; Codex did not repeat pytest. It supersedes
the earlier post-edit sandbox attempt that stalled during Windows Proactor
`TestClient` startup. The Starlette warning remains unchanged and did not prompt
a dependency update.

## Judge Demo and PostgreSQL E2E follow-up — 2026-10-09

Repository configuration was inspected before execution:

- `frontend/playwright.config.ts` runs the Judge Demo suite with
  `reuseExistingServer: false`, starts the demo seed/API and Vite, and gives the
  backend a unique `runtime/demo-e2e-<timestamp>.sqlite3` path. The command used
  `.venv-test-20261009` through `ORGANIZATIONAI_TEST_PYTHON`; database URL
  variables were unset.
- Playwright test discovery passed and listed **5** cases. The actual run seeded
  all 8 configured demo scenarios in its new SQLite file, then its health check
  repeatedly failed with `connect EACCES 127.0.0.1:8008`. No browser test body
  ran. The newly created SQLite file was removed after stopping the attempt;
  pre-existing runtime databases were left untouched.
- The PostgreSQL Auth E2E config expects the API on `localhost:8010`, Vite on
  `localhost:5173`, `AUTH_WORKFLOW_AI_PROVIDER=MOCK_VLM`, and seeded local Auth
  users. The repository's CI draft migrates a disposable PostgreSQL 16 service
  to head `20261009_08`, checks the idempotency index, seeds those users, then
  runs `auth-live.spec.ts` against that same disposable DB. The SQLite migration
  pytest is not PostgreSQL evidence.
- PostgreSQL/Auth E2E did not run in this sandbox: Docker CLI is present but
  Docker Engine access returned permission denied for
  `dockerDesktopLinuxEngine`; `psql` and `pg_ctl` are absent, and
  `DATABASE_URL` / `TEST_POSTGRESQL_DATABASE_URL` are unset. The isolated Python
  environment imports `psycopg`. No PostgreSQL database was contacted. The default local
  Playwright Chromium cache was absent, so an external run may need
  `npx playwright install chromium` first.

PowerShell commands for an external run, including a disposable PostgreSQL
container, are provided in the current handoff. No CI workflow was activated or
pushed, and no live DB, existing runtime SQLite file, dependency, or sandbox
setting was changed.

## User-run PostgreSQL Auth E2E update — 2026-10-09

The user reports running `scripts/run-auth-postgres-e2e.ps1` from Windows
PowerShell outside the Codex sandbox. This supersedes the earlier “not run”
status above for PostgreSQL migration, temporary Auth seed verification, and
Auth browser E2E:

| Gate | User-reported result | Scope of evidence |
|---|---|---|
| PostgreSQL migration | **PASS** — Alembic head `20261009_08` and unique draft idempotency index verified | A temporary isolated PostgreSQL container; not SQLite and not a live database. This verifies migration to head on the test database, not preservation while upgrading a populated pre-migration database. |
| Temporary Auth seed | **PASS** — configured Maker and Checker accounts verified active with expected roles | Seeded only in the temporary PostgreSQL database. No password or token is recorded. |
| Auth browser E2E | **PASS** — 2 passed in 11.0s; 0 skipped, 0 unexpected, 0 flaky | The configured provider was `MOCK_VLM`. Tests exercise the Maker → Checker reject → revise/resubmit → approve workflow, preserved version/evaluation history, and read-only listing of retained synthetic plans. |

This Auth run is **not evidence of real AI inference or AI auto-approval**. Its
provider was `MOCK_VLM`, and the workflow waits for human review. The earlier
Verify runs that exercised the real Decision Policy/Budget Rules code used
synthetic model observations and remain separately classified as mock-backed
rule-path evidence.

The successful run's original Playwright JSON and process logs were not
available to recover: the script version used for that run removed its TEMP
run directory on success. The user-reported counts and scope are preserved as
a sanitized summary at
[`evidence/auth-postgres-e2e-user-reported-2026-10-09.json`](evidence/auth-postgres-e2e-user-reported-2026-10-09.json);
that file is not represented as the original Playwright report. The script is
now prepared to redact generated credentials, database URLs, authorization
values, and JWT-shaped strings and archive the actual JSON/log files under
`docs/integration/evidence/auth-postgres-e2e/<run-id>` before deleting TEMP on
a future successful run. No E2E was rerun for this documentation/artifact
retention update.

The script's success cleanup targets only its unique
`organizationai-auth-e2e-<run-id>` temporary container and then removes its
TEMP directory; it does not name or stop the three existing application
containers. Docker Engine access from this sandbox returned permission denied,
so the external post-run container list could not be independently queried.
No existing container or volume was targeted or modified by this work.

## Remaining gates after the user-run E2E

- **Challenge A — verified:** backend pytest (**305 passed, 84 subtests, 1
  warning**, user-run outside the sandbox); Judge Demo E2E (**5 passed in
  16.5s**, user-run against its temporary SQLite setup); general/escalation/
  regression Verify (**4/4, 5/5, 15/15**, synthetic `MOCK_VLM` outputs); Auth
  E2E and migration/seed checks above. The [evidence matrix](scope-1-review-2026-10-09.md#latest-evidence-matrix-2026-10-09)
  and [Verify case report](verify-run-2026-10-09.md) contain the updated records.
- **Challenge A — still unverified:** Local VLM inference, Media Compliance
  model evaluation, and Strategy model evaluation on fresh synthetic image/
  plan data; model quality/calibration; a separately sourced and frozen
  independent holdout; live submission URL availability; official Sprint 1
  submission hash/tag; current remote PR/branch state; and the required video,
  five-slide deck, and verified development log.
- **Policy gate:** Auth/live auto-approval remains disabled until policy,
  budget/authority, Media rules, Strategy rubric, and model configuration are
  approved. The present mock-backed rule tests do not satisfy that approval or
  real-inference gate.
- **Scope Phase 1 — deferred/not complete:** employee/account and role
  administration, full Checker assignment/configuration, business-approved
  SLA/retry settings, notifications, and policy/budget/rubric administration
  screens remain incomplete or awaiting PO/stakeholder decisions. These
  administrative/SLA features were not expanded in this update.

The temporary PostgreSQL run did not test migration data preservation from an
earlier populated schema, and it did not contact or write to a live database.
No commit, push, merge, deploy, or database write outside the disposable test
database was performed.
