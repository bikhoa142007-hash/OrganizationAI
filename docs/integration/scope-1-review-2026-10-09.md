# OrganizationAI Challenge A and Scope 1 review — 2026-10-09

## Status

**PARTIAL.** This is a local review and implementation checkpoint, not a claim
that Challenge A, Sprint 1, or the pending-approval Phase 1 baseline is complete.
The Phase 1 scope document remains a baseline awaiting PO/stakeholder
confirmation. Changes described as made on 2026-10-09 are after the Sprint 1
submission date and are not part of a verified 2026-09-22 submission.

The review uses the attached Role 1 Challenge A brief, `AGENTS.md`,
`docs/scope-phase-1.md`, `docs/sprint-1-deliverables.md`, the 2026-10-03 and
2026-10-09 progress reports, and the existing role, workflow, AI, policy,
deployment, Verify, and packaging documentation. The brief itself is at
`docs/role1/archive/v2.1/legacy/Role1_Marketing_Escalation_Referee.pdf`.

## Local history and environment evidence

- Checkout: `codex/scope1-phase1-20261009`, HEAD `6ba137c0e5d57ad924754cb0949b92def3655299`.
- `199e97f` is an ancestor of `6ba137c`; the branch and its local `origin/` tracking ref point to the same HEAD. No branch switch, reset, stash, rebase, amend, commit, tag, or history rewrite was performed.
- The local `origin/main` tracking ref is PR #16 merge `29ec6236a5895661aea6707ef642941b824fe6e7`; local `main` is at `797b14dc5c3c00370242a52b040bb8a49d4f13ae` and behind that tracking ref by 9 commits. Current `HEAD` is 7 commits ahead of local `origin/main`; it is not itself a merge commit. Thus PR #16's merge is present in the local history, but no newer merge such as a PR #20 merge is recorded in these local refs. No local tags are present, so the official Sprint 1 submission hash/tag is **not verified**. The 2026-09-22 packaging report calls `c1288c9…` its verification baseline, explicitly not a release commit or official submission tag.
- A remote read/fetch could not be completed because DNS resolution for `github.com` failed. Read-only GitHub page retrieval also failed (cache miss/unavailable URL). PR #20, public-site availability, and the remote branch's current state are therefore **not verified in this run**. The 2026-10-09 progress document records an earlier report that PR #20 was open; that is historical local documentation, not a fresh remote check. GitHub CLI was unavailable.
- Repository stack remains FastAPI/Python, SQLAlchemy/Alembic, SQLite for Judge Demo, PostgreSQL for Auth, and React/TypeScript/Vite with npm. Pytest, Vitest, and Playwright are the configured test runners. Frontend has no standalone lint script.
- The checked-in `.venv` points to a missing Python 3.13 installation and cannot start. A separate ignored `.venv-test-20261009` was created with local Python 3.12; installation stopped because the package index DNS request for `rfc8785` could not resolve. The old `.venv` was not changed. Docker CLI exists, but its daemon pipe returned permission denied. No PostgreSQL client/service or usable Local Ollama service was available. No `DATABASE_URL` was present.
- No database migration, seed, live plan, account, AI inference, or external service write was performed. The incomplete test environment is ignored by `.gitignore`; it is not a runtime database.

## Requirement traceability

