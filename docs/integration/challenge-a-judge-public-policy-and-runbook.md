# Challenge A Public Judge: test policy and runbook

Status: implementation contract for the Challenge A Judge only. The automatic outcomes below apply only to isolated synthetic runs. They do not authorize production auto-approval or deployment.

## Scope and data boundary

- `POST /api/public/judge/runs` accepts only the server-owned `general` and `escalation` suite names. Case inputs and expected results stay in repository fixtures; the server runs the application workflow before comparing with the fixture oracle.
- Verify chung runs four cases: three expected automatic outcomes and one human-review case. Verify → Escalation runs five cases: three expected automatic outcomes and two human-review cases. Each case gets a new in-memory workflow/repository and a server-generated run id.
- `tests/fixtures/ba/v2.1/ground-truth-cases.json` is the 15-case reference catalog. Public requests cannot select individual cases, upload content, provide expected results, or configure policy/provider/model values.
- The suite runs use the repository's mock fixture provider path. `mode=MOCK` is mandatory evidence labeling; a passing assertion proves the workflow matched its synthetic oracle, not that real inference is accurate.
- The Judge router has no Auth dependency, actor header, Auth database, shared demo database, persistent result store, history endpoint, stop endpoint, or override endpoint. D must review and mount it only inside an isolated composition after reviewing trusted client-IP handling, request quotas, and concurrency.
- No public clock/admin controls, CORS changes, rate limiter, or production workflow access is part of this work package.

## New-input simulation policy

Policy identifier: `JUDGE-INPUT-SIMULATION-1.0`. This deterministic simulation accepts a small allowlist of text and numeric fields. It is not submitted as a marketing plan and it does not invoke VLM or strategy inference.

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
- There is no server stop or undo endpoint. A browser timeout or disconnect means the result is unknown and does not prove server work stopped. The UI must not claim cancellation or reversal; there are no production side effects to reverse.
- There is no user override in this test endpoint. Checker override behavior stays in the authenticated workflow and is outside the public Judge.
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

Once D mounts the router and approves isolated local composition, browser acceptance should use a disposable local environment and record the exact deployed/local SHA:

1. Open the public Judge entry in a fresh browser context with no account, cookie, or demo actor.
2. Confirm the first instruction is one sentence and the first action runs general Verify once.
3. Confirm general has 4 timestamped results and escalation has 5; compare actual vs server expected. Confirm escalation has 3 automatic and 2 human-review outcomes with case-specific questions.
4. Enter new allowed values, then vary source budget, department/channel/currency, and budget limit. Confirm `FACT_UNCERTAIN`, `POLICY_OUT_OF_SCOPE`, and `AUTHORITY_EXCEEDED` each arise from entered values, with `USER_SUPPLIED_UNVERIFIED`, `MOCK`, and `NOT_MEASURED` labels.
5. Confirm no Auth cookie/header is sent, request bodies are never retained, no stop/admin/clock route is exposed, and no production data is reachable.
6. If the browser request times out, report outcome unknown. Do not report that server work stopped or was undone.

Do not perform public acceptance on a deployment until D supplies the deployed SHA and confirms the isolated environment, request quota, concurrency limit, and deployment profile. A local or historical test result is not public acceptance evidence.

## Current readiness gaps

- The router is intentionally unmounted. D owns shared app composition and must approve the mounting point and verify Auth/database isolation.
- Request-rate and concurrency quotas are not implemented. D must verify the trusted client-IP source and approve quota values first.
- Browser acceptance and the production deployment SHA are pending D's scheduled browser/build slot and deployment evidence.
- The immediate response provides an input audit summary but no durable audit trail; retention requires a separately approved privacy/data contract.
