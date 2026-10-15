# Challenge A Public Judge: test policy and runbook

Status: implementation contract for the Challenge A Judge only. The automatic outcomes below apply only to isolated synthetic runs. They do not authorize production auto-approval or deployment.

## Scope and data boundary

- `POST /api/public/judge/runs` accepts only the server-owned `general` and `escalation` suite names. Case inputs and expected results stay in repository fixtures; the server runs the application workflow before comparing with the fixture oracle.
- Verify chung runs four cases: three expected automatic outcomes and one human-review case. Verify → Escalation runs five cases: three expected automatic outcomes and two human-review cases. Each case gets a new in-memory workflow/repository and a server-generated run id.
- `tests/fixtures/ba/v2.1/ground-truth-cases.json` is the 15-case reference catalog. Public requests cannot select individual cases, upload content, provide expected results, or configure policy/provider/model values.
- The suite runs use the repository's mock fixture provider path. `mode=MOCK` is mandatory evidence labeling; a passing assertion proves the workflow matched its synthetic oracle, not that real inference is accurate.
- The Judge router has no Auth dependency, actor namespace/header, Auth or shared demo database dependency, persistent result store, history endpoint, stop endpoint, or override endpoint. D mounted it in local candidate SHA `d6fb87c3068a61f127af32403d5ec4a4ad976e78`; this candidate state does not establish deployed/public acceptance.
- No public clock/admin controls or production workflow access are part of this work package. D's candidate preserves the existing CORS allowlist and adds a process-local request/concurrency gate for Judge POSTs only.

The existing `/demo/verify` route remains in Demo mode and continues to call `VerifyService`, including its 15-case regression suite; its `DEMO · MOCK` label disqualifies those runs as public acceptance evidence. D's local integration candidate `d6fb87c3068a61f127af32403d5ec4a4ad976e78` adds `/challenge-a`, which renders `VerifyDashboardPage mode="public"` and calls `publicJudgeService`. This is local candidate wiring, not a deployed public acceptance result.

## Public router contract and D boundary

- Router prefix is `/api/public/judge` in `src/backend/api/public_judge.py`. D's local candidate SHA `d6fb87c3068a61f127af32403d5ec4a4ad976e78` includes it in `src/backend/api/app.py` and adds the SPA route `/challenge-a` in `frontend/src/routes/AppRoutes.tsx`.
- `POST /api/public/judge/runs` accepts exactly `{"suite":"general"}` or `{"suite":"escalation"}`. The response contains a generated run id, suite status, `mode=MOCK`, `data_classification=SYNTHETIC`, timestamps/duration, summary, and per-case server expected/actual routes, PASS/FAIL/ERROR, input snapshot, evidence, questions, audit projection, and applied rule ids.
- `POST /api/public/judge/input-runs` accepts only the strict typed fields in `public_judge_schemas.py` (`title`, `department`, `objective`, `summary`, `target_audience`, `channel`, `currency`, `budget_vnd`, `source_budget_vnd`). It returns `mode=MOCK`, `processing_mode=DETERMINISTIC_INPUT_SIMULATION`, `USER_SUPPLIED_UNVERIFIED`, `NOT_MEASURED`, outcome/category/reason/question, timestamps, run id, and an immediate audit summary with input SHA-256. It persists nothing.
- Request and response schemas reject unknown fields. The router limits bodies to 16 KiB. Proxy/edge enforcement of a body cap has not been evidenced; confirm it before public deployment.
- The frontend sends `POST` with `Content-Type: application/json`, `credentials: omit`, no actor/auth/idempotency header, and `cache: no-store`. It sends no cookie and the router uses no Auth dependency or actor namespace.
- Errors follow `{code,message,correlation_id,http_status}`: `VALIDATION_ERROR` 422, `INPUT_TOO_LARGE` 413, `RATE_LIMITED` 429, `UNAVAILABLE` 503. Error responses do not include stack/provider text.
- D's candidate applies a process-local gate to Judge POSTs: 30 requests per rolling 60 seconds and at most 1 active POST per process. It does not partition by visitor/IP or trust `Forwarded`/`X-Forwarded-For`. Deployment instance/worker count has not been verified in this review and must be confirmed before public acceptance. Additional workers or instances have independent gates and increase aggregate capacity; this is not a distributed deployment-wide limit.
- The candidate keeps the existing `settings.cors_origins` CORS allowlist; no Auth CORS policy was expanded for Judge. The Judge client sends `POST` JSON with `credentials: omit` and no actor/auth headers. Do not loosen the shared allowlist to make this work.
- No stop/status/retry/override/admin/clock endpoints exist. Browser timeout means unknown completion, not cancellation.

