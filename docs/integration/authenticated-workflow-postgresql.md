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

Migration `20260928_03_auth_workflow` adds the core tables,
`20260929_04_authenticated_ai_pipeline` adds AI-run persistence, and
`20260930_05_auth_workflow_vlm_extraction` adds configured model identity and
separate immutable VLM extraction provenance. `20260930_06_auth_media_strategy_evaluations`
adds separate Media and Strategy step results without altering Auth users/roles
or the Judge Demo database:

| Table | Persisted information |
|---|---|
| `auth_workflow_plans` | Current plan payload, status, Maker, assigned Checker, revision and current version/round |
| `auth_workflow_attachments` | Private image bytes, media type, byte size and SHA-256 |
| `auth_workflow_versions` | Immutable payload and attachment manifest captured on each submit |
| `auth_workflow_evaluation_runs` | Provider/model ID, policy/config snapshot hash, immutable input hash, validated evaluation, separate VLM extraction and Media/Strategy step results, bounded retry count and run state, unique per plan/round |
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

Plan list/detail GETs only read persisted state; refresh never creates an
evaluation, recovery event, or decision. If a durable evaluation remains pending
for more than four minutes after a process interruption, the assigned Checker
can explicitly POST to
`/api/workflow/plans/{plan_id}/rounds/{round_number}/recovery`. The command
rechecks assignment/current-round state, uses the saved snapshot, and routes an
interrupted run to Human Review. Replaying it after recovery is safe and does not
append another event or engine decision. Before four minutes it returns the
current state without changing it.

Administrators can list all Auth workflow plans and open read-only plan details;
this does not grant Maker edit/submit or Checker decision rights. Private
attachment bytes remain available only to the Maker or assigned Checker under
the file-access rule. This is the narrow interpretation of the current scope's
different actor lists for “view all plans” and attachment download.

Draft creation accepts an optional `Idempotency-Key` header (1–200 characters),
scoped to the authenticated Maker. The server stores a hash of the submitted
payload and Checker assignment under a unique constraint: retrying the same
intent returns the original draft, while reusing a key with changed data returns
409. The Auth frontend retains the key across network/5xx retries for the same
form data and clears it after a success or client error.

Submission commits the immutable version and approval round before starting AI
evaluation. The bounded orchestrator loads only private media whose hashes
appear in that snapshot; provider I/O runs outside the database transaction.
The Local VLM extracts OCR and direct visual observations only. The server binds
evidence to snapshot attachment IDs/hashes and persists extraction separately.
Media Compliance evaluates those observations against a versioned content
policy. Strategy Evaluation uses the seven BA criteria and fixed weights; the
backend validates each score and computes the weighted total with Decimal
arithmetic. Each task has a separate provider/model, endpoint fingerprint,
timeout, input/output limits, retries and prompt/schema versions. Task progress
is committed in short transactions between provider calls, preserving one
successful step if a later step fails. Reload reads saved results and never
starts inference again. Missing policy/provider, unknown model, invalid output,
missing evidence, timeout or engine errors route to Checker without rolling
back submission. The pipeline never derives a Strategy score from OCR or
auto-rejects. Maximum configured run time is 190 seconds; stale-run recovery
waits 240 seconds before routing an interrupted run to Checker.

Provider selection is explicit through `AUTH_WORKFLOW_AI_PROVIDER`. The default
`LOCAL_VLM` transport speaks configurable OpenAI-compatible Chat Completions,
but model ID and endpoint are blank unless an operator configures them. An
unconfigured or unsupported runtime fails closed to Checker; no Mock fallback
occurs. `MOCK_VLM` can be selected only with `APP_ENV=demo` for local demos and
accepts `pass`, `review`, `timeout`, `error`, `malformed` or `unknown_media`
scenarios. Auth Mock VLM returns extraction evidence only; it does not replace
either task evaluator or the Judge Demo's legacy mock. The Auth workflow has no
approved production budget/authority source, so its default policy snapshot
disables auto-approval and does not borrow demo limits. Task configuration is
server-side and cannot be enabled through an API request.

## Media and Strategy configuration

Set independent `AUTH_WORKFLOW_MEDIA_*` and `AUTH_WORKFLOW_STRATEGY_*` variables
documented in `.env.example`. Each task supports the explicit protocol
`OPENAI_COMPATIBLE_CHAT_COMPLETIONS` and pins its provider, endpoint, model ID and
model version separately. API keys are sent only in backend bearer headers and
are excluded from snapshots/logs/frontend. The adapter requests strict JSON
Schema output and validates schema, model identity/version and evidence
references again on the backend. The protocol label does not prove compatibility
of any particular runtime.

