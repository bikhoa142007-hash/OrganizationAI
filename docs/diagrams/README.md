# OrganizationAI diagrams

Diagrams in this folder describe the implementation at source commit b67a658f357c482bd817d4230376c68d31c7ba35 (the inspected origin/main). The source files remain editable; the Archify JSON diagrams have checked-in HTML renders. The ERD is Mermaid in Markdown and renders in GitHub's Markdown view.

## Diagram index

| Diagram | Purpose | Editable source / render | Implementation references |
|---|---|---|---|
| Deployment profiles and local inference | React/Vite, FastAPI, Judge Demo SQLite/Mock, separate Auth/PostgreSQL workflow, Local VLM/Ollama and explicitly unconfigured tunnel path. | [Archify JSON](organizationai-architecture.json) · [HTML](organizationai-architecture.html) | [root Render blueprint](../../render.yaml), [Auth staging blueprint](../../deployment/render.auth-staging.yaml), [Compose](../../compose.yaml), [app composition](../../src/backend/api/app.py), [VLM adapter](../../src/ai_pipeline/providers/openai_provider.py) |
| Maker–AI–Checker workflow | Authenticated draft, Checker assignment, upload, immutable version/round, AI route, and Checker handoff. The lifecycle diagram shows final decisions and resubmission. | [Archify JSON](organizationai-main-workflow.json) · [HTML](organizationai-main-workflow.html) | [Auth workflow routes](../../src/backend/api/auth_workflow.py), [workflow application](../../src/backend/application/auth_workflow.py), [decision engine](../../src/backend/rules/decision.py) |
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
| Read workflow audit history | **GET** /api/workflow/audit | [workflow router](../../src/backend/api/auth_workflow.py) |
| Read current configuration / history / create revision | **GET** /api/workflow/configuration · **GET** /api/workflow/configuration/{kind}/history · **POST** /api/workflow/configuration/{kind}/revisions | [configuration router](../../src/backend/api/approval_configuration.py) |

Authentication and permission flow: POST /api/auth/login sets the Auth cookie; GET /api/auth/me returns the authenticated identity; POST /api/auth/logout clears the session. Backend guards enforce Maker permissions for owned plan changes and submission, Checker permission for assigned reviews and decisions, and Admin permission for configuration. A Maker cannot decide their own plan. Admin audit history is exposed at GET /api/workflow/audit.

Configuration revision kinds in code are approval_policy, budget, media_policy, strategy_rubric, authority, and checker_assignment. The authenticated configuration API requires Admin permission. Revisions are effective-dated and append-only; each submitted round stores its own configuration snapshot.

Auto-approval requires an enabled policy, Media PASS with confidence ≥ 0.85, Strategy score strictly > 70 with confidence ≥ 0.80, budget at or below its effective limit, an active authority within its limit and scope for the assigned Checker, no hard violations or unresolved conflicts, no agent errors, and a pending plan with an active round. The code defaults for confidence and score gates are not active deployment configuration. The current Auth workflow configuration is unconfigured and disabled, so a successful inference does not imply auto-approval.

The implemented business statuses are DRAFT, PENDING_APPROVAL, APPROVED, and REJECTED. The separate processing_stage values are DRAFT, AI_PENDING, AI_PROCESSING, HUMAN_REVIEW_REQUIRED, AI_AUTO_APPROVED, and COMPLETED. Pipeline failures route to HUMAN_REVIEW_REQUIRED; AI_PROCESSING_FAILED is a scope target, not a code status. The AI engine has no automatic-rejection outcome.

## Configuration status

The values below are approved business decisions for the target deployment configuration. They are **not confirmation that the checked-out code has those active revisions**:

- Department: Marketing; channel: social.
- Default Checker: `lekhoi`; Maker may select another eligible Checker.
- Policy Owner: `bkhoa`.
- Maximum marketing budget: **10,000,000 VND**; auto-approval authority threshold: **5,000,000 VND**.
- Approved Media WARNING rules: `MEDIA-CLAIM-CERTAINTY` and `MEDIA-PROMOTION-DETAILS`.
- Budget Authority: **not specified**; no account is inferred or assigned here.

At the inspected source commit, authenticated workflow configuration is not seeded with those values. Its unconfigured policy has auto-approval disabled, no configured budget limits, and no authority. The configuration API rejects `approval_policy.enabled=true` before PO sign-off; no sign-off endpoint, record, or workflow was found. Thus the auto-approval decision path exists in code but cannot be claimed as enabled in the current Auth configuration. A successful AI evaluation alone does not cause approval.

## Runtime and deployment boundary

- The checked-in root [Render blueprint](../../render.yaml) is the Judge Demo profile: React/Vite static frontend, FastAPI demo backend, SQLite at a temporary path, and explicit mock mode.
- Auth + PostgreSQL is implemented for local Compose and has a separate [Auth staging blueprint](../../deployment/render.auth-staging.yaml). Repository documentation says this staging blueprint was not deployed; no current Render dashboard or deployment metadata was available to verify a later change.
- Local Compose connects the backend to Ollama through the configured host alias and server-side `LOCAL_VLM_BASE_URL`. The Auth staging blueprint sets remote VLM access false and declares no tunnel. No tunnel endpoint is configured in the repository; the dashed tunnel in the architecture diagram is only an optional/unverified path.
- The Render commit currently serving the public demo could not be verified from repository contents. README notes a historical health check but explicitly leaves the running SHA as TBD.

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
