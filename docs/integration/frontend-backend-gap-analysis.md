# Frontend Developer frontend / backend integration

Baseline: one React/TypeScript/Vite package, npm lockfile, React Router, local
component state and ServicesProvider. App instantiated mock services, no HTTP
client or authentication. Main forms had placeholder create IDs, simulated file
selection, no real upload, and a single unresolved time field.

Retained UI shell, styles, router and service interfaces. Added centralized
ApiClient with VITE_API_BASE_URL, errors and stable pending intent keys. App now
constructs API services unconditionally. Old mocks remain isolated for reference,
with no automatic fallback on API failure.

All mutation requests use Idempotency-Key and expected_revision; errors include
code/message/correlation_id/http_status. Reads require X-Demo-Actor in demo mode.

| UI action | API / request | Response | Application method |
| --- | --- | --- | --- |
| Demo actor/config | GET /api/config | Directory, roles, assigned Checker, demo policy, capabilities | Server-owned demo configuration |
| List | GET /api/plans?offset=0&limit=100 | Authorized plan summaries | list_plans |
| Create/edit draft | PUT /api/plans/{id}/draft, payload + revision | Plan + new revision | save_draft |
| Upload | POST /api/plans/{id}/attachments, multipart file + revision | Plan + manifest/revision | upload_attachment |
| Submit | POST /api/plans/{id}/submit, revision + policy version | Immutable snapshot, round and ticket | submit_plan |
| Evaluate | POST /api/plans/{id}/rounds/{n}/evaluate, round revision | Persisted evaluation/decision/questions | run_evaluation -> ApprovalPipelineAdapter -> evaluate_round |
| Processing/result/detail | GET /api/plans/{id} | History, versions, rounds, records, audit | get_plan |
| Private image | GET /api/plans/{id}/attachments/{attachment_id} | Authorized image bytes | get_attachment |
| Review queue | Authorized plan list + details | Active Human Review records | list_plans / get_plan |
| Approve/reject | POST /api/plans/{id}/rounds/{n}/decision, action/reason/override_reason/round revision | HumanDecision | decide_round |
| Revise/resubmit | Same draft/submit endpoints after rejection | Next version and round | Existing workflow |
| Audit | Plan history | Immutable audit rows | get_plan |
| Policy | GET /api/config | Current synthetic demo snapshot | configuration |
| Verify | POST /api/verify/general or escalation | Actual comparison rows, timings, WP Verify view | Real runner/workflow in isolated database |

No role/maker privilege is accepted from request bodies. Read-only UI fields are
not treated as authorization: server validates ownership, assignment and state.
Client mapper excludes server-owned maker_id when loading a form for editing.

Frontend fixes: actual upload, incomplete draft save, explicit start/end dates,
optional audience/KPI, integer VND amount, mandatory summary, private image blobs,
plan list/detail/history, override reason, stale/network errors and loading/empty
states. Submitted pages do not offer editing. Human actions are only approve and
reject; unsupported Stop/Request Changes have no API action.

Initial evaluation runs synchronously in the demo; submit commits first. If the
browser loses the evaluation request, detail offers continuation of the existing
unevaluated round. Re-evaluating an already committed round under a new intent
conflicts. This is not pipeline retry scheduling.

Limitations: plan list currently displays the first 100 authorized records;
the API supports pagination. Verify run UI state lasts for the current page session;
the CLI writes durable actual reports. The demo header is not production login.