## New-input simulation policy

Policy identifier: `JUDGE-INPUT-SIMULATION-1.0`. This deterministic simulation accepts a small allowlist of text and numeric fields. It is not submitted as a marketing plan and it does not invoke VLM or strategy inference. The department, channel, currency, and budget values below are synthetic Judge-only simulation assumptions explicitly approved by the user on 2026-10-14 for this test scope only. This is not PO sign-off, company policy, or production auto-approval. The endpoint is mounted only in D's local candidate; do not claim deployed/public acceptance or production auto-approval.

All submitted fields remain `USER_SUPPLIED_UNVERIFIED`; `quality_status` is always `NOT_MEASURED`. The response contains only an outcome, reason, contextual handoff question where needed, timestamp, input SHA-256, and an in-memory audit summary. The body, result, and provider output are not saved or logged. Do not enter confidential or personal data.

Rules run in this order:

1. If department is not `DEMO-DEPT-01`, channel is not `DEMO_SOCIAL` or `DEMO_EMAIL`, or currency is not `VND`, return `HUMAN_REVIEW_REQUIRED / POLICY_OUT_OF_SCOPE` with the fields that fell outside the simulation scope.
2. If `source_budget_vnd` is missing or differs from `budget_vnd`, return `HUMAN_REVIEW_REQUIRED / FACT_UNCERTAIN`. The reason and question explicitly treat both values as unverified and ask for an authoritative source; neither value is asserted as true.
3. If the two supplied budget values match and exceed 100,000,000 VND, return `HUMAN_REVIEW_REQUIRED / AUTHORITY_EXCEEDED` and ask an appropriately authorized Checker to confirm the applicable limit.
4. If scope matches, both budget fields are present and equal, and the value is at or below 100,000,000 VND, return `SIMULATED_AUTO_APPROVE`. This is a Judge-only simulation, not an approval or persistent business action.

The request body is limited to 16 KiB. Unknown fields, including fixture/oracle/provider/policy fields, are rejected. Per-field bounds are in `src/backend/api/public_judge_schemas.py`.

## Audit, timeout, and intervention behavior

- Fixed suites return each real in-memory run's action, timestamp, input hash, reason, expected/actual route, pass/fail, evidence references, and escalation question. The suite does not retain a server-side run record.
- New-input evaluation returns an `INPUT_EVALUATED` audit summary with completion timestamp, SHA-256 of canonical typed input, and reason. That summary is delivered in the immediate response only; no persistent audit/history exists for this public input path because the approved data contract forbids retention.
- The Challenge A acceptance criterion requires intervention, stop, and override behavior to follow the contract and forbids claiming that irreversible effects were undone. This public Judge contract supports escalation only as a handoff recommendation; it does not expose a human decision, stop, status, retry, or override endpoint. A browser timeout or disconnect means unknown completion, not cancellation. The Judge simulation has no production side effects, and this route cannot claim cancellation, reversal, or Checker override. The authenticated product Checker workflow is separate and is not reachable through this public Judge route.
- Standard public errors use `{code, message, correlation_id, http_status}` and do not include stack traces, submitted field values, or provider text.

## Local verification

Use the isolated worktree and local dependencies. Do not point this runbook at a live database or configure a real provider.

Backend synthetic tests:

```powershell
python -m pytest tests/unit/verify/test_public_judge.py tests/unit/verify/test_harness.py -q
```

Frontend focused unit tests:

```powershell
cd frontend
npm run test -- src/pages/VerifyDashboardPage.test.tsx src/services/publicJudgeService.test.ts
```

For local candidate acceptance on D's mounted `/challenge-a`, use a disposable environment and record the candidate SHA. This local evidence does not qualify as deployed/public acceptance:

1. Open the public Judge entry in a fresh browser context with no account, cookie, or demo actor.
2. Confirm the first instruction is one sentence and the first action runs general Verify once.
3. Confirm general has 4 timestamped results and escalation has 5; compare actual vs server expected. Confirm escalation has 3 automatic and 2 human-review outcomes with case-specific questions.
4. Enter new allowed values, then vary source budget, department/channel/currency, and budget limit. Confirm `FACT_UNCERTAIN`, `POLICY_OUT_OF_SCOPE`, and `AUTHORITY_EXCEEDED` each arise from entered values, with `USER_SUPPLIED_UNVERIFIED`, `MOCK`, and `NOT_MEASURED` labels.
5. Confirm no Auth cookie/header is sent, request bodies are never retained, no stop/admin/clock route is exposed, and no production data is reachable.
6. If the browser request times out, report outcome unknown. Do not report that server work stopped or was undone.


