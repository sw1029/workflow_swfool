# Compiler-First Efficiency Contract

Use this contract when a cycle would otherwise ask the coordinator model to assemble
publication plans, result envelopes, packets, hashes, projections, or receipts.

## Contents

- [Ownership boundary](#ownership-boundary)
- [Persistent evidence and model work orders](#persistent-evidence-and-model-work-orders)
- [Stage executors and field origins](#stage-executors-and-field-origins)
- [Routing, semantic input, and usage](#routing-semantic-input-and-usage)
- [Compact result ledger](#compact-result-ledger)
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
- New cycles use compiler protocol v2 with preparation schema v3. Preserve the exact
  initialized markers for existing cycles; never upgrade a legacy cycle by inference.

## Persistent evidence and model work orders

Persist complete evidence once and expose a separate bounded work order to the model.
For owner and hybrid targets, the work order contains only the current target, exact
executor specification, task/goal/advice bindings or relevant slices, allowed semantic
fields, owner-result contract, routing requirement, and state fingerprint. A v3
deterministic preparation contains neither context nor work order: it binds one
machine-input artifact selected for the registered renderer and exposes zero
model-visible bytes.

- Bind static policy and result contracts by `ref`, raw SHA-256, and policy/schema ID.
- Collect context through target-declared selectors. Goal and selection-publication
  state are separate selectors. Do not read Git, task inventory, diagnostics, session
  audit, validation, schema, issue, goal, or selection state for unrelated targets.
- Keep a work order at or below 128 KiB and a v2 preparation at or below 256 KiB.
- Persist context, work orders, and canonical results by content digest; reference them
  from preparations, ledger events, and current projections.
- Recollect selected dependencies before submission and reject stale bindings. Keep
  task.md, cycle projection, authority projection, pending-run state, Git HEAD, and Git
  worktree identity as separate precondition selectors; an allowed owner effect on one
  may not mask concurrent movement in another. The Git worktree selector canonically
  binds each changed path's porcelain status, index identity, no-follow file type/mode,
  size, and regular-file byte digest or symlink-target digest. Missing paths have an explicit
  deletion identity. The model receives only a bounded, path-order-aligned row prefix;
  the full canonical inventory digest remains content-sensitive even when that prefix is
  truncated. Unsafe paths, unsupported file types, command/race failure, or scan/content
  limits make the selector incomplete and block execution. The exact scan is capped at
  50,000 paths, 8 MiB per Git command output, 1 MiB of literal pathspec arguments, and
  256 MiB of hashed worktree content. For governance and
  visible-increment effects, require every changed entry—not merely path-set membership—
  to map exactly to the owner's `changed_files` claim; fail closed when truncation makes
  exact path attribution unavailable.

Treat every preparation schema as closed. Validate its exact schema-dependent top-level
field set and require every compiler-artifact binding to contain exactly `artifact_type`,
`ref`, `sha256`, and `size_bytes` before opening that artifact. For preparation-v3, the
embedded executor specification must equal the registered projection for the target;
recomputing `preparation_id` cannot authorize an added field or substituted command.
Keep the established closed field sets for readable v1 and v2 artifacts.

## Stage executors and field origins

The closed target registry uses exactly three executor kinds:

- `deterministic`: an existing renderer or static analyzer produces the complete result.
- `owner`: a routed skill produces an exact result artifact which the compiler imports.
- `hybrid`: an owner artifact supplies protected facts and a bounded semantic overlay
  supplies only explicitly registered judgment fields.

Orchestration-owned `context`, route, contract, and ledger transitions are bounded
system mechanics outside this 27-target result-executor registry. They do not create a
fourth registry partition.

The closed registry has exactly 27 entries: seven deterministic, sixteen owner, and
four hybrid. Every row binds one target, executor kind, command ID, owner ID, routing
policy ID plus a closed allowed-profile set or explicit absence, input selector, output
adapter, optional semantic schema, and side-effect class. Registry coverage must exactly
match result-contract and routing-policy targets. Deterministic rows have no model
routing. Unknown or missing entries fail at load time; callers cannot supply a command
ID, owner, adapter, selector, routing policy, or profile.

`stage advance --apply` may invoke only the seven registered deterministic renderers:
repo-adapter scan, repo-adapter static validation, code-structure audit, repo-skill gap,
cycle-efficiency analysis, dashboard rendering, and report assembly. The dispatcher
loads the exact machine-input binding, validates the native envelope through the target
adapter, writes an exact owner-result CAS artifact, and submits through the ordinary
result and transition gates. It does not accept raw argv. Dry-run performs no write.

A native deterministic renderer may retain its own envelope. Register a target-specific
adapter that validates the exact envelope fields, scope, and internal content digest
before removing it. If a zero-result scan has no domain evidence path, the adapter may
use the exact bound renderer artifact ref as evidence; it must never invent evidence or
silently discard an unknown envelope field.

For adapter architecture, keep deterministic facts, bounded semantic assessment, and
final adjudication separate. The semantic receipt may distill responsibilities,
recursive module boundaries, design-pattern tradeoffs, and compatibility risks only by
citing deterministic fact IDs. It cannot set consumability, audit status, severity, or
raw-source fields. The deterministic adjudicator owns those final fields, and native
`repo_skill_adapter_validate` / `code_structure_audit` envelopes preserve their field
origins and integrity through stage normalization.

Classify every required and optional result field exactly once as `derived`, `owner`,
`semantic`, or explicitly permitted `reasoned_not_applicable`. Do not use a name-based
semantic fallback. Reject semantic overlays that set derived or owner fields.

## Routing, semantic input, and usage

- A registry target with `routing_required: true` must submit one exact routing-receipt
  ref/raw-SHA pair. A target without routing must not submit one.
- The receipt uses a closed schema and binds cycle ID, target, preparation ID, state
  fingerprint, policy/profile/tier, requested model reference/model/effort, and reason
  codes. Its policy ID and profile must match the executor row's exact policy and closed
  target profile set. Missing, extra, stale, malformed, or scope-mismatched receipts
  fail before result construction, effects, or publication.
- Owner and semantic inputs are canonical cycle-local CAS wrappers. Reopen and validate
  their exact kind, cycle, target, canonical bytes, and raw digest. Semantic artifacts
  have a hard 64 KiB limit; do not truncate and silently continue.
- Usage-v2 observations require exact provider ID, runtime ID, model ID, and request ID
  fields, but those caller-authored strings are descriptive provenance rather than a
  trusted runtime attestation. Classify current v2 observations as
  `caller_asserted_unverified` and aggregate-ineligible. Preserve usage-v1 separately as
  legacy/unverified evidence and expose a distinct unattested-v2 exclusion count. A
  caller-set eligibility flag, canonical encoding, or matching digest cannot upgrade
  either version. Reject prices, monetary estimates, and caller-added fields in both
  versions. A deterministic executor cannot accept a model-usage receipt.

## Compact result ledger

Write a validated compiled result once as canonical JSON in the cycle packet CAS. Append
only a format-v2 `compiled_stage_result_ref` ledger row containing bounded lifecycle and
result scalars plus the exact ref, raw digest, body digest, and byte size. Do not repeat
the result body in `stage.jsonl` or `current_stage.json`.

- Raw ledger reads return authoritative compact rows without opening result artifacts.
- Expanded/public reads reopen only the cycle-local packet CAS, reject path escape and
  symlinks, enforce the byte cap and canonical JSON, verify size plus raw/body digests,
  and then hydrate a legacy-equivalent result view.
- Projection and integrity validation use the raw ledger. Dashboard, context, profile,
  and downstream semantic consumers use the verified expanded reader.
- Missing, tampered, noncanonical, oversized, or mismatched result artifacts fail closed.
- Exact replay returns the existing hydrated event and never appends a second row.
- Derive CAS counters from the immutable writer's actual link outcome, not a pre-write
  existence check. Add context/work-order or machine-input, preparation, and result CAS
  receipts cumulatively. `files_written_count` counts actual newly linked files; a
  reused CAS object contributes bytes only to `cas_reused_bytes`.
- Keep per-attempt `cas_newly_written_bytes`, `cas_reused_bytes`, and
  `files_written_count` outside preparation identity and durable preparation content.
  This keeps the preparation digest stable while `prepare --publish` reports the full
  current attempt. For schema-v3 publication, write a canonical preparation-scoped
  origin intent under the cycle compiler directory before linking each context,
  work-order, machine-input, or preparation object. Serialize the intent/object pair
  with the cycle lock. Bind the exact target and its original `new`/`reused`
  classification in the intent; on retry, recover a missing originally-new target or
  reject a missing originally-reused target. Count the compact intent files in compiler
  I/O so the recovery protocol's overhead remains visible.
- Derive the first complete publication's counters from those verified intents and bind
  every intent through an immutable, preparation-digest-scoped schema-v2 origin receipt,
  including the receipt's own immutable write. Never reconstruct origin counters from a
  retry's current existence checks. Continue to read and validate established schema-v1
  receipts; use schema v2 for new receipt writes.
  Loading a durable preparation carries those origin counters forward and additionally
  classifies its preparation, bound compiler
  artifacts, and receipt as reused for the consuming attempt, so a later submit ledger
  row represents cycle-wide publication plus consumption I/O rather than losing the
  original new writes.
- If result CAS publication succeeds but ledger append fails, retry the exact result as
  reused bytes and append one event. If the event exists but current projection repair
  failed, return its stored metrics unchanged while repairing only the projection.

## Body-free selection publication

Use a compact selection intent that binds the authoritative selection decision, exact
prospective task source, and a schema-v2 prospective task-state plan. The compiler must
derive the publication ID, predecessor, target order, before/after hashes, and
transaction identity. Do not require an already-applied task-state receipt: that would
recreate a dependency cycle because the task-state owner intentionally binds prospective
bytes before `task.md` changes.

- Store exact task bytes once in the selection blob CAS.
- Keep Base64, task bodies, index bodies, and caller-authored target arrays out of v2
  prepares and command output.
- Reuse the task-state owner's prospective transition plan and pending receipt; do not
  duplicate index payloads inside selection publication.
- Apply the task-state event batch/render first as `pending_external_settlement` while
  `task.md` remains at its before digest. Publish the task alias last by CAS, then settle
  task-state from the exact committed schema-v3 publication receipt.
- Keep selection consumption false while settlement is missing or invalid. A prepare,
  pending owner projection, or committed alias without its exact external settlement is
  not a consumable selection lifecycle.
- Keep storage-v4 state bounded to one head and one active transaction. Resolve schema-v2
  intent replay through immutable intent-hash prepare/commit indexes; normal status and
  replay must not enumerate history or reopen historical sources. Reserve deep audit and
  explicit migration for full legacy validation.
- Render a selected-successor preparation bundle from only decision/task bindings. It
  must contain exact owner plan/prepare/result bindings, operation identities, subjects,
  idempotency keys, execution order, and recovery checkpoints without event or task
  bodies.
- Render selected-successor authority through `prepare-authority` from the exact bundle,
  one closed semantic request context, one schema-v2 session evaluation context, and
  exactly three closed present/absent grant choices. Derive the three requests,
  deterministic bundle idempotency keys, decision/reservation/pre-commit chains, and
  compact packet mechanically. Do not spend model context on request JSON, repeated
  proof argv, packet JSON, digests, IDs, or manifest-owned fields.
- Bind one semantic actor rank in the exact self-sealed request context and require every
  present grant holder rank to equal it. Never infer identity from a manifest source-rank
  floor or from grant absence.
- Keep semantic and authority ownership intact while rendering. The contexts may narrow
  but never invent a ceiling, goal envelope, capability, subject, operation, evidence,
  source approval or grant. The canonical evaluator is the sole producer of `allowed`.
  A genuine no-covering or other non-allowed evaluation emits one compact approval
  projection with exact non-authoritative compilation bindings and stops before any
  decision, reservation, or pre-commit proof. An absent declaration that evaluates
  allowed is an input conflict, not an approval wait.
- Use only the guarded `selected-successor execute|recover` path for effects. Prefer the
  compact authority packet binding; retain the explicit three-proof argv only for legacy
  compatibility. Both modes validate all three reservation/pre-commit/version proofs,
  then persist the immutable all-three authority gate before step 1. Individual owner
  commands are prepare/debug or explicitly governed historical-recovery surfaces; do
  not invoke them directly for the selected-successor route because they do not
  themselves establish this gate.
- Bind exact decision/task/timestamp prepare inputs to the canonical successor bundle
  through one immutable content-addressed index. Recheck source bytes and the closed
  bundle on replay before consulting current task state, so pending or completed
  execution cannot make the original prepare non-idempotent. Without that index, new
  owner preparation retains full source validation; only an exact existing owner
  prepare index may enter historical recovery, so absence cannot itself authorize a
  self-sealed substitute.
- Delegate settled event-batch/descendant/projection proof to the task-index owner. Do
  not copy owner validation or require the current whole ledger hash to equal a historical
  plan-after hash.

## Compatibility and recovery

- New validated cycles and selection writes use body-free intents. Readers and explicit
  recovery continue to accept v1 artifacts, but every public v1 new-write surface fails
  closed.
- Do not rewrite, delete, or garbage-collect historical v1 prepares, receipts, packets,
  ledger rows, or current projections during this rollout.
- A missing compact state may bootstrap only after a full legacy audit. A malformed or
  digest-invalid state fails closed rather than silently falling back.
- Preserve exact replay. A crash after blob, prepare, target, receipt, or state writes
  must be recoverable without a second logical publication or ledger event.

## Rollout gates

1. **Contract gate:** require closed executor and field-origin registries, complete
   target/renderer/routing coverage, unknown-field rejection, exact-binding tamper
   tests, semantic-size tests, and dry-run write assertions.
2. **Parity gate:** compare v1/v2/v3 canonical results on reusable fixtures before v3
   becomes the default preparation. Never change the protocol or preparation marker of
   an initialized cycle; explicit protocol-v1/preparation-v1 initialization remains the
   bounded rollback path.
3. **Operational gate:** monitor structural byte/file-read metrics and optional actual
   provider token observations. A wall-clock sample or estimated price is not a gate.
4. **Retention gate:** retain v1 journals and packets indefinitely during this rollout.
   Any later rewrite, deletion, or garbage collection requires a separate authorized
   migration with backup, retention, referential-integrity, and rollback evidence.

## Efficiency evidence

Record provider-neutral observations without prompt or source bodies:

- selected context sections, files opened, bytes read, and collection time;
- context, work-order, machine-input, preparation, owner, semantic, result-artifact,
  compact-ledger, mechanical, inline-payload, and written bytes;
- cumulative actual CAS new/reused bytes plus actual newly linked file count; a later
  publication layer must add its receipt rather than overwrite earlier compiler I/O;
- executor kind, semantic/owner field counts, model-visible bytes, model-call count,
  field-origin-derived mechanical bytes, and dedup bytes;
- input, cached-input, and output token claims as non-aggregate observations until a
  separately defined trusted runtime issuer and verifiable attestation are implemented;
  report legacy usage-v1 and unattested usage-v2 in separate exclusion counts.

The deterministic `cycle_efficiency_profile` aggregates these rows into
`compiler_efficiency.structural_totals`. Under the current unattested usage schemas it
does not aggregate any token claim: verified totals remain zero, usage-v1 increments the
legacy exclusion count, and well-formed usage-v2 increments the unattested-v2 exclusion
count. A hand-forged `usage_aggregate_eligible: true`, including one paired with an
otherwise valid canonical v2 file, is invalid-v2 evidence and is never reopened into
trust. Without a separately defined issuer-bound attestation and comparable runtime
receipt, emit `runtime_comparison.status: not_evaluated` and no savings,
token-reduction, price, or cost-reduction field or claim.

`compact_payload_bytes` is the canonical pre-append compact event envelope size with
that metric itself omitted. This non-self-referential definition is persisted in the
format-v2 row and aggregated; `ledger_event_bytes` may remain a transient diagnostic for
the larger storage-completed row and is not substituted for the persisted measure.

Do not estimate token counts, prices, or monetary savings inside the compiler. Gate the
rollout on structural byte/file-read assertions, v1/v2 result parity, tamper tests, and
crash-recovery tests rather than brittle wall-clock thresholds.
