"""Public Judge endpoints that do not use Auth, shared demo state, or persistence.

This router is intentionally not mounted by this module. D owns shared application
composition and must review isolation and quota controls before making it public.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from time import perf_counter
from time import monotonic
from typing import Any, TypeVar
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool

from src.backend.api.errors import error_response
from src.backend.api.public_judge_schemas import (
    PublicJudgeInputRequest,
    PublicJudgeInputResponse,
    PublicJudgeActionRequest,
    PublicJudgeActionResponse,
    PublicJudgeRunRequest,
    PublicJudgeRunResponse,
)


MAX_BODY_BYTES = 16 * 1024
JUDGE_INPUT_POLICY_VERSION = "JUDGE-INPUT-SIMULATION-1.0"
JUDGE_INPUT_BUDGET_LIMIT_VND = 100_000_000
JUDGE_INPUT_DEPARTMENT = "DEMO-DEPT-01"
JUDGE_INPUT_CHANNELS = frozenset({"DEMO_SOCIAL", "DEMO_EMAIL"})
ACTION_TTL_SECONDS = 15 * 60
MAX_ACTION_CASES = 3_000
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

router = APIRouter(prefix="/api/public/judge", tags=["Public Challenge A Judge"])
RequestModel = TypeVar("RequestModel", bound=BaseModel)


class _RequestError(Exception):
    def __init__(self, code: str, message: str, status: int):
        self.code = code
        self.message = message
        self.status = status


class PublicJudgeActionError(Exception):
    def __init__(self, code: str, status_code: int):
        self.code = code
        self.status_code = status_code


@dataclass
class _ActionCase:
    recommendation: str
    input_sha256: str
    reason: str
    audit: list[dict[str, Any]]
    expires_at: float
    final_response: dict[str, Any] | None = None
    idempotency_key: str | None = None
    idempotency_action: str | None = None
    idempotency_reason: str | None = None


class PublicJudgeActionStore:
    """Bounded process-local state for synthetic, post-result human actions."""

    def __init__(self, *, clock=monotonic, max_cases: int = MAX_ACTION_CASES,
                 ttl_seconds: int = ACTION_TTL_SECONDS):
        if max_cases < 1 or ttl_seconds < 1:
            raise ValueError("Public Judge action-store limits must be positive.")
        self._clock = clock
        self._max_cases = max_cases
        self._ttl_seconds = ttl_seconds
        self._records: OrderedDict[tuple[str, str], _ActionCase] = OrderedDict()
        self._lock = RLock()

    def register_run(self, run_id: str, cases: list[dict[str, Any]]) -> bool:
        now = self._clock()
        with self._lock:
            self._prune(now)
            keys = [(run_id, case["case_id"]) for case in cases]
            if len(keys) != len(set(keys)) or any(key in self._records for key in keys):
                return False
            if any(
                case.get("recommendation") not in {"AUTO_APPROVED", "HUMAN_REVIEW_REQUIRED"}
                or not isinstance(case.get("input_sha256"), str)
                or SHA256_PATTERN.fullmatch(case["input_sha256"]) is None
                for case in cases
            ):
                return False
            self._make_room(len(keys))
            if len(self._records) + len(keys) > self._max_cases:
                return False
            for key, case in zip(keys, cases):
                input_sha256 = case["input_sha256"]
                self._records[key] = _ActionCase(
                    recommendation=case["recommendation"],
                    input_sha256=input_sha256,
                    reason=str(case.get("reason") or "Synthetic Judge result.")[:500],
                    audit=deepcopy(case.get("audit") or []),
                    expires_at=now + self._ttl_seconds,
                )
            return True

    def perform_action(self, run_id: str, case_id: str, action: str, reason: str,
                       idempotency_key: str) -> dict[str, Any]:
        now = self._clock()
        key = (run_id, case_id)
        with self._lock:
            self._prune(now)
            record = self._records.get(key)
            if record is None:
                raise PublicJudgeActionError("ACTION_SESSION_UNAVAILABLE", 404)
            if record.idempotency_key == idempotency_key:
                if record.idempotency_action != action or record.idempotency_reason != reason:
                    raise PublicJudgeActionError("IDEMPOTENCY_CONFLICT", 409)
                replay = deepcopy(record.final_response)
                if replay is None:
                    raise PublicJudgeActionError("ACTION_SESSION_UNAVAILABLE", 404)
                replay["idempotent_replay"] = True
                return replay
            if record.final_response is not None:
                raise PublicJudgeActionError("ACTION_ALREADY_FINAL", 409)

            status = {"APPROVE": "HUMAN_APPROVED", "REJECT": "HUMAN_REJECTED", "STOP": "STOPPED"}[action]
            is_override = record.recommendation == "AUTO_APPROVED"
            action_suffix = {"APPROVE": "APPROVED", "REJECT": "REJECTED", "STOP": "STOPPED"}[action]
            audit_action = f"HUMAN_OVERRIDE_{action_suffix}" if is_override else f"HUMAN_{action_suffix}"
            timestamp = _now()
            event = {
                "event_id": "AUDIT-" + uuid4().hex,
                "action": audit_action,
                "timestamp": timestamp,
                "input_sha256": record.input_sha256,
                "reason": reason,
                "actor": "ANONYMOUS_PUBLIC_JUDGE",
            }
            audit = [*record.audit, event]
            result = {
                "run_id": run_id,
                "case_id": case_id,
                "status": status,
                "action": action,
                "is_override": is_override,
                "timestamp": timestamp,
                "input_sha256": record.input_sha256,
                "reason": reason,
                "audit": audit,
                "idempotent_replay": False,
            }
            record.final_response = deepcopy(result)
            record.idempotency_key = idempotency_key
            record.idempotency_action = action
            record.idempotency_reason = reason
            record.audit = audit
            return result

    def _prune(self, now: float) -> None:
        expired = [key for key, record in self._records.items() if record.expires_at <= now]
        for key in expired:
            del self._records[key]

    def _make_room(self, needed: int) -> None:
        while len(self._records) + needed > self._max_cases:
            completed = next((key for key, value in self._records.items() if value.final_response is not None), None)
            if completed is None:
                return
            del self._records[completed]


def _action_store(request: Request) -> PublicJudgeActionStore:
    store = getattr(request.app.state, "public_judge_action_store", None)
    if store is None:
        store = PublicJudgeActionStore()
        request.app.state.public_judge_action_store = store
    return store


def _input_hash(row: dict[str, Any]) -> str:
    for event in row.get("audit", []):
        candidate = event.get("input_sha256")
        if isinstance(candidate, str) and SHA256_PATTERN.fullmatch(candidate):
            return candidate
    canonical = json.dumps(row.get("input") or {}, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _correlation_id(request: Request) -> str:
    return getattr(request.state, "correlation_id", None) or "judge-" + uuid4().hex


def _no_store(response: Response, correlation_id: str) -> Response:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Correlation-ID"] = correlation_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _error(code: str, message: str, status: int, correlation_id: str) -> JSONResponse:
    response = error_response(code, message, correlation_id, status)
    return _no_store(response, correlation_id)  # type: ignore[return-value]


async def _parse_limited_json(request: Request, model: type[RequestModel]) -> RequestModel:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise _RequestError("VALIDATION_ERROR", "Content-Type must be application/json.", 422)

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_BODY_BYTES:
                raise _RequestError("INPUT_TOO_LARGE", "Request body exceeds the 16 KiB limit.", 413)
        except ValueError:
            raise _RequestError("VALIDATION_ERROR", "Invalid Content-Length.", 422) from None

    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise _RequestError("INPUT_TOO_LARGE", "Request body exceeds the 16 KiB limit.", 413)
        chunks.append(chunk)
    try:
        value = json.loads(b"".join(chunks))
        return model.model_validate(value, strict=True)
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError, TypeError):
        # Do not include validation details: Pydantic can attach submitted values.
        raise _RequestError("VALIDATION_ERROR", "Request fields are invalid or not allowed.", 422) from None


def _audit_projection(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    projected = []
    for event in events:
        projected.append({
            "event_id": event.get("event_id"),
            "action": event.get("action"),
            "timestamp": event.get("timestamp") or event.get("created_at"),
            "input_sha256": event.get("input_hash"),
            "reason": event.get("reason"),
        })
    return projected


def _question_projection(question: dict[str, Any]) -> dict[str, Any]:
    return {
        "category": question.get("category"),
        "question": question.get("question"),
        "disputed_or_missing_fact": question.get("disputed_or_missing_fact"),
        "applicable_rule_or_limit": question.get("applicable_rule_or_limit"),
        "reason": question.get("reason"),
        "evidence_references": question.get("evidence_reference") or question.get("evidence_references") or [],
    }


def _fixed_row(row: dict[str, Any]) -> dict[str, Any]:
    actual = row.get("actual") or {}
    decision = actual.get("decision") or {}
    evaluation = actual.get("evaluation") or {}
    plan = actual.get("plan") or {}
    expected = row.get("expected") or {}
    failed = bool(row.get("error") or row.get("differences"))
    status = "ERROR" if row.get("error") else "FAIL" if failed else "PASS"
    evidence = []
    for item in evaluation.get("evidence", []):
        evidence.append({
            "reference": item.get("evidence_id") or item.get("evidence_ref") or item.get("source_ref"),
            "kind": item.get("kind") or item.get("evidence_type"),
            "observation": item.get("observation") or item.get("observed_text") or item.get("description"),
        })
    return {
        "case_id": row.get("case_id"),
        "case_name": row.get("case_name"),
        "status": status,
        "passed": status == "PASS",
        "expected_action": expected.get("route"),
        "expected_category": expected.get("primary_category"),
        "actual_action": decision.get("outcome"),
        "actual_category": decision.get("escalation_category"),
        "started_at": row.get("started_at"),
        "completed_at": row.get("completed_at"),
        "duration_ms": row.get("duration_ms"),
        "reason": "Run case failed inside the isolated Judge." if row.get("error") else "; ".join(row.get("differences", [])) or decision.get("reason"),
        "input": plan.get("payload"),
        "evidence": evidence,
        "questions": [_question_projection(item) for item in actual.get("questions", [])],
        "applied_rule_ids": decision.get("applied_rule_ids", []),
        "policy_version": decision.get("policy_version") or evaluation.get("policy_version"),
        "model_version": evaluation.get("model_version"),
        "audit": _audit_projection(actual.get("audit", [])),
    }


def _evaluate_input(value: PublicJudgeInputRequest) -> tuple[str, str | None, str, str | None]:
    if value.department != JUDGE_INPUT_DEPARTMENT or value.channel not in JUDGE_INPUT_CHANNELS or value.currency != "VND":
        reason = (
            f"Judge simulation scope allows department {JUDGE_INPUT_DEPARTMENT}, channels "
            f"{', '.join(sorted(JUDGE_INPUT_CHANNELS))}, and VND. Submitted department/channel/currency "
            "are user supplied and remain unverified."
        )
        question = (
            f"Bạn nhập department={value.department}, channel={value.channel}, currency={value.currency}. "
            f"Hãy xác nhận đơn vị phụ trách, kênh và loại tiền có thuộc phạm vi thử nghiệm "
            f"{JUDGE_INPUT_DEPARTMENT}/{', '.join(sorted(JUDGE_INPUT_CHANNELS))}/VND hay không."
        )
        return "HUMAN_REVIEW_REQUIRED", "POLICY_OUT_OF_SCOPE", reason, question

    if value.source_budget_vnd is None or value.budget_vnd != value.source_budget_vnd:
        source = "chưa được cung cấp" if value.source_budget_vnd is None else f"{value.source_budget_vnd:,} VND"
        reason = (
            f"Các trường do người dùng cung cấp chưa khớp: budget_vnd={value.budget_vnd:,} VND; "
            f"source_budget_vnd={source}. Judge không xác nhận giá trị nào là đúng."
        )
        question = (
            f"Form bạn nhập budget_vnd={value.budget_vnd:,} VND, còn source_budget_vnd={source}. "
            "Hai trường này chưa chứng minh ngân sách chính thức. Hãy chỉ rõ nguồn có thẩm quyền và "
            "giá trị cần dùng; hiện không thể coi một trong hai là sự thật đã xác minh."
        )
        return "HUMAN_REVIEW_REQUIRED", "FACT_UNCERTAIN", reason, question

    if value.budget_vnd > JUDGE_INPUT_BUDGET_LIMIT_VND:
        reason = (
            f"Budget do người dùng cung cấp ({value.budget_vnd:,} VND) vượt trần mô phỏng "
            f"{JUDGE_INPUT_BUDGET_LIMIT_VND:,} VND; đây chỉ là kết quả thử, không phải quyết định phê duyệt thật."
        )
        question = (
            f"Hai trường ngân sách bạn nhập cùng là {value.budget_vnd:,} VND, vượt trần mô phỏng "
            f"{JUDGE_INPUT_BUDGET_LIMIT_VND:,} VND. Checker có thẩm quyền phù hợp cần xác minh hạn mức "
            "áp dụng và quyết định bước tiếp theo."
        )
        return "HUMAN_REVIEW_REQUIRED", "AUTHORITY_EXCEEDED", reason, question

    reason = (
        "Các trường user-supplied khớp với phạm vi và trần của Judge simulation. "
        "Đây là kết quả MOCK minh họa, chưa xác minh dữ liệu và không tạo quyết định thật."
    )
    return "SIMULATED_AUTO_APPROVE", None, reason, None


@router.post("/runs")
async def run_fixed_suite(request: Request):
    correlation_id = _correlation_id(request)
    started = perf_counter()
    try:
        body = await _parse_limited_json(request, PublicJudgeRunRequest)
    except _RequestError as exc:
        return _error(exc.code, exc.message, exc.status, correlation_id)

    try:
        # The oracle and all case content remain server-owned in run_suite.
        from src.verify.runner import run_suite

        source_rows = await run_in_threadpool(run_suite, body.suite)
    except Exception:
        return _error("UNAVAILABLE", "Judge suite could not complete.", 503, correlation_id)

    try:
        rows = [_fixed_row(row) for row in source_rows]
        completed_at = _now()
        run_id = "JUDGE-" + uuid4().hex
        result = PublicJudgeRunResponse.model_validate({
            "run_id": run_id,
            "suite": body.suite,
            "status": "ERROR" if any(row["status"] == "ERROR" for row in rows) else "COMPLETED",
            "mode": "MOCK",
            "data_classification": "SYNTHETIC",
            "started_at": rows[0]["started_at"] if rows else completed_at,
            "completed_at": completed_at,
            "duration_ms": max(0, int((perf_counter() - started) * 1000)),
            "summary": {
                "total_cases": len(rows),
                "passed_cases": sum(row["status"] == "PASS" for row in rows),
                "failed_cases": sum(row["status"] == "FAIL" for row in rows),
                "error_cases": sum(row["status"] == "ERROR" for row in rows),
            },
            "rows": rows,
        }, strict=True).model_dump(mode="json")
        action_cases = []
        for row in result["rows"]:
            recommendation = row.get("actual_action")
            if row.get("status") == "ERROR" or recommendation not in {"AUTO_APPROVED", "HUMAN_REVIEW_REQUIRED"}:
                continue
            input_sha256 = _input_hash(row)
            if not row["audit"]:
                row["audit"] = [{
                    "event_id": "AUDIT-" + uuid4().hex,
                    "action": "ENGINE_RESULT_RECORDED",
                    "timestamp": row.get("completed_at") or completed_at,
                    "input_sha256": input_sha256,
                    "reason": row.get("reason") or "Synthetic Judge result.",
                }]
            else:
                for event in row["audit"]:
                    if not event.get("input_sha256") or SHA256_PATTERN.fullmatch(event["input_sha256"]) is None:
                        event["input_sha256"] = input_sha256
            row["human_action_available"] = True
            row["human_action_status"] = "PENDING"
            action_cases.append({
                "case_id": row["case_id"],
                "recommendation": recommendation,
                "input_sha256": input_sha256,
                "reason": row.get("reason"),
                "audit": row["audit"],
            })
        if not _action_store(request).register_run(run_id, action_cases):
            return _error("JUDGE_CAPACITY_REACHED", "Judge cannot retain another synthetic review right now.", 503, correlation_id)
        result = PublicJudgeRunResponse.model_validate(result, strict=True).model_dump(mode="json")
    except Exception:
        return _error("UNAVAILABLE", "Judge response failed schema validation.", 503, correlation_id)
    return _no_store(JSONResponse(result), correlation_id)


@router.post("/input-runs")
async def run_user_input(request: Request):
    correlation_id = _correlation_id(request)
    try:
        value = await _parse_limited_json(request, PublicJudgeInputRequest)
    except _RequestError as exc:
        return _error(exc.code, exc.message, exc.status, correlation_id)

    started_at = _now()
    started = perf_counter()
    canonical_input = json.dumps(value.model_dump(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    input_sha256 = hashlib.sha256(canonical_input).hexdigest()
    outcome, category, reason, question = _evaluate_input(value)
    completed_at = _now()
    elapsed = max(0, int((perf_counter() - started) * 1000))
    try:
        run_id = "JUDGE-" + uuid4().hex
        result = PublicJudgeInputResponse.model_validate({
            "run_id": run_id,
            "mode": "MOCK",
            "processing_mode": "DETERMINISTIC_INPUT_SIMULATION",
            "data_classification": "USER_SUPPLIED_UNVERIFIED",
            "quality_status": "NOT_MEASURED",
            "outcome": outcome,
            "category": category,
            "policy_version": JUDGE_INPUT_POLICY_VERSION,
            "reason": reason,
            "handoff_question": question,
            "started_at": started_at,
            "completed_at": completed_at,
            "duration_ms": elapsed,
            "audit": {
                "action": "INPUT_EVALUATED",
                "timestamp": completed_at,
                "input_sha256": input_sha256,
                "reason": reason,
            },
        }, strict=True).model_dump(mode="json")
        recommendation = "AUTO_APPROVED" if outcome == "SIMULATED_AUTO_APPROVE" else "HUMAN_REVIEW_REQUIRED"
        if not _action_store(request).register_run(run_id, [{
            "case_id": "NEW_INPUT",
            "recommendation": recommendation,
            "input_sha256": input_sha256,
            "reason": reason,
            "audit": [{
                "event_id": "AUDIT-" + uuid4().hex,
                "action": "INPUT_EVALUATED",
                "timestamp": completed_at,
                "input_sha256": input_sha256,
                "reason": reason,
            }],
        }]):
            return _error("JUDGE_CAPACITY_REACHED", "Judge cannot retain another synthetic review right now.", 503, correlation_id)
        result["human_action_available"] = True
        result["human_action_status"] = "PENDING"
        result = PublicJudgeInputResponse.model_validate(result, strict=True).model_dump(mode="json")
    except Exception:
        return _error("UNAVAILABLE", "Judge response failed schema validation.", 503, correlation_id)
    return _no_store(JSONResponse(result), correlation_id)


@router.post("/runs/{run_id}/cases/{case_id}/action")
async def record_human_action(request: Request, run_id: str, case_id: str):
    correlation_id = _correlation_id(request)
    try:
        body = await _parse_limited_json(request, PublicJudgeActionRequest)
    except _RequestError as exc:
        return _error(exc.code, exc.message, exc.status, correlation_id)

    idempotency_key = request.headers.get("Idempotency-Key", "").strip()
    if not idempotency_key:
        return _error("IDEMPOTENCY_KEY_REQUIRED", "A UUID Idempotency-Key is required.", 422, correlation_id)
    try:
        parsed_key = UUID(idempotency_key)
        if str(parsed_key) != idempotency_key.lower():
            raise ValueError
        idempotency_key = str(parsed_key)
    except (ValueError, AttributeError):
        return _error("IDEMPOTENCY_KEY_INVALID", "Idempotency-Key must be a UUID.", 422, correlation_id)

    try:
        result = _action_store(request).perform_action(
            run_id, case_id, body.action, body.reason, idempotency_key,
        )
    except PublicJudgeActionError as exc:
        messages = {
            "ACTION_SESSION_UNAVAILABLE": "The synthetic case is unavailable or expired.",
            "ACTION_ALREADY_FINAL": "This synthetic case already has a final human action.",
            "IDEMPOTENCY_CONFLICT": "This Idempotency-Key was already used for another action.",
        }
        return _error(exc.code, messages.get(exc.code, "Judge action could not be recorded."), exc.status_code, correlation_id)

    try:
        payload = PublicJudgeActionResponse.model_validate(result, strict=True).model_dump(mode="json")
    except Exception:
        return _error("UNAVAILABLE", "Judge action response failed schema validation.", 503, correlation_id)
    return _no_store(JSONResponse(payload), correlation_id)