Reproduce the integrated local browser run on the D candidate with the repository Playwright config:

```powershell
cd frontend
npm run test:e2e -- --config playwright.config.ts e2e/public-judge.spec.ts
```

Use only the config's disposable local demo database and mock providers; do not set production DB/provider values.

Do not perform public acceptance on a deployment until D supplies the deployed SHA and confirms the isolated environment, request quota, concurrency limit, and deployment profile. A local or historical test result is not public acceptance evidence.

## Prior integration source baseline (2026-10-14; SHA b5c5dba82e3455f46837424e4f9061cb609daf26)

- D supplied source candidate `b5c5dba82e3455f46837424e4f9061cb609daf26` as the current comparison baseline. Its ancestry from frontend-live baseline `425b417309c7a9db5ee2bd71a74f5cdad6704178` was verified. The Judge worktree remains on its existing branch; no reset or rebase was performed.
- Relative to `425b417`, D-owned shared wiring changes include `src/backend/api/app.py` and `frontend/src/routes/AppRoutes.tsx`. The Judge package in the candidate includes `src/backend/api/public_judge.py`, `src/backend/api/public_judge_schemas.py`, `frontend/src/services/publicJudgeService.ts`, `frontend/src/pages/VerifyDashboardPage.tsx`, `tests/unit/verify/test_public_judge.py`, and this runbook. Do not edit the page or stylesheet while collaborator UI ownership remains unresolved.
- The `public_judge.py`, schema, service, page, and test file contents in `b5c5dba` match the corresponding Judge snapshots at code/test commit `e053237d56c86a81156a3122e93331ee0abd14f9`; this runbook matches docs commit `45854e7782e94a59b716706dce1ac0772838f52f`. Those local commit SHAs are not ancestors of `b5c5dba`; this is a read-only content comparison, not a rebase.
- Backend test evidence on the matching Judge code snapshot: `tests/unit/verify/test_public_judge.py` and `tests/unit/verify/test_harness.py` reported 10 passed with two Starlette/httpx deprecation warnings. The event-loop regression failed against the synchronous call and passed after the threadpool offload.
- Browser evidence below belongs to prior candidate `d6fb87c3068a61f127af32403d5ec4a4ad976e78`. The diff from `d6fb87c` to `b5c5dba` includes the threadpool change and regression test, so the prior browser PASS does not verify the new source SHA. No E2E result tied to `b5c5dba` is recorded here.

## Prior D integration reference (2026-10-15; SHA 47c9374eda3b210d6939bba6f6791e870cec7715)

- D supplied `47c9374eda3b210d6939bba6f6791e870cec7715` as the latest local integration source reference. Read-only Git inspection verified ancestry from frontend-live baseline `425b417309c7a9db5ee2bd71a74f5cdad6704178` and that browser-tested source `9c7f5411745de4d4d4362992eb216d8e4dc346a8` is an ancestor. This is not a deployed SHA and does not establish public acceptance.
- D describes the changes after `9c7f541` as OPS/GOV audit-only commits. The read-only diff confirms no changes since `9c7f541` in `frontend/`, the public Judge router/schemas, Judge unit tests, Judge fixture, or this Judge runbook. The Judge branch remains separate and was not reset or rebased; it was at `df45d000200ad0075e0ac72a09cea9a994ca1b8c` before this documentation-only update.
- D's earlier local synthetic counts (workflow/config PostgreSQL `16/16`, SLA PostgreSQL `6/6`, APR-05/draft `15/15`, retry unit `23/23`) were reported for the prior `9c7f541` reference. No corresponding test report for `47c9374` was supplied, so those counts are not attributed to the latest SHA.
- The browser and focused Judge test evidence below remains tied to exact source `9c7f541`. Although the Judge/frontend paths are unchanged in the `9c7f541..47c9374` diff, no browser run was performed at `47c9374`; no deployed/public acceptance evidence is available.

## Local Judge browser evidence (2026-10-15; source SHA 9c7f5411745de4d4d4362992eb216d8e4dc346a8)

