# OrganizationAI diagrams

Code and schema basis: b67a658f357c482bd817d4230376c68d31c7ba35. The seven commits from that code revision through origin/main d73bf61584af7b8690780df55b4ead537c126ee5 add configuration/deployment records but no backend code changes. Runtime configuration below follows the [activation package](../integration/auto-approve-activation/README.md), which reports a Render check on 2026-10-15. The source files remain editable; Archify JSON diagrams have checked-in HTML renders. The ERD is Mermaid in Markdown and renders in GitHub's Markdown view.

## Diagram index

| Diagram | Purpose | Editable source / render | Implementation references |
|---|---|---|---|
| Deployment profiles and local inference | React/Vite, FastAPI, Judge Demo SQLite/Mock, separate Auth/PostgreSQL workflow, Local VLM/Ollama and explicitly unverified tunnel path. | [Archify JSON](organizationai-architecture.json) · [HTML](organizationai-architecture.html) | [root Render blueprint](../../render.yaml), [Auth staging blueprint](../../deployment/render.auth-staging.yaml), [Compose](../../compose.yaml), [app composition](../../src/backend/api/app.py), [VLM adapter](../../src/ai_pipeline/providers/openai_provider.py) |
| Maker–AI–Checker workflow | Authenticated draft, Checker assignment, upload, immutable version/round, AI route, and Checker handoff. The lifecycle diagram shows approval, rejection, and resubmission. | [Archify JSON](organizationai-main-workflow.json) · [HTML](organizationai-main-workflow.html) | [Auth workflow routes](../../src/backend/api/auth_workflow.py), [workflow application](../../src/backend/application/auth_workflow.py), [decision engine](../../src/backend/rules/decision.py) |
| AI pipeline sequence and routing | VLM → Media → Strategy → deterministic rule engine, skip conditions, errors, persistence and retry. | [Archify JSON](organizationai-ai-technical.json) · [HTML](organizationai-ai-technical.html) | [authenticated orchestrator](../../src/ai_pipeline/authenticated_orchestrator.py), [task validation](../../src/ai_pipeline/task_evaluation.py), [workflow retry](../../src/backend/application/workflow_retry.py), [decision engine](../../src/backend/rules/decision.py) |
| Configuration and round snapshots | Admin configuration APIs, effective-dated revisions, approval-policy enable gate, and immutable per-round snapshot. | [Archify JSON](organizationai-config-workflow.json) · [HTML](organizationai-config-workflow.html) | [configuration API](../../src/backend/api/approval_configuration.py), [configuration rules](../../src/backend/application/approval_configuration.py), [configuration models](../../src/backend/db/models/approval_configuration.py), [SLA API](../../src/backend/api/auth_sla.py), [SLA model](../../src/backend/db/models/sla.py) |
| Plan lifecycle | The exact plan business statuses, separate processing stage, AI fallback, Checker actions, and resubmission. | [Archify JSON](organizationai-lifecycle.json) · [HTML](organizationai-lifecycle.html) | [plan model](../../src/backend/db/models/auth_workflow.py), [workflow application](../../src/backend/application/auth_workflow.py), [decision engine](../../src/backend/rules/decision.py) |
| Auth workflow ERD | Actual Auth/PostgreSQL tables and foreign-key relationships; distinguishes actual tables from JSON snapshots and round-number columns. | [Mermaid Markdown](organizationai-data-model.md) | [workflow models](../../src/backend/db/models/auth_workflow.py), [configuration models](../../src/backend/db/models/approval_configuration.py), [SLA models](../../src/backend/db/models/sla.py), [users/roles](../../src/backend/db/models/user.py), [role relations](../../src/backend/db/models/role.py) |

## Implemented endpoint map

These paths are mounted by the Auth workflow profile. The endpoint names and methods below come from the FastAPI routers; Judge Demo's public judge API is a separate profile.

