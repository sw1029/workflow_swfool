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

Return `not_evaluated` when an execution has no items, no oracles, or no supported item-oracle pairs. For authoritative gold evidence, identify deterministic/executable oracle IDs explicitly, set `authoritative: true` as a JSON boolean, and include bounded `evidence_paths`.

## Durable Execution Results

Run schema-v2 sets with `run_validation_oracles.py --root <root> --set-root <set-root>`. Bind the result to the current item and oracle-manifest file SHA-256 values and bind each executed pair to canonical `item_content_sha256` and `oracle_definition_sha256`. Validation must deterministically re-execute the current predicate and compare exact status/failures; updating hash metadata cannot preserve an obsolete pass. Record exact required, executed, unsupported, result, and failure counts. Only `execution_status: completed`, `status: passed`, zero failures, and complete required-pair coverage are non-blocking for finalization. Rerun oracles after either input changes.

Every item-referenced oracle is a required pair. Non-deterministic, non-item, or otherwise unsupported pairs are not silently skipped: require an accepted authoritative human-reviewed label for that exact item/oracle pair, or block consumption.