- Ran `frontend/e2e/public-judge.spec.ts`, test `public Challenge A runs isolated Mock suites and classifies new synthetic input`, from the D integration worktree at the exact SHA above. Playwright reported `1 passed (7.3s)`; its console-error assertion passed.
- The later D reference `47c9374` has no changes in Judge/frontend paths relative to this tested source. The result is still recorded only against `9c7f541`; it is not a test run at `47c9374`.
- Focused checks on the same source SHA also passed: `python -m pytest -q tests/unit/verify/test_public_judge.py tests/unit/verify/test_harness.py` reported `10 passed` with two Starlette/httpx deprecation warnings; `npm test -- src/pages/VerifyDashboardPage.test.tsx src/services/publicJudgeService.test.ts` reported 2 files and 9 tests passed.
- The disposable run used `APP_ENV=demo`, `MOCK_VLM`, a newly generated temporary SQLite file named `demo-*.sqlite3`, localhost ports 8008/5178, and a temporary Playwright output directory. It used no production DB/provider settings and made no public requests. The repo-local Python environment was selected with `ORGANIZATIONAI_TEST_PYTHON` because the D worktree has no `.venv`.
- The browser asserted the public page loads without an account, shows its first-step instruction, submits one general-suite request with no Authorization or Cookie header, reports `4/4 PASS`, then reports `5/5 PASS` for escalation. The screenshot shows three `AUTO_APPROVED` cases and two `HUMAN_REVIEW_REQUIRED` cases, with a per-run id and timestamps.
- The same browser run evaluated a fresh form input and then an unlisted channel; the latter returned `HUMAN_REVIEW_REQUIRED / POLICY_OUT_OF_SCOPE` with a specific transfer question. Separate backend unit coverage checks fact mismatch, out-of-scope channel, and budget over the simulation authority limit, and checks audit fields and epistemic wording.
- Visual review of this exact-SHA screenshot confirms a layout defect: the new-input fields and labels flow inline and overlap. Functional E2E passed, but the new-input form is not visually ready for public use. UI ownership remains with the collaborator; no UI file was changed.
- Screenshot retained as local temporary evidence at `%TEMP%\organizationai-judge-e2e-output-9c7-3686a7b9e6f24149b5599b389a343c5d\public-judge-public-Challe-954b8-ssifies-new-synthetic-input\challenge-a-public.png`. It contains only synthetic Judge data. The initial attempt stopped before app startup because its temporary database name did not match the required `demo-*.sqlite3` pattern; the corrected disposable run above passed.

## Challenge A brief acceptance gaps (local source 9c7f541; 2026-10-15)

| Brief criterion | Evidence at this source | Status / remaining gap |
| --- | --- | --- |
| Public entry without account; first instruction is actionable | Local `/challenge-a` browser run; page text and first instruction asserted; request had no Authorization or Cookie header | Local functional PASS. A deployed public URL/SHA has not been supplied. |
| Verify chung: one action, four cases executed in one Mock run, pass/fail and run timestamp | Playwright clicked `Run 4 cases`; response rendered per-run data; screenshot shows run id and timestamps | `4/4 PASS`, `MOCK` only. |
| Verify → Escalation: five cases, three automatic and two transferred | Same browser run and screenshot; expected/actual route and case result rendered | `5/5 PASS`, `MOCK` only; observed 3 automatic and 2 human-review outcomes. |
| New input; field-driven result rather than case-id/fixed result | Browser submitted a new form payload and changed its channel; unit cases vary fact match, policy scope, and authority fields | Local functional PASS for deterministic simulation. `quality_status=NOT_MEASURED`; this does not measure real AI inference. |
| Distinguish missing/uncertain fact, out-of-policy input, and exceeded authority | Unit assertions cover `FACT_UNCERTAIN`, `POLICY_OUT_OF_SCOPE`, and `AUTHORITY_EXCEEDED` separately | Local unit coverage PASS; only policy-scope transfer was exercised in the browser run. |
| Ask a concrete, contextual transfer question; do not treat flagged input as verified truth | Unit assertions check conflicting budget fields, ask for an authoritative source, include the unsupported channel/limit, and require wording that does not confirm either conflicting value | Local unit coverage PASS. Inputs and results remain `USER_SUPPLIED_UNVERIFIED`. |
| Audit action, time, input and reason | Input response contains `INPUT_EVALUATED`, timestamp, input SHA-256 and reason; fixed-suite rows return an audit projection | Present in the immediate response. No durable audit/history is implemented by this Judge contract. |
| Intervention/stop/override follows contract; do not claim irreversible work was undone | Judge returns `HUMAN_REVIEW_REQUIRED` with a concrete handoff question. It has no human-action, stop, or override endpoint; requests are ephemeral and no approval is committed. | PARTIAL: handoff guidance exists; a human response/control is missing on the public Judge route. A timeout is not a stop, and no undo is claimed. Product Checker controls are separate and are not reachable through the public Judge route. |
| Isolate Judge from production data/accounts and bound requests/concurrency | Local no-auth request assertion; isolated in-memory workflow per suite case; strict body limit and process-local request/concurrency gate documented in router contract | Local design evidence only. Proxy/edge body cap and deployed topology/quota have not been verified. |
| At least 15 dataset cases and policy consistent with behavior | Server fixture test asserts at least 15 unique case IDs; policy values and classifier behavior are documented and covered by input tests | Local unit coverage PASS; Mock fixture behavior only. |