| Requirement | Basis | Code/evidence in this checkout | Fresh verification in this run | Gap/status |
|---|---|---|---|---|
| Public judge route without Auth; keep Auth-first for business | Challenge A and Phase 1 | `/demo/*` uses the separate Judge Demo and shared demo actor; `/workflow/*` retains Auth cookie workflow. Frontend actor label now says demo actor, not authenticated session. | Frontend tests/build pass; no browser E2E or live URL check. | **Implemented in source; runtime not freshly verified.** Demo header actor is demo-only, not a real identity provider. |
| Verify chung: one action, 4 cases, at least one escalation | Challenge A | `general` runs the first four `verify-inputs.json` inputs; expected mix is three routine and one factual escalation. API returns actual/expected rows. | New backend test authored, but backend could not collect/run. | **Implemented locally; backend result unverified.** |
| Verify → Escalation: 5 cases, 3 routine + 2 escalations | Challenge A | `escalation` executes all five Verify inputs and checks actual persisted observation against a separate expected oracle. | New backend test authored; not executed. | **Implemented locally; backend result unverified.** |
| At least 15 synthetic regression cases across routine, fact, policy, authority and hard-violation boundaries | Challenge A and Role 1 package | `regression` runs all 15 ground-truth inputs. Fixture documentation identifies the synthetic data and categories. | New API regression test authored; not executed. | **Catalog exists; independent/blind holdout status is not established.** These are development regression fixtures, not a model benchmark. |
| A click performs fresh processing; no seeded or canned PASS | Challenge A | Runner creates a new `ApprovalRepository(':memory:')` per input and runs `ApprovalWorkflow`. It sends only the input to execution and loads expected values after execution. UI sends a fresh idempotency key per run. The canned Verify mock data/service was removed; mock service now errors rather than fabricating results. | Vitest passes; API/backend run not available. | **Source supports the requirement; fresh backend execution is unverified.** API replay for a reused idempotency key remains cached in process as intended. |
| Decisions must not depend on fixture names/IDs | Challenge A | Runner passes the case input—not the fixture envelope, id, or expected oracle—to `execute_input`/provider. Actual results are produced before oracle comparison. | Source review only because Python backend could not run. | **Implemented in source; backend test unverified.** |
| Verify provider and rule-engine provenance | Sprint/AI boundaries | `src/verify/runner.py` passes only `case['input']` to `execute_input`; it loads the expected oracle after all executions. `BAMockProvider` consumes the synthetic input's pre-authored `agent_outputs`. `ApprovalWorkflow` and the deterministic `Decision Policy Engine` evaluate/persist the result. | Source review; no Python runtime available. | **Rule engine is real application code; VLM, Media and Strategy outputs in these Verify suites are synthetic mock evidence. No model inference is exercised.** |
| Fresh plan input outside the fixed Verify catalog | User request 2026-10-09 | Added an API integration test that creates two random-ID plans with new titles and distinct budgets, then checks the real `BUDGET_LIMIT` rule result (`PASS`/`FAIL`) while identifying `MOCK_VLM`/`mock-1`. The Demo policy keeps both plans in Human Review. | Test authored, not executed because Python dependencies are unavailable. | **Custom-input path and deterministic rule behavior have not been runtime verified. Model evidence remains mock.** |
| Show expected/actual, pass/fail, timestamps, reason, evidence, policy/model and audit references | Challenge A | API mapping and Verify detail panel display the submitted payload, evidence, escalation question, policy/model version, audit event IDs and outcome. Missing questions for a human-review result are shown as a failed verification. Question evidence references are now displayed. | Verify component/service tests and typecheck pass; no browser run. | **UI implemented locally; full API/E2E unverified.** |
| Every escalation asks a contextual answerable question, with disputed fact/rule/evidence | Challenge A and structured workflow contract | Backend observation returns escalation records; Verify maps fact, applicable rule/limit, reason and evidence references. | UI unit test covers question and evidence reference; existing backend tests cover generated facts. | **Source exists; fresh backend execution unverified.** |
| Checker can approve/reject, override with reason, preserve audit/history; no AI auto-rejection | Challenge A, Sprint rules | Auth workflow requires override and rejection reasons, preserves versions/rounds, and AI routes hard violations to Human Review. Sprint rules prohibit AI auto-rejection. | Existing tests cover these rules; not runnable in this environment. | **Implemented in source, tests not freshly executed.** |
| Auto-approval only for a fully approved policy/configuration | Sprint 1 and Phase 1 | Auth defaults disable auto-approval when approved business budget/authority config is missing. Judge Demo uses separate synthetic settings. | Static review; Python tests and model integration unavailable. | **Auth/live remains disabled. Judge settings and thresholds are synthetic; they are not business-approved.** |
| Case entry for a judge, isolated from Auth/PostgreSQL | Challenge A | Verify links to `/demo/plans/new` through the Maker demo workflow, whose storage is separate from Auth/PostgreSQL. | Route/UI tests pass; browser E2E and DB fingerprint comparison not run. | **Entry path exists in source; end-to-end use not freshly verified.** A custom plan is a regular demo workflow plan, not appended to the fixed 15-case catalog. |
| Complete Phase 1 Maker/Checker workflow, immutable snapshots, private media, roles, audit | Phase 1 and Sprint 1 | Auth workflow, assignment, private attachment authorization, versions, approval rounds, idempotent decisions and audit exist. GET plan/list do not invoke stale recovery. | Existing backend tests cover the invariants; none executed now. | **Source implemented; runtime verification is blocked.** |
| Explicit stale-run recovery and 4-minute threshold | 2026-10-09 checkpoint and workflow docs | Recovery is an explicit assigned-Checker POST scoped to the active plan/round. Code default is 240 seconds. Docs record a 190-second max configured AI run and 240-second recovery allowance. A test checks early read/no side effect, stale recovery, replay safety, and late inference. | Source/test review only. | **No business SLA basis is documented.** The 240 seconds is a technical recovery threshold (50 seconds beyond the stated maximum run), not a PO-approved SLA. Test boundary not run here. |
| Admin read scope and attachment protection | Phase 1 and 2026-10-09 checkpoint | Admin list/detail and audit are read-only; attachment access remains limited to Maker/assigned Checker. | Tests exist; not executed now. | **Source implemented; fresh authorization tests blocked.** Employee/role administration remains a gap. |
| Draft creation idempotency: retry, changed payload conflict, Maker isolation, concurrency | 2026-10-09 checkpoint | Migration `20261009_08` adds a Maker/key unique index and request hash. Same request replays; changed request conflicts. Tests cover replay/conflict. | SQLite migration tests exist; no dedicated PostgreSQL test or fresh run. | **Implementation exists; concurrent draft-create coverage and PostgreSQL migration/data-preservation verification are not established by the inspected tests.** Do not treat the current SQLite migration test as PostgreSQL evidence. |
| Zero/nonnegative budget and self-approval | Phase 1 and Sprint rules | Auth submission accepts zero and rejects negative; multi-role Maker cannot approve self. | Tests exist; not executed now. | **Source implemented; fresh backend test unavailable.** |
| Reject → edit → resubmit keeps old version/round/result | Sprint rules | Auth workflow creates the next immutable version and round and preserves prior history. | Integration tests exist; not executed now. | **Source implemented; full flow not freshly executed.** |
| Local VLM v2 contract and separate evaluations | Sprint/AI boundaries and Role 1 package | Adapter extracts per-image evidence, confidence, object labels and technical quality; Media and Strategy are separate; model/config snapshots and attachment hashes are persisted. Confidence values are self-reported, not calibrated. | Tests and 2026-10-02 records exist in repository, but no Python suite or Ollama inference could run in this turn. | **Partial.** Real Local VLM/Media/Strategy runtime and v2 compatibility tests are not freshly verified. No external model was used. |
| SLA, notifications, employee/role admin, Checker defaults, Admin policy/budget/rubric config | Phase 1 draft | Existing docs identify these gaps; Phase 1 baseline is pending PO/stakeholder confirmation. | Source/docs review. | **Not implemented as a complete Phase 1 feature set.** Do not invent duration, retry limits, role matrix, budget cap, rubric anchors, policy content or notification channel. |
| Submission package: live URL, public repo, ≤3-minute video, 5 slides and development log | Challenge A | Repository URL is supplied by user. Earlier reports document a public demo URL and missing deck/video; no fresh remote/deployment access. Local files include scope reports and Role 1 package docs. | Local artifact inventory found no `.pptx` or video file; remote pages were inaccessible to Git/web fetch. | **Submission artifacts are incomplete/unverified.** No official submission hash/tag was found. The local progress reports are not a verified development journal. |

