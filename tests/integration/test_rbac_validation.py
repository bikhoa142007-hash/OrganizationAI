"""HTTP regression coverage for demo authorization and submission validation."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.backend.api.app import create_app
from src.backend.api.dependencies import Settings
from src.backend.demo import CHECKER, MAKER


PNG = b"\x89PNG\r\n\x1a\nsynthetic"
OTHER_CHECKER = "DEMO-DUAL-01"
@pytest.fixture
def client(tmp_path):
    settings = Settings("demo", str(tmp_path / "demo-rbac.sqlite3"), mock_mode="pass")
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def headers(actor=MAKER, key=None):
    return {"X-Demo-Actor": actor, "Idempotency-Key": key or uuid4().hex}


def valid_payload():
    return {
        "title": "Autumn product launch",
        "objective": "Reach qualified customers in the launch segment",
        "summary": "A phased campaign with approved creative and measurable conversion goals.",
        "department": "DEMO-DEPT-01",
        "checker_id": CHECKER,
        "start_date": "2026-10-01",
        "end_date": "2026-10-31",
        "budget_minor_units": "50000000",
        "currency": "VND",
    }


def policy_version(client):
    response = client.get("/api/config", headers=headers())
    assert response.status_code == 200, response.text
    return response.json()["policy"]["policy"]["policy_version"]


def save_draft(client, plan_id, payload=None):
    response = client.put(
        f"/api/plans/{plan_id}/draft",
        headers=headers(),
        json={"payload": valid_payload() if payload is None else payload, "expected_revision": 0},
    )
    assert response.status_code == 200, response.text
    return response.json()


def submit_ready_plan(client, plan_id="HTTP-RBAC"):
    draft = save_draft(client, plan_id)
    uploaded = client.post(
        f"/api/plans/{plan_id}/attachments",
        headers=headers(),
        data={"expected_revision": draft["revision"]},
        files={"file": ("campaign.png", PNG, "image/png")},
    )
    assert uploaded.status_code == 200, uploaded.text
    submitted = client.post(
        f"/api/plans/{plan_id}/submit",
        headers=headers(),
        json={"expected_revision": uploaded.json()["revision"], "expected_policy_version": policy_version(client)},
    )
    assert submitted.status_code == 200, submitted.text
    return uploaded.json()["attachments"][0]


def evaluate(client, plan_id="HTTP-RBAC"):
    response = client.post(
        f"/api/plans/{plan_id}/rounds/1/evaluate",
        headers=headers(),
        json={"expected_revision": 0},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_missing_or_unknown_demo_authentication_is_rejected(client):
    assert client.get("/api/config").status_code == 401
    assert client.get("/api/plans", headers=headers("NOT-A-PRINCIPAL")).status_code == 401
    assert client.put(
        "/api/plans/HTTP-UNAUTH/draft",
        json={"payload": {}, "expected_revision": 0},
    ).status_code == 401


def test_checker_cannot_create_a_maker_draft(client):
    response = client.put(
        "/api/plans/HTTP-CHECKER-CREATE/draft",
        headers=headers(CHECKER),
        json={"payload": {}, "expected_revision": 0},
    )

    assert response.status_code == 403


def test_review_queue_requires_an_authenticated_checker(client):
    assert client.get("/api/reviews").status_code == 401
    assert client.get("/api/reviews", headers=headers(MAKER)).status_code == 403
    assert client.get("/api/reviews", headers=headers("DEMO-ADMIN-01")).status_code == 403


def test_review_queue_only_shows_assigned_active_human_reviews(client):
    submit_ready_plan(client)
    evaluate(client)

    assigned = client.get("/api/reviews", headers=headers(CHECKER))
    unassigned = client.get("/api/reviews", headers=headers(OTHER_CHECKER))

    assert assigned.status_code == 200, assigned.text
    assert [plan["plan_id"] for plan in assigned.json()] == ["HTTP-RBAC"]
    assert unassigned.status_code == 200, unassigned.text
    assert unassigned.json() == []

    decision = {
        "action": "APPROVED",
        "expected_revision": 1,
        "reason": None,
        "override_reason": "Assigned Checker accepts the fully documented exception.",
    }
    finalized = client.post(
        "/api/plans/HTTP-RBAC/rounds/1/decision", headers=headers(CHECKER), json=decision
    )
    assert finalized.status_code == 200, finalized.text
    assert client.get("/api/reviews", headers=headers(CHECKER)).json() == []


def test_non_owner_cannot_read_plan_attachment_or_observation(client):
    attachment = submit_ready_plan(client)
    evaluate(client)

    assert client.get("/api/plans/HTTP-RBAC", headers=headers(OTHER_CHECKER)).status_code == 403
    assert client.get(
        f"/api/plans/HTTP-RBAC/attachments/{attachment['attachment_id']}",
        headers=headers(OTHER_CHECKER),
    ).status_code == 403
    assert client.get(
        "/api/plans/HTTP-RBAC/rounds/1/observation", headers=headers(OTHER_CHECKER)
    ).status_code == 403


@pytest.mark.parametrize(
    ("injected_field", "value"),
    [
        ("maker_id", OTHER_CHECKER),
        ("plan_status", "APPROVED"),
        ("approval_round", 99),
        ("expected_outcome", "AUTO_APPROVED"),
    ],
)
def test_draft_rejects_server_owned_field_injection(client, injected_field, value):
    payload = valid_payload()
    payload[injected_field] = value

    response = client.put(
        "/api/plans/HTTP-INJECTION/draft",
        headers=headers(),
        json={"payload": payload, "expected_revision": 0},
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update(title="   "),
        lambda payload: payload.update(title="test"),
        lambda payload: payload.update(objective="TBD"),
        lambda payload: payload.update(summary="lorem ipsum"),
        lambda payload: payload.update(summary="..."),
        lambda payload: payload.update(budget_minor_units="0"),
        lambda payload: payload.update(start_date="2026-11-01", end_date="2026-10-01"),
        lambda payload: payload.update(start_date="not-a-date"),
    ],
    ids=(
        "whitespace",
        "test-placeholder",
        "tbd-placeholder",
        "lorem-ipsum-placeholder",
        "ellipsis-placeholder",
        "zero-budget",
        "reversed-dates",
        "invalid-date",
    ),
)
def test_submission_rejects_invalid_or_placeholder_business_data(client, mutate):
    plan_id = "HTTP-INVALID-" + uuid4().hex
    payload = valid_payload()
    mutate(payload)
    draft = save_draft(client, plan_id, payload)
    uploaded = client.post(
        f"/api/plans/{plan_id}/attachments",
        headers=headers(),
        data={"expected_revision": draft["revision"]},
        files={"file": ("campaign.png", PNG, "image/png")},
    )
    assert uploaded.status_code == 200, uploaded.text

    response = client.post(
        f"/api/plans/{plan_id}/submit",
        headers=headers(),
        json={"expected_revision": uploaded.json()["revision"], "expected_policy_version": policy_version(client)},
    )

    assert response.status_code == (403 if payload["checker_id"] == OTHER_CHECKER else 422)
    history = client.get(f"/api/plans/{plan_id}", headers=headers()).json()
    assert history["plan"]["state"]["plan_status"] == "DRAFT"
    assert history["versions"] == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.pop("checker_id"),
        lambda payload: payload.update(budget_minor_units="-1"),
        lambda payload: payload.update(budget_minor_units="50000000.00"),
        lambda payload: payload.update(budget_minor_units="50,000,000"),
        lambda payload: payload.update(start_date="2026-02-30"),
    ],
    ids=(
        "missing-checker",
        "negative-budget",
        "decimal-budget",
        "separated-budget",
        "invalid-calendar-date",
    ),
)
def test_submission_rejects_missing_or_malformed_required_values(client, mutate):
    plan_id = "HTTP-MALFORMED-" + uuid4().hex
    payload = valid_payload()
    mutate(payload)
    draft = save_draft(client, plan_id, payload)
    uploaded = client.post(
        f"/api/plans/{plan_id}/attachments",
        headers=headers(),
        data={"expected_revision": draft["revision"]},
        files={"file": ("campaign.png", PNG, "image/png")},
    )
    assert uploaded.status_code == 200, uploaded.text

    response = client.post(
        f"/api/plans/{plan_id}/submit",
        headers=headers(),
        json={"expected_revision": uploaded.json()["revision"], "expected_policy_version": policy_version(client)},
    )

    assert response.status_code == 422


def test_dual_role_maker_cannot_assign_themself_as_checker(client):
    payload = valid_payload()
    payload["checker_id"] = OTHER_CHECKER
    draft = client.put(
        "/api/plans/HTTP-SELF-ASSIGN/draft",
        headers=headers(OTHER_CHECKER),
        json={"payload": payload, "expected_revision": 0},
    )
    assert draft.status_code == 422
    assert client.get("/api/plans/HTTP-SELF-ASSIGN", headers=headers(OTHER_CHECKER)).status_code == 404


@pytest.mark.parametrize("field,value,status", [
    ("department", "DOES-NOT-EXIST", 422),
    ("checker_id", OTHER_CHECKER, 403),
    ("checker_id", "UNKNOWN", 422),
    ("currency", "USD", 422),
])
def test_invalid_directory_references_cannot_grant_draft_access(client, field, value, status):
    payload = {**valid_payload(), field: value}
    response = client.put("/api/plans/HTTP-DIRECTORY/draft", headers=headers(),
                          json={"payload": payload, "expected_revision": 0})
    assert response.status_code == status
    assert client.get("/api/plans/HTTP-DIRECTORY", headers=headers(OTHER_CHECKER)).status_code == 404
    assert client.get("/api/plans", headers=headers(OTHER_CHECKER)).json() == []


@pytest.mark.parametrize(
    "body",
    [
        {"action": "REQUEST_CHANGES", "expected_revision": 0, "reason": None, "override_reason": None},
        {
            "action": "APPROVED",
            "expected_revision": 0,
            "reason": None,
            "override_reason": None,
            "plan_status": "APPROVED",
        },
    ],
    ids=("unsupported-human-action", "top-level-final-status-injection"),
)
def test_decision_request_rejects_unsupported_or_server_owned_fields(client, body):
    response = client.post(
        "/api/plans/HTTP-NO-DECISION/rounds/1/decision", headers=headers(CHECKER), json=body
    )

    assert response.status_code == 422


def test_checker_cannot_decide_before_evaluation_is_committed(client):
    submit_ready_plan(client)
    response = client.post(
        "/api/plans/HTTP-RBAC/rounds/1/decision",
        headers=headers(CHECKER),
        json={
            "action": "APPROVED",
            "expected_revision": 0,
            "reason": None,
            "override_reason": "A Checker cannot bypass evaluation.",
        },
    )

    assert response.status_code == 409


def test_demo_mock_pass_requires_human_review_when_auto_policy_is_disabled(client):
    submit_ready_plan(client)
    result = evaluate(client)

    assert result["decision"]["outcome"] == "HUMAN_REVIEW_REQUIRED"
    history = client.get("/api/plans/HTTP-RBAC", headers=headers()).json()
    assert history["plan"]["state"] == {
        "plan_status": "PENDING_APPROVAL",
        "processing_stage": "HUMAN_REVIEW_REQUIRED",
        "approval_round_status": "ACTIVE",
    }


def test_unassigned_checker_is_denied_even_after_the_round_is_finalized(client):
    submit_ready_plan(client)
    evaluate(client)
    decision = {
        "action": "APPROVED",
        "expected_revision": 1,
        "reason": None,
        "override_reason": "Assigned Checker accepts the fully documented exception.",
    }
    approved = client.post(
        "/api/plans/HTTP-RBAC/rounds/1/decision", headers=headers(CHECKER, "assigned-approve"), json=decision
    )
    assert approved.status_code == 200, approved.text

    denied = client.post(
        "/api/plans/HTTP-RBAC/rounds/1/decision", headers=headers(OTHER_CHECKER), json=decision
    )
    assert denied.status_code == 403


def test_assigned_checker_manual_approval_is_audited_and_idempotent(client):
    submit_ready_plan(client)
    evaluate(client)
    decision = {
        "action": "APPROVED",
        "expected_revision": 1,
        "reason": None,
        "override_reason": "Assigned Checker accepts the fully documented exception.",
    }

    first = client.post(
        "/api/plans/HTTP-RBAC/rounds/1/decision", headers=headers(CHECKER, "manual-approval"), json=decision
    )
    replay = client.post(
        "/api/plans/HTTP-RBAC/rounds/1/decision", headers=headers(CHECKER, "manual-approval"), json=decision
    )

    assert first.status_code == 200, first.text
    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json()
    history = client.get("/api/plans/HTTP-RBAC", headers=headers()).json()
    assert history["plan"]["state"]["plan_status"] == "APPROVED"
    assert [event["action"] for event in history["audit"]].count("HUMAN_APPROVED") == 1
    opposite = client.post(
        "/api/plans/HTTP-RBAC/rounds/1/decision",
        headers=headers(CHECKER, "opposite-decision"),
        json={
            "action": "REJECTED",
            "expected_revision": 1,
            "reason": "A finalized decision cannot be replaced.",
            "override_reason": None,
        },
    )
    assert opposite.status_code == 409


@pytest.mark.parametrize("payload", [{"checker_id": CHECKER}, {"checker_id": CHECKER, "department": ""}])
def test_incomplete_assignment_cannot_grant_checker_draft_visibility(client, payload):
    response = client.put("/api/plans/HTTP-INCOMPLETE-PAIR/draft", headers=headers(),
                          json={"payload": payload, "expected_revision": 0})
    assert response.status_code == 422
    assert client.get("/api/plans", headers=headers(CHECKER)).json() == []
    assert client.get("/api/plans/HTTP-INCOMPLETE-PAIR", headers=headers(CHECKER)).status_code == 404


@pytest.mark.parametrize("field", ["reason", "override_reason"])
def test_whitespace_reason_cannot_finalize_a_rejection_or_override(client, field):
    submit_ready_plan(client)
    evaluate(client)
    # PASS recommends approval; rejection requires both a reason and override.
    body = {"action": "REJECTED", "reason": "Revise strategy", "override_reason": "Evidence requires revision",
            "expected_revision": 1, field: "   \t "}
    response = client.post("/api/plans/HTTP-RBAC/rounds/1/decision", headers=headers(CHECKER), json=body)
    assert response.status_code == 422
    history = client.get("/api/plans/HTTP-RBAC", headers=headers()).json()
    assert history["rounds"][0]["final_id"] is None
    assert not any(r["kind"] == "human_decision" for r in history["records"])
