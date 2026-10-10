# Scope 1 / Phase 1 traceability — 2026-10-10

## Baseline and evidence rules

- **Git baseline at evidence capture:** branch
  `codex/scope1-phase1-continuation-20261010` was at
  `f27e6ba0e9d96fa8d1b420c140a43a7e8cd466e0`. The commit subject is the PR #21
  merge and its parents are `9152195` and `115a762`.
- **Remote refresh for this checkpoint:** an earlier `git ls-remote` attempt
  failed with DNS resolution error. During the current checkpoint preparation,
  `git fetch origin` succeeded; `origin/main` resolved to `f27e6ba` and the
  target branch did not exist at the pre-push check. This is separate from the
  historical evidence snapshot above.
- **Working tree at evidence capture:** tracked and untracked changes were
  present; HEAD alone did not identify the tested code. No reset, checkout,
  stash, or history rewrite was used. The authorized checkpoint publication
  occurs after this evidence capture and is not part of its fingerprint.
- **PR / CI provenance:** the local merge commit records PR #21 in its subject;
  PR metadata and CI run `38034105792` were not freshly queried. The reported
  four-job CI success remains **user-reported**.
- **Source status:** `docs/scope-phase-1.md` calls itself a baseline pending
  PO/stakeholder confirmation. This checklist does not turn proposed values
  into approved policy.
- **Official competition source:** `docs/competition/challenge-a-brief.pdf.pdf`
  is the supplied 11-page official brief (the on-disk filename has the extra
  `.pdf` suffix). This traceability now uses its general rules and Challenge A
  requirements directly: pp. 1–3, 6–10. The PDF is not edited.
- **Scope distinction:** the brief defines competition eligibility, judging,
  timing and submission artifacts. `docs/scope-phase-1.md` v1.1 defines the
  team's Marketing Approval product and still labels itself pending
  PO/stakeholder confirmation. A Sprint 1 timebox/exclusion is historical
  competition delivery guidance; it does not erase the product scope's current
  Phase 1 Must rows. Conversely, a product-scope Must is not automatically a
  competition requirement.
- **Competition artifact inventory:** no deployed public live URL, five-slide
  deck, <=3-minute video, one-page build log, or verified three-person user
  evidence is present in the inspected repository state. Do not claim any of
  those requirements met from local tests alone.
- **Evidence labels:** repository source/reports are inspected locally;
  previously supplied CI/E2E outcomes are user-reported unless this document
  says otherwise. No staging deployment or live database was queried.

## A. Official brief: Challenge A and cross-cutting competition requirements

Challenge A chooses a concrete routine process and asks the system to process
routine cases automatically while escalating ambiguity, out-of-policy cases,
and authority limits. The brief also has general requirements for no-account
public judging, fresh inputs, audit/intervention, real-user evidence and a
fixed submission package. These are competition requirements. The product
features in Section B remain the team's own Phase 1 scope.

The competition brief does not require an employee directory, password
activation/reset flow, dynamic role catalog, Local VLM, marketing strategy
scoring, deterministic budget engine, or auto-approval policy. Those are
product Scope Phase 1 items. They can support the Challenge A product only
where they directly serve its stated workflow and judging rules.

The five employee/account/role decisions in
[`scope1-employee-role-decisions-2026-10-10.md`](scope1-employee-role-decisions-2026-10-10.md)
do not appear as requirements in Challenge A. They do not directly conflict
with it if judge access is a separate public, no-account route. A judge flow
that requires an activated account or activation/reset link would conflict
with the mandatory no-account Live URL rule (brief pp. 2, 6–8); no live route
has been checked, so compatibility is not yet established.

