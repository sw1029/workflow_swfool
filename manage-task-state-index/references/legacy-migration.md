# Task-State Legacy Migration Contract

## Contents

- [Authority and scope](#authority-and-scope)
- [CLI](#cli)
- [Mapping and row disposition](#mapping-and-row-disposition)
- [Plan, seal, and receipt graph](#plan-seal-and-receipt-graph)
- [Publication and recovery](#publication-and-recovery)
- [Strict-reader compatibility](#strict-reader-compatibility)
- [Independent verifier](#independent-verifier)

## Authority and scope

Use `python3 -m manage_task_state_index migrate` only for an explicitly authorized legacy-ledger migration. Keep normal `init|scan|add|link|rebuild|audit` behavior strict. A plan is not authority to mutate: bind apply to the exact plan file SHA, source prefix SHA, mapping SHA, root identity, and caller-designated task and pack identities.

Preserve the complete source `.task/index.jsonl` as a byte-identical prefix and immutable snapshot. Never normalize, delete, reorder, or edit a historical prefix line. Keep repository-specific event, status, and type tokens in the caller-owned mapping manifest; do not add them to the helper.

## CLI

```bash
TASK_STATE_SCRIPTS="${CODEX_HOME:-$HOME/.codex}/skills/manage-task-state-index/scripts"

PYTHONPATH="$TASK_STATE_SCRIPTS" python3 -m manage_task_state_index migrate --root ROOT inspect

PYTHONPATH="$TASK_STATE_SCRIPTS" python3 -m manage_task_state_index migrate --root ROOT migrate plan \
  --expected-index-sha256 SHA \
  --current-task-id ID --current-task-path task.md --current-task-sha256 SHA \
  --current-pack-id ID --current-pack-path PATH --current-pack-sha256 SHA \
  --mapping-manifest MAP.json --output-plan /tmp/PLAN.json

PYTHONPATH="$TASK_STATE_SCRIPTS" python3 -m manage_task_state_index migrate --root ROOT migrate apply \
  --plan /tmp/PLAN.json --expected-plan-sha256 SHA \
  --expected-index-sha256 SHA [--dry-run]

PYTHONPATH="$TASK_STATE_SCRIPTS" python3 -m manage_task_state_index migrate --root ROOT migrate validate \
  --receipt RECEIPT.json --require-current-projection-evaluated \
  --require-single-active-task --require-single-active-pack --require-appendable

PYTHONPATH="$TASK_STATE_SCRIPTS" python3 -m manage_task_state_index migrate --root ROOT migrate recover \
  --transaction-id tsm-...

PYTHONPATH="$TASK_STATE_SCRIPTS" python3 -m manage_task_state_index verify-migration \
  --root ROOT \
  --receipt .task/migrations/tsm-.../receipt.json \
  --expected-mapping-manifest /caller-owned/exact-mapping.json \
  --expected-recovery-status not_required

PYTHONPATH="$TASK_STATE_SCRIPTS" python3 -m manage_task_state_index verify-migration \
  --root COPIED_FIXTURE_ROOT \
  --receipt .task/migrations/tsm-.../receipt.json \
  --expected-mapping-manifest /caller-owned/exact-mapping.json \
  --expected-recovery-status forward_completed \
  --recovery-observation /caller-owned/pre-recovery-observation.json \
  --expected-recovery-observation-sha256 SHA
```

`inspect`, `plan`, and `apply --dry-run` do not mutate canonical `.task` state. Keep the plan outside `.task` until a successful apply snapshots it into the transaction directory.

The independent verifier command is read-only. `not_required` rejects recovery-observation arguments. `forward_completed` requires both the pre-recovery observation and its externally preserved SHA-256; the observation must have been captured before recovery in a synthetic or copied fixture, never from the live transaction.

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

## Independent verifier

Use `task_state_migration_sealed_reader_recovery_boundary_independent_verifier` to establish verification evidence that is separate from producer status, `migrate validate`, and the normal strict-reader success path. The verifier implementation may reproduce the public on-disk contract, but it must not import the migration producer package, call its validation or recovery functions, or accept its self-declared `strict_reader_status`, `append_simulation_status`, receipt status, or recovery status as completion truth.

### Inputs and Python surface

`--root` names the live workspace or a relocated copied-fixture root. `--receipt` names a regular, non-symlink receipt inside that root's exact `.task/migrations/<transaction-id>/` directory. `--expected-mapping-manifest` is a caller-selected trust input and must satisfy all of these conditions:

- it is a regular non-symlink file outside every `.task/migrations` tree;
- it is a distinct file and inode, not the published mapping snapshot and not a hard link to it;
- its bytes are identical to the published transaction snapshot;
- its SHA-256 is independently recomputed and bound into the verification graph and result;
- it retains `mapping_method: exact_token_review`, `pattern_inference_used: false`, exact token-local mappings and reasons, and exact line-plus-raw-line-hash row resolutions.

The published mapping snapshot by itself is producer-owned evidence and cannot satisfy the external-input requirement. A copied file inside another migration transaction is also not caller-owned. The verifier mechanically inventories observed tokens but does not use prefix, suffix, substring, wildcard, or regex inference to assign their meaning.

`--expected-recovery-status` is caller-owned and accepts only `not_required` or `forward_completed`; it is never inferred from the receipt. The optional `--recovery-observation` and `--expected-recovery-observation-sha256` are an inseparable pair and are accepted only for `forward_completed`.

The Python surface exposes:

```python
verify_migration(
    root_raw,
    receipt_raw,
    *,
    expected_mapping_raw,
    expected_recovery_status,
    recovery_observation=None,
    expected_recovery_observation_sha256=None,
)

inspect_transaction_boundary(
    root_raw,
    transaction_id,
    *,
    expected_mapping_raw=None,
    expected_recovery_status=None,
    recovery_observation=None,
    expected_recovery_observation_sha256=None,
)
```

`inspect_transaction_boundary` observes publication and recovery eligibility without invoking producer recovery. Preserve its canonical observation SHA outside the transaction before a fixture recovery. Every declared observation field participates in that digest and in the final verification graph: schema/kind/status, transaction and plan identity, journal state and SHA, index SHA and byte length, prefix/boundary/anchor/receipt/marker presence, publication and replay classification, the exact owned-set identity and count, the outside-set and protected-anchor aggregates, and the read-only assertion. Validate each field's exact type, closed vocabulary, and phase consistency; a caller cannot make an ineligible state recoverable merely by rehashing a self-consistent object. `verify_migration` verifies only the resulting graph. Neither function applies, recovers, replays, truncates, appends, renders, locks for writing, or rewrites any file.

On success, the CLI emits one JSON object with `status=pass`, `evaluation_status=pass`, the required verifier name, `source_separated=true`, `read_only=true`, transaction and recovery identity, external mapping SHA, separately named immutable-boundary task/pack identity tokens and evidence refs, separately named current task/pack identity tokens and evidence refs, bounded counts, and a full verification-graph SHA. Raw dynamic task and pack IDs remain inside the independently checked graph; JSON projects them only as deterministic `task-sha256-*` or `pack-sha256-*` opaque tokens so arbitrary identifier text cannot become output. For `forward_completed`, that graph also binds the caller-preserved recovery-observation SHA and the verified transition evidence; `not_required` cannot silently substitute a recovery claim. Failure is non-zero and emits only `status=fail` plus an allowlisted stable `error_code`; exception text, argument bodies, paths, and tokens are never copied into failure JSON. Neither success nor failure emits prefix rows, raw source bodies, prompts, transcripts, corpus locators, credentials, or secrets. The entry point disables local bytecode publication before importing verifier modules so a default read-only invocation does not create `__pycache__` files.

Any zero operation counts in verifier JSON are scoped to migration-writer calls made by that verifier process; they are not an audit of other commands in the surrounding cycle. Issue lifecycle state is likewise outside the relocated verifier graph and must be established from an independent live-repository issue-path check. Do not encode an unconditional `issue_remains_open=true` as though it were observed by a relocated fixture.

### Independently recomputed graph

The verifier recomputes, rather than copies, all of these relationships:

1. The live ledger begins with the exact immutable prefix snapshot, with equal bytes, length, SHA-256, physical row count, row order, and per-row identity. Every row is independently parsed, mapped or quarantined exactly once, and matched to the resolution manifest without trusting the plan's row array or counts.
2. The external mapping bytes equal the transaction snapshot; the snapshot SHA is bound by the plan, receipt, seal, and independently reproduced migration identity. Each mapping entry has exact keys and types, each referenced reason exists, and booleans are not accepted as integer counts, offsets, lengths, lines, or versions.
3. The deterministic plan contract is rebuilt from its exact canonical core. The independent classification, normalized-event digests, correction events, correction IDs and SHAs, projection, task/pack anchors, and migration ID must reproduce the plan rather than merely agree with producer summary fields.
4. The correction segment begins at the prefix length and has the exact planned bytes, event count, length, and SHA. The seal immediately follows it and binds prefix, mapping, resolution manifest, plan contract, and correction identities. Prefix plus correction plus seal is the immutable commit boundary.
5. The receipt binds the prefix, mapping, resolution manifest, raw plan, plan contract, correction, seal, exact offsets, boundary, historical projection, rendered snapshot, immutable prepare journal, exact final journal, and immutable completion marker. The receipt-anchor event follows the sealed boundary and co-binds receipt, seal, boundary, final journal, and completion marker. The completion marker intentionally binds the receipt by ref rather than receipt SHA to keep the graph acyclic; the anchor supplies the receipt-SHA edge.
6. The rendered snapshot is independently reproducible from the migration-boundary projection. The live `.task/index.md` may legitimately reflect later events and is not required to equal the historical rendered snapshot.

Unknown document fields, missing fields, malformed nested types, unsafe refs, symlink components, path escapes, digest mismatches, duplicate row identities, changed order, missing correction bindings, conflicting subjects, or coherently rehashed producer-only claims fail closed. Supported producer tool and schema versions are exact contract inputs, not permissive minimums.

### Historical boundary and legitimate current tail

The immutable boundary ends at the seal. Its task and pack identities are reconstructed from normalized prefix events plus correction events and are reported under migration-boundary fields. Do not compare the historical task digest to the current mutable `task.md`, or the historical pack digest to a later mutated pack body.

The receipt anchor and every later event form a separate current-schema tail. Parse that tail sequentially and recompute the current projection. Full upserts and links are allowed; sparse status-only or fields-only upserts are allowed only for an ID already known at that point. A legitimate per-item `scan` prefix, task replacement, pack mutation, link, or lifecycle update changes current identity without changing the historical commit-boundary SHA. Current task and pack refs must resolve safely inside the relocated root, their latest indexed content hashes must match the current files when supplied, and a current pack file must embed its indexed pack ID.

Report at least two distinct identity surfaces: stable migration-boundary task/pack IDs and evidence refs, and volatile current task/pack IDs and evidence refs. Never hash the entire current ledger as though it were the historical receipt boundary, and never classify a valid post-seal `scan` event as an owned recovery tail.

### Recovery observation and write-set boundary

Recovery validation is fixture-only and observational. Capture an independent pre-recovery observation and its SHA, run producer recovery separately against the synthetic or copied fixture, then verify the final graph and a caller-owned expected recovery action. The verifier itself remains read-only throughout. The observation must prove one exact eligible phase: `prepared` has the exact prefix and no unowned tail; `partial_suffix` binds the exact appended length and SHA to a strict prefix of the precomputed correction-plus-seal tail; `sealed` has the exact commit boundary before receipt publication; `receipt_written` binds the provisional receipt that the producer may replace only with the independently reconstructed `forward_completed` receipt; `receipt_anchored` makes the receipt and anchor immutable while permitting only the exact final journal, marker, and projection publications; committed journal plus marker with a missing or stale projection is `committed_render_pending`, not replay-noop; only a fully committed and rendered state is an exact no-op. The final graph keeps the caller recovery action distinct from the receipt's publication-time recovery status and binds both to the observation phase. Contradictory presence flags, malformed digests or lengths, a foreign tail, and an unknown or ineligible journal state fail closed.

The allowed recovery-owned logical write set is phase-specific and bounded to:

- `.task/index.lock` coordination metadata;
- absent transaction sidecars whose bytes exactly match the precomputed prefix, plan, mapping, resolution manifest, correction segment, and immutable prepare journal;
- the transaction's mutable `journal.json` until its exact committed representation is published;
- an append after the immutable prefix for the exact correction-plus-seal tail, or truncation back to the prefix only when an immutable prepare journal and a `partial_suffix` journal bind the exact tail length and SHA and that tail is a strict byte-prefix of the precomputed boundary tail;
- the exact receipt, one receipt-anchor append, rendered snapshot, final journal, immutable completion marker, and `.task/index.md` projection required by the observed forward-completion phase.

For each owned path, compare its observed existence, bytes or digest, and ledger byte range with the final state and accept only the transition authorized by that observed phase. A digest of path names is not enough. The outside-owned aggregate includes directory entries, including empty directories, as well as files, symlinks, and other node kinds; adding or removing an unrelated empty directory therefore changes the boundary. The live `.task/index.md` must either remain byte-identical or become the exact already-bound projection authorized by the phase; arbitrary final projection bytes are not an owned recovery result. Protected task and pack artifacts must remain byte-identical across recovery.

The immutable prefix, `task.md`, task-pack JSON, existing immutable sidecars, an anchored receipt, an existing completion marker, unrelated ledger tail, and every unrelated path are outside the recovery write set. A `receipt_written` observation is the sole exception for an existing receipt: recovery may replace it only with the exact independently reconstructed forward-completion receipt before publishing the anchor. A conflicting existing immutable file, foreign or unbound partial tail, prefix drift, mutation outside the allowlist, marker/final-journal mismatch, rollback after a seal, or truncation of a valid post-seal event fails closed. Bind the pre-recovery observation SHA and the exact verified transition into the final graph and result so different recovery evidence cannot produce the same completion identity. Once committed, exact replay is a no-op except that a missing or stale mutable Markdown projection is classified as forward-required and may be republished from the already bound rendered snapshot.

### Copied-actual relocation and claim boundary

A copied-actual fixture preserves transaction bytes but may have a different absolute root, device, inode, and current mutable identities. Validate the historical `plan.root_identity` shape and its plan-contract binding, but do not require equality with the relocated root. Likewise, `plan.mapping_manifest.source_ref` is only a stale historical provenance string: validate its bounded scalar shape, but do not trust it, use it as the caller expectation, require that it was outside the producer transaction, or dereference its possibly stale absolute path. The live trust input is instead the separate `--expected-mapping-manifest` file, which must remain outside every transaction tree and satisfy the source-separation rules above. Resolve only current workspace-relative transaction refs against the supplied root.

The verifier mechanically proves byte equality plus physical separation: it rejects the transaction snapshot itself, transaction-tree paths, symlinks, and same-file or hard-link aliases. It cannot infer human ownership from equal bytes, so an ordinary external copy is not by itself caller-provenance evidence. The governing cycle must separately record who selected the expectation, why it predates or is independent of publication, its SHA/size, and its separation from the transaction snapshot. Producer evidence alone cannot create that governance attestation, and the verifier must not claim otherwise.

Relocation success proves graph integrity and verifier portability only. It does not prove semantic progress, artifact-truth completion, readiness, gold quality, canonical or production promotion, or closure of any repository-local issue. Live migration apply, recover, and replay counts remain zero for verification cycles.
