# Local Auth and AI Validation — 2026-10-02

## Scope and safety

Work ran on branch `feature/auth-ai-validation`, from `d93fb0f627656c497b1f60e83b4ff40203256a55`. No commit, push, merge, service restart, or deployment was performed. The existing PostgreSQL database was queried read-only before the isolated smoke and reported Alembic revision `20260930_06`; the Judge Demo SQLite database was not touched.

The three protected plan IDs supplied for this task were not used as mutation targets. All records listed below have synthetic titles and were created by these local smoke runs. Their state was read back after the tests; they were not deleted.

The ignored local `.env` now pins both text agents to the installed Ollama digest and the v5 prompt/schema versions. Compose defaults and `.env.example` match. The running API was not restarted: Docker was unavailable in this environment, and the live process does not reload `.env` changes. As a result, the browser workflow below observed the existing service configuration; the isolated real-model smoke loaded `.env` in its own process and connected to the existing PostgreSQL host port.

## Synthetic evaluator set

The bounded dataset has 16 synthetic cases: 8 Media and 8 Strategy. It uses 12 tune cases and 4 held-out cases. Every expected label and per-criterion information-state label is marked `PROPOSED_NOT_HUMAN_APPROVED`; the seven BA rubric point values remain unlabelled because the detailed scoring rubric is still open. The evaluator sends only each case's `input` to the model, never its case ID, rationale, or expected labels.

The direct task-agent runs used `organizationai-qwen3:4b-ctx8192`, Ollama digest `sha256:b2ef2f414e31e4e10ef46366751464631a5fa4b5c1bf183b1e3b9076ab2116ef`, with `num_ctx=8192`, sequential requests, and zero retries. Remote access and auto-approval were disabled. The held-out run was made once after prompt/schema tuning; only the aggregate counts below were used here.

Image extraction used local `qwen3-vl:4b`, digest `sha256:1343d82ebee38e26a4dd6b0180b915eb91550184e67c505dea97509571c8f683`. Its timeout was 45 seconds and its output cap fell back to the provider's bounded 1,536-token default; the VLM runtime context size is not pinned in this setup.

| Run | Media schema-valid | Strategy schema-valid | Timeouts / provider errors |
|---|---:|---:|---:|
| Initial v4 tune baseline | 0/6 | 3/6 | 0 |
| v4 prompt-only retune | 0/6 | 3/6 | 0 |
| v5 prompt + snapshot-constrained schema, tune | 2/6 | 4/6 | 0 |
| v5 prompt + snapshot-constrained schema, holdout | 1/2 | 2/2 | 0 |

The request schema now enumerates policy, rubric, rule, criterion, and evidence identifiers from the submitted snapshot. This improved tune validity without changing backend validation. Findings attached to `UNKNOWN` rules are now rejected as invalid. Remaining schema failures continue to route to Human Review. In the valid tune Strategy outputs, all seven criterion scores were zero; those values are retained as model output, not treated as calibrated quality or approved BA scoring.

Reports:

- [Initial tune baseline](media-strategy-evaluation-2026-10-02-baseline-tune.json)
- [Prompt-only tune retest](media-strategy-evaluation-2026-10-02-tuned-tune.json)
- [Snapshot-constrained tune](media-strategy-evaluation-2026-10-02-constrained-tune.json)
- [Snapshot-constrained holdout](media-strategy-evaluation-2026-10-02-constrained-holdout.json)

The direct evaluator can be rerun with `scripts/evaluate_local_media_strategy.py --split tune` or `--split holdout`; it accepts only loopback Ollama on port 11434 and verifies the model digest/context before making calls.

## Live Auth browser flow

The dedicated Playwright flow used the seeded local Maker and Checker accounts against the running UI/API. It saved an incomplete draft, uploaded a private image, submitted Version 1 / Round 1, confirmed rejection without a reason was blocked, rejected with a reason, revised and resubmitted Version 2 / Round 2, then approved with a Checker reason. The saved first-round AI evaluation compared equal before and after resubmission, and the browser reported no page errors. The primary test plan is `65d5e7c5-d368-4fee-b3a0-e4ca05955e24` (`APPROVED`, Version 2 / Round 2).

The live service successfully ran Local VLM extraction on both rounds, but its persisted Media Compliance and Strategy steps were `NOT_CONFIGURED`. The run therefore failed closed to Checker; the Checker completed the workflow manually. This is why the direct `.env`-loaded task-agent evaluation and isolated full-pipeline smoke were also run.

The retries needed to stabilize the browser selectors left these additional synthetic records in PostgreSQL:

| Plan ID | State |
|---|---|
| `f77f93d9-f0fa-4a9e-833b-d3a2b6f97aaf` | Pending Checker review |
| `a33e9006-2787-41e4-9765-f5b15aa9add6` | Pending Checker review |
| `bc397b7b-a705-4c0b-a7aa-fe30b584f55d` | Pending Checker review |
| `57df5783-621a-43f2-8892-aebd06f0115c` | Incomplete draft |

The protected IDs do not appear in this set.

## Isolated real Auth pipeline smoke

The documented smoke runner loaded the ignored `.env` into a separate process, used loopback Ollama and the existing PostgreSQL host port, and created three additional synthetic plans. It did not reseed or restart services. It verified Checker queue access, private attachment access, denial of unrelated plan/image access, Maker decision denial, stable evaluation IDs on reload, and a persisted Checker decision.

The host-side process remapped the Compose database hostname to the already-open host endpoint `127.0.0.1:5433` in memory and pointed the local-model adapters to `127.0.0.1:11434`; neither override was written back to `.env`.

| Plan ID | Run result | Media | Strategy | Final plan state |
|---|---|---|---|---|
| `4999312c-770e-489c-bc68-9176a6ed8c27` | Succeeded | PASS | Succeeded, weighted score `0.0` | Approved by Checker |
| `6439e0d4-93df-455a-9746-45dfd5834498` | Failed closed | `INVALID_SCHEMA` on the hard-marker case | Succeeded | Pending Checker review |
| `61798daf-ca6f-4356-ac8d-28eb63f8560c` | Failed closed | Extraction failed | `INVALID_SCHEMA` | Pending Checker review |

The third plan's VLM output was truncated; Media consequently returned `EXTRACTION_FAILED`, and Strategy returned `INVALID_SCHEMA`. The smoke command exited nonzero for these observed model failures. It did not relax schemas, invent a score, or change the routing. All three plans and their versions/evaluations remain available for inspection.

## Verification

- Full Python suite: `271 passed`, `84 subtests passed`, 2 existing deprecation warnings.
- Focused AI regression suite: `30 passed`.
- Frontend Vitest: 7 files, 33 tests passed.
- TypeScript typecheck and production build passed.
- Existing Judge Demo Playwright suite: 5 passed, 2 Auth-live cases skipped by the default config because it does not receive the local seed password. The dedicated live Auth workflow passed; its read-only synthetic-plan inventory also passed.
- `git diff --check` passed. No backend lint configuration or lint command is present in the repository.
- The local real-pipeline smoke is a documented model-quality failure, not a passing test: one plan succeeded and two correctly failed closed.

## Remaining work

The next safe step is to start the existing backend with the updated local task-agent environment after the data-protection procedure is available, then rerun the live Auth path. The current constraints are that Docker is not installed/available here, live Media/Strategy settings are not configured in the running API, and the pinned local model still produces schema failures, zero Strategy scores, and a truncated VLM output for the research-gap case. Auto-approval remains disabled; Checker review remains the safe route.
