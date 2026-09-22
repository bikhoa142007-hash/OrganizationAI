# Role naming refactor

Legacy Role1 = BA; Legacy Role3 = Frontend Developer.

Human labels: Role1 / Role 1 / role 1 -> BA; Role3 / Role 3 / role 3 -> Frontend Developer.
Active path tokens: role1 / role-1 / role_1 -> ba; role3 / role-3 / role_3 -> frontend-developer.
Python class Role1MockProvider -> BAMockProvider; Python module role1_adapter -> ba_adapter;
test_role1_application_regression -> test_ba_application_regression. No TypeScript variable
or Python Role3 identifier required renaming. frontend/ stays unchanged.

## Inventory and remaining matches

[Pre-edit inventory](role-naming-inventory.json) lists every tracked textual/path match and category.
[Remaining references](role-naming-remaining.json) lists each preserved line/path with its reason.
These audit artifacts necessarily quote old names. Imported docs/role1/ retains its original
location/wording; its README explains the mapping. Only links to relocated fixtures changed
in imported Markdown, with updated destination hashes in ba-import-manifest.json.
Archive bytes, fixture JSON/images, schema IDs, model version, original-package filenames,
historical branch names and recorded runtime report paths/hashes remain unchanged.
The ignored source delivery and agent-local files are outside tracked deliverables.
No API shape, policy, environment value, public URL or deployment setting changed.

## Collision checks

No case-insensitive destination collisions. Existing frontend/ is unaffected.
New Python module/class/test names are distinct; imports exercised by all project tests.

## Renamed files

- `docs/integration/role1-conflict-report.md` -> `docs/integration/ba-conflict-report.md`
- `docs/integration/role1-contract-mapping.md` -> `docs/integration/ba-contract-mapping.md`
- `docs/integration/role1-import-manifest.json` -> `docs/integration/ba-import-manifest.json`
- `docs/integration/role1-regression-results.json` -> `docs/integration/ba-regression-results.json`
- `docs/integration/role1-role3-integration-report.md` -> `docs/integration/ba-frontend-developer-integration-report.md`
- `src/verify/role1_adapter.py` -> `src/verify/ba_adapter.py`
- `tests/fixtures/role1/v2.1/README.md` -> `tests/fixtures/ba/v2.1/README.md`
- `tests/fixtures/role1/v2.1/base-policy.json` -> `tests/fixtures/ba/v2.1/base-policy.json`
- `tests/fixtures/role1/v2.1/fact-verification.schema.json` -> `tests/fixtures/ba/v2.1/fact-verification.schema.json`
- `tests/fixtures/role1/v2.1/fixture-manifest.json` -> `tests/fixtures/ba/v2.1/fixture-manifest.json`
- `tests/fixtures/role1/v2.1/ground-truth-cases.json` -> `tests/fixtures/ba/v2.1/ground-truth-cases.json`
- `tests/fixtures/role1/v2.1/images/budget-conflict.png` -> `tests/fixtures/ba/v2.1/images/budget-conflict.png`
- `tests/fixtures/role1/v2.1/images/creative-low-quality.png` -> `tests/fixtures/ba/v2.1/images/creative-low-quality.png`
- `tests/fixtures/role1/v2.1/images/creative-pass.png` -> `tests/fixtures/ba/v2.1/images/creative-pass.png`
- `tests/fixtures/role1/v2.1/images/hard-claim-demo.png` -> `tests/fixtures/ba/v2.1/images/hard-claim-demo.png`
- `tests/fixtures/role1/v2.1/images/kpi-conflict.png` -> `tests/fixtures/ba/v2.1/images/kpi-conflict.png`
- `tests/fixtures/role1/v2.1/images/scope-missing.png` -> `tests/fixtures/ba/v2.1/images/scope-missing.png`
- `tests/fixtures/role1/v2.1/images/synthetic-private-demo.png` -> `tests/fixtures/ba/v2.1/images/synthetic-private-demo.png`
- `tests/fixtures/role1/v2.1/mock-provider-modes.json` -> `tests/fixtures/ba/v2.1/mock-provider-modes.json`
- `tests/fixtures/role1/v2.1/source-register.json` -> `tests/fixtures/ba/v2.1/source-register.json`
- `tests/fixtures/role1/v2.1/verify-expected-results.json` -> `tests/fixtures/ba/v2.1/verify-expected-results.json`
- `tests/fixtures/role1/v2.1/verify-inputs.json` -> `tests/fixtures/ba/v2.1/verify-inputs.json`
- `tests/integration/test_role1_regression.py` -> `tests/integration/test_ba_regression.py`
- `tests/unit/verify/test_role1_mapping.py` -> `tests/unit/verify/test_ba_mapping.py`