| Confirmed decision | Competition rule comparison | Finding |
|---|---|---|
| D-01 — employee profile can exist without a login account | The brief has no employee-profile requirement. Live judging must not require an account (pp. 2, 6–8). | No direct conflict; keep judge entry independent of employee provisioning. |
| D-02 — Admin hands the recipient an activation/reset link | The brief has no activation/reset workflow, but the public Live URL must work without an account (pp. 2, 6–8). | Internal handover is compatible. Making a judge activate an account to access the Live URL would conflict. |
| D-03 — Admin grants/revokes Maker/Checker only for other activated accounts; separate owner/operator manages Admin | No role-grant authority is prescribed by Challenge A. | No direct conflict. Do not make Admin activation a prerequisite for judges. |
| D-04 — Admin explicitly reassigns pending plans before Checker deactivation; block if no replacement | No Checker lifecycle or reassignment authority is prescribed by Challenge A. | No direct conflict; this is product Scope policy. |
| D-05 — immutable built-in roles; custom roles limited to Phase 1 permissions | Challenge A does not prescribe a role catalog or dynamic role builder. | No direct conflict; this is product Scope policy. |

| ID | Requirement / authoritative source | Current evidence | Gap / acceptance criterion | Status |
|---|---|---|---|---|
| A-01 | **Challenge A Sprint 1, p. 2:** “Chọn một quy trình thường quy cụ thể” and “Tự động xử lý các trường hợp thường quy”; the brief requires a clearly documented process policy. | Product workflow is marketing-plan approval. The Role 1 v2.1 package contains a marketing approval policy and a synthetic case catalog. | Confirm the exact process/rules presented to judges and show the same rules govern the running product. Product domain similarity alone is not evidence of Challenge A compliance. | Partial — plausible process mapping; no end-to-end competition acceptance evidence. |
| A-02 | **Challenge A Sprint 1, p. 2:** at least 15 cases covering ambiguous facts, out-of-policy cases and cases beyond authority. | `tests/fixtures/ba/v2.1/ground-truth-cases.json` has 15 synthetic cases; the local run record reports regression 15/15. Fixture README maps cases across the three escalation classes. | Case-count/regression evidence exists, but it is synthetic development evidence, not an independent holdout. The v2.1 fixture docs mark proposed fact-verification fields as unconfirmed against the current WP1/WP2 contract; inspect that compatibility before claiming all cases exercise the intended live engine. Independent-set metrics and 3-person user testing are Sprint 2 requirements, not Sprint 1 minimums (pp. 2–3). | Local fixture regression reported PASS; independent holdout/model accuracy not claimed. |
| A-03 | **Challenge A Sprint 1, p. 2:** classify uncertainty as missing facts, outside policy, or beyond authority; escalation must ask a specific, answerable question; routine cases must not be over-escalated; never assert a result for suspicious input. | Role 1 v2.1 policy/authority docs and `src/verify` model the three classes. `tests/integration/test_approval_workflow.py::test_suspicious_input_cannot_auto_approve` covers the deterministic suspicious-input gate; `src/verify/runner.py` fails a case if a required escalation question is absent. | Current checks assert a question exists, not that an operator can answer it without rechecking the source. Unit/integration evidence is not proof of live judge behavior. Review question quality per case and exercise suspicious input through the current competition route. | Partial — category and suspicious-input rule evidence exists; question quality/live behavior remain unverified. |
| A-04 | **Challenge A Sprint 1 and preliminary judging, pp. 2–3:** one-action Verify run with 5 cases (3 routine, 2 escalations), show routing and a specific question; judge supplies a new ambiguous case based on the policy. | `tests/fixtures/ba/v2.1/README.md` describes the 5-case escalation suite as 3 routine + 2 escalation; the local run record reports 5/5. The Verify harness test asserts execution against the actual workflow. | No official judge run or deployed public Verify evidence. The new judge-authored ambiguous input has not been demonstrated end-to-end, so the fixed-suite result cannot stand in for it. | Partial — local 5-case fixture run reported PASS; new-input challenge not verified. |
| A-05 | **General challenge rules, p. 2; Challenge A evaluation, pp. 2–3:** accept new inputs; a fixed/hard-coded dataset loses points; preliminary round includes a new ambiguous case and final tests use 5 new cases. | Demo plan creation and Verify runner paths exist; local Demo browser suite passed 5/5 in the saved work record. | Demo creation is not proof the Challenge A policy evaluates a previously unseen input. Show two fresh judge-like inputs, including an anomaly, without fixture identifiers or expected labels influencing the result. | Partial — route exists; fresh-input behavior not proven. |
| A-06 | **General judging rubric, pp. 7–8:** decision boundary must match Slide 2; audit must expose action, time, input data and reason; stopping/override must work; explain a decision to a non-technical user. | Auth workflow tests and local Demo E2E cover authorization, decisions, audit events and Maker/Checker flow. | No evidence yet of the full rubric exercised through the public judge route, including a judge selecting an arbitrary audit event and successfully stopping/overriding an action. Ensure published slides describe actual behavior. | Partial — local workflow evidence only; public judging and complete rubric unverified. |
| A-07 | **Submission list, pp. 2, 6–8:** public Live URL with no account/install and a homepage instruction; one-click Verify for 4 general cases plus the selected challenge's quick test; case table with input/expected behavior/execution and clone-to-run runbook; public repository with full history and no squash/force-push; video <=3 minutes; exactly 5 slides with the prescribed contents (problem; input→processing→output and human decision; before/after impact plus measurement method; architecture with real vs simulated components; limitations/risks); one-page Build log. | Local records report General 4/4 and Challenge A escalation 5/5; local routes, Verify suites, README and a Git remote configuration exist. The previous local/demo E2E is not a deployment test. | No live URL/revision/public access check, runbook completeness check, video, fixed-structure 5-slide artifact or one-page Build log is evidenced. Public remote status/history was not freshly verified. The brief says impact claims without a measurement method do not count. Keep judge access separate from the authenticated Phase 1 workflow. | Not evidenced as a complete submission package. |
| A-08 | **General rubric, pp. 7–8; Sprint 2 requirements, pp. 2–3, 9–10:** 3 specifically identified real users and roles, their own verbatim written feedback, one product change traced to feedback, one concrete negative effect; real data/identity requires consent and fabricated users/quotes can disqualify. Sprint 2 user tests apply to finalists. | No verified user-consent/feedback package or three-person evidence was found in the inspected repository. | Collect actual written evidence and consent; do not synthesize identities, titles or quotations. Confirm finalist status before claiming Sprint 2 eligibility. The brief says core development must occur within sprint windows; work done for Phase 1 must not be retroactively represented as Sprint 1 competition work. | Not evidenced; Sprint 2 eligibility/status needs confirmation. |