`AUTH_WORKFLOW_MEDIA_POLICY_JSON` must contain an organization-approved,
versioned policy with department/channel scope and rules describing severity,
meaning and required evidence kinds. This repository does not supply a live
content policy. `AUTH_WORKFLOW_STRATEGY_RUBRIC_JSON` accepts only the seven BA
criteria and fixed weights: objective, audience, channel, timeline, KPI and
budget efficiency at 15 each, and risk control at 10. Both JSON variables are
blank by default; until a required task policy/rubric and model are configured,
the task is marked `NOT_CONFIGURED` and makes no inference request.

Remote endpoints require HTTPS and the task-specific `*_ALLOW_REMOTE=true`
opt-in. The endpoint itself is not persisted or returned; each submitted round
stores only a configuration fingerprint, model IDs/versions and prompt/schema
versions. Auto-approval stays disabled unless an approved server configuration
explicitly enables it together with budget and authority snapshots.

## Local VLM configuration

The backend accepts these operator-only environment variables; none comes from
an Auth request, and the API key is never persisted or logged:

| Variable | Purpose |
|---|---|
| `LOCAL_VLM_MODEL` | Runtime model ID; not treated as an immutable revision |
| `LOCAL_VLM_BASE_URL` | OpenAI-compatible API root including `/v1` |
| `LOCAL_VLM_ALLOW_REMOTE` | Defaults to `false`; non-local endpoints require explicit opt-in and HTTPS |
| `LOCAL_VLM_API_KEY` | Optional bearer credential for the configured runtime |
| `LOCAL_VLM_TIMEOUT_SECONDS` | 1–45 seconds per attempt; defaults to 30 |
| `LOCAL_VLM_MAX_OUTPUT_TOKENS` | Output token cap; defaults to 1536 |
| `LOCAL_VLM_MAX_RESPONSE_BYTES` | Response body cap; defaults to 262144 bytes |
| `LOCAL_VLM_MAX_INPUT_BYTES` | Aggregate image-byte cap; defaults to 20 MiB |

In `.env` for Docker Compose, point to a host runtime with
`LOCAL_VLM_BASE_URL=http://host.docker.internal:<port>/v1`; do not use
`localhost`, which addresses the backend container. Compose maps
`host.docker.internal` to `host-gateway` for Linux and Docker Desktop. A runtime
must listen on a host interface reachable from the backend container. The
adapter permits loopback and `host.docker.internal` by default. A non-local host
requires `LOCAL_VLM_ALLOW_REMOTE=true` and HTTPS; enable it only after explicitly
approving that destination for private image data. The actual runtime/model
remains operator-selected; no model is bundled or downloaded by this project.

The adapter sends image bytes as base64 `image_url` content parts and requests a
strict JSON Schema response. A runtime that lacks image or schema support is
classified and routed to Checker. It does not send permanent attachment URLs.
Visual-extraction schema v2 preserves per-image confidence as a self-reported,
uncalibrated value, plus object labels and technical quality findings; it does
not return bounding boxes. Confidence below the applied 0.85 policy threshold,
non-PASS image quality, or extraction uncertainty routes to Checker. This signal
is separate from Media Compliance and Strategy confidence and never decides
approval. Verify the selected runtime's official documentation before enabling
it; OpenAI protocol references for [image input](https://developers.openai.com/api/docs/guides/images-vision) and [structured output](https://developers.openai.com/api/docs/guides/structured-outputs) describe the request shape, not compatibility of a particular local runtime.

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
Run the manual smoke only after confirming the target API/PostgreSQL is an
authorized test environment and the intended Local VLM configuration is ready.
It creates one synthetic plan and can invoke AI; do not use it solely to test
deployment. Automated tests use isolated databases. Then execute the HTTP smoke
test from the repository root:

```powershell
& .\.venv\Scripts\python.exe scripts/smoke_auth_workflow.py
```

It asks for the seeded password without echoing it, then uses separate Maker,
Checker and Admin sessions to create one plan, upload a private image, submit,
reject, revise/resubmit and approve the same plan. It also checks forbidden
actions and demo identity separation. Concurrency is covered by isolated tests.

The runner checkpoints its run ID and plan ID at
`runtime/auth-workflow-smoke-state.json` (override with
`AUTH_WORKFLOW_SMOKE_STATE_FILE`). It refuses a second plan scenario in the same
state file. If a create request times out before returning an ID, it checks a
read-only PostgreSQL query for the exact generated run marker, resumes only a
unique match, and stops without retrying if none is visible. A completed state
prints the existing plan ID on the next invocation and does not create another
plan; the checkpoint file is ignored local runtime data.

Pytest with SQLite-backed test sessions checks API logic and permission behavior,
but it does not prove the PostgreSQL migration ran. Only `alembic upgrade head`
against the Compose PostgreSQL service followed by the smoke script establishes
that runtime result.

The local real-model smoke configuration and retained smoke records are
documented in [Local Media and Strategy inference](local-media-strategy-inference.md).
