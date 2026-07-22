# Compiler-First Efficiency Contract

Use this contract when a cycle would otherwise ask the coordinator model to assemble
publication plans, result envelopes, packets, hashes, projections, or receipts.

## Contents

- [Ownership boundary](#ownership-boundary)
- [Persistent evidence and model work orders](#persistent-evidence-and-model-work-orders)
- [Stage executors and field origins](#stage-executors-and-field-origins)
- [Body-free selection publication](#body-free-selection-publication)
- [Compatibility and recovery](#compatibility-and-recovery)
- [Rollout gates](#rollout-gates)
- [Efficiency evidence](#efficiency-evidence)

## Ownership boundary

- Let the model or a routed owner produce only bounded semantic judgments.
- Let deterministic compilers derive IDs, paths, ordering, hashes, CAS expectations,
  static bindings, journal rows, projections, and receipts.
- Reopen every owner or semantic artifact by an exact workspace-relative `ref` and raw
  SHA-256. Do not copy its body into a coordinator-authored wrapper.
- Reject unknown fields and unknown source kinds. Never treat a hash-shaped string,
  caller assertion, or familiar schema ID as evidence.
- Set `model_call_required: false` whenever the registered semantic field set is empty.

## Persistent evidence and model work orders

Persist complete evidence once and expose a separate bounded work order to the model.
The work order contains only the current target, executor kind, task/goal/advice
bindings or relevant slices, allowed semantic fields, owner-result contract, and state
fingerprint.

- Bind static policy and result contracts by `ref`, raw SHA-256, and policy/schema ID.
- Collect context through target-declared selectors. Do not read Git, task inventory,
  diagnostics, session audit, validation, schema, or issue state for unrelated targets.
- Keep a work order at or below 128 KiB and a v2 preparation at or below 256 KiB.
- Persist context, work orders, and canonical results by content digest; reference them
  from preparations, ledger events, and current projections.
- Recollect selected dependencies before submission and reject stale bindings.

## Stage executors and field origins

Register every canonical target with one executor kind:

- `system`: orchestration-owned canonical transitions such as context and contract checks.
- `deterministic`: an existing renderer or static analyzer produces the complete result.
- `owner`: a routed skill produces an exact result artifact which the compiler imports.
- `hybrid`: an owner artifact supplies protected facts and a bounded semantic overlay
  supplies only explicitly registered judgment fields.

A native deterministic renderer may retain its own envelope. Register a target-specific
adapter that validates the exact envelope fields, scope, and internal content digest
before removing it. If a zero-result scan has no domain evidence path, the adapter may
use the exact bound renderer artifact ref as evidence; it must never invent evidence or
silently discard an unknown envelope field.

Classify every required and optional result field exactly once as `derived`, `owner`,
`semantic`, or explicitly permitted `reasoned_not_applicable`. Do not use a name-based
semantic fallback. Reject semantic overlays that set derived or owner fields.

## Body-free selection publication

Use a compact selection intent that binds the authoritative selection decision,
prospective task source when applicable, and already-committed owner receipts. The
compiler must derive the publication ID, predecessor, target order, before/after hashes,
and transaction identity.

- Store exact task bytes once in the selection blob CAS.
- Keep Base64, task bodies, index bodies, and caller-authored target arrays out of v2
  prepares and command output.
- Reuse the task-state owner's transition plan and apply receipt; do not duplicate index
  payloads inside selection publication.
- Publish the task alias last. A prepare or partial owner projection is not selection
  authority.
- Update the compact head/pending state under the same publication lock. Normal status
  validates compact state and small receipt projections without decoding historical
  prepares or blobs; reserve deep audit for full plan/blob revalidation and migration.

## Compatibility and recovery

- New validated cycles and selection writes use v2. Readers and recovery continue to
  accept v1 artifacts.
- Do not rewrite, delete, or garbage-collect historical v1 prepares, receipts, packets,
  ledger rows, or current projections during this rollout.
- A missing compact state may bootstrap only after a full legacy audit. A malformed or
  digest-invalid state fails closed rather than silently falling back.
- Preserve exact replay. A crash after blob, prepare, target, receipt, or state writes
  must be recoverable without a second logical publication or ledger event.

## Rollout gates

1. **Contract gate:** require closed target registries, complete field-origin coverage,
   unknown-field rejection, exact-binding tamper tests, and dry-run write assertions.
2. **Parity gate:** compare v1 and v2 canonical results on reusable fixtures before v2
   becomes the default for new cycles. Never change the protocol of an initialized
   cycle; an explicit protocol-v1 initialization remains the bounded rollback path.
3. **Operational gate:** monitor structural byte/file-read metrics and optional actual
   provider token observations. A wall-clock sample or estimated price is not a gate.
4. **Retention gate:** retain v1 journals and packets indefinitely during this rollout.
   Any later rewrite, deletion, or garbage collection requires a separate authorized
   migration with backup, retention, referential-integrity, and rollback evidence.

## Efficiency evidence

Record provider-neutral observations without prompt or source bodies:

- context sections, files observed, bytes read, collection time;
- work-order, preparation, semantic, mechanical, inline-payload, and written bytes;
- executor kind, semantic/owner field counts, model-call requirement, and dedup bytes;
- actual input, cached-input, and output tokens only when supplied by a runtime receipt.

Do not estimate token counts, prices, or monetary savings inside the compiler. Gate the
rollout on structural byte/file-read assertions, v1/v2 result parity, tamper tests, and
crash-recovery tests rather than brittle wall-clock thresholds.