## B. Product Scope Phase 1

| ID | Requirement / source | Current code and evidence | Gap | Acceptance criterion | Status |
|---|---|---|---|---|---|
| B-01 | Maker plan list/detail, draft, private media, submit, immutable versions/rounds, Checker approve/reject, reject-revise-resubmit; `AGENTS.md`, Scope §§8–11 | Auth workflow implementation remains under `src/backend/application/auth_workflow.py`, `src/backend/api/auth_workflow.py`, and `frontend/src/pages/Authenticated*`. Local backend suite and Judge Demo E2E evidence are listed below. User-run external PostgreSQL verification reached PostgreSQL 16 and passed its existing Auth E2E suite (3 expected, 0 skipped, 0 unexpected, 0 flaky; includes idempotency/reload). | The runner's workflow fixture uses deterministic `MOCK_VLM`; this does not establish real AI inference or completion of all Scope 1 workflow/configuration requirements. | Critical workflow invariants pass backend tests; Judge Demo Maker→Checker→Maker browser flow passes. Distinguish synthetic workflow E2E from model-backed evaluation. | Partial — existing workflow/Auth gates evidenced; full Phase 1 remains incomplete. |
| B-02 | Employee directory and lifecycle (EMP-01..05), Scope §8.1 | `/api/workflow/employees` and `/workflow/employees` provide the Admin-only paginated directory. Employee creation is separate from account creation. Activation/reset links are single-use, 30-minute, stored as hashes, and reissue invalidates an older link of the same purpose; recipient chooses the password and Admin hands over the link separately. Successful reset revokes all existing sessions. Checker deactivation requires a per-plan replacement; reassignment, employee INACTIVE, linked account DISABLED, session revocation, token invalidation, workflow event and Admin audit share one transaction. Locking a Checker account or revoking effective CHECKER access is blocked while pending work remains. Reactivation changes only employment state and does not unlock the account or restore removed roles. User-run external PostgreSQL evidence `auth-postgres-verification-7308c19051.json` verifies migration 10, account/token/reassignment gates, lifecycle and concurrency; focused companion evidence is `auth-postgres-verification-dd41dd5e78.json`. | Default Checker selection and whether Makers may choose another Checker remain unspecified. Other Scope 1 EMP requirements outside these tested flows still need acceptance evidence. | Keep employee/account states separate and unknown migrated profile fields null; preserve one-time/expiry/reissue/reset-session rules and atomic replacement/deactivation behavior. | Implemented and verified by the recorded synthetic PostgreSQL gates; product policy/overall Phase 1 acceptance remains partial. |
| B-03 | System roles and plan/admin permissions (PER-01..04), Scope §§8.2, 11.1 | Role catalog endpoints/UI expose the named permission catalog and implement custom role management/audit locally. Built-in Maker/Checker/Admin are seeded and immutable in service. Maker/Checker grants require a different active, activated employee; self changes are denied. Custom ADMIN-management permissions are rejected by create/update/assignment. Full PostgreSQL evidence records migration role seed/19 permission rows plus the Checker-revoke guard and role non-restoration on reactivation; it does not publish a separate custom-role CRUD/assignment API gate. The catalog itself is descriptive data, and each API still needs its own enforcement. | No ADMIN grant/revoke or bootstrap endpoint is available pending a named system owner/operator. ADMIN-management permission codes cannot bypass that lock through a custom role. Standalone read-all/internal-note and approver/SLA controls still lack complete workflow/API behavior; custom-role CRUD/assignment still needs explicit PostgreSQL acceptance evidence. Do not claim full PER-02/03 enforcement. | Keep Admin-role mutations locked. Complete permission enforcement only against defined Scope behavior; preserve built-in immutability and no self-grant. | Partial implementation; owner/operator designation, custom-role PostgreSQL acceptance and several permission behaviors pending. |
| B-04 | Checker selection/reassignment (APR-05, BR-CHK-01..06), Scope §§8.4, 11.1, 11.6 | Assignment validation rejects self and excludes locked/inactive/unactivated employees. Custom full Checker permission bundles are also eligible. Deactivation requires a valid replacement for every pending plan; assignment/event, employee INACTIVE, linked account DISABLED, session-version increment, outstanding-token invalidation and Admin audit are one transaction. Invalid/missing replacement rolls back. Locking a Checker or revoking effective Checker access is blocked while pending plans remain. Reactivation changes employment only; account and removed roles stay unchanged. The full user-run PostgreSQL evidence records these lifecycle gates as PASS. | Default-Checker/Maker-choice behavior remains unspecified. | Preserve explicit replacement and atomic rollback behavior; obtain product policy for default/choice settings before enabling them. | Implemented and verified for recorded lifecycle gates; default/choice policy open. |
| B-05 | SLA configuration, per-round snapshot, due state and warning/overdue status (Scope §§8.5, 11.7, 12) | No SLA configuration or persisted per-round SLA state found. AI recovery timeout is technical, not an SLA. | Duration, calendar mode, warning threshold and owner are not approved; no SLA UI/service. | Admin config uses approved values; each round snapshots its effective config; due state is deterministic; later config changes do not alter active/closed rounds. | Gap / values pending. |
| B-06 | In-app and email notices, delivery state and retry (Scope §§8.6, 11.8, 13) | Workflow append-only events exist; no notification outbox/delivery state was found. | No in-app inbox, recipient policy, channel adapter, or retry; external email provider is not approved. | Required events create durable, idempotent delivery records; in-app status is visible; retry does not duplicate; failed delivery never rolls back submission/decision; email stays disabled absent approved provider/config. | Gap / provider and recipient details pending. |
| B-07 | History, audit, internal notes (Scope §§8.6, 11.9, 14) | Plan events remain append-only; Admin audit API and employee/account/role mutation audit writes exist. Checker reassignment writes both workflow event and Admin audit. The full PostgreSQL helper passes atomic audit/reassignment checks and records that raw handover values are absent from audit; handover URL carries the token in a fragment, not the HTTP request path. | Internal notes are not implemented. | Add notes only within established Scope rules; keep audit append-only and exclude handover secrets. | Partial — lifecycle audit gate verified; internal notes gap. |
| B-08 | Local VLM v2, evidence linked to attachment/hash/snapshot; separate Media and Strategy stages (Scope §8.7, AGENTS) | Provider interface, Local/Mock providers, versioned extraction, task evaluators, hashes and persisted evaluations exist. Strategy schema v5 validated 7 criteria, but content score/confidence were both 0, with 5 missing facts and 3 critical gaps. Media evaluator recorded a provider output hash and reached strict semantic validation. | **Media diagnosis:** prompt v5 says the exact forbidden literal must yield `FAIL`; synthetic OCR contained `UNAPPROVED_GUARANTEE`; at `rule_results[PROHIBITED_CLAIM].result`, expected was `FAIL` and actual was not `FAIL` (`PASS` or `UNKNOWN`). The response body was not persisted, so the exact actual enum cannot be recovered. This was not a JSON parse failure; field/type validation reached cross-field literal consistency, then failed. Old `INVALID_SCHEMA` classification was too broad; the local code now labels this `POLICY_OUTPUT_CONFLICT`, keeps strict validation, and does not retry the contradiction or alter expected output. **VLM:** `qwen3-vl:4b`, pin `sha256:1343d82ebee38e26a4dd6b0180b915eb91550184e67c505dea97509571c8f683` from local `.env`; observed local digest `e8503d318d8df6622abc18a317c0e5eee044821322c87a16a6acddd62984da84` from the saved Ollama tag snapshot. Keep the pin pending provenance approval; no download, pin change, or Mock fallback. | Keep Strategy schema validity distinct from content quality and pipeline success. Full pipeline and Decision Policy Engine did not execute because visual extraction stopped at digest precheck. Route malformed/unknown-version/low-confidence/failed stages to Human Review; no external data without approval. Evidence is in `docs/integration/evidence/media-invalid-schema-diagnostic-2026-10-10.json`, `local-task-evaluators-2026-10-10.json`, and `local-ai-pipeline-2026-10-10.json`. | Partial — Strategy schema evidence only; Media conflict diagnosis/code classification available; full pipeline and VLM output not verified. |
| B-09 | Deterministic budget, controlled Decision Policy Engine, human fallback; Scope §§8.7, 8.8 and decision contract | `src/backend/rules/decision.py` and persisted config snapshots implement deterministic gates; the current full backend suite passed (synthetic/local suite, not AI inference). Auto-approval remains disabled when approved business config is absent. | No Admin policy/budget/rubric configuration API/UI; no approved production values. The real local AI pipeline could not reach Decision Policy Engine because of the VLM digest precheck. | Equality at budget limit passes; over/unknown routes to Human Review; score 71 can pass and 70 cannot auto-approve; changes are versioned/snapshotted and never rewrite history; live auto-approval remains off until approved. | Partial / configuration gap; live auto-approval disabled. |
| B-10 | Auth registration/session, backend permissions and private attachments; AGENTS invariants and Scope §§4–5, 11 | User-run outside-sandbox full PostgreSQL evidence `auth-postgres-verification-7308c19051.json` records current Auth PostgreSQL E2E PASS (3 expected, 0 skipped, 0 unexpected, 0 flaky; idempotency/reload case present), directory authorization/filter/pagination PASS, migration head 10 empty/legacy PASS, and employee/account/token/reassignment PASS. Focused evidence `auth-postgres-verification-dd41dd5e78.json` separately records the employee-admin gate PASS. | Auth E2E uses deterministic `MOCK_VLM`; it does not demonstrate real AI inference. These gates do not prove all Phase 1 workflow, policy, notification or competition requirements. | Preserve the evidence boundaries and verify remaining Scope 1 behavior independently. | Recorded PostgreSQL gates PASS; Scope 1 remains PARTIAL. Historical failed evidence remains unchanged and is not part of this checkpoint. |

