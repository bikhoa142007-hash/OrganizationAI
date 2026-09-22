# Sprint 1 final packaging report

Date: 2026-09-22. Scope: final verification and packaging only. No business logic changes, directory relocation, staging, commit, push, tag or deployment.

## Git status

Branch: `integration/role1-role3-frontend`.
HEAD: `c1288c9ceb49fe16eea5887fc914a9ad50ba1e44`.
Index is empty. Working tree contains the integration and preserved initial user work.

```text
M README.md
 M requirements.txt
 M src/backend/application/workflow.py
 M src/backend/repositories/approval.py
 M src/backend/rules/decision.py
?? .env.example
?? app.py
?? docs/integration/
?? docs/role-integration-audit-2026-09-21.md
?? docs/role1/
?? frontend/
?? role1-sprint1-v2.1/
?? src/backend/api/
?? src/backend/demo.py
?? src/backend/seed_demo.py
?? src/frontend/
?? src/verify/
?? tasks/
?? tests/fixtures/
?? tests/integration/test_demo_seed.py
?? tests/integration/test_http_api.py
?? tests/integration/test_ba_regression.py
?? tests/unit/frontend/
?? tests/unit/verify/
```

This report and sprint1-proposed-commit-files.txt are additionally untracked under docs/integration/. The full changed/untracked file inventory proposed for review is [sprint1-proposed-commit-files.txt](sprint1-proposed-commit-files.txt). Do not use a broad git add: review that explicit inventory before approving staging.

## Changes in this packaging step

- frontend/.env.example: set VITE_API_BASE_URL=http://127.0.0.1:8010/api to match the README demo backend, including the /api prefix.
- README.md: distinguish demo example URL from the client's unchanged fallback of port 8000; no TBD remains anywhere in README.
- docs/integration/ba-regression-results.json: refreshed from the newly executed actual reports, including timestamps and hashes.
- docs/integration/sprint1-final-packaging-report.md and sprint1-proposed-commit-files.txt: final handoff and explicit proposed paths.
- Ignored runtime actual reports, build output and E2E evidence refreshed by tests; none proposed for commit.

All prior business-code changes are described in [integration report](ba-frontend-developer-integration-report.md). frontend/ remains at repository root. app.py, src/frontend/ and existing user changes remain present.

## Server shutdown

Stopped this integration's backend on 8010 (worker PID 852; parent exited) and Vite on 5173 (PID 37836). E2E started its own 8008/5178 servers and cleaned them up. Final port/process checks found no remaining integration listeners or uvicorn/Vite processes in this repository. The unrelated process previously using 8000 was not stopped. Demo URLs documented in the previous report are restart addresses; servers are now stopped.

## Commands and fresh results

Python executable: ./.venv/Scripts/python.exe, commands at repository root. npm commands run from frontend/.

| Command | Result |
| --- | --- |
| python -m pytest -q | 123 passed, 84 subtests passed, 2 warnings; 2.97s |
| python -m src.verify.runner --suite ground-truth --output runtime/role1-ground-truth-actual.json | 15/15 |
| python -m src.verify.runner --suite verify --output runtime/role1-verify-actual.json | 5/5; 3 automatic and 2 escalated |
| npm run test | 4 passed, 2 files; 1.01s |
| npm run build | TypeScript + Vite passed; 40 modules |
| npm run test:e2e | 4 passed; 8.2s |
| git diff --check | Passed after final documentation changes |

E2E covers auto-approval, Checker rejection followed by V2/R2 resubmission with immutable history, factual uncertainty/real Verify, and Checker approval with override/audit. BA expected files were not edited. Fresh durable results are in ba-regression-results.json; full observations remain ignored under runtime/.

## WP5 status

PASS for the user-authorized local Sprint demo integration: real API-backed Maker/Checker flows, immutable history, evidence/confidence/categories, override/rejection reasons, real one-click five-case Verify and passing browser tests. Old Streamlit WP5 app/service/tests are preserved.

