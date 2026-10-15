# Core Auth workflow data model (ERD)

**Purpose:** Show the PostgreSQL entities and foreign-key relationships used by the authenticated plan workflow. There is no separate approval-round table: the submitted round number is stored on auth_workflow_versions, auth_workflow_decisions, and related run/snapshot rows.

**Code basis:** [auth_workflow.py](../../src/backend/db/models/auth_workflow.py), [approval_configuration.py](../../src/backend/db/models/approval_configuration.py), [sla.py](../../src/backend/db/models/sla.py), [user.py](../../src/backend/db/models/user.py), [role.py](../../src/backend/db/models/role.py), and Alembic migrations under [alembic/versions](../../alembic/versions/).

Source commit: b67a658f357c482bd817d4230376c68d31c7ba35 (origin/main).

```mermaid
erDiagram
    users ||--o{ auth_workflow_plans : maker_id
    users o|--o{ auth_workflow_plans : checker_id
    users ||--o{ auth_workflow_attachments : uploaded_by
    users ||--o{ auth_workflow_versions : submitted_by
    users o|--o{ auth_workflow_events : actor_id
    users ||--o{ auth_workflow_notifications : recipient_user_id
    users ||--o{ auth_workflow_decisions : checker_id
    users ||--o{ auth_workflow_configuration_revisions : changed_by
    users ||--o{ auth_workflow_sla_configurations : changed_by
    users ||--o{ user_roles : user_id
    roles ||--o{ user_roles : role_id
    roles ||--o{ role_permissions : role_id

    auth_workflow_plans ||--o{ auth_workflow_attachments : plan_id
    auth_workflow_plans ||--o{ auth_workflow_versions : plan_id
    auth_workflow_plans ||--o{ auth_workflow_events : plan_id
    auth_workflow_plans ||--o{ auth_workflow_notifications : plan_id
    auth_workflow_plans ||--o{ auth_workflow_decisions : plan_id
    auth_workflow_plans ||--o{ auth_workflow_evaluation_runs : plan_id
    auth_workflow_plans ||--o{ auth_workflow_engine_decisions : plan_id
    auth_workflow_plans ||--o{ auth_workflow_round_configuration_snapshots : plan_id
    auth_workflow_plans ||--o{ auth_workflow_sla_rounds : plan_id
    auth_workflow_evaluation_runs o|--o{ auth_workflow_evaluation_runs : retry_parent_run_id
    auth_workflow_evaluation_runs ||--o| auth_workflow_engine_decisions : evaluation_run_id
    auth_workflow_sla_configurations ||--o{ auth_workflow_sla_rounds : configuration_id
```

## Relationship notes

- auth_workflow_versions stores both version_number and round_number; each plan has a unique version and a unique round in that table. No approval_rounds table exists.
- auth_workflow_decisions has a unique (plan_id, round_number); auth_workflow_engine_decisions references the evaluation run and plan, and limits outcomes to AUTO_APPROVED or HUMAN_REVIEW_REQUIRED.
- auth_workflow_round_configuration_snapshots points to the plan and contains configuration and Checker assignment snapshots as JSON. It does not have foreign keys to individual config revisions.
- Evaluation results are JSON columns on auth_workflow_evaluation_runs; Media, Strategy, and VLM extraction are not separate result tables.
- This is the Auth/PostgreSQL model only. Judge Demo's SQLite repository is a separate profile.
