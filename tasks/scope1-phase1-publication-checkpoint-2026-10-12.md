# Scope 1 publication checkpoint — 2026-10-12

## Identity and evidence boundary

- Clean publication branch: `codex/scope1-publication-clean-20261012`.
- Requested checkpoint before this local close-out: `460db9afbad0289fb9c4bef8333c98cdf2e07176`.
- Baseline: `8cd5e03c8f58354b6053c6544b8b3b2687e4c8c8`.
- PostgreSQL evidence uses disposable PostgreSQL 16 instances with synthetic users, plans, attachments and configuration. No live database was used.
- Browser Auth/SLA/configuration and retry runs use the integrated app with `MOCK_VLM`. Judge Demo regression uses a separate disposable SQLite database. These results establish integration behavior only.
- The prior notification evidence files had mismatched source fingerprints, so the three notification/retry tests were rerun against this checkpoint's source.

## PostgreSQL tests previously deselected by the default suite

All 13 tests were explicitly collected with `pytest --collect-only -q -m postgres`. The default broad test command deselects them because they carry the `postgres` marker. Tests 1–10 ran together in a focused temporary-PostgreSQL run (`10 passed`, two deprecation warnings). Tests 11–13 ran together in a separate current-source run (`3 passed`, one warning). None of the 13 remains unrun; they were run in focused groups rather than one test process per case.

| # | Test | Result / run group | Why it was deselected / separate evidence |
|---:|---|---|---|
| 1 | `test_admin_api_returns_unconfigured_and_rejects_maker` | PASS — group 1 (tests 1–10) | PostgreSQL marker; explicitly included in the focused temporary-DB gate. |
| 2 | `test_admin_revision_requires_allowed_browser_origin_and_keeps_auto_approval_off` | PASS — group 1 | PostgreSQL marker; explicitly included in the focused temporary-DB gate. |
| 3 | `test_concurrent_first_revision_has_exactly_one_winner` | PASS — group 1 | PostgreSQL marker; explicitly included in the focused temporary-DB gate. |
| 4 | `test_round_version_and_configuration_snapshot_rollback_together` | PASS — group 1 | PostgreSQL marker; explicitly included in the focused temporary-DB gate. |
| 5 | `test_postgres_snapshot_boundaries_recipients_replay_reassignment_and_resubmit` | PASS — group 1 | PostgreSQL marker; explicitly included in the focused temporary-DB gate. |
| 6 | `test_postgres_concurrent_config_writes_and_submit_capture_one_revision` | PASS — group 1 | PostgreSQL marker; explicitly included in the focused temporary-DB gate. |
| 7 | `test_postgres_parallel_workers_are_idempotent_and_rollback_is_atomic` | PASS — group 1 | PostgreSQL marker; explicitly included in the focused temporary-DB gate. |
| 8 | `test_postgres_decision_and_checker_reassignment_win_worker_lock_races` | PASS — group 1 | PostgreSQL marker; stale race fixture was aligned with the persisted Marketing department and checker-assignment snapshot contract. |
| 9 | `test_postgres_migration_constraints_indexes_and_immutability_triggers` | PASS — group 1 | PostgreSQL marker; explicitly included in the focused temporary-DB gate. |
| 10 | `test_postgres_missing_and_disabled_configuration_do_not_start_a_round` | PASS — group 1 | PostgreSQL marker; explicitly included in the focused temporary-DB gate. |
| 11 | `test_postgres_retry_race_reuses_the_round_snapshot` | PASS — group 2 | PostgreSQL marker; prior artifacts did not match current-source fingerprints, so rerun. |
| 12 | `test_postgres_policy_conflict_persists_safe_attempt_provenance_and_routes_to_checker` | PASS — group 2 | PostgreSQL marker; prior artifacts did not match current-source fingerprints, so rerun. |
| 13 | `test_postgres_notification_lifecycle_permissions_replay_and_rollback` | PASS — group 2 | PostgreSQL marker; prior artifacts did not match current-source fingerprints, so rerun. |

The focused database gates cover employee/account access, configuration revision races, checker reassignment, notification lifecycle and permissions, retry concurrency, policy-conflict provenance, and rollback. The new browser fixtures seed linked synthetic Maker/Checker/Admin employee profiles and a synthetic default Checker assignment; those values are test setup, not an approved business policy.

## Migration runtime verification

Actual temporary PostgreSQL migration runs, in addition to static graph inspection:

- Empty PostgreSQL 16 database → Alembic head `20261012_16`: PASS; one Alembic head and 24 application tables.
- Synthetic database at actual baseline revision `20261012_12` → `20261012_16`: PASS; one head. Preexisting synthetic rows were compared before and after and preserved.
- Runtime graph: revisions 13 and 14 both descend from 12; revision 15 merges 13 and 14; revision 16 descends from 15. The migration order was verified from `down_revision` and exercised against both database states.