## Verification run in this turn

| Command/check | Result |
|---|---|
| `npm run test` (from `frontend/`) | PASS after final UI edit: 12 files, 58 tests, using the thread-pool default in `frontend/vitest.config.ts`. |
| `npm run typecheck` (from `frontend/`) | PASS after final UI edit. |
| `npm run build` (from `frontend/`) | PASS after final UI edit; Vite transformed 1,917 modules. |
| Python AST parse for `src/verify/runner.py`, `src/backend/api/app.py`, and `tests/integration/test_http_api.py` | PASS for syntax only; this is not backend test evidence. |
| `git diff --check` | PASS on final working tree. Git reports configured LF-to-CRLF working-copy warnings. |
| `python -m pytest -q` using original `.venv` | BLOCKED before collection: broken Windows Store Python target; `.venv` unchanged. |
| New isolated `.venv-test-20261009` install | BLOCKED: package index DNS failure downloading `rfc8785`; no project test dependencies completed. |
| `.venv-test-20261009\Scripts\python.exe -m pytest -q` | BLOCKED before collection: `No module named pytest`. |
| Verify `general` CLI | BLOCKED before suite execution: `No module named rfc8785`; 4 expected rows, 0 actual rows. |
| Verify `escalation` CLI | BLOCKED before suite execution: `No module named rfc8785`; 5 expected rows, 0 actual rows. |
| Verify `regression` CLI | BLOCKED before suite execution: `No module named rfc8785`; 15 expected rows, 0 actual rows. |
| `npm run test:e2e` using `ORGANIZATIONAI_TEST_PYTHON=.venv-test-20261009\Scripts\python.exe` | BLOCKED before browser tests: Playwright launched the separate interpreter, but backend seed failed at import with `ModuleNotFoundError: No module named 'rfc8785'`. No E2E DB or plan was produced. |
| Docker/PostgreSQL/Verify backend/Local Ollama | NOT RUN: Docker daemon access denied; no PostgreSQL service; Python dependencies incomplete; no Local Ollama server. No test database was created. |
| GitHub/PR state | NOT VERIFIED: remote lookup failed DNS; no fetch or write occurred. |
| Workflow draft syntax validation | Manual review only; no Ruby, PyYAML, Node YAML parser, or actionlint was installed. Not executed or activated. |
| CI configuration | Drafted `.github/workflows/verify.yml` in the working tree. It defines backend pytest, all three Verify runners with case-level expected/actual JSON output, frontend checks, Judge Demo E2E, and Auth E2E plus migration against a disposable PostgreSQL service. | **Not executed or activated. Review the uncommitted workflow before any push.** |

