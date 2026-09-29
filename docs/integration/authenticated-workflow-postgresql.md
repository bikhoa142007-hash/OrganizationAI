# Authenticated Maker–Checker Workflow on PostgreSQL

## Boundary

The local authenticated workflow uses the `organizationai_access_token` HTTP-only
JWT cookie. Each request decodes the cookie, reloads the active user and roles
from PostgreSQL, then checks the operation against that principal. Request bodies
cannot set the Maker, the actor, or a role.

The Judge Demo remains an independent system: `/api/plans`, `/api/reviews`,
`/api/verify` and the existing demo pages continue to use SQLite and
`X-Demo-Actor`. Authenticated workflow pages use `/workflow/*` and `/api/workflow/*`;
their client sends cookies and does not send `X-Demo-Actor`.

## PostgreSQL records

Migration `20260928_03_auth_workflow` adds the core tables and
`20260929_04_authenticated_ai_pipeline` adds AI-run persistence without
altering Auth users/roles or the Judge Demo database:

| Table | Persisted information |
|---|---|
| `auth_workflow_plans` | Current plan payload, status, Maker, assigned Checker, revision and current version/round |
| `auth_workflow_attachments` | Private image bytes, media type, byte size and SHA-256 |
| `auth_workflow_versions` | Immutable payload and attachment manifest captured on each submit |
| `auth_workflow_evaluation_runs` | Provider, policy/config snapshot hash, immutable input hash, validated evaluation, bounded retry count and run state, unique per plan/round |
| `auth_workflow_engine_decisions` | Deterministic policy outcome and budget/rule checks, unique per plan/round and run |
| `auth_workflow_decisions` | Final Checker action, rejection reason and any AI override reason, unique per plan/round |
| `auth_workflow_events` | Append-only human/system actor, action, per-plan sequence, time, before/after status and event details |

Draft edits and file uploads require the owning Maker and the current revision.
Submission locks the plan row, validates required fields, a distinct active
Checker and an attachment, then inserts the version and history event in the same
transaction. Checker decisions lock the plan and have a unique plan/round key;
replaying the same decision returns the stored result. A rejected plan can be
edited and resubmitted as the next version and approval round. The API has no
delete operation for these records. Uploads are decoded server-side as PNG,
JPEG or WebP, must match their declared media type, stay below 25 million pixels
and 5 MB, and are stored with a SHA-256 hash.

Submission commits the immutable version and approval round before starting AI
evaluation. The existing bounded orchestrator then evaluates only the media
whose hashes appear in that version's snapshot; the provider call runs outside
the database transaction. A validated result and the deterministic engine
decision are stored against the same version/round. Provider, schema, snapshot,
policy or engine failures route the plan to Checker review; they never roll back
the submitted plan or create an AI rejection. Interrupted runs older than 60
seconds are recovered to Checker review when an authorized Maker or Checker
reads the plan or list.

Provider selection is explicit through `AUTH_WORKFLOW_AI_PROVIDER`. The default
`LOCAL_VLM` adapter currently has no inference transport configured in this
repository, so it fails closed to Checker review. `MOCK_VLM` can be selected
only with `APP_ENV=demo` for local demos and accepts `pass`, `review`, `timeout`,
`error`, `malformed` or `unknown_media` scenarios. It does not silently replace
Local VLM. The Auth workflow has no approved production policy, budget or
authority configuration source yet, so its default policy snapshot disables
auto-approval and does not borrow demo limits. The API/service accepts an
explicit configuration object for controlled environments; auto-approval must
remain disabled until real Auth configuration is approved and persisted.

Checker actions that differ from the AI recommendation, or are made without a
recommendation, require an override reason. Every Checker rejection requires a
separate non-blank rejection reason. An approved/rejected plan cannot be edited;
rejected plans may be revised and submitted as the next immutable version and
approval round.

## Existing SQLite data

The local `runtime/demo-organization.sqlite3` is the Judge Demo store and remains
in place. It contains demo actor IDs and synthetic plan history, which have no
approved mapping to PostgreSQL Auth users. No automatic copy, rewrite, or delete
is performed. A future migration would require an explicit `DEMO-*` to Auth user
mapping, a verified backup, a dry-run reconciliation report and a separately
authorized transfer. Keeping the stores split avoids treating demo identities as
real Maker/Checker ownership.

## API and page map

| Operation | Endpoint | Authorization |
|---|---|---|
| List Maker plans | `GET /api/workflow/plans` | Auth cookie and `MAKER` |
| List active Checkers | `GET /api/workflow/checkers` | Auth cookie and `MAKER` |
| Create draft | `POST /api/workflow/plans` | Auth cookie and `MAKER`; server assigns Maker |
| Edit draft | `PUT /api/workflow/plans/{id}` | Owner Maker; `DRAFT` or `REJECTED` |
| Upload private image | `POST /api/workflow/plans/{id}/attachments` | Owner Maker; editable state |
| Submit | `POST /api/workflow/plans/{id}/submit` | Owner Maker; creates immutable snapshot |
| Review queue | `GET /api/workflow/reviews` | Auth cookie and `CHECKER`; assigned pending plans only |
| Read detail/history | `GET /api/workflow/plans/{id}` | Owner Maker or assigned Checker |
| Decide | `POST /api/workflow/plans/{id}/rounds/{n}/decision` | Assigned Checker; rejection reason required |

The browser routes are `/workflow/plans`, `/workflow/plans/new`,
`/workflow/plans/{id}`, `/workflow/plans/{id}/edit` and `/workflow/reviews`.
`/login`, `/register` and `/account` remain the entry points for real Auth
sessions. `/` and `/plans/*` remain the synthetic Judge Demo.

## Local PostgreSQL smoke test

Start the Compose stack after setting local-only values in `.env`:

```powershell
docker compose up --build -d
docker compose ps
```

The backend startup runs `alembic upgrade head` and the idempotent Auth seed.
Then execute the HTTP smoke test from the repository root:

```powershell
& .\.venv\Scripts\python.exe scripts/smoke_auth_workflow.py
```

It asks for the seeded password without echoing it, then uses separate Maker,
Checker and Admin sessions to create three plans, upload images, submit, approve
one, reject another, and race two opposite decisions on a third round. It also
checks forbidden actions and demo identity separation. The script leaves the
three clearly named smoke plans in PostgreSQL; retain them or remove only those
exact IDs after confirming they are disposable test records.

Pytest with SQLite-backed test sessions checks API logic and permission behavior,
but it does not prove the PostgreSQL migration ran. Only `alembic upgrade head`
against the Compose PostgreSQL service followed by the smoke script establishes
that runtime result.
