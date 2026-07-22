# Authority Boundary Contract

Use this contract at the existing `authority` phase. `$manage-agent-authority` remains the sole owner of policy snapshots, grants, delegation, reservations, use receipts, revocation, and lifecycle state. The orchestrator validates and routes exact owner artifacts; it never grants, composes, widens, or retroactively invents authority.

## Contents

- [Closed phase packet](#closed-phase-packet)
- [Deterministic construction](#deterministic-construction)
- [Independent axes](#independent-axes)
- [Dispatch protocol](#dispatch-protocol)
- [Commit and settlement gates](#commit-and-settlement-gates)
- [Terminal-wait baseline publication](#terminal-wait-baseline-publication)
- [Selected-successor publication](#selected-successor-publication)
- [Decision routing](#decision-routing)
- [Terminal-wait replay](#terminal-wait-replay)
- [Legacy migration](#legacy-migration)

## Closed phase packet

Validate `schema_version: 2`, `artifact_kind: orchestrator_authority_packet`, and `step: authority` with:

```bash
python3 -P -m orchestrate_task_cycle result-contract \
  --target authority --mode block --result <authority-packet.json> \
  --context '{"workspace_root":"<workspace>"}'
```

The packet binds:

- the immutable `$manage-agent-authority` decision ref/hash, decision/request IDs and hashes, closed decision, and owner-computed effective fingerprint;
- exact skill/operation IDs and versions, operation-manifest ref/hash/status, and mutation class;
- exact subject kind/ref/digest/revision;
- cycle/task/pack/attempt IDs, `scope_kind`, decision class, intent type, required source rank, and risk tier;
- independent axis statuses and disjoint axis-owned evidence IDs;
- exact `selected_grants` plus deduplicated `lineage_grants`, each grant digest, state version, and immutable policy snapshot;
- a deterministic closed `approval_projection` only for `approval_required`; it exposes typed intent, exact effect/scope/budget, excluded effects, and a safe alternative without widening authority;
- an explicit composition receipt when more than one grant is selected;
- the authority reservation artifact, its mutable state CAS binding, and exact per-grant reserved-use transitions when mutating dispatch applies;
- an immutable `authority_verification` ref/hash and its exact reservation/grant-state projection before dispatch;
- a scoped orchestrator fingerprint and content hash.

Reject unknown fields. An unknown mutating operation, missing manifest, implicit union of grants, mutable-policy-only reference, stale subject, stale reservation state, missing use reservation, inactive grant, or verification mismatch blocks dispatch.

Packet hashes are not self-authenticating. The consuming result contract requires an explicit workspace root and reopens the owner decision, grant and policy snapshots, current grant states, reservation and reservation state, and pre-dispatch verification. Every ref must be an exact workspace-relative non-symlink regular file under `.task/authorization/`; raw bytes must match the bound SHA-256 and the reopened owner fields must match the packet projection. Path escape, symlink traversal, content drift, a forged packet echo, or unavailable artifact verification fails closed. A pure in-memory packet projection may support diagnostics and selection-key construction, but never dispatch or terminal authority consumption by itself.

The owner decision fingerprint and orchestrator fingerprint have different scopes. Preserve both. The owner fingerprint binds the authority evaluator's exact capability/operation/subject coverage. The orchestrator fingerprint additionally binds the selected grant and reservation/use state consumed by this dispatch. Neither fingerprint includes a mutable whole-policy document or unrelated grants.

## Deterministic construction

Construct the packet from owner bindings instead of copying fields by hand:

```bash
python3 -P -m orchestrate_task_cycle authority-packet --root . \
  --decision-binding '{"ref":".task/authorization/decisions/<id>.json","sha256":"<sha>"}' \
  --reservation-binding '{"ref":".task/authorization/reservations/<id>.json","sha256":"<sha>"}' \
  --verification-binding '{"ref":".task/authorization/verifications/<id>.json","sha256":"<sha>"}'
```

Omit reservation and verification only for observe or non-allowed decisions. The constructor derives operation, subject, scope, independent owner axes, selected and lineage grants, approval projection, and composition from the reopened decision; it derives mutable CAS bindings from the reopened reservation and verification; then it runs both closed-packet and artifact-bound validation before emitting JSON. A repository adapter may conservatively override `local_resolution` to evidence-backed `available` with repeated `--local-evidence-id`; it may not assert `unavailable`, alter an owner decision, or widen any other axis.

## Independent axes

Keep these axes typed and independent:

| Axis | Closed statuses | Meaning |
| --- | --- | --- |
| `authority` | `granted`, `approval_required`, `denied`, `unverified`, `not_applicable` | Whether an exact covering authority grant exists |
| `local_resolution` | `available`, `unavailable`, `unverified`, `not_applicable` | Whether existing local capability can resolve the item |
| `external_input` | `not_required`, `available`, `waiting_state`, `missing_supplyable`, `missing_unsupplyable`, `unavailable`, `unverified`, `not_applicable` | Availability of data or external state, not permission |
| `risk_cost` | `not_required`, `accepted`, `confirmation_required`, `declined`, `unverified`, `not_applicable` | Separate risk/cost consent |
| `goal_truth` | `aligned`, `blocked`, `unverified`, `not_applicable` | Exact GT/autonomy-envelope compatibility |

Do not reuse one evidence ID across axes. Do not infer external input from permission, permission from missing input, risk consent from a grant, goal ratification from risk acceptance, or local capability absence from external waiting. If local resolution is verified available, route an in-scope engineering task; do not escalate it as authority, capability, or external-input debt.

`missing_unsupplyable` remains an `external_input` fact under `waiting_external_input` so the workflow can route a local alternative, descope, or an externally classified terminal blocker. Do not rewrite that external fact into `goal_truth: blocked`. Likewise, `missing_supplyable` can support the existing exact external-wait route, but it never becomes a permission request.

Use `scope_kind: goal|design|task|improvement|action|authority_policy` together with `D0|D1|D2|D3`. A task-topology grant does not imply authority for its implementation actions. An improvement-direction choice does not change core GT. A risk acceptance does not grant a capability. A policy-management operation requires its own manifested capability and rank.

## Dispatch protocol

Use this sequence without adding a phase:

```text
exact request + exact subject + operation manifest
  -> manage-agent-authority evaluate
  -> closed decision artifact
  -> if allowed mutation: reserve exact uses
  -> manage-agent-authority verify --stage pre_dispatch
  -> orchestrator authority packet --mode block
  -> dispatch only when packet passes
  -> manage-agent-authority verify --stage pre_commit
  -> reopen current owner artifacts and apply the exact effect
  -> consume with the immutable execution-result binding
     or release only on verified no-effect
     or quarantine unknown effect
```

For `observe`, set reservation applicability and dispatch preflight to `not_applicable`. For an allowed mutation, require `reservation_binding.applicability: required`, `status: reserved`, exact grant-use transitions, and a `dispatch_preflight` copied from the immutable owner verification plus its ref/hash.

The pre-dispatch verification must echo the same request ID and owner fingerprint, exact reservation artifact/state, and the same set of selected plus lineage grant IDs/digests at their post-reservation versions. Every verified grant and finite-budget ancestor must remain `active`, and `reserved_uses` must cover the operation units. This is the TOCTOU/revocation/expiry/usage boundary. A later change requires a fresh owner verification and packet; a caller-authored boolean is not verification.

## Commit and settlement gates

Do not treat successful dispatch validation as permission to commit an effect at an arbitrary later time. Immediately before the effect, reopen the packet's immutable owner artifacts and current reservation/grant CAS projections, then validate a distinct immutable `authority_verification` at `stage: pre_commit`. The verification ID and path are derived from its closed canonical body. It must bind the packet's exact reservation, request/fingerprint, reservation state, and complete grant-state set; a pre-dispatch artifact cannot masquerade as this gate.

When validating a typed use receipt, call `$manage-agent-authority`'s public `validate_pre_commit_verification` and `validate_execution_result` contracts. The local settlement owner must not accept a partial structural mirror. Reopen and verify the closed key set, deterministic result ID/path, exact reservation and pre-commit bindings, request subject-before, subject-after ref/digest and expected digest, owner result binding, effect status, and timezone-bearing completion time. A rehashed wrapper with an extra field or a changed reservation, subject, after-state, timestamp, or verification binding is invalid even when the receipt echoes the same forged value.

After the effect, persist one immutable execution-result artifact and pass its exact ref/SHA-256 to `$manage-agent-authority consume`. Before exposing the effect as operationally active, validate the closed `authority_use_receipt`: its ID must derive from the reservation digest and operation-specific consume key; its reservation and execution-result bindings must be exact; every grant/reservation `state_changes` delta and `grant_versions_after` entry must be complete and deterministic. At activation time current CAS projections must equal the receipt after-images. Later read-only validation may accept only an immutable, owner-validated descendant history for reusable grant projections; it must not require an old after-image forever or accept a merely higher version.

Use the order `PREPARE -> revalidate pre_commit/current owner state -> effect -> immutable execution result -> consume -> settlement validation -> activation`. A crash after the effect but before consume remains visibly `authority_settlement_pending`; replay uses the same prepared result and consume key. Release or unknown-effect quarantine never substitutes for consume when activating an observed effect. `activate_task_topology_settlement` is therefore a `bound_lifecycle_artifact` operation: it can finalize only this already-authorized exact lifecycle and cannot widen subject, effect, capability, or budget.

## Terminal-wait baseline publication

A terminal-wait current pointer is an operational workflow binding, not a free-form cache file. Before authority evaluation, materialize one non-active, content-addressed `terminal_wait_baseline_authority_subject` under `.task/terminal_wait_baseline/subjects/`. Its closed body binds only the exact terminal `task.md`, direct full final source-derive result, optional transition evidence, verified selection-tick baseline, and expected predecessor snapshot. For a rebase, the source result must embed `C`, the validated selection-decision receipt ID, and the exact receipt-reopened three-lens analysis; `B` must descend from predecessor `A`, and `C` must descend from `B` with a recomputed empty material-change set. A wrapper, preliminary decision, receipt, or partial derive projection is not a valid source. The subject excludes the later authority packet and pre-commit verification, which removes the otherwise circular requirement to know authority artifacts before constructing their exact subject.

`materialize-subject` is an idempotent prepare-only metadata operation. It may create the immutable subject file, but it must not create a prepare/completion/activation, move the current pointer, enable fanout, or imply that authority was granted. Reopen every bound source before and after the write. The subject file's raw SHA-256 becomes the authority request subject digest; `$manage-agent-authority` can therefore apply its normal existing-file preflight without pretending that a semantic projection hash is the digest of `task.md`.

For a new publication, accept only a format-v2 selection baseline that uses the artifact-verified exact-premise contract and declares the fixed executable wake rule. Human-readable wake-predicate and minimum-delta IDs remain policy labels, not executable expressions. Legacy v1 baselines may be reopened for historical diagnosis only; they cannot become the new current pointer.

Use this lifecycle:

```text
exact terminal/task/direct-final-derive/transition/C/predecessor-A source bindings
  -> materialize immutable non-active authority subject
  -> evaluate + reserve publish_terminal_wait_baseline_binding
  -> verify pre_dispatch and construct the orchestrator packet
  -> verify pre_commit
  -> prepare immutable baseline snapshot and completion
  -> consume the exact reservation against that completion
  -> validate the authority-use receipt
  -> activate by predecessor CAS
  -> expose .task/terminal_wait_baseline/current.json
```

`publish_terminal_wait_baseline_binding` is the grant-authorized effect. `activate_terminal_wait_baseline_settlement` is a bound-lifecycle finalization and cannot alter the subject, sources, predecessor, completion, or use receipt. Preparation never exposes current state. Activation requires the exact consumed execution-result binding; an unconsumed completion remains visibly pending. A competing predecessor, source drift, subject drift, forged use receipt, malformed pointer, or selection baseline that permits raw premise wake fails closed.

After activation, `selection-tick` may discover the current pointer when no explicit previous packet is supplied. It must reopen and revalidate the pointer, activation, completion, snapshot, authority settlement, exact task/source bindings, and selection packet before comparison. No change returns `no_op` without proposal-agent fanout. A read failure is a blocker, not permission to silently initialize another baseline.

## Selected-successor publication

Treat publication of a selected successor as one authority-bound lifecycle spanning two
owners, not as permission inferred from either owner's receipt. The coordinator must use
the exact registered operations:

- `materialize_selection_publication_subject`: authority-free, non-active subject preparation only;
- `publish_selected_successor_topology`: ordinary grant-authorized publication of the selected successor topology;
- `settle_selected_successor_task_state`: ordinary grant-authorized settlement of the exact prospective task-state plan from the committed publication;
- `retire_terminal_wait_baseline_successor`: bound-lifecycle retirement of the exact predecessor baseline after settlement.

The task-state event batch remains separately governed by its ordinary
`mutate_task_state_index` operation. None of the low-level decision, task-state,
publication, status, or retirement helpers grants authority or mints an authority
packet. Do not share or infer a grant across these operations. The three effect grants
for task-state mutation, topology publication, and task-state settlement must all pass
the exact all-three gate. Predecessor retirement is the sole bound-lifecycle operation
in this route; it accepts only artifacts from the already authorized exact subject.
Neither grants nor retirement may widen the selected task, prospective bytes, index
events, publication target, predecessor, effect, or consume key.

Use this order:

```text
exact normal-cycle trigger + selection-decision receipt v2
  -> prospective task-state plan v2 over candidate bytes
  -> non-active selection-publication prepare v3
  -> authority/pre-commit gates for the exact owner effects
  -> task-state event batch/render + pending-external receipt (task.md unchanged)
  -> selection-publication task.md CAS last + committed receipt v3
  -> task-state external settlement from that exact committed receipt
  -> selection-consumption gate becomes true
  -> retire an exact predecessor terminal-wait baseline to an inactive pointer/history
```

Missing or conflicting pending/commit/settlement bindings, alias CAS drift, a different
plan or candidate digest, or an unsettled publication keeps selection consumption false.
Recovery must replay the same transaction artifacts or rederive a new exact subject; it
must not fabricate a trigger, mutate `task.md` ahead of the owners, or ask the user to
repeat authority for unchanged semantics.

## Decision routing

Use only:

`allowed|approval_required|denied|waiting_external_input|capability_unavailable|blocked_by_goal_truth|classification_repair|conflict|not_applicable`.

- `allowed`: continue only within the exact subject/operation/effect scope; reserve and verify before mutation.
- `approval_required`: consume the exact `approval_projection` and request only its typed missing decision. Keep `grant_authority`, `ratify_goal_truth`, `accept_risk_or_cost`, `supply_external_input`, and `select_design_option` distinct. Human-facing wording may improve, but effect/scope/exclusions/replay identity remain deterministic.
- `waiting_external_input`: wait or monitor the existing external owner; it is not an authority request.
- `capability_unavailable`: route a genuine unavailable-capability boundary, not a self-resolvable local wiring gap.
- `blocked_by_goal_truth`: route local alternative/descope/GT-owner decision as the GT contract allows.
- `classification_repair|conflict`: permit only bounded classification/contract repair before normal successor selection.
- `denied`: do not dispatch. A higher source rank may change only a capability lineage/scope it is itself authorized to manage.
- `not_applicable`: preserve the reason and continue without claiming a grant.

An unchanged approval request or external waiting state is not a new task or cycle. Preserve the exact request/decision artifact and wait record.

## Terminal-wait replay

Create and compare terminal-wait baselines with exact authority phase packets:

```bash
python3 -P -m orchestrate_task_cycle selection-tick --root . \
  --authority-packet <authority-packet.json> \
  --previous-json <prior-tick.json>
```

The tick stores only a scope ID, scoped effective fingerprint, closed decision, and axis statuses. It stores no policy, source, subject body, or artifact path. The same exact request/operation/subject and same relevant authority/local/external/risk/GT states return `no_op`; do not initialize a cycle or assign proposal agents.

A changed exact scope, owner/grant/reservation state, or independent axis may reopen only the existing derive-selection boundary. A change to an unrelated grant or mutable whole authority policy does not reopen. The helper rejects `.agent_goal/agent_authority.md` as a terminal-wait watch path; use an exact v2 packet.

## Legacy migration

Read legacy authority classifications and ad-hoc authority packets only for diagnostics. Project them as `classification_repair`/`unverified`; never use them to authorize dispatch, justify a terminal state, reopen a wait, or claim historical approval.

A migration may bind a contemporaneous immutable source record and produce a new v2 artifact. Missing historical evidence remains unverified. Current ratification can authorize a new action now but cannot turn an old action into a historical pass.

For invalid but declared-closed legacy task packs, use one exact per-pack topology subject and a new v2 grant for the retirement action now. Preserve the raw pack bytes and raw validation findings. An immutable overlay may remove that exact historical pack from the operational selection domain only after the pre-commit/effect/consume/activation chain above settles. The overlay must state that it does not prove pack/item completion, dependency satisfaction, provenance repair, or historical authority. A clean pack, active/current pack, unknown blocker, raw-byte drift, swapped execution result, missing consume receipt, or forged activation remains blocked.
