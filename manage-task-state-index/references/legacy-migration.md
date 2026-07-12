# Task-State Legacy Migration Contract

## Contents

- [Authority and scope](#authority-and-scope)
- [CLI](#cli)
- [Mapping and row disposition](#mapping-and-row-disposition)
- [Plan, seal, and receipt graph](#plan-seal-and-receipt-graph)
- [Publication and recovery](#publication-and-recovery)
- [Strict-reader compatibility](#strict-reader-compatibility)

## Authority and scope

Use `scripts/task_state_migration.py` only for an explicitly authorized legacy-ledger migration. Keep normal `init|scan|add|link|rebuild|audit` behavior strict. A plan is not authority to mutate: bind apply to the exact plan file SHA, source prefix SHA, mapping SHA, root identity, and caller-designated task and pack identities.

Preserve the complete source `.task/index.jsonl` as a byte-identical prefix and immutable snapshot. Never normalize, delete, reorder, or edit a historical prefix line. Keep repository-specific event, status, and type tokens in the caller-owned mapping manifest; do not add them to the helper.

## CLI

```bash
python3 scripts/task_state_migration.py --root ROOT inspect

python3 scripts/task_state_migration.py --root ROOT migrate plan \
  --expected-index-sha256 SHA \
  --current-task-id ID --current-task-path task.md --current-task-sha256 SHA \
  --current-pack-id ID --current-pack-path PATH --current-pack-sha256 SHA \
  --mapping-manifest MAP.json --output-plan /tmp/PLAN.json

python3 scripts/task_state_migration.py --root ROOT migrate apply \
  --plan /tmp/PLAN.json --expected-plan-sha256 SHA \
  --expected-index-sha256 SHA [--dry-run]

python3 scripts/task_state_migration.py --root ROOT migrate validate \
  --receipt RECEIPT.json --require-current-projection-evaluated \
  --require-single-active-task --require-single-active-pack --require-appendable

python3 scripts/task_state_migration.py --root ROOT migrate recover \
  --transaction-id tsm-...
```

`inspect`, `plan`, and `apply --dry-run` do not mutate canonical `.task` state. Keep the plan outside `.task` until a successful apply snapshots it into the transaction directory.

## Mapping and row disposition

Use mapping schema version 1:

```json
{
  "schema_version": 1,
  "mapping_policy_id": "caller-owned-policy-id",
  "mapping_method": "exact_token_review",
  "pattern_inference_used": false,
  "effective_at": "2026-01-01T00:00:00+00:00",
  "status_mappings": {"exact-token": {"to": "partial", "reason_code": "bounded_reason"}},
  "event_mappings": {"__MISSING__": {"to": "__INFER__", "reason_code": "legacy_shape"}},
  "type_mappings": {"exact-token": {"to": "task", "reason_code": "bounded_reason"}},
  "reason_codes": {"bounded_reason": "Concise caller-owned rationale."},
  "row_resolutions": []
}
```

The current deterministic helper emits plan, resolution-manifest, and receipt schema version 2. Those transaction schemas are separate from the caller-owned mapping schema version 1.

List every exact legacy token that is consumed. Do not use prefix, substring, suffix, wildcard, or regex logic to *decide* a token's meaning, including in a generator that later emits exact JSON keys. Inventory generation may be mechanical, but each semantic target and rationale must be token-local exact review. Inspect any mapping-builder source before accepting its manifest. Require `mapping_method: exact_token_review` and `pattern_inference_used: false`; the helper rejects other declarations. `__MISSING__` is the generic missing-token sentinel; `__INFER__` permits only the helper's unambiguous structural inference for an absent event discriminator.

Classify every physical prefix row exactly once as `accepted_current`, `normalized_legacy`, `mapped_legacy`, `quarantined_historical`, or `blocked_unknown_or_future`. Bind an exceptional row resolution to both physical line number and raw-line SHA-256. A future, malformed, or otherwise unmappable row blocks by default. Quarantine requires exact disposition metadata: reason, deterministic identity when available, projection impact, and resolution. `affected` or `unknown` impact also requires an enumerated current-projection correction; quarantine alone cannot resolve it. Give every correction suffix event a deterministic `fields.migration_correction_event_id`. Bind each non-independent quarantined row to the exact correction event ID list and canonical event SHA-256 list, and reject a plan or sealed graph when any referenced ID/hash is absent, duplicated, or changed.

When normalization changes an event, status, or type token, preserve the exact original token and its token-local mapping reason under the bounded `fields.legacy_original_event`, `fields.legacy_original_status`, or `fields.legacy_original_type` object. Each object contains only `token` and `reason_code`; use `__MISSING__` for an absent source token. Do not copy the raw source row into these fields.

The resolution manifest stores line, hash, enum, reason, identity, impact, and normalized-event digest only. It never stores raw row bodies. The immutable source-prefix snapshot is the sole byte-preserving copy.

## Plan, seal, and receipt graph

The hash graph is acyclic:

1. The deterministic plan contract binds prefix, mapping, all row dispositions, caller anchors, corrections, and projection.
2. The correction suffix binds the plan contract and is followed by one migration seal.
3. The completion receipt binds the immutable prefix snapshot, mapping snapshot, resolution manifest, plan snapshot, correction segment, exact boundary offsets and hashes, seal, projection counts, rendered-index snapshot, immutable prepare journal, exact final committed-journal SHA, and immutable completion-marker SHA.
4. A receipt-anchor event binds the already-written receipt SHA, earlier seal SHA, final journal SHA, and completion-marker SHA. It reuses the seal artifact ID and visible lifecycle fields, so it is an administrative projection no-op.
5. The immutable completion marker binds the prepare journal, receipt ref, plan, seal, commit boundary, rendered snapshot, recovery status, and exact final journal representation. The marker omits the receipt SHA to avoid a hash cycle; the anchor co-binds the receipt SHA and marker SHA in the ledger.

The receipt's commit boundary ends at the seal. Later current-schema `add|link|scan` events may extend the ledger without invalidating that historical boundary. The original prefix remains at offset zero and retains its exact SHA and byte length.

Current reconciliation appends only current-schema events. It supersedes stale active tasks and packs, restores one caller-designated active `task.md` and one caller-designated active pack, records their exact content hashes, retracts broken or stale current-task links through `fields.link_tombstones`, and adds an explicit non-promotion `pack_for_task` relationship. Link tombstones remove only exact `(rel,id)` pairs and never rewrite history.

Record before/after active-task, active-pack, duplicate-root-alias, and current-active-task broken-link counts in the plan and receipt. Count pre-migration broken links across every then-active task ID; superseding a stale active task removes its links from the current surface without deleting its historical events.

## Publication and recovery

Describe publication as locked, journaled, and crash-recoverable, not filesystem-atomic. Use a regular non-symlink `.task/index.lock` opened with no-follow semantics. While holding it:

1. Recheck safe in-root regular non-symlink task/pack paths, exact content SHA-256 values, and the pack's embedded `pack_id` while holding `.task/index.lock`, immediately before the first migration mutation. `apply --dry-run` performs the same anchor check without mutation.
2. Publish and fsync immutable prefix, plan, mapping, resolution, correction, and prepare-journal sidecars.
3. Write the mutable prepare journal.
4. Append and fsync the correction suffix and seal.
5. Write and fsync the completion receipt.
6. Append and fsync its receipt-anchor event.
7. Atomically publish `index.md` and its immutable rendered snapshot.
8. Publish the exact final journal and immutable completion marker, then fsync the directory.

Initial `apply` accepts only the exact planned prefix. If a crash leaves only prepared sidecars, resume through explicit `recover`. If an unsealed partial suffix exists, truncate only when an existing immutable prepare journal and mutable `partial_suffix` journal bind the exact appended byte length and SHA, and those bytes are a strict byte-prefix of that plan's precomputed correction-plus-seal tail. Any other tail conflicts without truncation. Never truncate prefix bytes. If the seal exists, forward-complete receipt, anchor, render, final journal, and completion marker; do not roll back. If render is pending, forward-render. A present completion marker is immutable: marker or final-journal mismatch is tamper, not a recoverable pending state. Prefix drift blocks automatic recovery. Reapplying the same committed plan is an idempotent no-op; another plan or source state conflicts.

## Strict-reader compatibility

The strict reader first looks for a current-schema receipt-anchor marker. If none exists, retain the ordinary fail-closed behavior. If a marker exists, validate receipt SHA, seal SHA and offsets, commit-boundary SHA, immutable prefix snapshot, plan, mapping, resolution manifest, correction segment, rendered snapshot, prepare journal, exact final journal, and immutable completion marker. Require the manifest to enumerate every physical prefix line and exact raw-line SHA once, and verify every non-independent quarantine-to-correction ID/SHA binding against the correction segment. Only then may the second pass normalize accepted/mapped legacy rows and omit exact quarantined rows. Parse every post-prefix row with the current schema.

Any sidecar, receipt, seal, anchor, prefix, or suffix tamper fails all strict mutation paths. Audit must report the sealed projection as evaluated only after the same verification; in-memory audit quarantine without a valid receipt graph is not a durable migration.

Post-seal suffix validation accepts the normal full current upsert/link schema plus exactly the writer's two sparse lifecycle upserts: an existing ID with only `status`, or an existing ID with only `fields`, in addition to the common version/event/id/timestamp fields. Reject a sparse upsert for an unknown ID and reject any explicitly supplied unsupported type. This compatibility applies only after the sealed prefix has already passed its complete receipt graph; it never relaxes legacy-prefix classification.

`scan` publishes each discovered artifact through its own locked append transaction. A later per-item failure can therefore leave an earlier, fully valid current-schema suffix event committed; that is a legitimate partial scan, not a journal tail eligible for truncation. Retry re-reads the sealed projection, skips already identical items, and continues remaining items. Never truncate a valid post-seal scan suffix to simulate whole-scan atomicity.