## Data and history safeguards

No live or restored SQLite/PostgreSQL data was opened for write, seeded, reset,
or deleted. No migration was executed. No model call, external service update,
commit, push, PR operation, merge, or deployment occurred. The new venv contains
only incomplete test dependencies and is ignored. Existing user data and Git
history remain in place.

## Verify provenance and independent evaluation

The 15-case synthetic regression catalog has been used during implementation
and is a development regression set, not an independent holdout. The same
limitation applies to the 4-case and 5-case Verify suites. Fixture IDs, names,
and expected output are outside the execution call; synthetic `agent_outputs`
are intentionally inside the test input because the provider is a mock. The
rule engine and budget calculation are actual application code, while the
VLM/Media/Strategy evidence is authored mock data. This is a rule-engine
contract check, not a real-model quality evaluation.

An independent set has **not** been created or evaluated: no independent source
or curator has been selected, and creating expected labels from this same
implementation context would not establish independence. Before claiming a
holdout, select an independent source/curator, author cases from that source
without reusing the current Verify fixture catalogs, stratify across routine and decision
boundaries, seal inputs and expected labels before execution, record the source
and selection procedure, and record the UTC evaluation time plus the frozen
code revision. The source, procedure, time, and frozen revision are all
currently **not established**.

The new custom-plan test is a separate, non-catalog smoke case, not a holdout.
It varies budget from 50,000,000 VND to 150,000,000 VND while using unrelated
random UUIDs and titles; the assertions expect the deterministic budget rule to
change from PASS to FAIL. Its runtime result remains **not run**.

## Remaining decisions and next safe work

1. Keep the Auth/live auto-approval policy disabled until an owner approves the
   applicable budget/authority source, policy content, Media rules, Strategy
   rubric anchors/weights, and model/provider configuration.
