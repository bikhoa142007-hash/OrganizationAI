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
- Current Challenge A scope does not specify a public stop/undo or override control; these are not acceptance Musts. This Judge path has no production side effects to reverse. A browser timeout or disconnect means the result is unknown, not cancellation. Do not claim cancellation, reversal, or Checker override through this route.
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

## Current D integration reference (2026-10-15; SHA 47c9374eda3b210d6939bba6f6791e870cec7715)

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
| Intervention/stop/override follows contract; do not claim irreversible work was undone | Challenge A brief, section A p. 2, sets the human-input boundary; Judge returns `HUMAN_REVIEW_REQUIRED` with a concrete handoff question. Requests are ephemeral and no approval is committed. | Public Judge contract PASS locally (`MOCK`). No separate stop/cancel/undo endpoint is required or claimed. Product Checker override/reason is a separate Phase 1 Scope requirement, not a public Judge control. |
| Isolate Judge from production data/accounts and bound requests/concurrency | Local no-auth request assertion; isolated in-memory workflow per suite case; strict body limit and process-local request/concurrency gate documented in router contract | Local design evidence only. Proxy/edge body cap and deployed topology/quota have not been verified. |
| At least 15 dataset cases and policy consistent with behavior | Server fixture test asserts at least 15 unique case IDs; policy values and classifier behavior are documented and covered by input tests | Local unit coverage PASS; Mock fixture behavior only. |

The screenshot verifies functional behavior but also records the unresolved form layout defect above. This local source run is not public deployment acceptance; a deployed SHA and environment verification remain outstanding.

## Prior D local-candidate evidence (2026-10-14; SHA d6fb87c3068a61f127af32403d5ec4a4ad976e78)

- Candidate SHA: `d6fb87c3068a61f127af32403d5ec4a4ad976e78` (local integration candidate, not a deployed SHA).
- Playwright test: `frontend/e2e/public-judge.spec.ts`, test `public Challenge A runs isolated Mock suites and classifies new synthetic input`. Evidence artifact ID: `public-judge-public-Challe-954b8-ssifies-new-synthetic-input`; screenshot: `frontend/test-results/public-judge-public-Challe-954b8-ssifies-new-synthetic-input/challenge-a-public.png`.
- The browser run reports Verify chung `4/4 PASS`, Verify → Escalation `5/5 PASS`, routine synthetic input `SIMULATED_AUTO_APPROVE`, and out-of-scope input `HUMAN_REVIEW_REQUIRED / POLICY_OUT_OF_SCOPE`. The escalation run ID visible in the screenshot is `JUDGE-dec872c6b9944830941862f4332d0a43`.
- This evidence is local and `MOCK`: the suites use synthetic fixtures; custom input uses deterministic simulation, not VLM or strategy inference. `quality_status=NOT_MEASURED`; these results do not prove real-provider inference quality or deployed public behavior.
- Visual review of the screenshot found the new-input form fields flowing inline and overlapping because `.form-grid`/`.form-field` have no styles. Logic E2E passed, but visual acceptance is incomplete. Judge has not changed page or stylesheet files while UI ownership is being resolved.

## Current readiness gaps

- The latest source reference is D candidate `47c9374eda3b210d6939bba6f6791e870cec7715`, descended from `425b417309c7a9db5ee2bd71a74f5cdad6704178`. It is not a deployed SHA and does not establish public deployment acceptance. The Judge worktree remains on its separate branch; no rebase was performed.
- The 30/60-second rate limit and one-active-POST gate are process-local/global among visitors on each process. Deployment instance/worker count has not been verified here; verify it before public acceptance and reassess aggregate limits for the deployed topology.
- The exact-source `9c7f541` local E2E and focused unit results are recorded above. D's later `47c9374` diff has no Judge/frontend changes, but browser behavior was not rerun at that SHA. Visual review shows the new-input form layout defect; UI edits remain pending file-level ownership clearance. This functional local evidence does not establish deployed/public behavior.
- A 16 KiB router body limit exists; proxy/edge body-cap evidence is still required before public deployment.
- No real provider inference or quality evaluation was run. Mock functional PASS is not a real-AI quality PASS.
- The immediate input response contains an audit summary and hash but no durable audit/history; retention needs a separately approved data contract.
