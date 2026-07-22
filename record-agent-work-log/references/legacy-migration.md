# Legacy Agent-Log Migration

Use `python3 -P -m record_agent_work_log migrate` only for a legacy or malformed `.agent_log`
store that the normal writer correctly refuses to extend. Do not relax the
normal reader or hand-edit `index.jsonl`.

## Transaction

Run the commands in this order:

```bash
RECORD_LOG_SCRIPTS="${CODEX_HOME:-$HOME/.codex}/skills/record-agent-work-log/scripts"

PYTHONPATH="$RECORD_LOG_SCRIPTS" python3 -P -m record_agent_work_log migrate inspect --root ROOT --json
PYTHONPATH="$RECORD_LOG_SCRIPTS" python3 -P -m record_agent_work_log migrate plan --root ROOT \
  --expected-index-sha256 SHA --status-map STATUS-MAP.json --output PLAN.json
PYTHONPATH="$RECORD_LOG_SCRIPTS" python3 -P -m record_agent_work_log migrate apply --root ROOT --plan PLAN.json \
  --expected-plan-sha256 SHA --expected-index-sha256 SHA \
  --expected-inventory-sha256 SHA --dry-run
PYTHONPATH="$RECORD_LOG_SCRIPTS" python3 -P -m record_agent_work_log migrate apply --root ROOT --plan PLAN.json \
  --expected-plan-sha256 SHA --expected-index-sha256 SHA \
  --expected-inventory-sha256 SHA
PYTHONPATH="$RECORD_LOG_SCRIPTS" python3 -P -m record_agent_work_log migrate validate --root ROOT \
  --receipt .agent_log/migrations/ID/receipt.json --require-appendable
PYTHONPATH="$RECORD_LOG_SCRIPTS" python3 -P -m record_agent_work_log verify-migration --root ROOT \
  --receipt .agent_log/migrations/ID/receipt.json \
  --expected-status-map STATUS-MAP.json \
  --expected-recovery-status not_needed
```

`inspect` is read-only. `plan` writes only its caller-selected plan output and
does not change the canonical store. `apply` is blocked unless every source row
and Markdown body has one exact disposition and `unresolved_count` is zero.

The final command is a read-only, source-separated trust-boundary check. It
does not import or call the migration producer. A producer return value,
receipt claim, or rehashed sidecar is insufficient: the verifier independently
reconstructs source rows, exact status mappings, Markdown inventory,
duplicate/orphan dispositions, counts, committed records, journal bindings,
and the marker/index publication boundary. It may run against a byte-for-byte
copied workspace fixture; the plan's root identity remains provenance rather
than a hardcoded current path. A copied fixture must still contain every
migration-time body unchanged. `--expected-status-map` must be a caller-owned
exact copy outside every `.agent_log/migrations/` sidecar tree. The verifier
also checks the external source recorded in `plan.status_map.ref`; neither that
reference nor the caller-owned oracle may diverge from the published copy.
Passing a transaction sidecar back as its own trust anchor fails.

## Exact Status Map

Keep repository-specific tokens in a caller-owned JSON file, never in the
helper. The map has this shape:

```json
{
  "schema_version": 1,
  "mapping_policy_id": "caller-policy-id",
  "version": "1",
  "entries": [
    {
      "original_status": "partial",
      "normalized_status": "partial",
      "reason": "exact partial identity"
    },
    {
      "original_status": null,
      "normalized_status": "informational",
      "reason": "status was not evaluated",
      "status_evidence": "not_evaluated"
    }
  ]
}
```

Enumerate every observed string exactly. Do not use prefix, substring, glob, or
regular-expression completion rules. An unknown token remains unresolved. A
non-`completed` token cannot be mapped to `completed`; missing status can only
be `informational` with `status_evidence=not_evaluated`.

## Plan And Manifest

The deterministic plan binds:

- the resolved root identity;
- source index path, SHA-256, byte length, and raw-row count;
- the complete path/hash/size Markdown inventory digest;
- the exact status-map path, SHA-256, policy ID, and version;
- one classification and disposition for every source row;
- one disposition for every Markdown body;
- the expected canonical prefix SHA-256, length, and row count.

Source rows are `canonical_log`, `duplicate_alias`, `foreign_event`, or
`unresolved`. An unsafe path, malformed JSON, missing/tampered body, unmapped
status, or unresolved duplicate tie blocks apply. No-path lifecycle events stay
in the byte-identical source snapshot and manifest; they are not forged into log
rows or moved to another ledger.

For duplicate paths, body/log metadata selects the uniquely best-supported row.
An exact-byte duplicate may use a deterministic equivalent representative; a
non-identical tie blocks. Byte-identical bodies at different paths cannot both
be current rows because `content_id` remains body-derived and duplicate IDs
remain fail-closed. The plan keeps one canonical body and seals the others as
non-consumable alias evidence. The shared inspector excludes only those exact
manifest-bound paths from collectors.

Unindexed regular in-root Markdown is bound as `legacy_import=true`,
`structured_fields_status=not_evaluated`, and `status=informational`. A
byte-identical redundant body may instead be `quarantine_nonlog_body`. Bodies
are never moved or changed.

## Publication And Recovery

Apply uses `.agent_log/index.lock` and rechecks the expected source index and
inventory inside the lock. It then:

1. publishes and fsyncs the byte-identical source snapshot;
2. publishes the status map, plan, resolution manifest, and staged index;
3. writes a prepare journal;
4. switches the canonical index to the staged current-format prefix;
5. writes a completion receipt and active commit marker;
6. validates the marker, receipt, sidecars, body inventory, current-row
   identities, and appendability;
7. marks the journal committed.

The marker binds the migration commit boundary by exact prefix length and
SHA-256. Standard current rows may be appended after that boundary; all such
tail rows remain strictly validated. Removing or changing the marker, receipt,
snapshot, plan, map, manifest, prefix, or a sealed body invalidates the store.

Use `recover --root ROOT --transaction-id ID` after a crash. Before index switch,
recovery keeps the original index unchanged and marks prepared work retryable.
After switch, recovery never rolls history back: it forward-completes the
receipt and marker. Source or prefix drift blocks automatic recovery. Reapplying
the exact committed plan is an idempotent no-op; a different plan conflicts.
After forward recovery, run the independent verifier and require
`recovery_status=forward_completed`. Repeating the verifier over an unchanged
graph must return the same `graph_sha256`; this observes replay idempotency
without replaying or recovering a live migration. A forward-recovered graph
also requires `--recovery-observation OBSERVATION.json`, captured by the
read-only transaction-boundary observer before recovery. The observation must
prove a hash-bound post-switch/incomplete state. Preserve its emitted hash
outside the transaction and pass it as
`--expected-recovery-observation-sha256 SHA`; the final graph digest binds that
hash. Changing only the producer's receipt/journal recovery strings, or
coherently rehashing the observation without the external hash anchor, cannot
pass. Set `--expected-recovery-status forward_completed`; this caller-owned
expectation is mandatory so a recovered graph cannot erase its observation
requirement by rewriting receipt/journal strings to `not_needed`.

The receipt kind is `agent_log_legacy_migration`. It binds the source snapshot,
inventory, plan, map, manifest, before/after index boundaries and counts,
integrity result, appendability, zero body mutation, and
`historical_claims_upgraded=false`. Sidecars store only paths, hashes, line
numbers, enums, reasons, and counts; they do not copy Markdown, prompt, corpus,
or transcript bodies.
