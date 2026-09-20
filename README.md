# OrganizationAI – Marketing Plan Approval

OrganizationAI is a Sprint 1 MVP for approving marketing plans through a controlled **Maker–AI–Checker** workflow. Local visual processing and specialized evaluation components support approval while deterministic rules and human review retain control over uncertain or high-risk cases.

## Sprint 1 objective

Deliver a runnable end-to-end flow within 72 hours:

```mermaid
flowchart TD
    A["Maker creates plan"] --> B["Save draft"]
    B --> C["Submit"]
    C --> D["Local VLM extraction"]
    D --> E["Media compliance"]
    C --> F["Strategy feasibility"]
    C --> G["Budget validation"]
    E --> H["Decision policy"]
    F --> H
    G --> H
    H -->|All rules pass| I["Auto approve"]
    H -->|Uncertain or failed| J["Human review"]
    J -->|Reject| K["Revise and resubmit"]
```

## Core capabilities

- Create, save and submit marketing plans.
- Upload and preserve versioned campaign media.
- Extract visual content through a Local VLM adapter.
- Evaluate media compliance against policy.
- Score marketing-strategy feasibility with evidence and confidence.
- Validate budget against deterministic limits.
- Auto-approve only when every configured rule passes.
- Route uncertain, invalid or failed AI results to a Checker.
- Approve, reject, revise and resubmit without losing history.
- Preserve auditable model, policy, evidence and decision metadata.

## Auto-approval policy

The default policy requires all conditions below:

```text
media_result = PASS
AND media_confidence >= 0.85
AND feasibility_score > 70
AND feasibility_confidence >= 0.80
AND budget <= applicable_budget_limit
AND hard_violation_count = 0
AND unresolved_conflict_count = 0
AND agent_error_count = 0
AND auto_approval_policy_enabled = true
AND plan_status = PENDING_APPROVAL
AND approval_round_status = ACTIVE
```

All other cases require Human Review. Sprint 1 does not automatically reject a plan based solely on AI output.

## Documentation

- `AGENTS.md` – mandatory rules for Codex and other coding agents.
- `docs/scope-phe-duyet-ke-hoach-marketing-phase-1.md` – authoritative business scope and rules.
- `docs/chien-luoc-codex-sprint-1-72h.md` – implementation strategy, timeline and tests.

## Recommended repository structure

The actual structure must follow the existing repository. If this is a new repository, use the following as a target without forcing unnecessary layers:

```text
OrganizationAI/
├── AGENTS.md
├── README.md
├── docs/
│   ├── scope-phe-duyet-ke-hoach-marketing-phase-1.md
│   └── chien-luoc-codex-sprint-1-72h.md
├── .agents/
│   └── skills/
├── frontend/                 # if separated by the selected stack
├── backend/                  # if separated by the selected stack
├── tests/
└── scripts/
```

Recommended application modules:

```text
application/
├── plan-module/
├── approval-module/
├── ai-orchestrator/
│   ├── vlm-adapter/
│   ├── media-compliance/
│   ├── strategy-feasibility/
│   ├── budget-validator/
│   └── decision-policy/
├── audit-module/
├── notification-module/
└── shared/
```

## Main actors

| Actor | Responsibility |
|---|---|
| Maker | Creates, edits, submits and resubmits their plans |
| Checker | Reviews assigned plans that require a human decision |
| Administrator | Manages approval, budget and AI-policy configuration |
| Approval Orchestrator | Runs and validates the AI evaluation pipeline |
| Local VLM | Extracts OCR, image description, objects, quality and evidence |
| Media Compliance Agent | Evaluates media against policy |
| Strategy Feasibility Agent | Scores feasibility with confidence and assumptions |
| Budget Rules Engine | Deterministically validates the budget limit |
| Decision Policy Engine | Auto-approves or routes to Human Review |

## Plan states

Business states remain intentionally small:

- `DRAFT`
- `PENDING_APPROVAL`
- `APPROVED`
- `REJECTED`

Internal AI processing stages:

- `AI_PENDING`
- `AI_PROCESSING`
- `HUMAN_REVIEW_REQUIRED`
- `AI_AUTO_APPROVED`
- `AI_PROCESSING_FAILED`

## Local VLM resilience

Business logic must depend on a provider interface rather than one model implementation:

```text
VisualModelProvider
├── analyzeImage()
├── healthCheck()
└── getModelMetadata()
```

Sprint 1 requires:

- `LocalVLMProvider` for real local inference.
- `MockVLMProvider` for deterministic demo and automated tests.

The mock provider must support PASS, REVIEW_REQUIRED and timeout/error scenarios.

## Getting started

The repository stack must be inspected before final installation commands are documented. Codex must update this section after WP1 using commands verified in the actual repository.

### Prerequisites

To be confirmed from the repository:

- Runtime and supported version.
- Package manager.
- Database.
- Local VLM runtime/model.
- Required environment variables.

### Installation

```text
TBD after repository audit (WP1).
Do not insert guessed commands here.
```

### Environment configuration

Create an example environment file containing variable names and safe example values only. Never commit real credentials or secrets.

```text
TBD after repository audit (WP1).
```

### Database migration and seed

```text
TBD after repository audit (WP1).
```

### Run the application

```text
TBD after repository audit (WP1).
```

### Run tests and quality checks

```text
TBD after repository audit (WP1).
```

## Seeded demo scenarios

The completed Sprint must provide:

1. **Auto approval:** compliant media, feasibility above 70, sufficient confidence and budget within limit.
2. **Human review:** low confidence, warning, rule conflict or budget issue.
3. **Reject and resubmit:** Checker rejects; Maker submits a new version and approval round.
4. **Pipeline failure:** provider timeout/error routes to Human Review without rolling back submission.

## Minimum data model

```text
users
marketing_plans
marketing_plan_versions
attachments
approval_rounds
approval_decisions
ai_evaluation_runs
agent_executions
media_evaluation_results
strategy_evaluation_results
budget_validation_results
auto_approval_policies
budget_limits
activity_logs
notifications
```

## Critical safety and integrity rules

- A Maker cannot decide their own plan.
- Submitted content and attachments are immutable.
- Only one approval round is active at a time.
- Decisions are idempotent and concurrency-safe.
- Previous versions and AI results are never overwritten.
- AI failures route to Human Review.
- Budget decisions are deterministic.
- External model use is prohibited unless explicitly configured and approved.
- Significant business and AI actions are auditable.

## 72-hour checkpoints

| Time | Required outcome |
|---|---|
| Hour 20 | Maker can create and save a plan |
| Hour 28 | Submission creates Version 1 and Approval Round 1 |
| Hour 48 | AI pipeline returns Auto Approve or Human Review |
| Hour 62 | Maker → AI → Checker → Maker works end-to-end |
| Hour 68 | Scope freezes; only stabilization and demo preparation remain |
| Hour 72 | Runnable demo, tests, seed data and verified README |

## Development workflow

1. Read `AGENTS.md` and all authoritative docs.
2. Audit the repository before changing code.
3. Implement in small vertical work packages.
4. Run relevant tests after every work package.
5. Report changed files, commands, results, assumptions and limitations.
6. Freeze new feature work after Hour 68.

## Sprint 1 completion criteria

Sprint 1 is complete when:

- The four seeded demo scenarios run reliably.
- Critical business rules have automated coverage.
- The app can be started from documented commands.
- A submitted plan can be traced through every AI and human decision.
- Failed or uncertain AI processing never produces an unreviewed rejection.
- Build, lint/type checks and relevant tests succeed, or a known pre-existing blocker is explicitly documented.