## Modified files (including rename destinations)

- `README.md`
- `deployment/README.md`
- `docs/contracts/verify-result-schema.md`
- `docs/implementation-plan.md`
- `docs/integration/api-examples.md`
- `docs/integration/ba-conflict-report.md`
- `docs/integration/ba-contract-mapping.md`
- `docs/integration/ba-frontend-developer-integration-report.md`
- `docs/integration/ba-import-manifest.json`
- `docs/integration/ba-regression-results.json`
- `docs/integration/frontend-backend-gap-analysis.md`
- `docs/integration/sprint1-final-packaging-report.md`
- `docs/integration/sprint1-proposed-commit-files.txt`
- `docs/role-integration-audit-2026-09-21.md`
- `docs/role1/v2.1/00-index.md`
- `docs/role1/v2.1/05-ground-truth-cases.md`
- `docs/role1/v2.1/07-verify-cases.md`
- `docs/role1/v2.1/08-verify-expected-results.md`
- `docs/role1/v2.1/17-demo-data-and-seed-guide.md`
- `frontend/UI_FLOW.md`
- `frontend/e2e/workflow.spec.ts`
- `frontend/src/mocks/index.ts`
- `src/backend/demo.py`
- `src/verify/ba_adapter.py`
- `src/verify/observation.py`
- `src/verify/runner.py`
- `tasks/plan.md`
- `tasks/todo.md`
- `tests/fixtures/ba/v2.1/README.md`
- `tests/fixtures/ba/v2.1/base-policy.json`
- `tests/fixtures/ba/v2.1/fact-verification.schema.json`
- `tests/fixtures/ba/v2.1/fixture-manifest.json`
- `tests/fixtures/ba/v2.1/ground-truth-cases.json`
- `tests/fixtures/ba/v2.1/images/budget-conflict.png`
- `tests/fixtures/ba/v2.1/images/creative-low-quality.png`
- `tests/fixtures/ba/v2.1/images/creative-pass.png`
- `tests/fixtures/ba/v2.1/images/hard-claim-demo.png`
- `tests/fixtures/ba/v2.1/images/kpi-conflict.png`
- `tests/fixtures/ba/v2.1/images/scope-missing.png`
- `tests/fixtures/ba/v2.1/images/synthetic-private-demo.png`
- `tests/fixtures/ba/v2.1/mock-provider-modes.json`
- `tests/fixtures/ba/v2.1/source-register.json`
- `tests/fixtures/ba/v2.1/verify-expected-results.json`
- `tests/fixtures/ba/v2.1/verify-inputs.json`
- `tests/integration/test_ba_regression.py`
- `tests/unit/verify/test_ba_mapping.py`

Additional files: this report, role-naming-inventory.json, role-naming-remaining.json,
and docs/role1/README.md. Changes remain unstaged.

## Verification

Final python -m pytest: 141 passed (2 existing dependency warnings).
Frontend npm run test: 4 passed; npm run build: passed. git diff --check: passed.
No YAML file was modified; JSON validation included updated manifests and fixtures. Modified JSON parses, relocated Markdown
links resolve, immutable fixture/archive hashes match, and deployment configuration
and environment examples match their pre-refactor SHA-256 hashes.

## Limits

Historical references deliberately retain legacy names; do not globally replace them.
Original-package links require the locally retained source package and were already
non-portable before this refactor. Two dependency deprecation warnings remain.
