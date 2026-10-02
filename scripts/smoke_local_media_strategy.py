"""Create three retained PostgreSQL smoke plans through the real Auth API and local models."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
import os
from time import perf_counter

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

from src.backend.api.app import app


DEPARTMENT = "Nori Pilot"
CHANNEL = "social"
POLICY_ID = "LOCAL_MEDIA_RULESET_1"
POLICY_RULE_ID = "PROHIBITED_CLAIM"
FORBIDDEN_TEXT = "UNAPPROVED_GUARANTEE"
LOCAL_OLLAMA_URLS = {
    "http://host.docker.internal:11434/v1",
    "http://127.0.0.1:11434/v1",
}
TEXT_MODEL = "organizationai-qwen3:4b-ctx8192"
TEXT_MODEL_DIGEST = "sha256:b2ef2f414e31e4e10ef46366751464631a5fa4b5c1bf183b1e3b9076ab2116ef"
VISUAL_MODEL_DIGEST = "sha256:1343d82ebee38e26a4dd6b0180b915eb91550184e67c505dea97509571c8f683"


def _require_local_configuration() -> None:
    visual_provider = app.state.auth_workflow_provider
    if (
        getattr(visual_provider, "model_id", None) != "qwen3-vl:4b"
        or getattr(visual_provider, "model_version", None) != VISUAL_MODEL_DIGEST
        or getattr(visual_provider, "base_url", None) not in LOCAL_OLLAMA_URLS
        or getattr(visual_provider, "allow_remote", True)
    ):
        raise RuntimeError("VLM extraction must use local qwen3-vl:4b through Ollama with remote access disabled.")
    for name in ("auth_workflow_media_provider", "auth_workflow_strategy_provider"):
        provider = getattr(app.state, name)
        settings = provider.settings
        if not settings.is_configured:
            raise RuntimeError(f"{name} is not configured: {settings.configuration_error or 'missing settings'}")
        media_task = name.endswith("media_provider")
        expected_prompt = "media-compliance-prompt-v5" if media_task else "strategy-evaluation-prompt-v5"
        expected_schema = "media-compliance-schema-v3" if media_task else "strategy-evaluation-schema-v5"
        if (
            settings.provider != "OPENAI_COMPATIBLE_CHAT_COMPLETIONS"
            or settings.model_id != TEXT_MODEL
            or settings.model_version != TEXT_MODEL_DIGEST
            or settings.base_url not in LOCAL_OLLAMA_URLS
            or settings.allow_remote
            or settings.reasoning_effort != "none"
            or settings.prompt_version != expected_prompt
            or settings.schema_version != expected_schema
        ):
            raise RuntimeError(f"{name} must use the pinned local Qwen3 alias with remote access disabled.")
    configuration = app.state.auth_workflow_configuration
    if configuration.media_policy is None or configuration.strategy_rubric is None:
        raise RuntimeError("The scoped synthetic policy and BA strategy rubric must be configured.")
    if configuration.policy.auto_approval_policy_enabled:
        raise RuntimeError("Refusing smoke run while auto-approval is enabled.")
    if configuration.media_policy.policy_id != POLICY_ID:
        raise RuntimeError("The local smoke policy has an unexpected policy ID.")
    if configuration.media_policy.scope_departments != (DEPARTMENT,):
        raise RuntimeError("The local smoke policy is not scoped to its dedicated department.")
    if configuration.media_policy.scope_channels != (CHANNEL,):
        raise RuntimeError("The smoke content policy is not scoped to the synthetic channel.")
    if not any(FORBIDDEN_TEXT in rule.forbidden_literals for rule in configuration.media_policy.rules):
        raise RuntimeError("The local smoke policy must contain its exact forbidden OCR literal.")


def _login(client: TestClient, username: str, password: str) -> None:
    response = client.post("/api/auth/login", json={"identifier": username, "password": password})
    if response.status_code != 200:
        raise RuntimeError(f"Local {username} login failed with HTTP {response.status_code}.")


def _image(text: str) -> bytes:
    image = Image.new("RGB", (1800, 620), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 82)
    except OSError:
        font = ImageFont.load_default(size=72)
    if text == FORBIDDEN_TEXT:
        # Keep the configured OCR literal on its own so the visual extractor
        # returns an unambiguous piece of evidence for the policy check.
        draw.text((72, 250), text, fill="black", font=font)
    else:
        draw.text((72, 86), "NORI PILOT CAMPAIGN", fill="black", font=font)
        draw.text((72, 250), text, fill="black", font=font)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _payload(title: str, *, research_gaps: bool = False) -> dict:
    return {
        "title": title,
        "objective": "Increase trial sign-ups for Nori products among micro-retailers in Ho Chi Minh City during October.",
        "summary": "Internal planning target: 200 trial sign-ups tracked by a campaign form. No external market evidence is supplied.",
        "department": DEPARTMENT,
        "start_date": "2026-10-01",
        "end_date": "2026-10-31",
        "budget_minor_units": "10000000",
        "currency": "VND",
        "target_audience": "First-time micro-retail customers in Ho Chi Minh City",
        "channels": [CHANNEL],
        "kpi_expected": (
            "Pilot target: 200 trial sign-ups tracked by the campaign form; baseline and conversion methodology are not established."
            if research_gaps else "200 trial sign-ups tracked by the campaign form"
        ),
        "notes": (
            "No audience research, channel benchmark, conversion baseline, or cost-per-acquisition evidence is available; these remain open research gaps, not established market facts."
            if research_gaps else "Nori pilot planning record; no external market evidence is supplied."
        ),
    }


def _create_and_submit(client: TestClient, checker_id: str, title: str, image_text: str,
                       *, research_gaps: bool = False) -> tuple[dict, float]:
    created = client.post("/api/workflow/plans", json={
        "checker_user_id": checker_id,
        "payload": _payload(title, research_gaps=research_gaps),
    })
    if created.status_code != 201:
        raise RuntimeError(f"Plan creation failed with HTTP {created.status_code}: {created.text[:400]}")
    plan = created.json()
    upload = client.post(
        f"/api/workflow/plans/{plan['id']}/attachments",
        data={"expected_revision": str(plan["revision"])},
        files={"file": ("synthetic-local-smoke.png", _image(image_text), "image/png")},
    )
    if upload.status_code != 200:
        raise RuntimeError(f"Synthetic image upload failed with HTTP {upload.status_code}: {upload.text[:400]}")
    plan = upload.json()
    started = perf_counter()
    submitted = client.post(
        f"/api/workflow/plans/{plan['id']}/submit",
        json={"expected_revision": plan["revision"]},
    )
    elapsed = perf_counter() - started
    if submitted.status_code != 200:
        raise RuntimeError(f"Submission failed with HTTP {submitted.status_code}: {submitted.text[:400]}")
    return submitted.json(), elapsed


def _check_case(name: str, plan: dict, submit_seconds: float, expected_media: str,
                *, report_strategy_gap: bool = False,
                expect_media_schema_failure: bool = False) -> list[str]:
    errors = []
    if plan["current_version"] != 1 or plan["current_round"] != 1:
        errors.append("first submission did not create Version 1 / Round 1")
    if plan["status"] != "PENDING_APPROVAL":
        errors.append(f"unexpected plan status {plan['status']}")
    if len(plan["ai_evaluations"]) != 1:
        errors.append("expected one persisted evaluation run")
        return errors

    run = plan["ai_evaluations"][0]
    media = run.get("media_evaluation") or {}
    strategy = run.get("strategy_evaluation") or {}
    media_result = media.get("result") or {}
    strategy_result = strategy.get("result") or {}
    if expect_media_schema_failure:
        accepted_literal = (
            run.get("status") == "SUCCEEDED"
            and media.get("status") == "SUCCEEDED"
            and media_result.get("outcome") == expected_media
        )
        safely_rejected = (
            run.get("status") == "FAILED"
            and media.get("status") == "FAILED"
            and media.get("error_code") == "INVALID_SCHEMA"
        )
        if not (accepted_literal or safely_rejected):
            errors.append(
                "Media literal case neither returned a validated review finding nor failed closed "
                f"({run.get('status')}/{media.get('status')}/{media.get('error_code')})"
            )
        if accepted_literal:
            found = any(
                item.get("rule_id") == POLICY_RULE_ID and item.get("severity") == "HARD_VIOLATION"
                for item in media_result.get("findings", [])
            )
            if not found:
                errors.append("Validated Media review omitted the configured hard finding")
    else:
        if run.get("status") != "SUCCEEDED":
            errors.append(f"evaluation run status is {run.get('status')}")
        if media.get("status") != "SUCCEEDED":
            errors.append(f"Media step status is {media.get('status')} ({media.get('error_code')})")
        elif media_result.get("outcome") != expected_media:
            errors.append(f"Media outcome {media_result.get('outcome')} did not match the smoke assertion {expected_media}")
    if strategy.get("status") != "SUCCEEDED":
        errors.append(f"Strategy step status is {strategy.get('status')} ({strategy.get('error_code')})")
    if len((strategy_result.get("criterion_scores") or [])) != 7:
        errors.append("Strategy result did not persist seven criteria")
    reported_gap = any((strategy_result.get(key) or []) for key in (
        "missing_facts", "critical_gaps", "evidence_conflicts"
    ))
    if report_strategy_gap and not reported_gap:
        errors.append("Strategy did not surface the explicitly stated research gaps")

    engine = plan["engine_decisions"][-1] if plan.get("engine_decisions") else None
    if not engine or engine["outcome"] != "HUMAN_REVIEW_REQUIRED":
        errors.append("disabled auto-approval did not leave the plan for Checker review")
    if strategy_result.get("criterion_scores"):
        weighted = sum(
            Decimal(str(item["score"])) * Decimal(str(item["weight"])) / Decimal(100)
            for item in strategy_result["criterion_scores"]
        )
        if weighted != Decimal(str(strategy_result.get("feasibility_score"))):
            errors.append("persisted Strategy score does not match backend Decimal weighting")

    visual = run.get("visual_extraction") or {}
    print(
        f"{name}: id={plan['id']} run={run.get('run_id')} version={run.get('version_number')} "
        f"round={run.get('round_number')} status={run.get('status')} "
        f"vlm={visual.get('model_id') or visual.get('model_version')} "
        f"media={media_result.get('outcome') or media.get('status') + '/' + str(media.get('error_code'))} "
        f"({media.get('latency_ms')}ms) "
        f"strategy={strategy_result.get('feasibility_score')} ({strategy.get('latency_ms')}ms) "
        f"strategy_gap_reported={reported_gap} submit={submit_seconds:.2f}s "
        f"checker={engine.get('outcome') if engine else 'MISSING'}"
    )
    if expected_media == "REVIEW_REQUIRED" and not expect_media_schema_failure:
        found = any(
            item.get("rule_id") == POLICY_RULE_ID and item.get("severity") == "HARD_VIOLATION"
            for item in media_result.get("findings", [])
        )
        if not found:
            errors.append("Media missed the scoped synthetic hard rule or failed to attach its finding")
    return errors


def main() -> int:
    _require_local_configuration()
    password = os.environ.get("AUTH_SEED_PASSWORD", "")
    if not password:
        raise RuntimeError("AUTH_SEED_PASSWORD must already be configured in the local backend environment.")

    suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    maker = TestClient(app)
    checker = TestClient(app)
    unrelated = TestClient(app)
    errors = []
    try:
        _login(maker, "maker", password)
        _login(checker, "checker", password)
        _login(unrelated, "admin", password)
        checker_response = maker.get("/api/workflow/checkers")
        if checker_response.status_code != 200:
            raise RuntimeError(f"Maker could not list checkers (HTTP {checker_response.status_code}).")
        assigned = next((item for item in checker_response.json() if item["display_name"] == "Demo Checker"), None)
        if assigned is None:
            raise RuntimeError("The seeded Demo Checker was not available for assignment.")

        cases = (
            ("synthetic-compliant", "SMOKE ALPHA CAMPAIGN ASSET", "PASS", False, False),
            ("synthetic-policy-marker", FORBIDDEN_TEXT, "REVIEW_REQUIRED", False, True),
            ("synthetic-research-gaps", "SMOKE GAMMA CAMPAIGN ASSET", "PASS", True, False),
        )
        records = []
        for index, (name, image_text, expected_media, incomplete, expect_media_schema_failure) in enumerate(cases, 1):
            title = f"Nori Pilot Campaign {suffix} case-{index}"
            plan, elapsed = _create_and_submit(
                maker, assigned["id"], title, image_text, research_gaps=incomplete
            )
            errors.extend(_check_case(
                name, plan, elapsed, expected_media, report_strategy_gap=incomplete,
                expect_media_schema_failure=expect_media_schema_failure,
            ))
            records.append(plan)

        first = records[0]
        plan_id = first["id"]
        attachment_id = first["attachments"][0]["id"]
        checker_detail = checker.get(f"/api/workflow/plans/{plan_id}")
        checker_media = checker.get(f"/api/workflow/plans/{plan_id}/attachments/{attachment_id}")
        if checker_detail.status_code != 200 or checker_media.status_code != 200:
            errors.append("Assigned Checker could not read the submitted plan and private image")
        if unrelated.get(f"/api/workflow/plans/{plan_id}").status_code not in (403, 404):
            errors.append("Unrelated Admin account could read a plan outside its assignment")
        if unrelated.get(f"/api/workflow/plans/{plan_id}/attachments/{attachment_id}").status_code not in (403, 404):
            errors.append("Unrelated Admin account could read a private image")
        maker_decision = maker.post(
            f"/api/workflow/plans/{plan_id}/rounds/1/decision",
            json={"action": "APPROVED"},
        )
        if maker_decision.status_code not in (401, 403):
            errors.append("Maker was able to call the Checker decision endpoint")

        before_reload = [item["evaluation_id"] for item in checker_detail.json()["ai_evaluations"]]
        reloaded = maker.get(f"/api/workflow/plans/{plan_id}")
        after_reload = [item["evaluation_id"] for item in reloaded.json()["ai_evaluations"]]
        if before_reload != after_reload:
            errors.append("Reload changed or duplicated the saved evaluation")

        decision = checker.post(
            f"/api/workflow/plans/{plan_id}/rounds/1/decision",
            json={
                "action": "APPROVED",
                "reason": "Checker reviewed the synthetic local evaluation.",
                "override_reason": "AI evaluation is incomplete; the assigned Checker manually reviewed the submitted plan.",
            },
        )
        if decision.status_code != 200 or decision.json().get("status") != "APPROVED":
            errors.append(
                f"Assigned Checker could not approve after review (HTTP {decision.status_code}): {decision.text[:300]}"
            )

        print(f"Checker queue read={checker_detail.status_code}; private image read={checker_media.status_code}; "
              f"unrelated plan/image={unrelated.get(f'/api/workflow/plans/{plan_id}').status_code}/"
              f"{unrelated.get(f'/api/workflow/plans/{plan_id}/attachments/{attachment_id}').status_code}; "
              f"Maker decision blocked={maker_decision.status_code}; reload IDs stable={before_reload == after_reload}; "
              f"Checker decision={decision.status_code}")
        print("Retained synthetic plan IDs: " + ", ".join(item["id"] for item in records))
    finally:
        maker.close()
        checker.close()
        unrelated.close()

    if errors:
        for error in errors:
            print("SMOKE FAILURE: " + error)
        return 1
    print("PASS: real Local VLM, Media and Strategy inference persisted to PostgreSQL; Checker/RBAC checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