The screenshot verifies functional behavior but also records the unresolved form layout defect above. This local source run is not public deployment acceptance; a deployed SHA and environment verification remain outstanding.

## Prior D local-candidate evidence (2026-10-14; SHA d6fb87c3068a61f127af32403d5ec4a4ad976e78)

- Candidate SHA: `d6fb87c3068a61f127af32403d5ec4a4ad976e78` (local integration candidate, not a deployed SHA).
- Playwright test: `frontend/e2e/public-judge.spec.ts`, test `public Challenge A runs isolated Mock suites and classifies new synthetic input`. Evidence artifact ID: `public-judge-public-Challe-954b8-ssifies-new-synthetic-input`; screenshot: `frontend/test-results/public-judge-public-Challe-954b8-ssifies-new-synthetic-input/challenge-a-public.png`.
- The browser run reports Verify chung `4/4 PASS`, Verify → Escalation `5/5 PASS`, routine synthetic input `SIMULATED_AUTO_APPROVE`, and out-of-scope input `HUMAN_REVIEW_REQUIRED / POLICY_OUT_OF_SCOPE`. The escalation run ID visible in the screenshot is `JUDGE-dec872c6b9944830941862f4332d0a43`.
- This evidence is local and `MOCK`: the suites use synthetic fixtures; custom input uses deterministic simulation, not VLM or strategy inference. `quality_status=NOT_MEASURED`; these results do not prove real-provider inference quality or deployed public behavior.
- Visual review of the screenshot found the new-input form fields flowing inline and overlapping because `.form-grid`/`.form-field` have no styles. Logic E2E passed, but visual acceptance is incomplete. Judge has not changed page or stylesheet files while UI ownership is being resolved.

## Readiness gaps recorded before D's 12539 integration (2026-10-15)

- The latest source reference is D candidate `47c9374eda3b210d6939bba6f6791e870cec7715`, descended from `425b417309c7a9db5ee2bd71a74f5cdad6704178`. It is not a deployed SHA and does not establish public deployment acceptance. The Judge worktree remains on its separate branch; no rebase was performed.
- The 30/60-second rate limit and one-active-POST gate are process-local/global among visitors on each process. Deployment instance/worker count has not been verified here; verify it before public acceptance and reassess aggregate limits for the deployed topology.
- The exact-source `9c7f541` local E2E and focused unit results are recorded above. D's later `47c9374` diff has no Judge/frontend changes, but browser behavior was not rerun at that SHA. Visual review shows the new-input form layout defect; UI edits remain pending file-level ownership clearance. This functional local evidence does not establish deployed/public behavior.
- A 16 KiB router body limit exists; proxy/edge body-cap evidence is still required before public deployment.
- No real provider inference or quality evaluation was run. Mock functional PASS is not a real-AI quality PASS.
- The immediate input response contains an audit summary and hash but no durable audit/history; retention needs a separately approved data contract.

## D baseline 12539 follow-up: Judge UI and acceptance audit (2026-10-15)

