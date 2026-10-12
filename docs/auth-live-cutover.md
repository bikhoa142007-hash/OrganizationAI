# Auth database cutover runbook

This runbook prepares the Auth schema cutover from `20261003_07` to
`20261011_12`. The checked-in runner is fail-closed and does not change Render
settings. Keep the API and every other writer paused through migration and the
subsequent Auth deployment.

## Migration effects in the pinned source

The runner extracts only source SHA
`0d17887cf1d6a6571fc8b02b74706343e2555e19` and upgrades to the literal target
revision `20261011_12`.

| Revision | Schema and data effects |
| --- | --- |
| `20261009_08` | Adds nullable plan-creation idempotency key and request hash, plus a unique Maker/key index. Existing plan rows receive nulls. |
| `20261010_09` | Adds nullable department, title and start date to users; adds `employment_status` defaulting existing and future rows to `ACTIVE`. |
| `20261010_10` | Adds account flags/session version and role status/built-in markers; marks the three built-in roles; copies each user into `employee_profiles`; creates built-in role permission rows, management-token and admin-audit tables and indexes. Existing Auth users and roles are retained. |
| `20261011_11` | Creates the in-app notification table and indexes; no notification rows are backfilled. |
| `20261011_12` | Creates SLA configuration and approval-round tables, indexes, PostgreSQL immutability triggers, and expands allowed notification event types; it does not seed SLA rows. |

The rehearsal and live post-check compare every pre-existing public table's
ordered row fingerprint and verify the employee-profile copy. They also require
the newly introduced token, audit, notification and SLA history tables to be
empty at cutover.

## Before the final backup

1. In the Render Dashboard, open the intended Auth API service and its
   Environment page. Confirm that its `DATABASE_URL` points to the PostgreSQL
   service intended for this cutover. Compare the service name, project, and
   environment in the Dashboard; do not copy a URL or credential into chat.
   Use the External Database URL from that same PostgreSQL service only for
   the Windows runner.
2. Confirm the Auth API service and the PostgreSQL service are the intended
   production resources. The previously reported Start Command is
   `python -m deployment.start_backend` (Judge Demo); do not infer that a
   Dashboard service is the Auth API just from its name or URL.
3. Stop scheduled jobs, workers, integrations, and any other clients that can
   write Auth data. For a paid web service, Render Maintenance Mode can block
   public requests, but the service remains running and reachable over its
   private network. After public traffic has drained, suspend the verified Auth
   API service from the Render Dashboard and confirm its status is Suspended.
   Suspend any other writer service separately. Do not suspend PostgreSQL.
4. Keep the API suspended. Run the existing rehearsal runner in its normal
   fresh-backup mode, explicitly passing the verified Python interpreter
   shown below. Confirm `AUTH_WRITERS_PAUSED` before the runner creates a dump,
   then enter the exact Dashboard service-link confirmation and supply the
   External Database URL only at its hidden prompt. Rehearsing a reused archive
   does not issue a cutover receipt. It creates a private
   logical backup, checks the archive, restores to a temporary PostgreSQL
   instance, migrates that copy with the pinned source, checks data
   preservation, and writes `auth-migration-rehearsal.json` only after all
   checks and cleanup pass.
5. Keep the printed backup directory and SHA-256 locally. The dump contains
   real private data; keep it in `%LOCALAPPDATA%` and outside Git. Do not send
   the dump or any database rows as evidence.

