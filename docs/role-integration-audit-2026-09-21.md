# Role 1 / Backend / Role 3 integration audit

Date: 2026-09-21. Status: baseline audited; integration not implemented.

## Discovery and preservation

Audit started at the repository root. Discovery excluded node_modules, dist,
build, .venv and .git contents. A separate recursive directory inspection checked
for .git entries without traversing their contents.

- Role 1: extracted `role1-sprint1-v2.1/` package found; no matching Role1 ZIP
  found in the searched tree.
- Frontend candidate list: only `frontend/package.json`.
- Selected frontend: `frontend/`, supported by React/react-dom/react-router-dom
  dependencies, Vite scripts, `vite.config.ts`, `src/main.tsx`, `src/App.tsx`,
  routes, pages and service interfaces. npm lockfile is present.
- Only the root `.git` was found; no frontend nested Git repository was found.
- Initial Git state: modified README.md and requirements.txt; untracked app.py,
  frontend/, role1-sprint1-v2.1/, src/frontend/, src/verify/,
  tests/unit/frontend/ and tests/unit/verify/.
- No user files or Git metadata were removed. No commit was created. Existing
  changes were preserved. Frontend build regenerated ignored dist output.
- Root .gitignore covers node_modules, dist, build, .env variants, common secret
  files and local database/runtime artifacts. This is not a full secret audit.

## Current structure

| Area | Implementation and reusable modules |
| --- | --- |
| Backend | Python application services; pip requirements and existing .venv; ApprovalWorkflow in src/backend/application/workflow.py |
| Domain | Typed models, policy snapshots, deterministic rules in src/backend/domain/ and src/backend/rules/ |
| Storage | Standard-library SQLite; ApprovalRepository; migration_001.sql with wp3 plans, rounds, immutable records, finals, intents, attachments and audit tables |
| AI | src/ai_pipeline/ orchestrator, validation, ApprovalPipelineAdapter, VisualModelProvider interface, mock/local provider classes; real local inference was not tested in this audit |
| Existing demo | Streamlit app.py and transport-neutral FrontendService in src/frontend/service.py |
| Role 3 UI | React + TypeScript + Vite; AppShell, routes, plan form, processing, result, review, audit, policy and Verify pages |
| UI service seam | ServicesProvider and interfaces; App.tsx currently instantiates createMockServices unconditionally |
| Verify/seeds | src/verify/harness.py contains five TEST_ONLY scenarios and demo configuration; Role 1 has separate 15 GT and five Verify datasets with fixtures |
| Tests | pytest unit suites for domain/rules/AI/frontend facade/Verify and integration suites for workflow/AI |

Backend authorization accepts a trusted server-owned actor ID and role directory.
It checks Maker ownership and assigned Checker permissions. The workflow explicitly
requires its host to authenticate callers; no HTTP authentication layer is supplied
by this service. The Streamlit demo uses fixed demo identities. Public HTTP input
must not be allowed to supply trusted actors or roles.

The current demo configuration uses a 10000 VND budget/authority limit and PNG
uploads. Role 1 documents a separate 100m demo limit. These configurations must not
be silently treated as the same policy or as approved company limits.

## Executed baseline

| Working directory | Command | Actual result |
| --- | --- | --- |
| Root | `& ./.venv/Scripts/python.exe -m pytest -q` | 88 passed, 84 subtests passed; 1.64s |
| frontend | `npm run build` | TypeScript and Vite build passed; Vite 8.3.0, 43 modules |
| frontend | `npm run test --if-present` | No test script exists; no frontend tests executed |
| frontend | `npm run typecheck` | Passed |
| role1-sprint1-v2.1 | `& ../.venv/Scripts/python.exe tools/validate_package.py` | 192/192 artifact checks passed; eight negative mutation controls; WP compatibility NOT_VERIFIED and engine regression NOT_RUN |

No frontend lint/test script or root formatter/typecheck configuration was found
in the inspected manifests. No dependencies required installation for these
baselines. Browser runtime and end-to-end integration were not tested.

Sandbox commands initially failed before launching because of
`helper_read_acl_helper_spawn_failed`. The executed commands used approved
escalated execution; this was a tool-environment issue, not a project build error.

## Contract gaps and missing input

1. AGENTS.md references docs/scope-phe-duyet-ke-hoach-marketing-phase-1.md and
   docs/chien-luoc-codex-sprint-1-72h.md, which do not exist. Corresponding scope
   and sprint documents exist as docs/scope-phase-1.md and
   docs/sprint-1-deliverables.md. Do not fabricate missing files or treat the old
   empty-repository inventory in implementation-plan.md as current evidence.
2. The user message refers to an integration prompt "below", but no such prompt
   was included. Its acceptance criteria and any authorization decisions cannot
   be inferred from that reference.
3. Role 3 exposes REQUEST_CHANGES and Stop/retry processing actions. Existing
   backend/frozen decision contract has only APPROVED/REJECTED human decisions,
   immutable final rounds and no Stop/Undo operation. AGENTS excludes a separate
   request-changes decision. Integration must preserve these existing rules.
4. HTTP routes/DTOs and authentication wiring have not been implemented. The
   choice between a clearly restricted demo and authenticated multi-user access
   affects authorization and requires the missing integration requirements.
5. Role 1 fact_verification is explicitly a fixture extension proposal. Its
   mapping into existing evidence/conflict schemas still needs implementation
   and engine regression, especially GT-007/008/009 and VERIFY-A04. Artifact
   validation alone does not establish compatibility.
6. Existing TEST_ONLY Verify cases are not the Role 1 dataset. Their successful
   tests must not be reported as Role 1 engine acceptance.

## Proposed implementation order and verification

After obtaining the missing integration requirements:

1. Record transport/authentication decisions and a mapping to existing frozen
   domain DTOs; retain domain outcomes, thresholds, identity and revision guards.
2. Add a Role 1 dataset adapter and actual regression tests without changing
   expected outputs. Preserve unresolved fact evidence and provenance.
3. Add HTTP hosting around ApprovalWorkflow/ApprovalPipelineAdapter, private
   attachment access, trusted authentication, consistent errors and idempotency.
4. Implement Role 3 API services through existing interfaces; connect forms,
   uploads, revision-aware submit, result, Checker decisions and audit. Resolve
   unsupported UI actions according to AGENTS and the integration requirements.
5. Connect Verify to real application execution, retain separately owned
   expectations and expose actual errors/results.
6. Run affected unit/integration tests, full pytest, TypeScript/build checks and
   browser end-to-end Maker -> AI -> Checker -> revise/resubmit scenarios.
   Verify forbidden access, stale revisions, immutable history, private uploads,
   idempotent/concurrent decisions and AI failure fallback.

Expected change areas: new HTTP adapter and tests, Role 1 integration adapter and
tests, frontend API services and affected pages/types, Vite proxy configuration,
dependency manifests only as required, and run instructions. Existing user edits
must be incorporated, never reset. Schema migration is not presumed necessary.

## Handoff

- Outcome: discovered packages and stack, inspected integration boundaries,
  executed baseline and recorded gaps.
- Files changed by this audit: this report only, plus ignored build output.
- Assumptions: existing Python/SQLite and React/Vite stacks remain; no policy or
  authorization change is approved merely by the presence of mock UI controls.
- Limitations: no API/frontend integration delivered; no Role 1 engine regression
  or browser tests executed.
- Next safe work package: obtain the omitted integration prompt, resolve its
  authentication requirements against the existing trusted-principal contract,
  then implement the adapter/API/UI slices above.