## C. Out of scope and unresolved business decisions

| ID | Item / source | Current code and evidence | Gap / boundary | Acceptance criterion | Status |
|---|---|---|---|---|---|
| C-01 | Sprint 1 exclusions/timebox; `AGENTS.md` §§4, 15; official brief pp. 2, 9–10 | The 72-hour Sprint 1 and its “Do not implement” list describe that sprint's competition delivery boundary. The official brief dates Sprint 1 to 19–22 Sep and Sprint 2 to 28 Sep–15 Oct for finalists. | These clauses do not permanently remove EMP-02..05 or PER-01..03 from current product Phase 1, where Scope marks them Must. The official brief separately requires core competition work to occur within sprint windows; current work must not be retroactively labelled Sprint 1 work. Whether the team is a finalist is not evidenced. | Keep the product backlog separate from competition timing/eligibility. Preserve all applicable backend authorization, audit, safety and workflow invariants. | Boundary distinction confirmed; finalist status unknown. |
| C-02 | Phase 1 source acceptance | `docs/scope-phase-1.md` version 1.1 says pending PO/stakeholder confirmation. | The specification is not evidence of approval for business values or the full baseline. | Record explicit approval and version before enabling corresponding live behavior. | Decision required. |
| C-03 | Role/permission authority and employee/account lifecycle | Scope Phase 1 §§8.1–8.2 marks EMP-02..05 and PER-01..03 Must; `AGENTS.md` §4 records Sprint 1 exclusions only. The five policy choices remain fixed. Local services/API/UI implement independent profile/account flows, Admin handover links, Maker/Checker management, role catalog and explicit reassignment. User-run temporary PostgreSQL gates pass for recorded head-10 migration, employee lifecycle, Checker-revoke guard and role seed behavior. | ADMIN grant/revoke remains locked until a system owner/operator is designated; do not open an endpoint or choose an account. Some catalog permissions lack corresponding workflow/API behavior, and custom-role CRUD/assignment has no separate PostgreSQL acceptance result in the supplied JSON. | Keep decisions fixed. Provide the named ADMIN authority/bootstrap path; close remaining required permission behaviors and other Phase 1 gaps. | Policy resolved except ADMIN owner; recorded employee lifecycle/role guards verified; product Scope 1 remains partial. |
| C-04 | Checker defaults and reassignment | The decision record confirms Admin authority for explicit pending-plan replacement and blocking deactivation without an eligible replacement. | Scope still does not decide default Checker selection or whether Maker can choose a different Checker. | Implement only the confirmed reassignment behavior; obtain product policy for default/choice settings before enabling them. | Reassignment policy confirmed; default/choice policy open. |
| C-05 | SLA and notifications | Scope gives relationships and event triggers; durations, calendar values, recipients, email provider and operational owner are not established by current evidence. | Do not invent numeric SLA/warning/retry values or send external messages. | Approve durations, calendar mode, warnings, recipients, channels, retry/backoff and failure ownership. | Decision required. |
| C-06 | Auto-approval policy inputs | Scope/contract define algorithmic gates; approved budget authority, content policy, rubric anchors/weights, and production model/provider config are absent. | Keep Auth/live auto-approval disabled; never tune scores to hit an expected result. | Obtain versioned, approved configurations and test them without changing historical snapshots. | Decision required; safety gate active. |
| C-07 | Competition brief and submission artifacts; official brief pp. 2, 6–10 | Official brief is now present at `docs/competition/challenge-a-brief.pdf.pdf`; Challenge A and general criteria are traced in Section A. | Required submission artifacts and live no-account behavior are not evidenced. The Sprint 2 finalist condition is unknown. | Collect only evidence tied to the actual rubric; do not represent Phase 1 product work as competition compliance without the required public/demo and provenance evidence. | Source confirmed; evidence/artifact gaps remain. |
| C-08 | Phase 2 / explicit exclusions; Scope §17.2 | Multi-level/parallel approvals, delegation, separate request-changes state, market-data integration, AI auto-rejection, model training, third-party media transfer without approval, advanced dashboards/export are explicitly out of Phase 1. | Avoid expanding beyond the approved Phase 1 baseline. | No such feature is introduced without an approved scope change. | Out of scope. |