- D supplied integration baseline `12539b30eaaf74379508f5a5735ab338d0ea64ed`. Judge's local code commit is `2e6ce52a7742a16b0f260ed640d233a3f28ee961`, directly based on that SHA. It is not deployed. Only `VerifyDashboardPage.tsx`, its page-local CSS, and a responsive Playwright spec changed in the code commit.
- The UI fix replaces generic form classes with Judge-scoped classes; the new page-local CSS lays out fields in two columns on desktop and one column at widths up to 680 px, constrains controls to their field, and gives keyboard focus a visible outline. The regression spec checks field containment, label/control order, overlap, and horizontal overflow at 320, 768, 1024, and 1440 px.
- The exact three UI files in commit `2e6ce52` were SHA-256 compared with the three files in the populated disposable verification worktree; all matched. On that exact source content, Playwright reported `2 passed`: the public Judge workflow test and the layout test. The layout assertion reproduced red against the unstyled 12539 baseline (`display: block`, expected `grid`) and then passed after the fix. Screenshot evidence: `%TEMP%\organizationai-judge-layout-green-c13689ea835e47e39b4f912060008201\public-judge-layout-public-51602-s-desktop-and-mobile-widths\challenge-a-layout.png`.
- The public-run screenshot for the same disposable 12539-plus-UI verification is `%TEMP%\organizationai-judge-e2e-output-12539-f833e36ce82a43c6bcd5c4bfcdad581b\public-judge-public-Challe-954b8-ssifies-new-synthetic-input\challenge-a-public.png`; it contains only synthetic Judge data and shows the 4/4 and 5/5 Mock runs, case routes, run id, and timestamps.
- The same disposable UI verification environment reported 3 frontend test files / 33 tests passed, `npm run typecheck` passed, and `npm run build` passed with the existing Vite warning that a JavaScript chunk exceeds 500 kB. A fresh `npm ci --offline` in the new worktree could not complete because `xmlchars@2.2.0` was not in the local cache; the browser/unit/build evidence used an already populated disposable dependency tree. Backend tests were run again from the `12539` worktree using the repository's existing Python environment: `python -m pytest -q tests/unit/test_deployment.py tests/integration/test_public_judge_composition.py tests/unit/verify/test_public_judge.py tests/unit/verify/test_harness.py` → `33 passed, 2 deprecation warnings`.
- Browser checks used `APP_ENV=demo`, `MOCK_VLM`, a fresh temporary SQLite database, and localhost only. No production database/provider, real inference, public POST, or deployment was used. This is local functional evidence; real-inference quality remains `NOT_MEASURED`.

### Brief acceptance map at the local 12539-based candidate

| Challenge A criterion | Local evidence / exact capability | Status and remaining gap |
| --- | --- | --- |
| Public entry without account and one actionable first instruction | Browser loaded `/challenge-a` without an account, asserted the first-step instruction, and sent no Authorization/Cookie header. | Local functional PASS only. D reports its read-only live check found `/challenge-a` not found and no separate Judge API service; Judge did not independently repeat that check. No deployed SHA/URL was supplied. |
| Verify chung: one action, four cases, pass/fail and a real run timestamp | Browser ran the server-backed synthetic suite once; the response and screenshot contain run id, timestamps, and per-case status. | Local `4/4 PASS`, `MOCK`; not real inference. |
| Verify → Escalation: five cases, three automatic and two transferred | Browser ran the synthetic escalation suite; the response and screenshot show the route counts and contextual questions. | Local `5/5 PASS`, `MOCK`: 3 simulated automatic outcomes and 2 human-review handoffs. |
| New input drives results, rather than case-ID/fixed output | Browser changed user-supplied fields, including an unlisted channel; deterministic input rules returned an out-of-scope handoff. | Local functional simulation PASS. It is not VLM/strategy inference; `quality_status=NOT_MEASURED`. |
| Distinguish missing/uncertain fact, out-of-policy input, and exceeded authority | Unit tests separately assert `FACT_UNCERTAIN`, `POLICY_OUT_OF_SCOPE`, and `AUTHORITY_EXCEEDED`; the browser exercised the out-of-scope path. | Local unit PASS; browser coverage for the other two categories remains absent. |
| Do not accept a flagged/uncertain input as verified truth | Every custom-input result is `USER_SUPPLIED_UNVERIFIED`; conflict tests check that neither budget value is asserted true and ask for an authoritative source. | Local unit PASS; this is simulation behavior only. |
| Audit action, time, input, and reason | Fixed suites return a per-run audit projection. New input returns `INPUT_EVALUATED`, completion timestamp, canonical-input SHA-256, and reason in the immediate response. | Partial: no durable audit/history exists; the submitted raw input is not retained. |
| Human intervention, stop, and override follow the contract; do not claim irreversible work was undone | Escalations provide a contextual handoff question. Public Judge exposes only `POST /runs` and `POST /input-runs`; no human response, stop/status, retry, or override operation exists. Client timeout/disconnect does not cancel server work. The simulation has no production side effect to undo. | Missing on the public Judge route beyond handoff guidance. No cancellation, reversal, or Checker override may be claimed. Product Checker controls are separate and are not reachable from this route. This is an unresolved scored acceptance gap, not an out-of-scope PASS. |
| Isolate from production and bound inputs/requests/concurrency | Exact-source tests cover no Auth DB/demo workflow dependency, production-mode route 404, strict request schemas, 16 KiB route body cap, 30 requests / 60 seconds and one active POST per process. | Local source PASS. Proxy/edge body cap and deployed limits remain unverified. |
| Dataset has at least 15 cases and policy agrees with behavior | Fixture/catalog and classifier tests cover the 15-case reference set and approved `JUDGE-INPUT-SIMULATION-1.0` rules. | Local deterministic/Mock PASS only. The user-approved scope (`DEMO-DEPT-01`, `DEMO_SOCIAL`/`DEMO_EMAIL`, VND, 100,000,000 VND) is Judge simulation policy, not production policy. |

