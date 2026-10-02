# Local Media Compliance and Strategy Inference

## Verified local runtime

The local Compose backend can call Ollama on the Windows host through
`http://host.docker.internal:11434/v1`. Keep external access disabled:

| Pipeline step | Local model | Purpose |
|---|---|---|
| Visual extraction | `qwen3-vl:4b` | OCR and direct visual observations from the submitted-version image snapshot |
| Media Compliance | `organizationai-qwen3:4b-ctx8192` | Evaluate extracted evidence against the configured content policy |
| Strategy Evaluation | `organizationai-qwen3:4b-ctx8192` | Score the fixed seven-criterion BA rubric and surface assumptions/gaps |

The task alias is Qwen3-4B Q4_K_M (2.5 GB download, Apache-2.0) with an 8,192-token context. Its Ollama model digest is pinned in local `.env` as
`sha256:b2ef2f414e31e4e10ef46366751464631a5fa4b5c1bf183b1e3b9076ab2116ef`.
The base tag is `qwen3:4b`; create the constrained alias with:

```powershell
ollama pull qwen3:4b
ollama create organizationai-qwen3:4b-ctx8192 -f deployment/ollama/Modelfile.qwen3-4b-ctx8192
ollama show organizationai-qwen3:4b-ctx8192
```

Keep `LOCAL_VLM_MODEL=qwen3-vl:4b` for image extraction and set
`LOCAL_VLM_MODEL_VERSION` to the `sha256:` digest reported by Ollama for that
exact tag. Ollama's `fp_ollama` response fingerprint identifies the runtime,
not the model weights. For both task providers, set
`PROVIDER=OPENAI_COMPATIBLE_CHAT_COMPLETIONS`, `BASE_URL` to the host URL
above, `MODEL=organizationai-qwen3:4b-ctx8192`, and `MODEL_VERSION` to the
digest above. Set `ALLOW_REMOTE=false`, `TIMEOUT_SECONDS=45`,
`MAX_OUTPUT_TOKENS=2048`, `MAX_RESPONSE_BYTES=262144`, `MAX_INPUT_BYTES=8192`,
`MAX_RETRIES=1`, and `REASONING_EFFORT=none`. Use the supported prompt and schema
versions already shown in `.env.example`; do not substitute an unrecognized
version. Media uses `media-compliance-prompt-v5` and
`media-compliance-schema-v3` to constrain policy identifiers to the submitted
snapshot and keep findings aligned with failed policy rules
and require cited evidence, without inferring exceptions from synthetic/demo
context. The request schema constrains policy, rule, and evidence IDs to the
active submitted snapshot. Configured forbidden OCR literals are checked
against the submitted extraction evidence before the Media result is accepted.
Strategy uses `strategy-evaluation-prompt-v5` and
`strategy-evaluation-schema-v5` to constrain rubric, criterion, and evidence IDs
to the active submitted snapshot and distinguish missing facts from conflicts,
require two references per conflict, require each criterion to cite a supplied
evidence ID, and keep local-model output concise. The
backend Compose service passes these settings into the container.

The local smoke policy in `.env` is named `LOCAL_MEDIA_RULESET_1`, is scoped
only to department `Nori Pilot` and channel `social`, and contains one synthetic
OCR trigger (`UNAPPROVED_GUARANTEE`). It is test data, not a real advertising,
legal, or OrganizationAI policy. Other plans do not match this scope and must
go to Checker. The local Strategy rubric is `BA-STRATEGY-7`,
version `BA-STRATEGY-7-1.0`, with weights 15/15/15/15/15/15/10. Do not use the
synthetic content policy outside local smoke tests.

Auto-approval remains disabled. No real approved budget limit or authority
configuration is supplied by this setup; every evaluation therefore remains
for human review. The Judge Demo still uses its existing Mock VLM and SQLite
database.

## Run and inspect the smoke flow

For a new local stack, set the model and task variables in the ignored `.env`,
then start the services and run the smoke:

```powershell
docker compose up -d --build
docker compose exec -T backend python /app/scripts/smoke_local_media_strategy.py
```

For an existing stack, the Judge Demo database is at
`/tmp/organizationai/demo-organization.sqlite3` in the backend container and
is not on a persistent volume. Back it up and restore it around any backend
recreation. The following sequence uses SQLite's online backup API so a live
WAL database is copied consistently; keep the backup outside the repository:

```powershell
$backupPath = Join-Path $env:TEMP 'organizationai-demo-organization.sqlite3'
docker compose exec -T backend python -c "import sqlite3; src=sqlite3.connect('/tmp/organizationai/demo-organization.sqlite3'); dst=sqlite3.connect('/tmp/organizationai-demo-organization.sqlite3'); src.backup(dst); dst.close(); src.close()"
docker compose cp backend:/tmp/organizationai-demo-organization.sqlite3 $backupPath
docker compose up -d --build backend frontend
docker compose stop backend
docker compose cp $backupPath backend:/tmp/organizationai/demo-organization.sqlite3
docker compose up -d backend
```

Do not use `docker compose down -v`; it removes the PostgreSQL data volume.
The current verification deliberately did not recreate the running backend:
the smoke ran in an isolated process with the `.env` task settings and used the
existing PostgreSQL database, while the already-running UI backend kept its
original environment and Judge Demo SQLite file.

The script uses the seeded `maker`, `checker`, and `admin` accounts and the
existing PostgreSQL database. It creates and retains three synthetic plans:
compliant media, a policy-marker image, and a valid plan that explicitly
records strategy research gaps. It checks model step status, schema output,
seven weighted Strategy criteria, the scoped Media result or fail-closed path,
Human Review, role permissions, private attachment access, reload persistence,
and a Checker decision. On this Qwen build the marker case returned a PASS
status together with a hard-violation finding; the deterministic literal check
rejected that inconsistent output as `INVALID_SCHEMA` and routed it to the
Checker. The script accepts either a valid `REVIEW_REQUIRED` finding or this
fail-closed result. It prints generated plan/run IDs and per-step timings. It
does not delete existing plans or reset database volumes. The smoke script requires
`AUTH_SEED_PASSWORD` to already be set in the local container environment.

With the verified Ollama build, GPU inference used roughly 3.6 GB VRAM for the
text model at context 8,192. The machine had 23.7 GB RAM with about 2.5 GB
available and an RTX 5050 Laptop GPU with 8 GB VRAM. Ollama unloaded the VLM
when the text alias was loaded; the smoke flow exercised the models sequentially.
Concurrent residency of both models was not verified. Model timings vary with
warm/cold state and host load; use the output of the latest smoke run rather
than treating a prior duration as a service-level guarantee.

If the model responds with an invalid schema, unknown version, timeout, or
insufficient evidence, the backend keeps the successful submission and routes
the case to Checker. Do not replace these providers with Mock or weaken the
output validators to make the smoke pass.
