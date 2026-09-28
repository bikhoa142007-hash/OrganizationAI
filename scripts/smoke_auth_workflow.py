"""Smoke-test the cookie-authenticated workflow against a running local API."""
from __future__ import annotations

import getpass
import struct
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import zlib

import httpx


def png_chunk(kind: bytes, content: bytes) -> bytes:
    body = kind + content
    return struct.pack(">I", len(content)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


SMOKE_PNG = (
    b"\x89PNG\r\n\x1a\n"
    + png_chunk(b"IHDR", struct.pack(">2I5B", 1, 1, 8, 6, 0, 0, 0))
    + png_chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00\xff"))
    + png_chunk(b"IEND", b"")
)


def require_status(response: httpx.Response, expected: int, step: str) -> dict:
    if response.status_code != expected:
        raise RuntimeError(
            f"{step}: expected HTTP {expected}, got {response.status_code}: "
            f"{response.text[:600]}"
        )
    if response.status_code == 204:
        return {}
    return response.json()


def login(client: httpx.Client, username: str, password: str) -> dict:
    data = require_status(
        client.post("auth/login", json={"identifier": username, "password": password}),
        200,
        f"login {username}",
    )
    return data["user"]


def create_and_submit(
    client: httpx.Client,
    checker_id: str,
    title: str,
) -> dict:
    draft = require_status(client.post("workflow/plans", json={
        "checker_user_id": checker_id,
        "payload": {
            "title": title,
            "objective": "Reach qualified customers through a measurable campaign",
            "summary": "A synthetic Docker smoke-test plan with defined audience and measurement.",
            "department": "Marketing",
            "start_date": "2026-10-01",
            "end_date": "2026-10-31",
            "budget_minor_units": "10000000",
            "currency": "VND",
            "target_audience": "Customers aged 25 to 40",
            "channels": ["Email", "Social"],
            "kpi_expected": "1,000 qualified visits",
            "notes": "Synthetic local test data.",
        },
    }), 201, "create Maker draft")

    uploaded = require_status(client.post(
        f"workflow/plans/{draft['id']}/attachments",
        data={"expected_revision": str(draft["revision"])},
        files={"file": ("smoke.png", SMOKE_PNG, "image/png")},
    ), 200, "upload private image")
    return require_status(client.post(
        f"workflow/plans/{draft['id']}/submit",
        json={"expected_revision": uploaded["revision"]},
    ), 200, "submit Maker plan")


def main() -> None:
    password = getpass.getpass("Local AUTH_SEED_PASSWORD: ")
    if not password:
        raise SystemExit("A non-empty seed password is required.")
    base_url = input("API base URL [http://localhost:8010/api/]: ").strip()
    base_url = (base_url or "http://localhost:8010/api/").rstrip("/") + "/"
    suffix = uuid4().hex[:8]

    with (
        httpx.Client(base_url=base_url, timeout=20) as maker_client,
        httpx.Client(base_url=base_url, timeout=20) as checker_client,
        httpx.Client(base_url=base_url, timeout=20) as admin_client,
    ):
        maker = login(maker_client, "maker", password)
        checker = login(checker_client, "checker", password)
        login(admin_client, "admin", password)

        # Auth cookie does not authenticate Judge Demo; the demo actor remains a
        # separate, explicit header identity.
        require_status(maker_client.get("config"), 401, "Auth cookie alone on Judge Demo config")
        demo_config = require_status(
            maker_client.get("config", headers={"X-Demo-Actor": "DEMO-MAKER-01"}),
            200,
            "Judge Demo actor header",
        )
        if demo_config.get("actor") != "DEMO-MAKER-01":
            raise RuntimeError("Judge Demo did not preserve the explicit demo actor.")

        approved = create_and_submit(maker_client, checker["id"], f"Docker approval smoke {suffix}")
        rejected = create_and_submit(maker_client, checker["id"], f"Docker rejection smoke {suffix}")
        racing = create_and_submit(maker_client, checker["id"], f"Docker concurrency smoke {suffix}")
        if approved["status"] != "PENDING_APPROVAL" or rejected["status"] != "PENDING_APPROVAL":
            raise RuntimeError("Submitted plans were not routed to Checker review.")

        own_decision = maker_client.post(
            f"workflow/plans/{approved['id']}/rounds/1/decision",
            json={"action": "APPROVED"},
        )
        require_status(own_decision, 403, "Maker self-approval block")
        maker_only_action = checker_client.post("workflow/plans", json={"payload": {}})
        require_status(maker_only_action, 403, "Checker cannot create as Maker")
        require_status(admin_client.get("workflow/plans"), 403, "Admin without Maker/Checker permission")
        require_status(
            admin_client.get(f"workflow/plans/{approved['id']}"),
            403,
            "User without plan workflow permission",
        )

        approved_result = require_status(checker_client.post(
            f"workflow/plans/{approved['id']}/rounds/1/decision",
            json={"action": "APPROVED", "reason": "Reviewed in local Docker smoke test."},
        ), 200, "Checker approval")
        rejected_result = require_status(checker_client.post(
            f"workflow/plans/{rejected['id']}/rounds/1/decision",
            json={"action": "REJECTED", "reason": "Please clarify the measurement plan."},
        ), 200, "Checker rejection")

        maker_approval = maker_client.get(f"workflow/plans/{approved['id']}")
        maker_rejection = maker_client.get(f"workflow/plans/{rejected['id']}")
        require_status(maker_approval, 200, "Maker reads approved plan")
        rejection_data = require_status(maker_rejection, 200, "Maker reads rejected plan")
        if approved_result["status"] != "APPROVED" or rejected_result["status"] != "REJECTED":
            raise RuntimeError("Checker decisions did not persist the expected states.")
        if not any(event["action"] == "REJECTED" for event in rejection_data["history"]):
            raise RuntimeError("Rejected decision is missing from persisted history.")

        def race_decision(action: str) -> int:
            with httpx.Client(base_url=base_url, timeout=20) as client:
                login(client, "checker", password)
                response = client.post(
                    f"workflow/plans/{racing['id']}/rounds/1/decision",
                    json={"action": action, "reason": f"Concurrent {action.lower()} smoke."},
                )
                return response.status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(race_decision, ("APPROVED", "REJECTED")))
        if sorted(outcomes) != [200, 409]:
            raise RuntimeError(f"Expected one concurrent decision and one conflict; received {outcomes}.")
        race_detail = require_status(
            checker_client.get(f"workflow/plans/{racing['id']}"),
            200,
            "read concurrent decision result",
        )
        final_actions = [event["action"] for event in race_detail["history"] if event["action"] in {"APPROVED", "REJECTED"}]
        if len(final_actions) != 1:
            raise RuntimeError("Concurrent decision persisted more than one final action.")

    print("PASS: seeded Maker created and submitted two plans with private images.")
    print("PASS: assigned Checker approved one plan and rejected another with a reason.")
    print("PASS: self-approval, Checker-as-Maker, and no-workflow-role access were blocked.")
    print("PASS: Auth cookie stayed separate from Judge Demo X-Demo-Actor identity.")
    print("PASS: concurrent opposite Checker decisions produced one decision and one conflict.")
    print(f"Synthetic smoke plan IDs: {approved['id']}, {rejected['id']}, {racing['id']}")


if __name__ == "__main__":
    main()