Render documents Maintenance Mode as public-traffic blocking while the service
continues running and remains reachable privately; suspending the service is
therefore required when private or background writers must also stop:
[Render Maintenance Mode](https://render.com/docs/maintenance-mode),
[Dashboard service suspension](https://render.com/changelog/suspend-and-resume-services-in-bulk-from-the-dashboard).

## Run the live migration

Run `scripts/run_auth_live_migration.ps1` with the verified Python interpreter
path below. This interpreter is outside the Render worktree; the runner checks
the actual `sys.executable` and versions before prompting. Pass the same path to
the final rehearsal before starting the cutover. Run the rehearsal immediately
before cutover; the live runner rejects a receipt or archive older than 12
hours. Only fresh-backup rehearsal receipts record the typed writer-pause
confirmation.

```powershell
& 'C:\Users\Khoa Bi\.codex\worktrees\fix-render-test-isolation-20261011\OrganizationAI\scripts\run_auth_live_migration.ps1' -PythonExe 'C:\Users\Khoa Bi\VS Studio\repos\OrganizationAI\.venv-test-20261009\Scripts\python.exe'
```

The runner imports Alembic, SQLAlchemy, and psycopg before prompting. It then:

- requires confirmation that the Auth API and all database writers are paused;
- verifies the backup archive hash, sidecar, and successful rehearsal receipt;
- obtains the External URL with hidden input and forces PostgreSQL TLS,
  a 10-second connect timeout, a 60-second statement timeout, and a 10-second
  lock timeout;
- checks the connected database is `organizationai_db`, schema is `public`,
  PostgreSQL major is 16, Auth relations resolve through the active
  `search_path`, and exactly one Alembic revision is `20261003_07`;
- fingerprints existing table data in a read-only repeatable-read transaction
  and explicitly rolls it back;
- displays the target database, source SHA, target revision, backup hash, and
  data counts without displaying credentials;
- requires the exact `MIGRATE ...` confirmation immediately before writing;
- extracts the exact Git archive at
  `0d17887cf1d6a6571fc8b02b74706343e2555e19` outside the repository and runs
  Alembic to the literal revision `20261011_12` from that extracted source;
- verifies target revision, ORM tables and columns, the two pinned indexes,
  existing table-data fingerprints, employee-profile backfill, and the empty
  token/audit/notification/SLA history tables.

If the runner fails, leave writers paused, retain the backup, and inspect only
its sanitized diagnostic. It never retries, downgrades, stamps, seeds, or
restores over the live database. If migration completed but a post-check fails,
the database may already be at revision 12; stop and investigate before any
further write or deployment.

## Deployment remains a separate step

The migration runner does not edit the Dashboard or deploy. The Auth launcher
at the pinned SHA is `python -m deployment.start_auth_backend`; it validates
`APP_ENV=production`, `JWT_SECRET` (at least 32 bytes and not a placeholder),
`AUTH_COOKIE_SECURE=true`, HTTPS-only exact `CORS_ORIGINS`, and a PostgreSQL
`DATABASE_URL`, then upgrades Alembic to the deployed source's `head` before
starting Uvicorn. Its cookie defaults are `SameSite=Lax`, HttpOnly, Secure, and
host-only. Use `AUTH_COOKIE_SAMESITE=none` only if the frontend/API deployment
is cross-site; it requires secure cookies.

For the Auth API service, prepare these non-secret settings and enter the
secret values directly in Render:

| Setting | Value or rule |
| --- | --- |
| Start Command | `python -m deployment.start_auth_backend` |
| `APP_ENV` | `production` |
| `DATABASE_URL` | Render service link to the verified PostgreSQL service |
| `JWT_SECRET` | Generate a backend-only secret with at least 32 bytes; do not reuse the frontend secret |
| `AUTH_COOKIE_SECURE` | `true` |
| `AUTH_COOKIE_SAMESITE` | `lax` by default; use `none` only for cross-site frontend/API and keep Secure enabled |
| `CORS_ORIGINS` | Exact frontend HTTPS origin, e.g. `https://frontend.example`; no path, trailing slash, wildcard or query |
| Frontend `VITE_API_BASE_URL` | Exact public HTTPS API base URL assigned by Render |

The pinned migration SHA is the source for the DB upgrade. The deployment SHA
is a separate build identity and is not determined by this runner. Before
changing the Start Command, verify the exact deployment build SHA contains
`deployment.start_auth_backend` and Alembic head `20261011_12`. The launcher
runs `upgrade head`, so a later source SHA with newer migrations would apply
them at startup. Set the Auth variables in the Dashboard without putting
values in this repository or chat. Configure the Auth Start Command before
resuming or deploying the suspended API; the currently reported command is
still `python -m deployment.start_backend`. Render's deploy hooks return HTTP
409 for suspended services, so don't rely on a hook during the paused window.
Keep cron jobs and other writers suspended while the Auth API starts and is
checked. After deployment, verify the live commit SHA, `/api/health/ready`,
login, `/api/auth/me`, and workflow listing. Then resume other writers and
remove Maintenance Mode when ready for public traffic. `/api/health` alone is
only process liveness and is not proof that the database is ready.