The broader WP5 document's Stop/Undo and request-changes controls are intentionally not introduced: existing frozen workflow supports approve/reject and revision after rejection. This recorded scope resolution remains in ba-conflict-report.md. Public judge hosting and formal business/UAT sign-off have not been established by local automated tests. In-app notifications remain optional scope, not newly implemented here.

## WP6 status

PASS for the requested local final verification and packaging. Full pytest, actual BA regression, UI tests/build/E2E, status/hygiene checks and handoff are complete.

Full WP6 Challenge-A submission remains NOT COMPLETE: no public Live URL/deployment, clean-clone execution evidence, formal reviewer/PO sign-off, final runbook/build-log submission set, exactly-five-slide deck, <=3-minute demo video or Sprint-1 tag. These are not added in this packaging-only step. Commit/push/tag remain withheld pending explicit user confirmation. Existing repository HEAD above is the baseline, not a release commit.

## Hygiene checks

- git diff --cached --name-only is empty: zero staged files, including zero secrets or generated files.
- git check-ignore confirms .env, frontend/.env, runtime/demo-organization.sqlite3, frontend/node_modules, frontend/dist and frontend/test-results are ignored.
- Full tracked-change/untracked inventory contains no .env (except safe .env.example), local DB, runtime data, dependency tree, build output, temporary screenshot/test-result or credential/key file candidates.
- Path and content pattern scan of text candidates found no private-key blocks, common provider token formats or quoted long credential assignments. This is a bounded heuristic check, not proof against every possible secret representation.
- Fixture PNGs are intentional synthetic test inputs, not temporary screenshots. Legacy PDF is reference provenance, not runtime input.
- No source/fixture deletion, Git reset/clean or nested Git removal performed.

## Proposed commit files

The linked text manifest enumerates each path; nothing is staged. Proposed grouping for approval/review:

1. Preserved pre-existing WP5 work: app.py, src/frontend/, original src/verify/harness.py and package init, associated tests, README/requirements additions.
2. Backend/BA integration: three modified backend modules, API/demo/seed modules, new Verify adapter/runner/observation, integration and mapping tests, .env.example.
3. Frontend Developer frontend: frontend source, package manifests/lockfile, build/test configs, E2E tests, UI_FLOW.md and safe .env.example. Keep frontend/ at root.
4. Fixtures and documentation: tests/fixtures/ba/v2.1/, docs/integration/, docs/role1/, audit and tasks files.
5. Original role1-sprint1-v2.1/ reference package: propose as a separate provenance commit because imported links/validator instructions reference it. Review this duplicated reference material explicitly; do not include its generated/runtime files. Original documents retain historical NOT_VERIFIED/NOT_RUN status.

The manifest includes existing user work for a reproducible checkout; inclusion is a proposal for the user's approval, not permission already exercised. Excludes node_modules, dist, test-results/screenshots, runtime databases/reports/backups, .env and credentials. Safe .env.example files and package-lock.json are included.

## Known limitations

- Demo-only server-owned identities and mock model; production identity, real local model validation and real company policy remain owner decisions.
- GT-014/015 original expected category is null; hard-violation acceptance passes, actual category POLICY_OUT_OF_SCOPE. Full WP Verify category compatibility for these two cases is not claimed.
- Verify replay cache is process-local; workflow mutation idempotency is persisted. UI list is limited to first 100 plans; Verify UI state lasts the page session.
- Two Python dependency deprecations (Starlette/httpx and AnyIO), plus harmless E2E NO_COLOR/FORCE_COLOR warning. No dependency or business changes were made to suppress them.
- No configured standalone lint command; frontend build provides TypeScript checking. Clean-clone/install and production deployment were not rerun in this step.

Next safe action: user reviews this report and explicit manifest, then confirms staging/commit scope. No commit or push has occurred.