2. Confirm whether the Phase 1 pending baseline is accepted, then set actual
   employee/role authority, default Checker behavior, SLA and retry values,
   notification requirements, and Admin configuration responsibilities.
3. Provide a disposable PostgreSQL test service or working local Docker daemon
   to run migration upgrade/data-preservation and backend/E2E gates without
   touching a live database.
4. Obtain a working isolated Python dependency source/environment and run pytest,
   the 4/5/15 Verify suites, and Playwright against a new temporary SQLite DB.
5. Establish whether the existing 15-case catalog is accepted as the published
   regression set or whether a separately held-out synthetic set is required.
6. Confirm official Sprint submission ref/hash/tag and the current PR/branch
   state remotely; create/review missing slide, video, and development-log
   artifacts only from verified source materials.
7. Review `.github/workflows/verify.yml`. It uses a disposable CI PostgreSQL
   service and explicit MockVLM for Auth E2E; it has no deployment job. Do not
   push or enable the workflow until it is approved.

## Proposed Git actions — not performed

After local gates pass and the remote branch/PR are freshly checked, propose one
reviewable commit on `codex/scope1-phase1-20261009`, for example:

```text
feat(verify): add evidence-backed escalation suites
```

The commit would contain this turn's Verify/UI/API/test/documentation changes,
not the ignored test environment. Then push only if the remote branch is a
fast-forward of the verified local history and update the existing PR if it is
still the intended review target. Do not create a second PR until remote state
is known. No deployment is proposed until PostgreSQL, approved production
configuration and an explicitly identified staging target are available.

## Later verification addendum — 2026-10-09

This addendum supersedes earlier statements in this report that backend tests
and Verify were blocked by missing Python dependencies. Dependencies are now
present in the user-designated `.venv-test-20261009`. `pip check` passed;
pytest 9.1.1 and rfc8785 0.1.4 imported. DB URL variables were unset for the
test processes, the tests do not auto-load `.env`, and Verify cases ran against
in-memory repositories.

| Gate | Latest result | Evidence / limitation |
|---|---|---|
| Full backend pytest | **INCOMPLETE / environment stall** | Collected 302; first 38 passed. Reproducibly stalled at the first Auth `TestClient` case when AnyIO creates its Windows Proactor socketpair. No assertion failure observed. |
| Verify oracle/ID tests | **PASS** | `tests/unit/verify`: 11 passed, including oracle-field rejection and ID/title/filename invariance. |
| Verify general | **PASS 4/4** | Actual runtime decisions matched expected rows. |
| Verify escalation | **PASS 5/5** | Actual runtime decisions matched expected rows. |
| Verify regression | **PASS 15/15** | Used during development; regression evidence only, not an independent holdout. |
| Fresh input outside fixture catalog | **PASS, synthetic smoke** | Two newly authored inputs and a new PNG. Contradictory title labels did not steer decisions; the real deterministic budget rule routed 1,500,000 VND over a 1,000,000 VND limit to Human Review, even while mock advisory budget output said `IN_LIMIT`. All model-facing observations were synthetic. |
| Judge Demo browser E2E | **BLOCKED before browser tests** | Playwright seeded a unique temporary SQLite DB, then its health probe returned `connect EACCES 127.0.0.1:8008`. The sandbox loopback restriction prevented webServer readiness. |
| Auth browser E2E | **NOT RUN** | Requires isolated PostgreSQL, seeded test identities/password and local browser networking. |
| PostgreSQL migration | **NOT RUN** | No local PostgreSQL binaries/service. Docker CLI exists; Docker Engine named pipe access is denied. SQLite migration tests are not treated as PostgreSQL evidence. |
| Remote GitHub/PR comparison | **NOT REFRESHED** | Earlier DNS failure to `github.com` still prevented fetch; no history mutation was attempted. |
| CI workflow validation | **DRAFT FOR REVIEW** | `.github/workflows/verify.yml` targets ephemeral CI PostgreSQL and Mock Auth E2E, but no YAML parser is installed; manual review only. Uncommitted and inactive. |