## Current work package

**WP-EMP-DIR-01 — Admin employee directory (EMP-01, implemented).** The
Admin-only paginated read endpoint and responsive directory view now cover the
Phase 1 list fields. Search includes code, name, phone and email; filters cover
department, job title, role, employee status and account status. The view keeps
employee and account status distinct. The latest user-run full PostgreSQL
evidence verifies the directory on migration head 10; the earlier head-09
report remains historical.

**WP-EMP-PROFILE-02 — Employee profile fields (implemented, additive).** Added
nullable department, job title and employment-start date plus an employee
status constrained to ACTIVE/INACTIVE, separate from the existing login account
status. SQLite and PostgreSQL legacy-upgrade evidence cover additive
upgrade/preservation; in the PostgreSQL legacy fixture, unknown nullable profile
fields remained null while `employment_status` received the migration's
`ACTIVE` default. Full user-run evidence reaches migration head 10.

**WP-EMP-LIFECYCLE-03 — Employee/account lifecycle and roles (local implementation).**
Added employee profile CRUD/deactivation independent from login-account
creation; single-use, 30-minute activation/reset links handed from Admin to the
recipient; recipient-selected password; account lock/unlock and session-version
revocation; append-only admin audit; explicit per-plan Checker reassignment;
custom role catalog and Phase 1 permission composition. Built-in roles are
immutable. Maker/Checker grants require another active, activated account.
ADMIN grant/revoke and bootstrap remain unavailable until the system
owner/operator is named. Deactivation reassigns every pending Checker plan,
marks employment INACTIVE, locks the linked account, revokes all sessions and
invalidates outstanding links in the same transaction; any invalid replacement
rolls the transaction back. Locking or removing effective Checker access while
pending plans remain is blocked. Reactivation only changes employee status and
does not unlock the account or restore revoked roles. Reset links revoke old
sessions only after successful password change. User-run temporary PostgreSQL
focused and full evidence now covers the recorded lifecycle, token race,
migration and directory gates. This is not evidence that Scope 1 is complete.