| Use | Method and path | Source |
|---|---|---|
| Sign in / current identity / sign out | **POST** /api/auth/login · **GET** /api/auth/me · **POST** /api/auth/logout | [auth router](../../src/backend/api/auth.py) |
| List eligible Checkers and plans | **GET** /api/workflow/checkers · **GET** /api/workflow/plans | [workflow router](../../src/backend/api/auth_workflow.py) |
| Create / view / edit plan | **POST** /api/workflow/plans · **GET** /api/workflow/plans/{plan_id} · **PUT** /api/workflow/plans/{plan_id} | [workflow router](../../src/backend/api/auth_workflow.py) |
| Upload / fetch private attachment | **POST** /api/workflow/plans/{plan_id}/attachments · **GET** /api/workflow/plans/{plan_id}/attachments/{attachment_id} | [workflow router](../../src/backend/api/auth_workflow.py) |
| Submit / list Checker reviews / record Checker decision | **POST** /api/workflow/plans/{plan_id}/submit · **GET** /api/workflow/reviews · **POST** /api/workflow/plans/{plan_id}/rounds/{round_number}/decision | [workflow router](../../src/backend/api/auth_workflow.py) |
| Retry an eligible evaluation | **POST** /api/workflow/plans/{plan_id}/rounds/{round_number}/evaluation-retries | [retry router](../../src/backend/api/workflow_retry.py) |
| Read Admin audit history | **GET** /api/workflow/audit | [workflow router](../../src/backend/api/auth_workflow.py) |
| Read current configuration / history / create revision | **GET** /api/workflow/configuration · **GET** /api/workflow/configuration/{kind}/history · **POST** /api/workflow/configuration/{kind}/revisions | [configuration router](../../src/backend/api/approval_configuration.py) |

Authentication and permission flow: POST /api/auth/login sets the Auth cookie; GET /api/auth/me returns the authenticated identity; POST /api/auth/logout clears the session. Backend guards enforce Maker permissions for owned plan changes and submission, Checker permission for assigned reviews and decisions, and Admin permission for configuration. A Maker cannot decide their own plan.

Configuration revision kinds in code are approval_policy, budget, media_policy, strategy_rubric, authority, and checker_assignment. The authenticated configuration API requires Admin permission. Revisions are effective-dated and append-only; each submitted round stores its own configuration snapshot.

Auto-approval requires an enabled policy, Media PASS with confidence ≥ 0.85, Strategy score strictly > 70 with confidence ≥ 0.80, budget at or below its effective limit, an active authority within its limit and scope for the assigned Checker, no hard violations or unresolved conflicts, no agent errors, and a pending plan with an active round. A successful inference is not an approval.

The implemented business statuses are DRAFT, PENDING_APPROVAL, APPROVED, and REJECTED. The separate processing_stage values are DRAFT, AI_PENDING, AI_PROCESSING, HUMAN_REVIEW_REQUIRED, AI_AUTO_APPROVED, and COMPLETED. Pipeline failures route to HUMAN_REVIEW_REQUIRED; AI_PROCESSING_FAILED is a scope target, not a code status. The AI engine has no automatic-rejection outcome.

## Configuration status

The approved business decisions remain the target configuration:

- Department: Marketing; channel: social.
- Target default Checker: lekhoi; Maker may select another eligible Checker.
- Target Policy Owner: bkhoa.
- Marketing budget ceiling: 10,000,000 VND; auto-approval authority ceiling: 5,000,000 VND.
- Approved Media policy: ORG-MEDIA-MARKETING-SOCIAL v1.0.0, Marketing/social, with MEDIA-CLAIM-CERTAINTY and MEDIA-PROMOTION-DETAILS both at WARNING severity.
- Budget Authority: not specified. No account is inferred or assigned.

The [activation record](../integration/auto-approve-activation/README.md) reports PostgreSQL revision 1 effective from 2026-10-15 16:00 Asia/Ho_Chi_Minh with this current state:

| Configuration | Recorded production state |
|---|---|
| budget | EFFECTIVE — 10,000,000 VND for Marketing |
| media_policy | EFFECTIVE — ORG-MEDIA-MARKETING-SOCIAL v1.0.0; both approved rules remain WARNING |
| strategy_rubric | EFFECTIVE — BA-STRATEGY-7-1.0; seven criteria |
| approval_policy | DISABLED — thresholds 0.85 / score >70 / 0.80 are recorded; enabled=false |
| authority | DISABLED — 5,000,000 VND Marketing cap recorded; checker_id, policy_owner_id, and budget_authority_id are null |
| checker_assignment | UNCONFIGURED — no default Checker revision |

The target Checker lekhoi and Policy Owner bkhoa are not active assignments/designations in the recorded configuration. The activation record says checker_assignment is UNCONFIGURED and the employee directory does not establish a unique Marketing default; do not infer one from existing plan assignments. Budget Authority remains unspecified and unassigned. Auto-approval is therefore disabled. The backend rejects approval_policy.enabled=true before PO sign-off; no sign-off endpoint, record, or workflow is implemented. Do not infer an account or enable authority with null actor IDs.

The activation record reports production remote-inference switches enabled and model identities/digests checked, but /api/health/ready does not probe VLM and no production plan/image inference was sent. Real-task model availability and output remain unverified. A successful inference alone does not authorize auto-approval.

## Runtime and deployment boundary

- The checked-in root [Render blueprint](../../render.yaml) describes the Judge Demo profile: React/Vite static frontend, FastAPI demo backend, SQLite at a temporary path, and explicit Mock mode.
- Auth + PostgreSQL is implemented for local Compose. A separate [Auth staging blueprint](../../deployment/render.auth-staging.yaml) exists and is documented as not deployed. The latest activation record reports Render service organizationai-api was running code commit b67a658 on 2026-10-15 and that PostgreSQL readiness passed after restart. This review did not query Render directly, so later deployments remain unverified.
- Local Compose connects the backend to Ollama through its configured host alias and server-side LOCAL_VLM_BASE_URL. Production remote-inference switches and model pins are reported as configured, but no production inference was run. Endpoint values are not checked into the repository.
- The Auth staging blueprint sets remote VLM access false and declares no tunnel. The optional tunnel route in the architecture diagram is not independently verified for the production service; no temporary URL or secret is included.

## Render / validate

The source format for the first five entries is Archify JSON. From the repository root, with the Archify CLI installed:

```sh
archify validate architecture docs/diagrams/organizationai-architecture.json --quality showcase --repo-root .
archify deliver architecture docs/diagrams/organizationai-architecture.json docs/diagrams/organizationai-architecture.html --quality showcase --repo-root .
archify validate workflow docs/diagrams/organizationai-main-workflow.json --quality showcase
archify deliver workflow docs/diagrams/organizationai-main-workflow.json docs/diagrams/organizationai-main-workflow.html --quality showcase
archify validate workflow docs/diagrams/organizationai-ai-technical.json --quality showcase
archify deliver workflow docs/diagrams/organizationai-ai-technical.json docs/diagrams/organizationai-ai-technical.html --quality showcase
archify validate workflow docs/diagrams/organizationai-config-workflow.json --quality showcase
archify deliver workflow docs/diagrams/organizationai-config-workflow.json docs/diagrams/organizationai-config-workflow.html --quality showcase
archify validate lifecycle docs/diagrams/organizationai-lifecycle.json --quality showcase
archify deliver lifecycle docs/diagrams/organizationai-lifecycle.json docs/diagrams/organizationai-lifecycle.html --quality showcase
archify check docs/diagrams/organizationai-architecture.html
archify check docs/diagrams/organizationai-main-workflow.html
archify check docs/diagrams/organizationai-ai-technical.html
archify check docs/diagrams/organizationai-config-workflow.html
archify check docs/diagrams/organizationai-lifecycle.html
```

The ERD stays editable as Mermaid inside [organizationai-data-model.md](organizationai-data-model.md). GitHub renders that source inline. Code links are repository-relative so they remain useful across branches.
