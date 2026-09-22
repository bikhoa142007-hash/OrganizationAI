# Role integration implementation plan

User-approved scope: attachment Pasted text.txt, 2026-09-22.
Baseline c1288c9 on feature/wp5-frontend-verify; working branch
integration/role1-role3-frontend. Preserve initial uncommitted work.

1. Import immutable BA references and fixture copies; strict input-only
   mapping into existing WP schemas, regression through workflow/pipeline.
2. Fix evidenced MEDIA_PASS classification bug without changing precedence,
   thresholds or schema; run old and new tests.
3. Add FastAPI demo transport, strict DTOs, server principals, private media,
   request idempotency/revision guards; test API and production auth denial.
4. Wire React service interfaces to HTTP; retain layout, add real draft/upload,
   read-only history and Checker override reason; disable unsupported commands.
5. Add idempotent demo seed, real Verify runner, frontend tests and browser E2E.
6. Validate all checks; document mapping, conflicts, commands, rollback and limits.

Dependencies follow this order. No schema migration expected. Runtime never reads
expected fixtures. Demo identity is enabled only in APP_ENV=demo. Production
authentication is deliberately unavailable until a real identity adapter exists.
No further PO decision is required for this explicitly authorized demo integration.
Open BA proposals remain proposals and do not change production policy.
