# Leakage Policy

Run leakage checks before freezing a validation set and before using it for readiness claims. Report `execution_status: not_evaluated` when there are no items; never report `ok` for an empty inspection.

## Blockers

Block or downgrade the set when:

- raw body field names are persisted in durable artifacts, even with empty/null values
- fixture/synthetic/metadata-only records are promoted to sampled-real or real-reviewed status
- a local source path escapes the declared root, resolves through a symlink outside it, disappears, or no longer matches its SHA-256
- an opaque/remote source is promoted beyond candidate without an explicit authoritative attestation
- duplicate `item_id` values exist
- labels reference missing items
- sealed holdout labels are exposed to implementation workers
- `quality_tier: gold` lacks human-reviewed or fully deterministic authoritative evidence

## Checks

Check:

- duplicate `source_hash`, `preimage_hash`, or item hash values
- identical source locator reused across train/test-like splits without an explicit allowed reason
- raw-body field names such as `raw_body`, `provider_body`, `full_text`, `source_text`, or `document_body`
- source class and evidence status consistency
- oracle references that cannot be resolved
- schema-v2 local source byte/hash bindings and authoritative-attestation fields before finalization

When source evidence is unavailable, return `blocked_or_candidate_only` with a concrete blocker. Do not fill the gap with fixtures while claiming sampled-real progress.
