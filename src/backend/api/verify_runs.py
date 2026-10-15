"""Authenticated transport for the synthetic Verify suite."""

import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import Response

from src.backend.api.auth import AuthenticatedPrincipal, _check_browser_origin, require_role
from src.verify.manager import VerifyRunConflict, VerifyRunManager, VerifyRunNotFound


router = APIRouter(prefix="/api/workflow/verify/runs", tags=["authenticated Verify"])


def _manager(request: Request) -> VerifyRunManager:
    manager = getattr(request.app.state, "verify_run_manager", None)
    if not isinstance(manager, VerifyRunManager):
        raise RuntimeError("Verify is unavailable in this application profile.")
    return manager


@router.post("", status_code=202)
def start_verify_run(
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=200),
    principal: AuthenticatedPrincipal = Depends(require_role("ADMIN")),
):
    _check_browser_origin(request)
    try:
        return _manager(request).start(str(principal.id), idempotency_key)
    except VerifyRunConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/latest")
def latest_verify_run(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_role("ADMIN")),
):
    try:
        return _manager(request).latest(str(principal.id))
    except VerifyRunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{run_id}")
def get_verify_run(
    run_id: str,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_role("ADMIN")),
):
    try:
        return _manager(request).get(str(principal.id), str(run_id))
    except VerifyRunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{run_id}/report")
def download_verify_report(
    run_id: str,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_role("ADMIN")),
):
    try:
        report = _manager(request).report(str(principal.id), str(run_id))
    except VerifyRunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    safe_name = str(run_id).replace("-", "")[:24]
    return Response(
        content=json.dumps(report, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="verify-{safe_name}.json"',
        },
    )