## Frontend and browser acceptance

- Frontend TypeScript typecheck (`npm run typecheck`): PASS.
- Retry-panel Vitest regression: PASS, 3 tests. The success message remains visible after the round limit hides the retry button.
- Integrated Auth browser suite: the three Auth specs and the dashboard/configuration/notes/retry spec passed on temporary PostgreSQL. The integrated spec was rerun after adding the terminal policy-conflict case and passed 1/1.
- SLA browser spec: PASS, 1/1 on temporary PostgreSQL. It covers Admin configuration, Maker submission, Checker reminders and decision, resubmission, per-round snapshot history, and elapsed SLA boundaries. Focused runs exposed two incorrect test assumptions: `closed_at` can be later than `due_at`, and `seconds_until_due` is derived and changes over time. The assertions now match those semantics while comparing all stored SLA history fields.
- Judge Demo regression `factual evidence and real Verify results render`: PASS, 1/1 on a separate temporary SQLite database; Verify returned 4/4 and 5/5.
- The publication browser scenario covers Admin versus Maker permissions, valid-but-unsupported rubric messaging, the old round snapshot after a later config revision, Checker-only notes, terminal `EVALUATOR_RUBRIC_UNSUPPORTED` and `POLICY_OUTPUT_CONFLICT`, a retryable `INVALID_SCHEMA`, preserved attempt/model/input/policy provenance, and rejection of a second manual retry in the same round.

These are synthetic integration gates. They do not measure real model accuracy or approve any policy weights.

## Migration, snapshot, retry and provenance contract

- Round creation captures the configuration snapshot once in the transaction that creates the approval round. Evaluation and retry use that stored snapshot and do not resolve current configuration again.
- The evaluator currently supports only the baseline `StrategyRubric`; a structurally valid custom-weight rubric can be saved but must be shown as unsupported by the evaluator and fail closed.
- `EVALUATOR_RUBRIC_UNSUPPORTED` and `POLICY_OUTPUT_CONFLICT` are terminal. Manual retry for `INVALID_SCHEMA` / `INVALID_PROVIDER_RESPONSE` is bounded to one attempt per round and remains separate from internal provider retries.
- Attempt history, model identity/provenance, and safe conflict totals are persisted. No raw model output was added to public evidence.
- Evidence for this checkpoint does not contain a raw hash for each policy conflict. No historical hash has been attached to a new run.

## Traceability status

| Status area | Checkpoint result |
|---|---|
| Integration and fail-closed acceptance | PASS for the database and browser gates listed above, using synthetic data and the mock provider. |
| Real AI quality | FAIL. This checkpoint is not a quality acceptance for live Media/Strategy model output. |
| VLM inference | BLOCKED. The reported digest mismatch remains unresolved; no VLM inference was performed for this checkpoint. |

Open Phase 1 Must items remain:

- Scope 1 v1.1 still requires product-owner/stakeholder approval of the policy values. Test-only SLA and Checker defaults do not approve them.
- Admin authority/bootstrap still awaits a named system owner/operator; some role/permission behaviors and custom-role PostgreSQL acceptance remain open.
- Checker default-versus-Maker-choice behavior remains a business decision.
- In-app notification lifecycle is covered, but the Phase 1 email-notification Must and approved recipients/channels/retry ownership remain open.
- AI-02/AI-03/AI-04 quality and VLM inference are not accepted; approved content policy, rubric anchors/weights, budget authority and production provider/model configuration are still missing. Keep auto-approval disabled and Human Review fail-closed.
- The complete Phase 1 workflow, audit and competition/public-judge requirements are not claimed complete by these focused gates.

See [`scope1-phase1-traceability-2026-10-10.md`](scope1-phase1-traceability-2026-10-10.md) for the requirement-level source map; this checkpoint supersedes its older evidence status only for the gates listed above.

## Publication history audit

The complete four-commit range from the requested baseline to checkpoint `460db9afbad0289fb9c4bef8333c98cdf2e07176` was inspected at commit-blob level (74 changed blobs). It contains no `handoff-a.md`, `handoff-b.md`, or `handoff-c.md` path and no copied-content candidate against the three files in excluded commit `df64da278e9e5949ba7fcb44ff8eb6261171ca69`. The scan found no raw log paths, private keys, AWS credentials, bearer tokens or JWTs. Four credential-pattern matches were confined to synthetic test/API-key placeholders; observed email domains were example/test domains. No real user records were identified.

No push, pull request, main merge, deployment or model-pin change is part of this checkpoint.