### Deployment and remaining verification

- Repository intent in `render.yaml` is one API instance (`numInstances: 1`) in Demo mode with an ephemeral `/tmp/organizationai/demo-*.sqlite3` database; the frontend sets `VITE_DEMO_ENABLED=true`. `deployment/start_backend.py` starts Uvicorn with one worker and `--limit-concurrency 32`. The Judge quota is process-local at 30 POSTs per rolling 60 seconds and at most one active Judge POST per process. These settings yield that quota for one process only; they do not establish an actually deployed topology or a distributed/global limit.
- D reports the live frontend entry currently returns not found, no separate Judge API service exists, and the existing Auth API uses `deployment.start_auth_backend`. This Judge task did not access Render or production; deployed service configuration, deployed SHA, service URLs, and edge/proxy request-body cap remain unverified. Do not use the Auth service as the Judge deployment.
- Before D enables a public Demo entry, D must supply the deployed frontend/API URLs and SHA and verify a separate Demo-only service, no Auth/production data/provider access, the actual instance/worker counts, process-wide aggregate quota, and edge body cap. Public acceptance evidence must match that deployed SHA. The missing human response/stop/override capability and lack of durable audit must also be resolved against the scored Challenge A contract; do not simulate a stop or claim it is covered by the handoff question.
- Reproduction for the local disposable run: from `frontend/`, `npm run test:e2e -- --config playwright.config.ts e2e/public-judge.spec.ts e2e/public-judge-layout.spec.ts`, `npm test -- src/routes/AppRoutes.test.tsx src/pages/VerifyDashboardPage.test.tsx src/services/publicJudgeService.test.ts`, `npm run typecheck`, and `npm run build`; from the repository root, run the backend pytest command listed above. Use a fresh `demo-*.sqlite3` file and Mock mode; keep browser outputs under a temporary directory.

## Judge action contract checkpoint (2026-10-15)

- The user approved the Judge-only simulation policy: `DEMO-DEPT-01`, `DEMO_SOCIAL`/`DEMO_EMAIL`, `VND`, and a maximum of 100,000,000 VND. This approval applies to deterministic Judge simulation only; it does not enable a production policy or auto-approval.
- D reports an in-progress backend action contract at `POST /api/public/judge/runs/{run_id}/cases/{case_id}/action`, with JSON `{ "action": "APPROVE" | "REJECT" | "STOP", "reason": "..." }` and a UUID `Idempotency-Key`. The route handles completed fixed-run cases and new input (`case_id=NEW_INPUT`). The reported response includes final status, action, override flag, timestamp, input SHA-256, reason, audit events, and replay flag. Reasons are required, trimmed, and limited to 500 characters. Same-key/same-body is replayed; conflicts and a second final action return 409. Capacity is a safe retryable 503. This is D-reported contract state, not yet independently verified against a committed candidate SHA.
- D reports its in-memory action store is process-local, capped at 3,000 case records with a 15-minute TTL. It keeps bounded derived recommendation/reason, the input hash, audit metadata and one final action/response; it does not retain raw input or durable run history. Process restart/redeploy, expiry, or a different instance can lose the session. The browser therefore labels the actor `ANONYMOUS_PUBLIC_JUDGE` and calls the action a simulated Checker decision or simulated override. STOP is available only after a completed result; it does not cancel in-flight inference or undo side effects.
- D reports 45 targeted backend tests passed, but has not supplied the final candidate SHA/command in this checkpoint. D also found Judge-only startup still constructs Auth AI/config despite route isolation and is fixing that in D-owned `app.py`. Until that fix is committed and reviewed, production/Auth isolation is not a PASS for the new action candidate. No Judge-owned change touches that file.
- This branch's client displays action/status, actor, timestamp, input hash, reason, override and replay information; preserves the same action/reason/idempotency key after an unknown network outcome; treats terminal conflicts as final; and permits retry after capacity errors. Its Vitest responses and the new Playwright response are contract mocks. They verify frontend behavior only, not the action server.
- The new browser test `frontend/e2e/public-judge-actions.spec.ts` was attempted with a Vite-only server and mocked API responses. Playwright Chromium was absent; using installed Chrome then failed to load loopback with `ERR_NETWORK_ACCESS_DENIED`. The sandbox also denies the local socket from PowerShell. Therefore this action E2E is present but BLOCKED here, not PASS. The configured Chrome DevTools MCP required by the browser-testing skill is not available in this session.