## Cập nhật xác minh gần nhất

Giữ provenance tách biệt: evidence PostgreSQL bên dưới do người dùng chạy ngoài sandbox theo xác nhận của người dùng; runner chỉ dùng PostgreSQL tạm và không truy cập DB live. Hai evidence lưu kết quả tại `docs/integration/evidence/auth-postgres-verification-dd41dd5e78.json` (focused) và `docs/integration/evidence/auth-postgres-verification-7308c19051.json` (full). [`emp-role-local-verification-2026-10-10.json`](../docs/integration/evidence/emp-role-local-verification-2026-10-10.json) là báo cáo local riêng, không phải PostgreSQL evidence; `database_url` trong đó chỉ ghi `removed from process environment`.

### Focused `--only employee-admin`

- Overall và migration DB trống lên `20261010_10`: **PASS**; PostgreSQL 16.15; DB trống có 3 built-in roles, 19 role-permission rows và không có user/workflow/token/audit rows.
- Employee/account identity, activation, reset/reissue/expiry/replay, thu hồi session sau reset, purpose CHECK constraint trong savepoint, Checker pending-work guard/reassignment/deactivation, rollback, reactivation và redaction audit: **PASS** theo các trường kết quả trong JSON.
- Race RESET: hai client/session/transaction/connection độc lập, barrier đồng bộ; một HTTP 204 và một HTTP 422 `VALIDATION_ERROR`, không exception. `session_version_delta=1`, `password_reset_audit_delta=1`, mật khẩu cũ không còn đúng, session cũ bị thu hồi; replay sau race bị 422 và không có side effect.
- `gates_not_run` ghi rõ: `migration_legacy_database`, `admin_directory_postgres`, `auth_e2e`. Không tính các gate này là PASS từ focused run.
- Cleanup: container do runner sở hữu và temporary files đã xóa; container có trước được giữ nguyên, không có ID nào bị thiếu/thay đổi; `errors=[]`.

