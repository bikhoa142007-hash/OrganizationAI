# Phase 1 employee and role decisions — 2026-10-10

## Scope interpretation

The current task explicitly targets **Scope Phase 1**, so Sprint 1's 72-hour
timebox and its "Do not implement in Sprint 1" list do not permanently remove
Phase 1 Must requirements. Those clauses describe the historical Sprint 1
delivery boundary. The official competition brief is a separate source for
eligibility and judging; it does not define the employee/account decisions
below. The Scope document itself still says it is pending PO/stakeholder
confirmation, except the five policy choices explicitly confirmed by the user
for this work.

The AGENTS.md business invariants and security rules remain applicable while
implementing Phase 1: backend authorization, no self-approval, valid active
Checker assignment, immutable audit/history, no default passwords, and no
silent privilege escalation. The five decisions below are **settled and must
not be reopened during implementation**. No role, assignment, account or
password was changed by recording these decisions.

## Decision table

| ID / Scope requirement (verbatim source) | Behavior to implement | Confirmed decision | Implementation boundary / remaining detail |
|---|---|---|---|
| **D-01 / EMP-02 —** “Quản lý thông tin nhân viên &#124; Administrator &#124; Tạo, xem, cập nhật và ngừng hoạt động nhân viên &#124; Must” — `docs/scope-phase-1.md` §8.1. Employee profile fields are listed below the table. | Create, inspect, update and deactivate an employee profile. Keep employment status separate from account status; audit changes. | **Confirmed:** employee profile creation does not require creating a login account. EMP-02 and EMP-03 are separate operations; an employee may have no account. Deactivation sets employment INACTIVE and locks a linked account, revokes sessions, and invalidates outstanding management links. Reactivation changes employment status only; it does not unlock the account or restore removed roles. | Required/unique field rules and edits to identity data after activation remain unspecified. The Scope lists profile fields but does not mark each as required. |
| **D-02 / EMP-03 —** “Quản lý tài khoản đăng nhập &#124; Administrator &#124; Tạo tài khoản, đặt lại mật khẩu, khóa/mở khóa &#124; Must” — `docs/scope-phase-1.md` §8.1. | Create/activate a login, reset password, lock/unlock accounts; audit; do not expose credentials or token secrets. | **Confirmed:** no default or administrator-known password. Admin initiates activation/reset and separately hands the recipient a single-use link; the recipient sets their own password. Activation/reset tokens expire in 30 minutes, only token hashes are stored, and reissue invalidates earlier tokens of that purpose. Successful reset revokes every existing session; issuing a reset link does not. Raw token/link material is excluded from logs and audit. | Link delivery is manual, not automatic email. The competition brief does not require this account flow. |
| **D-03 / EMP-04 —** “Gán vai trò hệ thống &#124; Administrator &#124; Gán vai trò quyết định quyền sử dụng module &#124; Must” — `docs/scope-phase-1.md` §8.1. **BR-AUTH-09 —** “Quyền từ các role được gán được cộng dồn; ADMIN chỉ cho đọc workflow, ADMIN+MAKER có quyền Maker trên kế hoạch của mình, và ADMIN không tự cấp quyền MAKER hoặc CHECKER” — §11.1. | Grant/revoke roles through authorized service; enforce at backend APIs; audit actor, target and before/after roles. | **Confirmed:** Admin may grant/revoke Maker and Checker only for another employee with an activated account; Admin cannot self-grant/revoke Maker/Checker. ADMIN grant/revoke, bootstrap and last-Admin changes remain locked until a separate system owner/operator is named. | The authorized system-owner is an implementation prerequisite. No implicit Admin self-escalation or last-Admin removal. No role assignment is performed merely by documenting the rule. |
| **D-04 / EMP-05 —** “Kiểm soát nhân viên ngừng hoạt động &#124; Administrator/System &#124; Không cho chọn làm Checker; yêu cầu chuyển kế hoạch đang chờ nếu cần &#124; Must” — `docs/scope-phase-1.md` §8.1; **BR-AUTH-08** §11.1 and **BR-CHK-06** §11.6. | Inactive or locked employees cannot be selected as new Checkers. Preserve assignment history when transferring pending work. | **Confirmed:** before deactivating an assigned Checker, Admin explicitly selects an eligible replacement for each affected pending plan (or an explicit batch). Reassignment and employee/account state changes plus assignment history and audit commit atomically; absent or invalid replacement blocks and rolls back. Locking a Checker account or revoking effective CHECKER access is blocked while pending work remains. Never auto-reassign. | Scope's phrasing “nếu cần” is implemented as a blocking transfer when pending plans exist, to avoid orphaned approvals. Default Checker/Maker-choice policy remains a separate open product setting. |
| **D-05 / PER-01..04 —** `docs/scope-phase-1.md` §8.2: PER-01 role catalog create/edit/deactivate (Must); PER-02 marketing-plan permissions (Must); PER-03 admin permissions (Must); PER-04 inherited permission summary (Should). | Manage built-in/custom role catalog and named permissions; enforce effective permissions at APIs; audit changes and avoid deleting assigned roles. | **Confirmed:** Maker, Checker and Admin are immutable built-ins. Custom roles may compose allowed Phase 1 permissions. ADMIN-management permission codes are reserved and rejected by custom-role create/update/assignment until an owner/operator exists. Preserve Admin read-only workflow and no self-approval/self-grant invariants. | A permission's appearance in a catalog is not proof that an API action is implemented or authorized. PER-01..03 remain implementation requirements; complete plan/admin permission enforcement must be verified independently. |

## Decision state and remaining work

All five decisions D-01..D-05 above are confirmed by the user's current
instruction and must remain unchanged. The official Challenge A brief does not
prescribe employee creation, activation/reset links, role grant authority,
Checker reassignment, or custom role design. The manual Admin link handover is
compatible with the brief only if the judge-facing Live URL remains usable
without an account; requiring judges to activate accounts would conflict with
the brief's no-account requirement (pp. 2, 6–8). That judge route is not yet
verified.

No role was granted/revoked, no assignment or password was changed, and no
live employee/account data was changed while recording or implementing these
decisions. The current worktree contains local EMP/RBAC endpoints and UI, but
this does not prove PostgreSQL acceptance. ADMIN grant/revoke remains locked
pending a named system owner/operator and approved bootstrap method. The
default-Checker policy remains unresolved separately from the five confirmed
decisions.
