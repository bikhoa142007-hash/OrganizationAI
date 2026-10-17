# Architecture diagrams

**Last reconciled:** 2026-10-17. These diagrams describe repository code and checked-in deployment configuration. They do not establish that a Render service, Cloudflare Tunnel, or AI host is currently live.

## Status labels

- **CODE** — behavior or boundary found in the current repository.
- **MOCK / TEST** — synthetic fixtures, mock providers, or demo-only persistence.
- **CONFIG ONLY** — declared in a local or Render configuration file; deployment was not verified.
- **UNVERIFIED EXTERNAL** — described by the requested topology, but its implementation/configuration is outside this repository or was not available for inspection.
- **PROPOSED** — future architecture, not implemented.

Labels and line styles both carry status; color alone does not. No diagram includes secrets, cookies, Bearer values, or temporary tunnel hostnames.

## Architecture findings

| Concern | Verified repository behavior | Limit of verification |
|---|---|---|
| Auth identity and authorization | Auth API verifies the HttpOnly JWT cookie, reloads the principal and roles from PostgreSQL, and checks permissions at API/service boundaries. The browser does not receive inference API keys. | Render Auth is described by a separate staging Blueprint and runbook; this repository does not verify a live service. |
| Inference client authentication | VLM and text-task adapters add `Authorization: Bearer …` only when their backend-only API key setting is nonblank. Inference uses `POST /v1/chat/completions`; the VLM provider also defines `GET /v1/models` for `health_check()`. No call site for that health check was found in the submit path. | No Bearer proxy implementation, allowlist, bind address, forwarding target, or Cloudflare Tunnel config is present in the repository. Therefore the proxy's allowed methods/paths and its network/filesystem/resource limits are **unverified**. The application request paths must not be mistaken for a proxy allowlist. |
| Endpoint and transport | `LOCAL_VLM_BASE_URL` and task-specific `*_BASE_URL` are operator settings. Local Compose documentation describes a direct host-runtime endpoint. Remote endpoints are rejected unless explicitly allowed and HTTPS. | `.env.example` leaves endpoints and API keys blank. The Auth staging Blueprint sets remote inference off. The 2026-10-16 diagnostic records a then-observed direct-to-Ollama tunnel; it is historical evidence, not proof of today's external state. No current proxy-to-Ollama route was independently verified. |
| Model identity | The provider compares the model ID returned by a Chat Completions response with the configured ID. Local smoke scripts can separately inspect Ollama inventory/digests. | The submit path does not call `GET /v1/models` as a preflight, and the application does not independently verify an Ollama weight digest on every inference request. |
| AI authority | VLM, Media Compliance, and Strategy produce evidence/evaluation. The deterministic rules engine applies budget and approval gates. Persisted engine outcomes are `AUTO_APPROVED` or `HUMAN_REVIEW_REQUIRED`; AI auto-rejection is not supported. | Auto-approval code support is not an enabled production policy. The unconfigured Auth policy disables it; the staging configuration does not supply approved policy/budget/authority. Live production behavior is unverified. |
| Persistence | Auth workflow records, immutable versions, private attachment bytes/hashes, evaluations, decisions, and audit events use PostgreSQL in the authenticated application. Judge Demo uses a separate SQLite database. Verify creates a fresh in-memory SQLite repository per case in the same process and uses synthetic inputs plus Mock providers. | Render root configuration declares ephemeral SQLite for Judge Demo. The Auth PostgreSQL Blueprint is configuration only. In-memory SQLite is not process isolation, and Verify does not prove production inference. |

VLM extraction, Media Compliance, and Strategy Evaluation are pipeline steps/models. When their configured endpoints resolve to the same Ollama runtime, they share one server; the diagram does not imply three Ollama servers.

## Diagram register

| Diagram | Source / rendered artifact | Evidence checked on 2026-10-17 | Limit |
|---|---|---|---|
| Runtime architecture | [runtime architecture HTML](organizationai-runtime-architecture.html) · [candidate source](organizationai-runtime-architecture-v2.candidate.json) | `src/backend/api/`, `src/backend/db/`, `src/backend/application/auth_workflow_ai.py`, `src/ai_pipeline/`, `render.yaml`, `deployment/render.auth-staging.yaml` | Local candidate source is not a proxy or deployment configuration. Render state is not live-verified. |
| Deployment topology | [deployment diagram HTML](architecture-deployment.source.html) · [source](architecture-deployment.source.candidate.json) | `render.yaml`, `deployment/render.auth-staging.yaml`, `deployment/README.md`, `.env.example`, `src/ai_pipeline/providers/openai_provider.py`, `src/ai_pipeline/task_providers.py`, `docs/integration/evidence/local-vlm-403-diagnostic-2026-10-16.md` | Tunnel and Bearer proxy are explicitly marked external/unverified; no proxy path allowlist is claimed. |
| Inference dataflow and trust | [AI technical diagram HTML](organizationai-ai-technical.html) · [source](organizationai-ai-technical.candidate.json) | `src/backend/application/auth_workflow.py`, `src/ai_pipeline/authenticated_orchestrator.py`, `src/ai_pipeline/task_evaluation.py`, `src/backend/rules/decision.py` | Shows pipeline order and custody from code; it does not attest to remote model quality. |
| Maker–AI–Checker decisions | [main workflow HTML](organizationai-main-workflow.html) · [source](organizationai-main-workflow.json) | `src/backend/api/auth_workflow.py`, `src/backend/application/auth_workflow.py`, `src/backend/rules/decision.py`, `src/backend/db/models/auth_workflow.py`, `docs/contracts/decision-contract.md` | The diagram distinguishes code support from configured policy and live deployment. |
| Auth inference sequence | [sequence HTML](organizationai-inference-sequence.html) · [source](organizationai-inference-sequence.json) | `src/backend/application/auth_workflow.py`, `src/ai_pipeline/providers/openai_provider.py`, `src/ai_pipeline/task_providers.py`, `src/backend/rules/decision.py` | Shows request order and optional Bearer generation in code; external tunnel/proxy/Ollama hops remain unverified. |
| Judge Demo Verify | [Verify diagram HTML](judge-demo-regression.html) · [source](judge-demo-regression.candidate.json) | `src/backend/api/app.py`, `src/verify/runner.py`, `src/verify/harness.py`, `src/backend/repositories/approval.py` | Synthetic/mock regression only; each in-memory repository is per case, not per process. |

Archify HTML deliverables contain the current inline SVG. The separately tracked
`organizationai-runtime-architecture.png` was not regenerated in this update;
use the linked HTML as the current runtime diagram.

## How to read the inference path

The backend can be configured to call an inference endpoint through an external tunnel and Bearer proxy, but that route is not fully represented by repository code/config. Treat tunnel, proxy, origin transport, proxy allowlist, loopback binding, Ollama target, and current deployment as **UNVERIFIED EXTERNAL** until their source/config and a controlled health/inference check are available. A tunnel transports traffic; it does not itself establish the proxy's authentication or request restrictions. A Bearer proxy is an access-control layer, not a complete sandbox.

No loopback hop is drawn as HTTPS. Where the origin transport is not evidenced, it is labeled unknown instead of inferred. Authenticated browser identity, backend service credentials, and decision/persistence authority are separate boundaries.

## Related documentation

- [Authenticated workflow and PostgreSQL](../integration/authenticated-workflow-postgresql.md)
- [Local Media, Strategy, and VLM inference](../integration/local-media-strategy-inference.md)
- [Render deployment runbook](../../deployment/README.md)
- [Decision contract](../contracts/decision-contract.md)