### Full runner

- Overall **PASS** trên PostgreSQL 16.15, migration head `20261010_10`.
- DB trống lên head: **PASS**. Schema synthetic cũ có 2 users và 1 workflow plan nâng cấp lên head: **PASS**; users, roles, user_roles, plans, versions, events và employee profiles được giữ; 2 profiles được backfill; trường profile chưa biết vẫn `null`, employment status mặc định `ACTIVE`; defaults và 19 role-permission rows được giữ.
- Danh bạ Admin: **PASS** — anonymous 401, Maker 403, Checker 403, Admin 200; các bộ lọc search/role/account status/department/job title/employment status và phân trang offset/limit trả distinct rows với total=2; response fields an toàn; số workflow events không đổi.
- EMP/account/token/role/reassignment helper: **PASS**. Bao gồm token một lần, hạn 30 phút, chỉ lưu SHA-256, reissue vô hiệu token cũ, replay/expiry/purpose handling; reset thành công thu hồi session cũ. Purpose ngoài catalog bị đúng `ck_auth_management_tokens_purpose`/SQLSTATE `23514` chặn trong savepoint và rollback không làm đổi RESET token hợp lệ. API tiêu thụ chung `/api/auth/activate`, nên không có ca endpoint riêng cho “dùng sai thao tác”.
- Race RESET: hai request độc lập; một 204 và một 422 `VALIDATION_ERROR`; `session_version_delta=1`, `password_reset_audit_delta=1`, chỉ password của request thắng khớp, session cũ bị thu hồi; replay kế tiếp 422 và không thay đổi audit/session/mật khẩu.
- Checker lock/role revoke khi còn pending bị chặn; deactivation đòi replacement cho từng plan; reassignment/deactivation/account lock/audit nguyên tử; invalid reassignment rollback; reactivation không tự mở account hoặc phục hồi role.
- Auth E2E: **PASS**, 3 expected, 0 skipped, 0 unexpected, 0 flaky; idempotency/reload case hiện diện. Provider được evidence ghi là deterministic `MOCK_VLM`; đây không phải real AI inference.
- Cleanup: container tạm do runner tạo và temporary files đã dọn; toàn bộ container có trước được giữ nguyên; không có container bị thiếu/thay đổi; `errors=[]`.