### Current acceptance gap map at this checkpoint

| Challenge A brief criterion | Evidence available at this checkpoint | Current status / exact remaining gap |
| --- | --- | --- |
| Public entry without account; one first instruction | Earlier disposable browser evidence on the 12539-based page asserted the entry and instruction with no Auth/Cookie headers. The action UI is covered by unit tests only in this checkpoint. | Prior local functional PASS; current action-bearing page was not browser-retested. No deployed URL/SHA. |
| Verify chung: four cases in one run, pass/fail and actual timestamps | Earlier exact-source public Judge browser run showed 4/4 `MOCK`, run id, timestamps and per-case status. | Prior local functional PASS, `MOCK`; current source/browser regression check pending. |
| Verify → Escalation: five cases, three automatic and two transferred | Earlier exact-source browser evidence showed the five-case 3/2 route distribution and questions. | Prior local functional PASS, `MOCK`; current source/browser regression check pending. |
| New input; result responds to changed inputs | Earlier browser and input-rule tests changed fields and exercised out-of-scope routing; current action client tests use variable response fixtures. | Prior deterministic simulation PASS, not real inference; current server candidate SHA is unverified. |
| Separate missing fact, policy scope and authority overflow | Earlier backend unit coverage asserts `FACT_UNCERTAIN`, `POLICY_OUT_OF_SCOPE`, `AUTHORITY_EXCEEDED`. | Prior local unit PASS. Exact-source rerun against D's current candidate is pending. |
| Contextual transfer question; uncertain/flagged values remain unverified | Earlier tests check source-document questions and do not assert either conflicting budget as true; responses are `USER_SUPPLIED_UNVERIFIED`. | Prior local unit PASS. Current action test does not establish inference quality (`NOT_MEASURED`). |
| Audit action, time, input and reason | Client maps and displays action audit event, timestamp, input SHA-256 and reason. D reports bounded in-memory audit metadata and no raw-input persistence/durable history. Frontend unit tests pass with a contract fixture. | Frontend contract PASS; backend exact-SHA verification pending. Audit is ephemeral for up to 15 minutes, not a durable production audit trail. |
| Intervention/stop/override; no false rollback claim | UI offers APPROVE/REJECT/STOP only after completed results, labels anonymous simulated actions/overrides, preserves idempotent retries, and states STOP does not cancel or undo. Unit tests pass. D reports endpoint tests pass, but no final SHA. | Frontend contract PASS; server integration pending. STOP is post-result only. Never describe this as a production Checker decision, cancellation, or rollback. |
| Judge isolation and bounded requests/concurrency | Prior 12539 source tests documented strict schema, 16 KiB request cap and process-local gate. D reports action store bound, but reports an unresolved Auth AI/config initialization on Judge-only startup. | NOT VERIFIED for D's new candidate until D fixes/tests startup isolation. Proxy/edge cap, actual deployed topology and aggregate quota remain outstanding. |
| At least 15 cases; policy consistent with behavior | Earlier 15-case fixture/catalog and deterministic policy tests passed. User approved the simulation-only scope stated above. | Prior local fixture/policy PASS. No production policy changes. |
| Exact deployed public acceptance | No deployed SHA or Judge URL has been provided; no deployment was performed. | NOT RUN. D must provide deployment requirements and exact environment/SHA; public POST/inference remains unauthorized. |

### Reproduction for this action-client checkpoint

- From `frontend/`: `npm test -- --pool=threads --maxWorkers=4` → 28 files / 199 tests passed; `npm run typecheck` → passed; `npm run build` → passed with the existing 586.55 kB chunk warning; `git diff --check` → passed (one line-ending warning).
- The Playwright command is `npm run test:e2e -- --config playwright.config.ts e2e/public-judge-actions.spec.ts`. In this sandbox it cannot start the backend because the branch worktree lacks an executable local Python runtime, and the browser cannot reach loopback. Do not treat the attempted run as a failed application assertion or as a pass; rerun from the disposable environment that can start the local backend/browser.
- D-reported backend result: 45 targeted tests passed on an uncommitted candidate; exact SHA and command remain to be supplied. Do not combine that report with the frontend mock E2E as integrated acceptance evidence.
