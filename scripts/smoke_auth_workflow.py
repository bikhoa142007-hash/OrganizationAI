"""Smoke-test the cookie-authenticated workflow against a running local API."""
from __future__ import annotations

import hashlib
import getpass
import json
import os
import struct
from pathlib import Path
from time import monotonic, sleep
from uuid import uuid4
import zlib

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


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


class SmokeRunState:
    """Persist draft identity before any attachment or submission work begins."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if self.path.exists():
            try:
                state = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raise RuntimeError(f"Smoke state file is unreadable: {self.path}") from None
            if not isinstance(state, dict) or not isinstance(state.get("plan_ids"), dict):
                raise RuntimeError(f"Smoke state file has an invalid shape: {self.path}")
        else:
            state = self._new_state()
        run_id = state.get("run_id")
        if not isinstance(run_id, str) or not run_id.strip():
            raise RuntimeError(f"Smoke state file is missing its run ID: {self.path}")
        self._state = state
        self._save()

    @property
    def completed(self) -> bool:
        return self._state.get("completed") is True

    @staticmethod
    def _new_state() -> dict:
        return {"run_id": uuid4().hex, "completed": False, "creation_started": {}, "plan_ids": {}}

    @property
    def run_id(self) -> str:
        return self._state["run_id"]

    def marker(self, scenario: str) -> str:
        return f"organizationai-smoke:{self.run_id}:{scenario}"

    def plan_id(self, scenario: str) -> str | None:
        value = self._state["plan_ids"].get(scenario)
        return value if isinstance(value, str) and value else None

    def creation_started(self, scenario: str) -> bool:
        return self._state.get("creation_started", {}).get(scenario) is True

    def assert_single_plan_scenario(self, scenario: str) -> None:
        other_ids = {
            key for key in self._state["plan_ids"]
            if key != scenario and self._state["plan_ids"].get(key)
        }
        other_attempts = {
            key for key, started in self._state.get("creation_started", {}).items()
            if key != scenario and started is True
        }
        if other_ids or other_attempts:
            raise RuntimeError("A smoke run may create or resume only one plan; refusing another scenario.")

    def mark_creation_started(self, scenario: str) -> None:
        self._state.setdefault("creation_started", {})[scenario] = True
        self._save()

    def save_plan_id(self, scenario: str, plan_id: str) -> None:
        if not isinstance(plan_id, str) or not plan_id.strip():
            raise RuntimeError("The workflow API returned a plan without an ID.")
        self._state["plan_ids"][scenario] = plan_id
        self._save()

    def mark_complete(self) -> None:
        self._state["completed"] = True
        self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(self._state, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)


def get_plan(client: httpx.Client, plan_id: str) -> dict:
    return require_status(client.get(f"workflow/plans/{plan_id}"), 200, "read smoke plan")


def wait_for_checker_review(client: httpx.Client, plan: dict, timeout_seconds: int = 180) -> dict:
    """Wait for persisted evaluation; polling reads the saved plan and never reruns AI."""
    plan_id = plan["id"]
    deadline = monotonic() + timeout_seconds
    latest = plan
    while True:
        if latest["status"] != "PENDING_APPROVAL":
            return latest
        round_number = latest["current_round"]
        version_number = latest["current_version"]
        has_evaluation = any(
            item["version_number"] == version_number and item["round_number"] == round_number
            for item in latest["ai_evaluations"]
        )
        has_decision = any(
            item["version_number"] == version_number and item["round_number"] == round_number
            and item["outcome"] == "HUMAN_REVIEW_REQUIRED"
            for item in latest["engine_decisions"]
        )
        if (latest["processing_stage"] == "HUMAN_REVIEW_REQUIRED"
                and has_evaluation and has_decision):
            return latest
        if monotonic() >= deadline:
            raise RuntimeError(
                f"Plan {plan_id} has not reached persisted Checker review; "
                "the runner stopped without resubmitting or rerunning evaluation."
            )
        sleep(1)
        latest = get_plan(client, plan_id)


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL", "").strip()
    if not value:
        env_file = Path(".env")
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and line.startswith("DATABASE_URL="):
                    value = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not value:
        raise RuntimeError("Cannot safely resolve a timed-out create without DATABASE_URL.")
    url = make_url(value)
    if os.name == "nt" and url.host in {"db", "organizationai-db-1"}:
        url = url.set(host="127.0.0.1", port=5433)
    return url.render_as_string(hide_password=False)


def find_plans_by_run_marker(marker: str) -> list[dict]:
    """Use read-only SQL for uncertain-create recovery; the API list route can repair stale runs."""
    engine = create_engine(
        _database_url(),
        connect_args={"options": "-c default_transaction_read_only=on"},
        pool_pre_ping=True,
    )
    try:
        with engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT id::text AS id, payload FROM auth_workflow_plans "
                "WHERE payload ->> 'notes' = :marker ORDER BY id"
            ), {"marker": marker}).mappings().all()
            return [{"id": row["id"], "payload": row["payload"]} for row in rows]
    finally:
        engine.dispose()


def unique_run_candidate(client: httpx.Client, marker: str) -> dict | None:
    matches = find_plans_by_run_marker(marker)
    if len(matches) > 1:
        ids = [str(plan.get("id", "<missing-id>")) for plan in matches]
        raise RuntimeError(
            "Multiple plans match the smoke run marker; refusing to select or delete any: "
            + ", ".join(ids)
        )
    if not matches:
        return None
    plan_id = matches[0].get("id")
    if not isinstance(plan_id, str) or not plan_id:
        raise RuntimeError("A smoke plan matching the run marker has no plan ID.")
    candidate = get_plan(client, plan_id)
    if not isinstance(candidate.get("payload"), dict) or candidate["payload"].get("notes") != marker:
        raise RuntimeError(f"Recovered smoke plan ID {plan_id} does not match the run marker.")
    return candidate


def create_or_recover_draft(
    client: httpx.Client,
    checker_id: str,
    title: str,
    state: SmokeRunState,
    scenario: str,
) -> dict:
    state.assert_single_plan_scenario(scenario)
    marker = state.marker(scenario)
    saved_id = state.plan_id(scenario)
    if saved_id:
        draft = get_plan(client, saved_id)
        if not isinstance(draft.get("payload"), dict) or draft["payload"].get("notes") != marker:
            raise RuntimeError(f"Saved smoke plan ID {saved_id} does not match this run marker.")
        return draft

    if state.creation_started(scenario):
        candidate = unique_run_candidate(client, marker)
        if candidate:
            plan_id = candidate.get("id")
            if not isinstance(plan_id, str) or not plan_id:
                raise RuntimeError("A smoke plan matching the run marker has no plan ID.")
            state.save_plan_id(scenario, plan_id)
            return candidate
        raise RuntimeError(
            "A create was already attempted but no matching plan is visible; "
            "the runner stopped without sending another create request."
        )

    payload = {
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
        "notes": marker,
    }
    body = {"checker_user_id": checker_id, "payload": payload}
    if not state.creation_started(scenario):
        state.mark_creation_started(scenario)

    try:
        response = client.post("workflow/plans", json=body)
    except httpx.TransportError:
        candidate = unique_run_candidate(client, marker)
        if candidate:
            draft = candidate
        else:
            raise RuntimeError(
                "Plan creation timed out and no matching run marker is visible; "
                "the runner stopped without retrying."
            ) from None
    else:
        if response.status_code != 201:
            raise RuntimeError(
                f"create Maker draft: expected HTTP 201, got HTTP {response.status_code}: "
                f"{response.text[:600]}"
            )
        try:
            draft = response.json()
        except ValueError:
            candidate = unique_run_candidate(client, marker)
            if candidate:
                draft = candidate
            else:
                raise RuntimeError("Create returned an unreadable response; no plan ID could be recovered.") from None

    plan_id = draft.get("id") if isinstance(draft, dict) else None
    returned_payload = draft.get("payload") if isinstance(draft, dict) else None
    if not isinstance(plan_id, str) or not plan_id.strip():
        raise RuntimeError("Create returned a plan without a valid ID.")
    state.save_plan_id(scenario, plan_id)
    if not isinstance(returned_payload, dict):
        raise RuntimeError("Create returned a plan without the documented payload field.")
    if returned_payload.get("title") != title or returned_payload.get("notes") != marker:
        raise RuntimeError("Create response did not match the submitted payload.title and run marker.")
    return draft


def create_and_submit(
    client: httpx.Client,
    checker_id: str,
    title: str,
    state: SmokeRunState,
    scenario: str,
) -> dict:
    draft = create_or_recover_draft(client, checker_id, title, state, scenario)
    if draft.get("status") != "DRAFT":
        return draft

    expected_hash = hashlib.sha256(SMOKE_PNG).hexdigest()
    if not any(item.get("content_hash") == expected_hash for item in draft.get("attachments", [])):
        try:
            uploaded = require_status(client.post(
                f"workflow/plans/{draft['id']}/attachments",
                data={"expected_revision": str(draft["revision"])},
                files={"file": ("smoke.png", SMOKE_PNG, "image/png")},
            ), 200, "upload private image")
        except httpx.TransportError:
            uploaded = get_plan(client, draft["id"])
            if not any(item.get("content_hash") == expected_hash for item in uploaded.get("attachments", [])):
                raise RuntimeError("Attachment upload result is uncertain; the runner will not upload it again.") from None
        draft = uploaded
    try:
        return require_status(client.post(
            f"workflow/plans/{draft['id']}/submit",
            json={"expected_revision": draft["revision"]},
        ), 200, "submit Maker plan")
    except httpx.TransportError:
        latest = get_plan(client, draft["id"])
        if latest.get("status") != "DRAFT":
            return latest
        raise RuntimeError("Submission result is uncertain; the runner stopped without resubmitting.") from None


def reject_round_one(checker: httpx.Client, plan: dict) -> dict:
    if plan["status"] == "REJECTED" and plan["current_round"] == 1:
        return plan
    if plan["status"] != "PENDING_APPROVAL" or plan["current_round"] != 1:
        raise RuntimeError("The one-plan smoke flow expected Version 1 / Round 1 in Checker review.")
    try:
        response = checker.post(
            f"workflow/plans/{plan['id']}/rounds/1/decision",
            json={
                "action": "REJECTED",
                "reason": "Clarify how verified outcomes are attributed to this campaign.",
                "override_reason": "The assigned Checker reviewed the submitted snapshot.",
            },
        )
    except httpx.TransportError:
        latest = get_plan(checker, plan["id"])
        if latest["status"] == "REJECTED" and latest["current_round"] == 1:
            return latest
        raise RuntimeError("Rejection result is uncertain; the runner stopped without retrying.") from None
    return require_status(response, 200, "Checker rejects Version 1")


def revise_rejected_plan(maker: httpx.Client, plan: dict) -> dict:
    revised_summary = "Revised synthetic plan with an explicit attribution method and review checkpoint."
    revised_notes = "The Checker feedback is addressed in the second submitted version."
    if plan["payload"].get("summary") == revised_summary and plan["payload"].get("notes") == revised_notes:
        return plan
    if plan["status"] != "REJECTED" or plan["current_version"] != 1:
        raise RuntimeError("The one-plan smoke flow expected a rejected Version 1 before revision.")

    payload = dict(plan["payload"])
    payload["summary"] = revised_summary
    payload["notes"] = revised_notes
    try:
        response = maker.put(
            f"workflow/plans/{plan['id']}",
            json={"expected_revision": plan["revision"], "payload": payload},
        )
    except httpx.TransportError:
        latest = get_plan(maker, plan["id"])
        if (latest["payload"].get("summary") == revised_summary
                and latest["payload"].get("notes") == revised_notes):
            return latest
        raise RuntimeError("Revision result is uncertain; the runner stopped without repeating the edit.") from None
    return require_status(response, 200, "Maker revises rejected plan")


def submit_revision(maker: httpx.Client, plan: dict) -> dict:
    if plan["status"] == "PENDING_APPROVAL" and plan["current_version"] == 2 and plan["current_round"] == 2:
        return plan
    if plan["status"] != "REJECTED" or plan["current_version"] != 1:
        raise RuntimeError("The one-plan smoke flow expected the revised rejected plan before resubmission.")
    try:
        response = maker.post(
            f"workflow/plans/{plan['id']}/submit",
            json={"expected_revision": plan["revision"]},
        )
    except httpx.TransportError:
        latest = get_plan(maker, plan["id"])
        if (latest["status"] == "PENDING_APPROVAL" and latest["current_version"] == 2
                and latest["current_round"] == 2):
            return latest
        raise RuntimeError("Resubmission result is uncertain; the runner stopped without retrying.") from None
    return require_status(response, 200, "Maker resubmits Version 2")


def approve_round_two(checker: httpx.Client, plan: dict) -> dict:
    if plan["status"] == "APPROVED" and plan["current_round"] == 2:
        return plan
    if plan["status"] != "PENDING_APPROVAL" or plan["current_round"] != 2:
        raise RuntimeError("The one-plan smoke flow expected Version 2 / Round 2 in Checker review.")
    try:
        response = checker.post(
            f"workflow/plans/{plan['id']}/rounds/2/decision",
            json={
                "action": "APPROVED",
                "reason": "The revised attribution method addresses the Checker feedback.",
                "override_reason": "The assigned Checker reviewed the revised submitted snapshot.",
            },
        )
    except httpx.TransportError:
        latest = get_plan(checker, plan["id"])
        if latest["status"] == "APPROVED" and latest["current_round"] == 2:
            return latest
        raise RuntimeError("Approval result is uncertain; the runner stopped without retrying.") from None
    return require_status(response, 200, "Checker approves Version 2")


def main() -> None:
    state_path = os.environ.get(
        "AUTH_WORKFLOW_SMOKE_STATE_FILE", "runtime/auth-workflow-smoke-state.json",
    )
    state = SmokeRunState(state_path)
    scenario = "maker-checker-cycle"
    if state.completed:
        print(f"Smoke run already completed; no new plan created. Plan ID: {state.plan_id(scenario)}")
        return
    state.assert_single_plan_scenario(scenario)

    password = getpass.getpass("Local AUTH_SEED_PASSWORD: ")
    if not password:
        raise SystemExit("A non-empty seed password is required.")
    base_url = input("API base URL [http://localhost:8010/api/]: ").strip()
    base_url = (base_url or "http://localhost:8010/api/").rstrip("/") + "/"
    suffix = state.run_id[:8]

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

        plan = create_and_submit(
            maker_client, checker["id"], f"Auth workflow smoke {suffix}", state, scenario,
        )
        plan = wait_for_checker_review(maker_client, plan)
        plan_id = plan["id"]
        if len(plan["ai_evaluations"]) < 1 or not plan["engine_decisions"]:
            raise RuntimeError("Submission did not persist its evaluation and deterministic Checker route.")
        if plan["processing_stage"] != "HUMAN_REVIEW_REQUIRED" or any(
            item["outcome"] != "HUMAN_REVIEW_REQUIRED" for item in plan["engine_decisions"]
        ):
            raise RuntimeError("The smoke plan did not fail closed to human review.")

        if plan["status"] == "PENDING_APPROVAL" and plan["current_round"] == 1:
            own_decision = maker_client.post(
                f"workflow/plans/{plan_id}/rounds/1/decision",
                json={"action": "APPROVED"},
            )
            require_status(own_decision, 403, "Maker self-approval block")
        maker_only_action = checker_client.post("workflow/plans", json={"payload": {}})
        require_status(maker_only_action, 403, "Checker cannot create as Maker")
        require_status(admin_client.get("workflow/plans"), 403, "Admin without Maker/Checker permission")
        require_status(
            admin_client.get(f"workflow/plans/{plan_id}"),
            403,
            "User without plan workflow permission",
        )

        if plan["status"] == "PENDING_APPROVAL" and plan["current_round"] == 1:
            blank_rejection = checker_client.post(
                f"workflow/plans/{plan_id}/rounds/1/decision",
                json={"action": "REJECTED", "reason": "   "},
            )
            require_status(blank_rejection, 422, "blank rejection reason is blocked")
        if plan["status"] == "PENDING_APPROVAL" and plan["current_round"] == 1:
            plan = reject_round_one(checker_client, plan)
        if plan["status"] == "REJECTED" and plan["current_round"] == 1:
            if not any(event["action"] == "REJECTED" for event in plan["history"]):
                raise RuntimeError("The first Checker rejection is missing from persisted history.")
            plan = revise_rejected_plan(maker_client, plan)
            plan = submit_revision(maker_client, plan)
            plan = wait_for_checker_review(maker_client, plan)

        if (plan["status"] != "PENDING_APPROVAL" or plan["current_version"] != 2
                or plan["current_round"] != 2 or len(plan["ai_evaluations"]) != 2):
            if not (plan["status"] == "APPROVED" and plan["current_version"] == 2
                    and plan["current_round"] == 2 and len(plan["ai_evaluations"]) == 2):
                raise RuntimeError("Resubmission did not create Version 2 / Round 2 with a second evaluation.")
        if len(plan["versions"]) != 2:
            raise RuntimeError("Resubmission did not create Version 2 / Round 2 with a second evaluation.")
        original_evaluation = plan["ai_evaluations"][0]
        original_version = plan["versions"][0]

        if plan["status"] == "PENDING_APPROVAL":
            plan = approve_round_two(checker_client, plan)
        final_plan = require_status(maker_client.get(f"workflow/plans/{plan_id}"), 200, "Maker reads approved plan")
        if final_plan["status"] != "APPROVED" or final_plan["current_version"] != 2:
            raise RuntimeError("Checker approval of Version 2 did not persist.")
        if final_plan["versions"][0] != original_version or final_plan["ai_evaluations"][0] != original_evaluation:
            raise RuntimeError("The first submitted version or AI evaluation changed after resubmission.")
        if not any(event["action"] == "REJECTED" for event in final_plan["history"]):
            raise RuntimeError("The rejection is missing from the final audit history.")
        if not any(event["action"] == "APPROVED" for event in final_plan["history"]):
            raise RuntimeError("The approval is missing from the final audit history.")

    state.mark_complete()
    print("PASS: one synthetic plan completed Maker submit → Checker reject → Maker revision/resubmit → Checker approve.")
    print("PASS: V1/R1 and its AI evaluation remained unchanged after V2/R2.")
    print("PASS: self-approval, Checker-as-Maker, blank rejection reasons, and no-workflow-role access were blocked.")
    print("PASS: Auth cookie stayed separate from Judge Demo X-Demo-Actor identity.")
    print(f"Synthetic smoke plan ID: {plan_id}")


if __name__ == "__main__":
    main()
