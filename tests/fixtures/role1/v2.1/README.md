# Role 1 synthetic test fixtures

Source: extracted role1-sprint1-v2.1 package. JSON and image bytes are preserved.
Images moved from data/fixtures/ to images/; fixture path strings and original
manifest are source provenance, not runtime attachment identity.

`fact-verification.schema.json` is **PROPOSED_FIXTURE_SCHEMA**, not a WP1 schema.
`verify-expected-results.json` is an assertion oracle; only runner/tests may read
it. Ground-truth case expected blocks are also assertion-only. Provider accepts
only each case's input object, never the envelope or expected result.

See docs/integration/role1-contract-mapping.md and role1-import-manifest.json for
mapping and source/copy checksums. No fixture is production configuration.
