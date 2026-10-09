# BA synthetic test fixtures

Source: extracted role1-sprint1-v2.1 package. JSON and image bytes are preserved.
Images moved from data/fixtures/ to images/; fixture path strings and original
manifest are source provenance, not runtime attachment identity.

`fact-verification.schema.json` is **PROPOSED_FIXTURE_SCHEMA**, not a WP1 schema.
`verify-expected-results.json` is an assertion oracle; only runner/tests may read
it. Ground-truth case expected blocks are also assertion-only. Provider accepts
only each case's input object, never the envelope or expected result.

See docs/integration/ba-contract-mapping.md and ba-import-manifest.json for
mapping and source/copy checksums. No fixture is production configuration.

Judge Verify suites added 2026-10-09:
- `general`: 4 cases; three routine and one factual escalation.
- `escalation`: all 5 Verify inputs; three routine and two escalations.
- `regression`: all 15 ground-truth cases across the three escalation classes,
  routine cases, and hard-violation boundaries.

Each run executes only the case `input` in a fresh in-memory workflow before
the runner reads its separate expected-results oracle. These synthetic
fixtures are the published regression catalog, not a proven blind holdout from
system development or a model-quality benchmark.
