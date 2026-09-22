# Public Sprint 1 deployment: Render

Status: configured locally, NOT DEPLOYED. No public URLs have been assigned here.
Render authentication is unavailable: no CLI/token found; browser control failed
with a Windows sandbox access error. Sign in to Render directly; never put
credentials in repository files or chat.

## Architecture and provisioning

Root render.yaml declares the primary React static site and FastAPI web service.
The API uses plan: free; the React frontend is a free static site. No disk,
Postgres or paid service is configured or authorized. Do not upgrade either service.
Use one instance/worker. SQLite is unsuitable for independent horizontal replicas.
There is no Docker/Compose dependency. Streamlit remains a separate legacy demo.

1. Sign in and authorize Render's GitHub connection for this repository.
2. Make the reviewed deployment branch available through normal Git workflow.
   Select that branch explicitly for a Blueprint using root render.yaml.
3. Confirm actual assigned service URLs: names may receive suffixes. Configure
   CORS_ORIGINS and VITE_API_BASE_URL with those exact URLs. Do not guess hostnames.
   Blueprint creation may launch builds immediately. Invalid/missing values must
   remain a failed deployment until corrected and manually redeployed.
4. Use /tmp/organizationai/demo-organization.sqlite3 on the ephemeral filesystem.
   Startup validates environment, creates its parent directory, seeds, then serves.
5. Automatic redeployment is disabled. Manually deploy the reviewed revision only
   after the tests and staged-file inspection below pass.

## Environment variables

| Variable | Service | Configuration |
| --- | --- | --- |
| PYTHON_VERSION | Backend | 3.13.14 |
| APP_ENV | Backend | demo; production rejects demo identities |
| DEMO_DATABASE | Backend | /tmp/organizationai/demo-organization.sqlite3 |
| DEMO_MOCK_MODE | Backend | pass |
| CORS_ORIGINS | Backend | Exact assigned HTTPS frontend origin; no path, slash or wildcard |
| PORT | Backend | Supplied by Render; launcher default 10000 |
| NODE_VERSION | Frontend build | 24.17.0 |
| VITE_API_BASE_URL | Frontend build | Actual HTTPS API hostname plus /api, no trailing slash |

No external-model secret is required. Future secrets belong only in backend host
environment variables. VITE_ values are public JavaScript; never place credentials
there. Rebuild frontend after changing its API URL. https://api.example.com/api is
only a local production-build verification value, never a deployment destination.

## Exact commands: repository root, Linux

Backend build:

```sh
python -m pip install -r requirements.txt
python -m pytest
```

Backend start:

```sh
python -m deployment.start_backend
```

The launcher permits only /tmp/organizationai/demo-*.sqlite3 for this hosted demo,
runs seed, and execs Uvicorn on 0.0.0.0:$PORT with one worker and concurrency cap 32.
Seed runs at startup, not during build. Existing migration_001.sql is reused.
Missing databases receive five deterministic demo scenarios; repeated startup safely
replays seed intents without duplicating existing records.

Frontend build with VITE_API_BASE_URL already set in Render:

```sh
node --test deployment/validate_frontend.test.mjs
node deployment/validate_frontend.mjs
npm ci --include=dev --prefix frontend
npm run test --prefix frontend
npm run build --prefix frontend
```

Publish frontend/dist. No Vite dev/preview server is deployed. The Blueprint rewrites
/* internally to /index.html so React routes work after refresh. The service root
must remain repository root: deployment helpers and tests/fixtures/role1/v2.1 are
needed for build and the real Verify harness. The ignored original Role 1 package
is not needed. Runtime pins were tested locally; availability on hosted Linux must
be confirmed during the authenticated build.

## Release verification

Before deployment: python -m pytest; frontend tests and production build; inspect
git diff and the index. No .env, runtime DB, dependencies, build output or credentials
may be committed. No force-push, squash or merge is required.

After deployment, record both public URLs and the deployed commit, then:

1. GET /api/health: 200 with environment demo. It is liveness, not DB readiness.
   GET /api/config as DEMO-MAKER-01 verifies the authenticated demo path too.
2. Preflight API requests from the frontend origin must return that exact
   Access-Control-Allow-Origin. An unrelated origin must receive no permission.
3. Open and refresh /, /plans/new, /plans, /review, /audit, /policy, /verify.
   Inspect browser requests: no localhost URLs, mixed content or failed requests.
4. Actor selector must contain DEMO-MAKER-01, DEMO-CHECKER-01, DEMO-ADMIN-01 and
   DEMO-DUAL-01. Unknown actors/internal evaluator must fail authentication.
5. Create a uniquely named synthetic plan, save, upload, submit; confirm result,
   immutable version/round and audit. Exercise Checker review with required reasons.
6. Run all five Verify cases: five pass, three automatic and two escalated.
7. After restart/redeploy or idle spin-down, expect user-created plans, images and
   audit to be lost. Verify the five seeded scenarios are available after cold start.
8. Record actual results; a successful local build is not public verification.

## Persistence, rollback and limits

Render Free spins down the backend when idle. The next request may require a cold
start. SQLite data is ephemeral: treat plans, uploaded images, audit and idempotency
records as erased on restart, redeploy or spin-down. Only deterministic demo seed
scenarios are recreated. A process restart that happens to retain /tmp is not a
persistence guarantee; startup preserves that existing file rather than deleting it.
This loss of submitted data is acceptable only for the Sprint 1 judge demo, never
for real approval records. Verify cache also resets with the process.

Rollback by selecting a previous verified free service deployment. Expect a fresh
seeded demo; no user-submission recovery is promised. There is no new schema migration.

Anyone can select shared demo actors, including Checker. Only synthetic data is
permitted. CORS is not authentication and does not prevent direct API calls.
Concurrency limiting is not rate limiting: repeated Verify requests can grow its
process-local cache, and uploads/plans can consume disk. Edge request limits and
storage monitoring remain necessary before broad/long-lived public exposure; they
are not claimed implemented here. Initially supervise the demo and keep an owner
able to stop it. The free service has idle cold starts and deployment downtime.

Real production identity, company policy and real VLM validation remain out of scope.
Dependency deprecation warnings remain. Authenticated hosted Linux execution and
public acceptance are pending.

References consulted: https://render.com/docs/blueprint-spec and
https://render.com/schema/render.yaml.json.

Pytest discovery is restricted by pytest.ini to tests/ and excludes runtime, .venv
and node_modules. Do not install conformance dependencies for generated vendor tests.
