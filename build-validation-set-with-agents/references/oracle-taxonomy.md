# Oracle Taxonomy

Prefer oracles in this order.

1. `deterministic`: schema, required fields, ID uniqueness, source-class rules, no-overclaim flags, graph invariants.
2. `executable`: pytest, CLI validator, graph checker, parser round-trip, script result.
3. `span_hash`: source span, quote hash, source locator, preimage hash, bounded excerpt hash.
4. `reference`: comparison to a reviewed fixture, approved artifact, or authoritative small reference.
5. `agent_consensus`: semantic labels, motif, causality, narrative/world-rule judgment. Keep `not_gold: true`.
6. `human_reviewed`: human-reviewed label or adjudication. Required for most gold semantic claims.

## Oracle Manifest

Each oracle record should include:

- `oracle_id`
- `oracle_type`
- `target`: `item`, `label`, `set`, `output`, or `root`
- `description`
- `required_fields`, `forbidden_fields`, or `allowed_values` for deterministic runner support when applicable
- `evidence_paths` for executable or reference oracles

Do not claim gold because multiple agents agree. Agent consensus can reduce uncertainty, but it is still `candidate` or `silver` unless independently grounded.
