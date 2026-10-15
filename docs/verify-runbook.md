# Verify runbook

Verify is an Admin-only synthetic acceptance harness at `/workflow/verify`. It runs four fixed cases sequentially through the real domain workflow, each with a fresh in-memory SQLite repository. It never loads or changes marketing plans in the configured application database.

## Truth labels and data boundary

- **Environment:** `SYNTHETIC_TEST`.
- **AI provider:** `MockVLMProvider`; the suite makes no external AI or market-data calls.
- **Persistence:** synthetic workflow records live in per-case in-memory SQLite. Run progress/report data live in the API process and are scoped to the starting Admin. Reloading the page restores that Admin’s latest run. Restarting the API process clears this transient run history.
- **Policy:** the Verify fixture uses a test-only 10,000,000 VND budget ceiling and 5,000,000 VND auto-approval authority. It does not change Auth or production policy.

## The four cases

| Case | Synthetic input | Expected actual workflow result |
| --- | --- | --- |
| TC01 | Marketing/social plan, 3,000,000 VND, valid attachment, passing mock | `AUTO_APPROVED`; plan becomes `APPROVED` |
| TC02 | Same campaign with 6,000,000 VND, below the 10,000,000 budget ceiling but above 5,000,000 authority | `HUMAN_REVIEW_REQUIRED`; Checker remains the final decision maker |
| TC03 | Accepted submission with an attachment; mock returns no media evidence | Provider schema validation fails closed; submission remains pending and is routed to Checker |
| TC04 | Accepted submission; controlled mock provider timeout | Submission and audit remain; decision routes to Checker |

Every case reports the expected result beside the actual persisted plan, AI evaluation, engine decision, audit events, and individual assertions. `PASS` is computed from those actual workflow records. A timeout or failed assertion is shown as `FAIL`; the UI does not turn a failed result into a pass.

## Run from a clean clone

Requirements and Auth seed setup are documented in [README local setup](../README.md#cài-đặt-và-chạy-local) and [Auth local setup](../README.md#auth-cục-bộ-với-postgresql-và-docker-compose). For the authenticated UI, use the local Compose setup so PostgreSQL, migrations, and the Admin seed account are present.

```powershell
git clone https://github.com/bikhoa142007-hash/OrganizationAI.git
Set-Location OrganizationAI
Copy-Item .env.example .env
# Set local-only POSTGRES_PASSWORD, JWT_SECRET (at least 32 random bytes), and AUTH_SEED_PASSWORD in .env.
docker compose -p organizationai-verify up --build
```

Open `http://localhost:5173/login`, sign in with the seeded local Admin account using the `AUTH_SEED_PASSWORD` value from `.env`, then choose **Verify** in the left navigation under **Tổng quan** and press **Chạy kiểm thử**. The UI updates each case in sequence, restores the latest or running run after a page reload, and downloads the current/final JSON report.

Keep `.env` local. Do not copy seed passwords into a ticket, commit, screenshot, or the generated Verify report.

Stop the stack with `docker compose -p organizationai-verify down`; this preserves its local PostgreSQL volume. The Verify history itself is process-local, so `docker compose -p organizationai-verify restart backend` clears that history while preserving the Auth database. Do not use `down --volumes` unless you intentionally want to erase this isolated local database.

## 90-second operator guide

1. Open **Verify** with an Admin account.
2. Press **Chạy kiểm thử** once. The server enforces one active suite and an idempotency key protects against repeated requests.
3. Watch `TC01` through `TC04`; the server marks unfinished cases `FAIL` when the 90-second suite deadline expires. Each case also fails if it exceeds 20 seconds.
4. Expand each case for its actual workflow, AI schema/evaluation, decision, audit, and assertions. Confirm the environment and provider labels before sharing results.
5. Select **Tải báo cáo JSON**. The API report matches the on-screen run and can also be fetched from `GET /api/workflow/verify/runs/{run_id}/report` while signed in as the Admin who started it.

## CLI run and checks

From the repository root, after installing the Python requirements:

```powershell
python -m src.verify.competition --output runtime/verify-report.json
python -m pytest tests/unit/verify/test_competition_harness.py tests/unit/verify/test_manager.py tests/integration/test_auth_workflow.py::test_verify_run_api_is_admin_only_reloadable_and_idempotent
```

The CLI writes the actual JSON report and exits non-zero if any assertion fails. The focused pytest command covers the four outcomes, deadline behavior, idempotent starts, Admin-only access, reload recovery, and report download.

Frontend checks, from `frontend/`:

```powershell
npm ci
npm run test -- --maxWorkers=4 --testTimeout=15000
npm run typecheck
npm run build
```

## Troubleshooting

- **Verify is missing:** sign in as a user with the `ADMIN` role. Both the route and API enforce authorization.
- **A run is already active:** the UI restores the current run; let it finish before starting another.
- **Latest run not found after API restart:** run reports are intentionally process-local synthetic data; start a new suite.
- **TC03 is not PASS:** it is expected to route to Checker because the mock supplies no media evidence and the provider schema fails closed.
- **TC04 is not PASS:** verify the report shows `PROVIDER_TIMEOUT`, a pending plan, and submission/engine-routing audit actions. The expected case result itself is still PASS when these actual records match the assertions.
