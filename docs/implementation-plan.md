# WP1 implementation plan and repository audit

Status: documentation-only contract freeze, pending user approval. Audit date: 2026-09-20.
Repository: `C:/Users/Khoa Bi/VS Studio/repos/OrganizationAI`.

## Authority and bounded inspection

AGENTS.md is the highest project authority. The approved WP1 execution prompt and follow-up clarify its application: no automatic rejection in Sprint 1; the third outcome is reserved only. The controlling WP is `docs/work-packages/WP1-repository-audit.md`. Root README describes intended behavior, not implemented capability.

Exactly two read-only agents participated: project_explorer (repository inventory) and reviewer (Challenge-A boundary review). Neither delegated further. Both completed before the main agent consolidated their results once. No production code was changed. WP2-WP6, the full docs/skills trees, generated files and dependency contents were not reviewed. No runnable security audit or application tests are claimed.

## Observed repository

| Area | Audit result |
|---|---|
| Application root | NOT_AVAILABLE; repository root is not yet an application root |
| Language/framework/runtime/package manager/database/test framework | NOT_SELECTED |
| Root manifest, solution/project file, lockfile | NOT_AVAILABLE in bounded inventory |
| Frontend | `src/frontend/` exists; no source implementation |
| Backend and AI | `src/backend/`, `src/ai_pipeline/` exist; no source implementation |
| Shared schema | `src/shared/` exists; no implementation |
| Database migrations and seeds | NOT_AVAILABLE |
| Authentication/authorization | NOT_AVAILABLE; no mechanism to reuse |
| Upload, audit, policy, AI/VLM modules | NOT_AVAILABLE; README/AGENTS are requirements only |
| Tests | `tests/unit/`, `tests/integration/`, `tests/e2e/`, `tests/fixtures/` exist; no test implementation |
| Verify and synthetic data | `verify/runner/`, `data/synthetic/` exist; no runner/cases/seed implementation |
| Deployment/scripts/CI | Directories exist; no executable setup found |
| Git | NOT_AVAILABLE; user confirms repository is not initialized |
| Reusable assets | AGENTS, WP1 and README business/workflow descriptions; folder ownership boundaries |

The executed bounded inventory returned only README.md and AGENTS.md outside excluded documentation/configuration/generated trees. See [verified commands](contracts/verified-commands.md) for the exact command and limits. `.vs/` is IDE metadata and was skipped. Dependency/build paths such as node_modules, vendor, bin, obj, dist, build and __pycache__ were excluded, not asserted to contain application code. No framework or database was selected.

## Frozen contract set

- [Decision contract](contracts/decision-contract.md): runtime outcomes, policy checks, state guards and human final decisions.
- [Evaluation](contracts/evaluation-schema.md): provider evidence, failure envelope and provenance.
- [Escalation questions](contracts/escalation-question-schema.md): category, evidence, rule and responsible authority.
- [Verify results](contracts/verify-result-schema.md): observed application output and comparison evidence.
- [Audit events](contracts/audit-event-schema.md): immutable actor/state/input/configuration traceability.
- [Ownership](contracts/repository-ownership.md): one writer per path.
- [Command evidence](contracts/verified-commands.md) and [WP1 signoff](contracts/WP1-signoff.md).

All contract field tables are normative framework-independent specifications, not implemented validators. Shared JSON conventions and enum definitions live in decision-contract.md. No HTTP route, framework, database or executable API is claimed.

## Proposed implementation order after explicit WP1 approval

This is a dependency order for later work, not execution of WP2.

1. Team lead resolves the application stack/runtime/storage decision before implementation. Role 2 owns shared schema and migration design; Frontend Developer consumes approved contracts.
2. BA defines versioned policy/authority/budget configuration, synthetic cases and expected results. Role 2 builds authenticated Maker drafts, protected uploads and versioned transactional submission.
3. Role 2 implements LocalVLMProvider/MockVLMProvider, schema-validating orchestration, media/feasibility evaluation and deterministic budget/authority checks.
4. Role 2 implements guarded engine routing/auto-approval and authorized Checker decisions; Frontend Developer integrates Maker/Checker UI after contracts are stable.
5. Frontend Developer connects Verify to the same application path, adds end-to-end checks and deployment/runbook; BA evaluates actual results against independently owned expectations.
6. Stabilize the Must scope, audit history, demo data and documented commands. Do not start Should scope until Must is stable.

## Verification plan

WP1: confirm nine allowed new Markdown files; check mandatory fields, runtime/reserved enum consistency, linked documents and ownership; repeat bounded inventory to confirm no production files appeared. No install/build/test/migrate/seed/start command exists. Document validation does not prove application behavior.

Later implementation must execute AGENTS critical tests: incomplete drafts; invalid submissions and self-approval blocked; submitted content/attachments locked; V1/Round1 and V2/Round2; score 71 versus 70; budget equal versus over limit; confidence thresholds; hard violation, timeout, schema failure and evidence conflict fallback; reject/override reasons; unchanged historical evaluations; concurrent auto/human decisions; retry without duplicate final decisions or notifications. Audit persistence, private attachment access and authorization/error paths must be covered. Verify must exercise actual application services through its public adapter and must fail on a missing application, never manufacture PASS.

## Assumptions and readiness gaps

- Role ownership was supplied by the approved WP1 execution prompt; docs/team/roles/README.md was unavailable at audit time.
- A similarly named `docs/team/role/README.md` was discovered but not used as the approved temporary ownership source. WP1 does not create either role README.
- Git initialization is outside scope and not a contract-freeze blocker. Do not run git status again or git init.
- The user-approved reserved outcome is disabled throughout Sprint 1 runtime.
- Category precedence, correlation fields, failure envelopes and hash representation are contract design choices presented for approval, not claims about existing code.
- Concrete budget limits, authorized Checker assignments, policy versions and provider/model configuration must be supplied before runtime auto-approval. Missing/invalid configuration fails closed to Human Review for an accepted submission.
- Stack selection is a prerequisite to later implementation, not a WP1 blocker.
- No unresolved blocker prevents this framework-independent contract freeze.

## Change scope and handoff

Only the nine documents linked above plus this plan are created (the link list represents eight distinct documents). Production modules, expected results, README, AGENTS, settings and role documentation remain untouched. Command execution and validation evidence are in verified-commands.md. The next safe action is user review of WP1; no subsequent work package is authorized by this document.

