# Handoff: notification checkpoint independence — 2026-10-11

## Outcome

**PASS — the notification package runs from the isolated checkpoint `f728de097351e415cedd0c52586ae08c9ee8f46a` without uncommitted AI/Judge changes.** This is verification of that commit only; Scope 1 remains **PARTIAL**.

- Verification checkout: isolated verification worktree (local path omitted from this handoff), detached at the exact target SHA. It was clean before tests.
- New run: `cf81891ccaf24afb8df7fc95794ba6c4`; migration head `20261011_11`.
- Main evidence: `docs/integration/evidence/auth-postgres-notifications/cf81891ccaf24afb8df7fc95794ba6c4/notification-postgres-evidence.json`.
- Fingerprint reconciliation: `docs/integration/evidence/auth-postgres-notifications/cf81891ccaf24afb8df7fc95794ba6c4/checkpoint-independence-evidence.json`.
- Provider: `MOCK_VLM`; no live inference.
- Backend runtime: image `organizationai-backend:latest` (`sha256:d3d41f59d89820cc0c832e27c1b5bca56768986c4009cceee454b83839233f1a`), interpreter `/usr/local/bin/python` 3.13.15; pytest 9.1.1, SQLAlchemy 2.1.1, FastAPI 0.141.1, psycopg 3.3.6. PostgreSQL image `postgres:16`.

## Fingerprint and source independence

The older c285 evidence records HEAD `a806fbf1a816764c4f1dd8713b60579aa910a1fb`, so its PASS is not treated as commit-bound evidence for f728. Its 13 expected source hashes all match the preserved source tree. In the clean checkout, 7 raw hashes match directly; 6 differ only because `core.autocrlf=true` checked those files out with CRLF. After normalizing CRLF to LF, all 13 files match the preserved source content. The new run then records SHA-256 fingerprint `fad6aa38855db8c27d4b39544912993343073358de19593809e3fd4ac73397b5`; all 13 hashes and the digest were independently recomputed from the clean checkout.

The committed runner mounts the verification worktree as `/app` for both backend Python commands and the API container. Its imported AI/workflow modules are tracked at the target commit. No uncommitted AI/Judge file was mounted or needed. The clean checkout lacked ignored frontend `node_modules`; `npm ci --prefer-offline --no-audit --no-fund` installed 114 packages from the committed lockfile without changing tracked files.

The runner hardcodes the named feature branch and refuses detached HEAD. To test this exact detached commit, a temporary launcher outside the worktree mapped its root/helper paths and allowed only the exact f728 SHA. Reversing its four substitutions reproduces the committed runner exactly. The committed runner and application files were not edited. The temporary launcher was removed.

## Verification

- Empty PostgreSQL database migrated to `20261011_11`: **PASS**.
- Synthetic PostgreSQL database at `20261010_10` seeded and upgraded to `20261011_11`: **PASS**; existing synthetic rows remained unchanged.
- PostgreSQL notification acceptance test: **1 passed** (one Starlette/httpx deprecation warning).
- Acceptance assertions cover assigned-recipient routing, replay/idempotency, transactional rollback, ownership/read behavior, link authorization, and notification privacy. Auto-approve is exercised only with synthetic policy in the runner-owned temporary database; no live policy was enabled.
- Auth browser E2E: **3 passed, 0 skipped, 0 unexpected, 0 flaky**. The flow verifies the assigned Checker receives and reads the submit notice, then the Maker receives and reads the decision notice while opening the correct plan. Retry/replay and other notification contract assertions are in the same PostgreSQL acceptance test.
- Temporary DB/API containers and network were cleaned up; pre-existing container IDs were preserved. No live application database was used.

The runner evidence itself is `PASS` with `error=null`. The outer PowerShell launcher returned exit code 1 only because its cleanup command addressed the temporary launcher incorrectly after the runner completed; I verified the path was under `%TEMP%` and removed that exact file. No test assertion failed.

## Scope 1 gaps remain

The notification package is independently verified; this does not complete Scope 1. Remaining items from the existing traceability include SLA persistence/configuration/warning behavior, employee/admin ownership and PostgreSQL validation for custom-role administration, internal notes and their permissions, business configuration screens for AI/budget/rubric policies, real Local VLM inference and digest provenance, manual pipeline retry/dashboard acceptance, and PO/Stakeholder approval of Scope v1.1. Judge Đề A remains separate: no public PASS, no verified live inference, and session isolation/quota/cross-session evidence still need work. Do not change the pinned digest, bypass Auth, or deploy based on this notification result.

## SLA proposal for PO decision

All values below remain proposals, not approved policy.

| Decision | Proposed value | PO confirmation needed |
|---|---|---|
| Duration | 24 continuous calendar hours per approval round | Different duration by plan type or department? |
| Warning thresholds | One warning at 4 hours remaining; one overdue notice after the deadline | Repeat overdue reminders? |
| Time basis | Continuous hours, no work calendar/holiday logic; store UTC and display Asia/Saigon | Accept this Phase 1 simplification? |
| Start/end | Start after successful submit into `PENDING_APPROVAL`; end at approve, reject, or auto-approve | Include AI evaluation time, or start only at `HUMAN_REVIEW_REQUIRED`? |
| Resubmit/reassign | New round on resubmit gets a new deadline; reassignment in the same round keeps its deadline | Confirm no reset on reassignment? |
| Recipients | In-app Maker and currently assigned Checker; reassignment alerts Maker and new Checker; configuration failures go to Admin | Notify the former Checker too? |

## Preservation and next safe work package

The existing continuation worktree was not mounted or written by this run; after verification it remains at HEAD `f728de097351e415cedd0c52586ae08c9ee8f46a` on `codex/scope1-phase1-judge-continuation-20261011` with its local edits still present. At the end of the verification run, no commit, push, PR, merge, deploy, or live DB/container operation had been performed; these evidence files and this handoff were then uncommitted. For publication, captured test email addresses in `notification-postgres-evidence.json` are redacted, and raw logs are excluded.

Next safe work: obtain PO decisions on the SLA table and name an Admin/owner; then implement SLA persistence, warning/overdue notifications, and PostgreSQL tests as a separate package. Continue Judge Đề A independently.