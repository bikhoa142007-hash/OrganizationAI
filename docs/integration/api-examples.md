# Demo HTTP API

Start in APP_ENV=demo. OpenAPI is available at http://127.0.0.1:8000/openapi.json
and interactive documentation at http://127.0.0.1:8000/docs. Production mode
returns 401 for demo actors. Public health remains available.

Requests use `X-Demo-Actor: DEMO-MAKER-01` or `DEMO-CHECKER-01`; roles are loaded
on the server. `Idempotency-Key` identifies one intent and must be reused when
retrying the same request. Do not silently update a stale revision and retry.

```http
PUT /api/plans/DEMO-EXAMPLE/draft
X-Demo-Actor: DEMO-MAKER-01
Idempotency-Key: draft-example-1
Content-Type: application/json

{"expected_revision":0,"payload":{"title":"Demo campaign"}}
```

An incomplete draft is valid. Response includes plan_id, maker_id supplied by
server, payload, attachments, revision=1, current_round=0 and DRAFT state.
Complete the draft using its new revision before submitting:

```json
{
  "expected_revision": 1,
  "payload": {
    "title": "Demo campaign",
    "objective": "Reach qualified customers",
    "summary": "Synthetic strategy for the demonstration",
    "department": "DEMO-DEPT-01",
    "checker_id": "DEMO-CHECKER-01",
    "start_date": "2026-10-01",
    "end_date": "2026-10-31",
    "budget_minor_units": "50000000",
    "currency": "VND"
  }
}
```

Upload multipart fields `file` and `expected_revision` to attachments. Filename is
ignored for identity; response carries server-computed content_hash and byte_size.
PNG/JPEG/WebP signatures are checked, maximum 5 MB. Read media only through the
authorized attachment route; no permanent public URLs.

Submit body: `{"expected_revision":3,"expected_policy_version":"DEMO-HTTP-1"}`.
Use actual returned plan revision. Then evaluate the returned round number with
`{"expected_revision":0}`. Evaluation uses round revision, not plan revision.

Checker decision example:

```http
POST /api/plans/DEMO-EXAMPLE/rounds/1/decision
X-Demo-Actor: DEMO-CHECKER-01
Idempotency-Key: checker-example-1
Content-Type: application/json

{"expected_revision":1,"action":"APPROVED","reason":"Reviewed evidence","override_reason":"Manual evidence resolves the recommendation for review"}
```

Rejection requires reason. Either action needs override_reason when it contradicts
the recorded evaluation recommendation. Human Review routing is not a rejection
recommendation; budget routing can coexist with a model auto-approval recommendation.

Error response example (HTTP 409):

```json
{"code":"CONFLICT","message":"Stale revision.","correlation_id":"http-opaque-id","http_status":409}
```

Codes: validation 422, unauthenticated 401, forbidden 403, missing resource 404,
conflict 409, unavailable 503. Error responses do not contain traceback or raw input.
CORS permits only environment-configured origins; credentials are disabled.

`POST /api/verify/general` runs five Role 1 Verify cases. `escalation` runs the 15
GT regressions. These demo-only test runs use isolated in-memory repositories and
return actual report rows; they do not alter the normal demo plan database.