The Verify implementation was reviewed and tightened so the expected-results
file is loaded only after every application execution completes. `case["input"]`
is the only fixture payload passed to `execute_input`; fixture case IDs/names
are retained for reporting, and expected values/result labels are used only in
the post-execution comparison. `BAMockProvider` intentionally supplies
synthetic model observations which do affect the actual workflow. The
Decision Policy Engine and deterministic budget rules are real application
code. See [case-level expected/actual evidence](verify-run-2026-10-09.md).

The dependency installation issue is resolved. The remaining local blockers
are TestClient/loopback access in this sandbox and unavailable PostgreSQL
service access. No registry, sandbox, or permission setting was changed. No
live database, commit, push, merge, deploy, or administration/SLA expansion
occurred in this later verification pass.

## Auth failure follow-up — 2026-10-09

The user subsequently reported an external full pytest result of **2 failed,
300 passed, 84 subtests passed, 1 warning**. The two failures were traced to a
stale success fixture missing three required VLM v2 fields and an obsolete
expectation that Admin plan-list reads return 403. The fixture and tests now
match the existing schema and read-only Admin contract; API permissions and
validation were not relaxed. The authority matrix was corrected to match the
current runtime contract.

After these edits, the new/matching VLM unit tests passed **12/12**. The focused
Auth integration group stalled before its first test body in `TestClient`.
The attempted full suite completed 38 tests and then stalled at Auth `TestClient`
startup; the traceback points to Windows Proactor `socketpair()` / `accept()`
in AnyIO. Therefore the post-change Auth tests and full suite remain unverified
inside this sandbox. The external PowerShell rerun command and detailed
failure-by-failure evidence are in the [progress report](scope-1-progress-2026-10-09.md#auth-regression-follow-up--2026-10-09).

## User-run backend result — 2026-10-09

The user reports the post-fix full backend pytest completed outside the Codex
sandbox using `.venv-test-20261009`: **305 passed, 1 warning, 84 subtests
passed in 59.20s**. This supersedes the sandbox-stalled attempt above; Codex
did not rerun pytest. No dependency was changed for the warning.

The Judge Demo Playwright configuration discovered 5 tests, then its run seeded
8 scenarios into a newly generated timestamped SQLite DB and stalled at the
backend health check with `connect EACCES 127.0.0.1:8008`; no browser test ran.
That DB was removed; earlier runtime DBs were preserved. PostgreSQL Auth E2E and
migration remain unrun because Docker Engine access is denied in the sandbox and
no local PostgreSQL service/client is available. The latest Alembic head is
`20261009_08`; the project CI draft specifies disposable PostgreSQL 16 for the
migration and Auth E2E. Exact outside-app PowerShell steps are in the handoff.

## Latest evidence matrix: 2026-10-09

This matrix supersedes earlier “blocked/not run” entries where the latest
evidence is a user-reported run outside the Codex sandbox. The original
Challenge A / Phase 1 traceability matrix above remains the requirement source;
this table records current verification provenance and its limits.

| Gate / requirement | Latest result and source | What this verifies | Still not established |
|---|---|---|---|
| Backend regression suite | **PASS — 305 passed, 84 subtests passed, 1 warning in 59.20s.** User-run with `.venv-test-20261009` in external PowerShell. | Backend test suite completed without a hang in that run. | Real model behavior, PostgreSQL migration semantics, and production deployment. |
| Challenge A Judge Demo E2E | **PASS — 5 passed in 16.5s.** User-run outside the sandbox. | Browser path on the isolated Judge Demo configuration, which uses its separate temporary SQLite setup. | Auth database behavior, real model inference, or live-site availability. SQLite is not PostgreSQL migration evidence. |
| Verify chung / Escalation / regression | **PASS — 4/4, 5/5, 15/15.** Case-level actual/expected results are in [the Verify report](verify-run-2026-10-09.md). | The real Decision Policy and deterministic Budget Rules code executed against synthetic agent observations. Fixture IDs/names and expected values are post-execution reporting/oracle data. | VLM, Media Compliance, or Strategy model inference. The 15-case set is development regression data, not an independent holdout. |
| Auth PostgreSQL migration | **PASS — user-reported external PowerShell run.** Head `20261009_08`; unique index `uq_auth_workflow_plans_maker_creation_key` verified. | Alembic reached head and the expected index existed in the temporary PostgreSQL database. | Upgrade/data preservation from a populated prior schema; live database behavior. |
| Auth seed verification | **PASS — user-reported external PowerShell run.** Temporary seeded Maker/Checker accounts were active with expected roles. | The configured test identities matched database role assignments after seed. | Real employee/account provisioning or production identity configuration. Credentials were not retained. |
| Auth browser workflow | **PASS — 2 passed in 11.0s; 0 skipped, 0 unexpected, 0 flaky.** User-run outside the sandbox. | Auth login/session, Maker → Checker review, reject with reason, Maker revision/resubmission, V1/Round 1 to V2/Round 2 history preservation, final Checker approval, and read-only synthetic-plan listing. | This run used `MOCK_VLM`; it does not verify real AI inference or successful AI auto-approval. Auth/live auto-approval remains disabled. |
| Temporary test container cleanup | The script uses a unique `organizationai-auth-e2e-<run-id>` PostgreSQL container, `--rm`, and a targeted stop/fallback remove. Existing app container names are not targeted. | Cleanup behavior is present in the script; no existing app container or volume was modified by this work. | The external Docker post-run inventory could not be independently queried because Docker Engine access from this sandbox returned permission denied. |
| Original Auth JSON/log retention | **Unavailable for the reported run.** Its script cleanup deleted the successful run's TEMP directory before retention was added. A sanitized user-reported summary is saved at [the evidence JSON](evidence/auth-postgres-e2e-user-reported-2026-10-09.json). | The JSON records only the result supplied by the user and explicitly identifies itself as a summary. | It is not the original Playwright JSON or raw API/frontend logs. The script now archives redacted JSON/logs before TEMP cleanup on future successful runs. |

### Remaining gaps against Challenge A and Scope Phase 1

**Challenge A**

- Real Local VLM inference, Media Compliance model evaluation, and Strategy
  model evaluation remain unverified. The latest Auth E2E explicitly used
  `MOCK_VLM`; no AI inference or model-driven auto-approval is claimed.
- No separately sourced, independently curated, sealed holdout has been
  created. The existing 15-case set was used during development and is not an
  independent evaluation set.
- The Auth migration run verified a temporary PostgreSQL database at head and
  its unique index. It did not establish preservation while upgrading a
  populated database from a prior schema.
- Live URL availability, official Sprint 1 submission hash/tag, current remote
  branch/PR state, competition finalist status, and required video, five-slide
  deck, and verified development journal remain unverified or absent from the
  local evidence inventory.
- Real business auto-approval remains gated on approved budget/authority
  limits, content policy, Media rules, Strategy rubric and provider/model
  configuration. Auth/live auto-approval is still disabled.

**Scope Phase 1**

- Full employee/account and role administration, Checker assignment/default
  configuration, business-approved SLA/retry settings, notifications, and
  policy/budget/rubric administration are incomplete or awaiting PO/stakeholder
  decisions. The latest update did not expand administration or SLA scope.
- Phase 1 remains a draft baseline awaiting PO/stakeholder confirmation; test
  results do not constitute approval of unresolved business values.

**Evidence retention and cleanup**

- The raw JSON/logs from the completed user run could not be recovered. The
  evidence JSON is explicitly labeled as a user-reported summary, not a
  Playwright report. The Auth run script now copies its report and API/frontend
  logs through secret redaction to
  `docs/integration/evidence/auth-postgres-e2e/<run-id>` before TEMP cleanup;
  if archiving fails, it retains the run's TEMP folder. The tests were not
  rerun solely for this retention change.
- The script's cleanup is scoped to its unique temporary PostgreSQL container.
  Docker listing was denied in this sandbox, so the external container's
  post-run absence is not independently confirmed here. The three existing
  application containers (`organizationai-backend-1`,
  `organizationai-frontend-1`, `organizationai-db-1`) were not targeted or
  modified.

No commit, push, merge, deploy, live database write, or existing application
container/volume modification was performed.