### Working-tree identity và giới hạn

Hai JSON đều ghi branch `codex/scope1-phase1-continuation-20261010`, HEAD `f27e6ba0e9d96fa8d1b420c140a43a7e8cd466e0` và `working_tree.dirty=true`; HEAD đơn lẻ không định danh source được kiểm tra. Fingerprint lần focused là `15d75df87e5f426056882c7b541629a6a0e830814a55858bd9bd81bda2b3022f`; lần full là `b488befbf4727f435310ca2398612f819ddaa4b524e0600f16852d6f74a0b3be`. Cả hai được tái tính từ danh sách file tại runner start và khớp chính xác. Snapshot bao gồm các thay đổi local chưa commit khác trong working tree, không chỉ EMP/Role. Các sửa đổi tài liệu của báo cáo này xảy ra sau hai lượt runner; source implementation không đổi kể từ fingerprint.

Các evidence này chỉ chứng minh những gate nêu trên. Auth E2E dùng `MOCK_VLM`; không suy ra real AI inference, public competition judging hoặc hoàn tất Scope 1. Scope 1 vẫn **PARTIAL**: ADMIN grant/revoke và bootstrap tiếp tục bị khóa chờ chỉ định system owner/operator; một số quyền chỉ có trong catalog chưa có hành vi API đầy đủ; các phần SLA/notification/policy và evidence competition/public judge còn thiếu. Evidence lỗi lịch sử được giữ nguyên local; `auth-postgres-verification-f4802d9b15.json` có SQL parameters/token hash nên không đưa vào checkpoint công khai.
