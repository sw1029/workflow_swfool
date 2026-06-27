# Leakage Policy

Run leakage checks before freezing a validation set and before using it for readiness claims.

## Blockers

Block or downgrade the set when:

- raw body fields are persisted in durable artifacts
- fixture/synthetic/metadata-only records are promoted to sampled-real or real-reviewed status
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

When source evidence is unavailable, return `blocked_or_candidate_only` with a concrete blocker. Do not fill the gap with fixtures while claiming sampled-real progress.
