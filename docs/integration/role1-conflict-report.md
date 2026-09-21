# Role 1 / WP contract differences

Integration date: 2026-09-22. Authority: AGENTS, existing WP contracts, and the
user's explicit integration request. No frozen contract file was overwritten.

| Difference | Resolution |
| --- | --- |
| AGENTS references missing Vietnamese filenames | Existing docs/scope-phase-1.md and docs/sprint-1-deliverables.md are the available source documents; missing filenames were not fabricated. |
| Role 1 fact_verification is proposed | Treat as PROPOSED_FIXTURE_SCHEMA, validate strictly, map into existing missing_facts/evidence_conflicts/evidence. No WP schema extension or migration. |
| REVIEW_REQUIRED was always treated as policy failure | Reproduced GT-007/008 failure with successfully mapped evidence. MEDIA_PASS still fails; classify that failure FACT_UNCERTAIN when unresolved facts exist and no rule-backed media finding exists. Independent policy/authority failures retain precedence. |
| GT-014/015 expected category is null on Human Review | Role 1 does not specify a category for these hard cases; WP runtime emits POLICY_OUT_OF_SCOPE. Test route, pending state, absence of final decision, hard-rule evidence and questions. Do not emit a WP Verify row with invalid null expected category; retain the GT regression report. Expected files unchanged. |
| Role 1 reason codes differ from runtime rule IDs | Map assertions to persisted checks/evidence; do not add new engine outcome/rule IDs just to mirror fixture vocabulary. |
| Role 1 VLM confidence vs frozen media confidence gate (OQ-01) | Preserve both confidence values separately in evidence. Do not introduce another production gate. Cases with low VLM confidence already have unresolved facts and/or low media confidence. |
| Role 1 100m VND vs old WP5 10000 VND demo | Separate configurations: old Streamlit demo untouched; HTTP demo has explicit DEMO-HTTP-1 with 100m; Role 1 test adapter uses the fixture's own policy/criteria. No company limit is inferred. |
| Request Changes / Stop / Undo in UI mock | No new human action or reopening of final rounds. UI offers Approve/Reject; revision follows rejection. Stop controls removed from API-backed flow. Initial unevaluated submitted round can be continued; committed evaluation cannot be rerun. |
| Existing domain expects trusted principals | FastAPI resolves X-Demo-Actor only in APP_ENV=demo against server directory; provider identity is never a public actor. Production rejects demo authentication. |
| Historical WP1 implementation-plan says repo has no code/Git | Retained as historical baseline. Current audit and integration report supersede its inventory, not its contracts. |

## Open decisions

Production identity provider, company policy/limits, real Local VLM deployment,
VLM-only confidence gate, kill switch behavior and the Role 1 proposed policy
questions remain OPEN_DECISION for their owners. They do not block the explicitly
authorized synthetic demo. No external inference is enabled.

Hard-violation category oracle completion remains a Role 1 documentation decision;
the original null expectations were preserved, and the tests do not claim full WP
Verify compatibility for those two rows.
