# Authority v2 Contract

## Contents

- [Artifact layout](#artifact-layout)
- [Closed enums](#closed-enums)
- [Operation manifest](#operation-manifest)
- [Authority request](#authority-request)
- [Evaluation context](#evaluation-context)
- [Source approval and bootstrap](#source-approval-and-bootstrap)
- [Grant and delegation](#grant-and-delegation)
- [Decision and fingerprint](#decision-and-fingerprint)
- [Reservation lifecycle](#reservation-lifecycle)
- [Execution settlement and reconciliation](#execution-settlement-and-reconciliation)
- [Workflow status and resolution](#workflow-status-and-resolution)
- [Transition and revocation](#transition-and-revocation)
- [Typed decisions](#typed-decisions)
- [Operation compilation](#operation-compilation)
- [CLI surface](#cli-surface)
- [Migration](#migration)
- [Required invariants](#required-invariants)

## Artifact layout

Use this workspace-local layout:

```text
.task/authorization/
├── operation_compilations/ immutable non-authoritative preparation artifacts
├── policy_snapshots/       immutable content-addressed policy bytes and metadata
├── source_snapshots/       immutable content-addressed approval/evidence bytes
├── grants/                 immutable closed grant contracts
├── compositions/           immutable explicit multi-grant composition receipts
├── decisions/              immutable evaluator decisions
├── reservations/           immutable reserve events
├── verifications/          immutable pre-dispatch/pre-commit checks
├── execution_results/      typed authority settlement wrappers
├── reconciliation_evidence/ closed effect-observation evidence
├── use_receipts/           immutable consume receipts
├── release_receipts/       immutable release or quarantine receipts
├── reconciliation_receipts/ immutable quarantine settlements
├── events/                 immutable suspend/reactivate/revoke/expire events
└── state/
    ├── current_policy.json mutable CAS pointer to one policy snapshot
    ├── grants/             mutable usage/lifecycle projections
    └── reservations/       mutable reservation projections
```

Bind every immutable artifact by workspace-relative `ref` plus lowercase full `sha256`. Write an exact replay idempotently. Reject a different body at an existing identity.

## Closed enums

Use only these values:

- Source rank: `S0`, `S1`, `S2`, `S3`, `S4`.
- Risk: `R0`, `R1`, `R2`, `R3`.
- Decision class: `D0`, `D1`, `D2`, `D3`.
- Cardinality: `single_use`, `bounded_reusable`, `task_lease`, `improvement_lease`, `standing_policy`.
- Mutation: `observe`, `local_mutation`, `external_mutation`, `destructive`.
- Reversibility: `reversible`, `conditionally_reversible`, `irreversible`.
- Decision: `allowed`, `approval_required`, `denied`, `waiting_external_input`, `capability_unavailable`, `blocked_by_goal_truth`, `classification_repair`, `conflict`, `not_applicable`.
- Intent: `grant_authority`, `ratify_goal_truth`, `accept_risk_or_cost`, `supply_external_input`, `select_design_option`.

Treat higher source rank as a stronger decision source, not a new runtime capability. Treat risk and decision axes as independent from source rank.

## Operation manifest

Place `authority.operations.json` at the owning skill root. Use:

```json
{
  "schema_version": 2,
  "manifest_kind": "authority_operations",
  "skill_id": "skill-id",
  "skill_version": "2.0.0",
  "operations": [
    {
      "operation_id": "operation-id",
      "operation_version": "1",
      "mutation_class": "local_mutation",
      "required_capabilities": ["namespace.capability"],
      "source_rank_floor": "S1",
      "risk_floor": "R1",
      "decision_class": "D3",
      "effect_classes": ["bounded_effect"],
      "data_classes": ["repository_code"],
      "reversibility": "conditionally_reversible",
      "subject_kinds": ["task"],
      "authority_applicability": "required",
      "authorization_mechanism": "grant"
    }
  ]
}
```

Use `required`, `conditional`, or `none` for applicability. Use exactly one mechanism:

- `grant`: ordinary operation evaluation through a covering authority grant;
- `typed_source_approval`: issuance, composition, or transition verified against a closed authority source approval;
- `bound_lifecycle_artifact`: delegation or reservation lifecycle action verified against an immutable parent/decision/reservation artifact;
- `none`: authority does not apply; this must pair with `authority_applicability=none`.

The last three mechanisms prevent recursive administration: issuing or spending a grant is governed by its typed source or bound lifecycle artifact rather than by another grant whose creation would require itself. Keep every operation ID/version and capability exact. Never use `*`. Bind a decision to the SHA-256 of the raw manifest file bytes. Runtime context may add capabilities or increase risk, mutation, or irreversibility; it may not lower the manifest.

## Authority request

Require exactly these top-level fields:

```json
{
  "schema_version": 2,
  "request_kind": "authority_operation",
  "request_id": "request-id",
  "skill_id": "skill-id",
  "skill_version": "2.0.0",
  "operation_id": "operation-id",
  "operation_version": "1",
  "cycle_id": null,
  "task_id": "task-id",
  "pack_id": null,
  "attempt_id": "attempt-id",
  "actor_rank": "S0",
  "subject": {
    "kind": "task",
    "ref": ".task/task.md",
    "digest": "64 lowercase hex",
    "revision": "revision-id"
  },
  "required_capabilities": ["namespace.capability"],
  "effect_class": "bounded_effect",
  "data_class": "repository_code",
  "mutation_class": "local_mutation",
  "reversibility": "conditionally_reversible",
  "risk_tier": "R1",
  "decision_class": "D3",
  "intent_type": "grant_authority",
  "cardinality_requested": "single_use",
  "use_budget_requested": 1,
  "reservation_units": 1,
  "idempotency_key": "attempt-operation-key",
  "context": {
    "external_input_status": "not_required",
    "external_input_evidence": null,
    "goal_truth_status": "aligned",
    "risk_acceptance_status": "not_required",
    "risk_acceptance_evidence": null,
    "design_selection_status": "not_required",
    "design_selection_evidence": null
  },
  "composition_receipt": null
}
```

In schema v2, `subject.ref` is a workspace-relative reference to an existing
regular file. It does not encode an expected-absent resource. Reject missing,
symlinked, or non-regular subjects, and rehash the current regular file before
reserve, dispatch, and commit to require an exact `subject.digest` match.

Use `composition_receipt: {"ref": "...", "sha256": "..."}` only for a separately approved exact composition. Bind the composition to the canonical SHA-256 of the same request with `composition_receipt=null`; this avoids a self-referential digest while preserving every substantive field. Keep nullable IDs present as `null` so canonical bytes are stable.

Evidence bindings are positive assertions, not optional decoration. Require immutable `{ref, sha256}` evidence when external input is asserted `available`, `missing_supplyable`, or `missing_unsupplyable`, when risk acceptance is `resolved`, or when design selection is `resolved`. Require the corresponding field to be `null` for `unverified`, `unresolved`, and `not_required`. Re-hash these bindings during evaluation and pre-commit verification.

Keep cardinality and scope internally consistent: `single_use` requires both budgets to be 1; `reservation_units` must be positive and no greater than `use_budget_requested`; `task_lease` requires an exact non-null `task_id`; and `improvement_lease` requires an exact non-null `pack_id`. Treat `use_budget_requested` as the grant/reuse scope and `reservation_units` as the units charged by one dispatch. New requests must set `reservation_units` explicitly, normally to 1. Requests that predate the field retain their historical behavior by charging `use_budget_requested`; this is a compatibility rule, not the recommended request form.

## Evaluation context

Require the session ceiling and GT autonomy envelope separately:

```json
{
  "schema_version": 2,
  "context_kind": "authority_evaluation",
  "session_ceiling": {
    "capabilities": ["namespace.capability"],
    "risk_ceiling": "R1",
    "mutation_classes": ["observe", "local_mutation"],
    "evidence_id": "active-session-id"
  },
  "goal_autonomy_envelope": {
    "envelope_id": "envelope-id",
    "capabilities": ["namespace.capability"],
    "risk_ceiling": "R1",
    "decision_classes": ["D3"],
    "subjects": ["exact subject digest"],
    "operations": ["skill-id:2.0.0:operation-id:1"],
    "source_binding": {"ref": ".agent_goal/goal_architecture.md", "sha256": "64 lowercase hex"}
  }
}
```

Derive the autonomy envelope from ratified concept IDs and exact revisions. Keep concept truth in goal theory/architecture/schema; store only the resulting decision right and binding here.

## Source approval and bootstrap

A root grant, explicit grant composition, or lifecycle transition must trace to a closed, immutable authority source rather than to prose or an inferred user preference. Snapshot this JSON before use:

```json
{
  "schema_version": 2,
  "artifact_kind": "authority_source_approval",
  "approval_id": "approval-id",
  "source_kind": "explicit_user_instruction",
  "source_rank": "S3",
  "decision_type": "grant_authority",
  "capabilities": ["authority.grant.issue", "namespace.capability"],
  "subjects": [{"kind":"task","ref":".task/task.md","digest":"64 lowercase hex","revision":"revision-id"}],
  "operations": [{"skill_id":"skill-id","skill_version":"2.0.0","operation_id":"operation-id","operation_version":"1"}],
  "risk_ceiling": "R1",
  "decision_classes": ["D3"],
  "cardinalities": ["single_use"],
  "max_uses": 1,
  "grant_ids": ["grant-id"],
  "request_digests": [],
  "lineage_ids": ["lineage-id"],
  "delegation_binding": null,
  "not_before": "RFC3339",
  "expires_at": "RFC3339 or null",
  "evidence_id": "opaque-evidence-id",
  "integrity_status": "verified"
}
```

The `source_kind`/rank pairs are fixed: `platform_session_ceiling/S4`, `explicit_user_instruction/S3`, `delegated_policy_steward/S2`, and `cycle_coordination_grant/S1`. Require `decision_type=grant_authority`; another typed decision cannot be smuggled through this object. Root-grant issuance requires `authority.grant.issue` in the effective source approval. S1/S2 approvals require an immutable `delegation_binding`. Resolve that exact workspace-relative source-approval artifact, rehash its bytes, and require a strictly higher rank. Follow the lineage until S3 or S4 while rejecting a repeated approval/binding, a missing artifact, digest mismatch, equal/lower rank, or an approval that is not effective at the administrative action time. Every delegated approval must be an exact subset of its parent across capabilities, subjects, operations, grant IDs, request digests, lineage IDs, risk, decision classes, cardinalities, budget, and validity window; therefore the issuance capability must also be present in every parent. This rank-monotone, finite lineage prevents an S1/S2 label or self-reference from becoming a new root of trust. Root grant creation must occur during the complete approval-lineage window and may only narrow it.

For composition, additionally require capability `authority.grant.compose`, source rank at least S3, the exact base-request digest in `request_digests`, and every composed grant ID. For transition, require `authority.grant.transition`, exact grant and lineage IDs, and a source rank above the holder. A source below the original issuer is valid only when its immutable higher-rank delegation binding covers that same transition capability, grant, lineage, and time window. These typed-source checks are the root of trust for authority administration; do not recursively ask the ordinary grant evaluator to authorize them.

## Grant and delegation

Use a closed grant:

```json
{
  "schema_version": 2,
  "artifact_kind": "authority_grant",
  "grant_id": "grant-id",
  "lineage_id": "lineage-id",
  "parent_grant_id": null,
  "issuer_rank": "S3",
  "holder_rank": "S0",
  "capabilities": ["namespace.capability"],
  "subjects": [{"kind":"task","ref":".task/task.md","digest":"64 lowercase hex","revision":"revision-id"}],
  "operations": [{"skill_id":"skill-id","skill_version":"2.0.0","operation_id":"operation-id","operation_version":"1"}],
  "risk_ceiling": "R1",
  "decision_classes": ["D3"],
  "cardinality": "single_use",
  "max_uses": 1,
  "not_before": "RFC3339",
  "expires_at": "RFC3339 or null",
  "session_id": "session-id or null",
  "task_id": "task-id or null",
  "improvement_id": "improvement-id or null",
  "source_approval": {"ref":"immutable source snapshot","sha256":"64 lowercase hex"},
  "policy_snapshot": {"ref":"immutable policy snapshot","sha256":"64 lowercase hex"},
  "created_at": "RFC3339",
  "idempotency_key": "grant-key"
}
```

Require `issuer_rank > holder_rank`. For `single_use`, require `max_uses=1`. For `bounded_reusable`, require finite positive `max_uses`. Bind task and improvement leases to their exact IDs.

Cardinality coverage is directional. A `single_use` request may consume one use from any cardinality. A `bounded_reusable` request requires bounded-reusable or standing authority; a task lease requires task or standing authority; an improvement lease requires improvement or standing authority; standing-policy reuse requires standing authority. Independently enforce every non-null `session_id`, `task_id`, and `improvement_id`, including when the grant cardinality itself is not a lease.

For delegation, require:

- child parent and lineage IDs match;
- child issuer rank equals parent holder rank, and child holder rank is lower;
- child capabilities, subjects, operations, and decision classes are subsets;
- child risk ceiling, expiry, task/improvement scope, and budget are no broader;
- parent is active and unexpired;
- child `source_approval` binds the exact immutable parent-grant artifact and digest;
- revoke/expire cascades to all descendants;
- self or circular delegation fails.

An active child does not bypass an inactive, expired, out-of-scope, or budget-exhausted ancestor. Evaluate every ancestor and reserve the requested use against the selected grant plus all unique ancestors. This shared lineage accounting prevents several children from multiplying a finite parent budget.

## Decision and fingerprint

Persist a decision with these exact keys:

```text
schema_version, artifact_kind, decision_id, request, request_sha256,
evaluation_context, evaluation_context_sha256, decision, reason_codes,
approval_projection, selected_grants, lineage_grants, operation_manifest,
effective_authority_fingerprint, evaluated_at
```

Each selected or lineage grant binds `grant_id`, immutable `grant_sha256`, mutable `state_version`, and immutable `policy_snapshot`. `lineage_grants` contains de-duplicated ancestors that constrain the decision even though they are not the direct covering grant.

Compute `effective_authority_fingerprint` only from:

- exact operation and subject;
- requested capabilities;
- versioned operation-manifest binding;
- whether the session ceiling covers the requested capabilities/risk/mutation;
- whether the GT envelope covers the requested capabilities/risk/decision/subject/operation;
- the typed external-input/risk/design status plus only its relevant immutable evidence binding;
- selected and lineage grant IDs, immutable digests, relevant state versions, and policy snapshots.

Do not include the mutable whole policy, unrelated grants, unrelated concept nodes, or the full context digest in the wakeup fingerprint. Keep the full context digest separately for audit and preflight revalidation.

Set `approval_projection` to `null` unless the decision is `approval_required`. For an approval wait, generate it deterministically from the one missing typed decision, request ID, exact operation/subject/capabilities/effect, cardinality/use/session/cycle/task/improvement/attempt scope, sorted reason codes, idempotent replay key, remaining excluded typed axes, fixed out-of-scope effects, and a closed safe-alternative code. A grant request blocked on unresolved risk projects `accept_risk_or_cost`; one blocked on a D0/D1 design choice projects `select_design_option`. Never list the projected intent itself as excluded. Derive `projection_id` from the canonical body. Approval covers only this projection; it does not resolve another typed axis, add capability, raise risk, broaden scope, or increase reuse.

## Reservation lifecycle

Use this state sequence:

```text
grant:       draft -> active -> suspended -> active (explicit reactivation only)
                         └----> revoked | expired
                active --------> revoked | expired | exhausted
single use:  allowed -> reserved -> consumed
                           └----> released (only no effect)
                           └----> quarantined_unknown_effect
                                      ├----> consumed (confirmed effect)
                                      ├----> released (confirmed no effect)
                                      └----> quarantined_unknown_effect (still unknown)
```

Reserve under an exclusive workspace lock. Re-evaluate the exact request, resolve its subject as an existing workspace-relative non-symlink regular file, verify the scoped fingerprint, exact subject digest, raw-manifest binding, selected and lineage grant digest/state/version, policy snapshot, expiry, session/task/improvement scope, and budget. Increment `reserved_uses` and the CAS version for every de-duplicated grant in the lineage.

Before dispatch or commit, write an immutable `authority_verification` binding:

- reservation ref/digest;
- reservation-state ref/digest/version/status;
- current grant digest/version/status/remaining/reserved counters;
- exact request ID and scoped fingerprint;
- verification stage and time.

Consume only with an explicit exact `pre_commit` verification binding, a typed owner-result binding, and an exact expected subject-after SHA-256. Do not discover or silently select a verification. The pre-commit verification proves the pre-effect subject and reserved CAS state. After the effect, do not re-require the pre-effect subject digest. Instead, compare the current subject to the expected-after digest and create an immutable `authority_execution_result` that binds the reservation, verification, owner result, subject before/after, effect status, and completion time. Bind the use receipt to this typed result and the owner result. Decrement remaining/reserved uses, increment consumed uses and state version, and exhaust a finite grant at zero.

Release only with immutable evidence of `not_started` or `verified_no_effect`. For `unknown_effect`, preserve reserved use and set reservation state to `quarantined_unknown_effect`.

## Execution settlement and reconciliation

Require this closed authority-generated execution result for every new consume:

```text
schema_version, artifact_kind=authority_execution_result, result_id,
reservation, pre_commit_verification, owner_result, effect_status=confirmed_effect,
subject_before, subject_after, expected_subject_after_sha256, completed_at
```

Derive `result_id` and its `execution_results/<result_id>.json` path from the canonical body. Require `subject_after.sha256=expected_subject_after_sha256`. Preserve validation of older immutable use receipts, but never issue a new untyped receipt.

Prepare reconciliation evidence with `prepare-reconciliation-evidence`; do not hand-author paths or IDs. Settle a quarantined reservation only with the resulting closed `authority_effect_reconciliation_evidence` at its deterministic content-derived path. Bind its evidence ID, exact reservation, versioned operation, subject before, observed subject digest, outcome, observation time, and a typed owner result for a confirmed effect or confirmed no-effect. Require confirmed no-effect to preserve the exact subject-before digest. Reject arbitrary JSON, mismatched outcomes, stale observed subjects, or a missing typed owner result.

Write an immutable reconciliation receipt before applying its CAS projections:

- `confirmed_effect`: consume retained units and mark the reservation `consumed`; require the original exact pre-commit verification.
- `confirmed_no_effect`: release retained units and mark the reservation `released`.
- `still_unknown`: preserve units and advance the quarantined reservation version without changing its status.

Reconciliation settles evidence about an existing effect. It does not create a new approval for the original operation.

## Workflow status and resolution

`status` must include `evaluated_at`, an optional exact `request_sha256_filter`, grants, reservations, quarantines, pending versus superseded waits, verifications, typed execution results, use/release/reconciliation receipts, `workflow_state`, `should_prompt`, and one machine-readable next action. It must also include a `workflow_basis` carrying the exact decision, reservation and reservation-state, source-approval, settlement-receipt, and blocker bindings that justify the selected state. Accept an optional explicit RFC3339 `--at` for deterministic diagnosis and replay; otherwise capture the current UTC time once. Use only that captured time for the selected grant and every ancestor. Report each grant's raw state separately from `effective_usable`, effective status, and lineage blocker codes. A raw `active` grant is effectively unusable before its `not_before`, at or after its `expires_at`, or under any ancestor that is inactive, not yet active, or time-expired.

Before deriving workflow state or suppressing a prompt, validate the complete immutable lifecycle intent graph and prove every intent projection is at its exact `after` state or a validated descendant. Public closed validators must recheck deterministic identities, paths, bindings, and schemas for decisions, reservations, use/release/reconciliation receipts, grants, and current grant/reservation states. Resolve the decision's operation manifest from the same explicit skills root used for evaluation (or the declared default), validate its closed contents and exact requested operation identity, and require its current ref/digest binding to equal the persisted decision binding. A missing, changed, or identity-incompatible manifest and any malformed or unsettled artifact are errors, never evidence that a wait was superseded or that an operation can resume. Reject a symlink at any component of every authority-owned decision, source-snapshot, grant, state, and receipt directory. Read status-visible JSON through a stable no-follow acquisition and report the digest of the same bytes that were parsed. Suppress an approval wait only when the same request digest has a validated reserved, consumed, released, or quarantined lifecycle artifact, a current exact allowed decision, or an exact usable/materializable source candidate.

Choose the public state using this precedence, after applying the optional exact request filter: `effect_reconciliation` for quarantine; `already_consumed` or `already_released` for settled lifecycle state; `ready_to_resume` for a reserved operation whose complete authority lineage remains usable; `reserved_authority_recovery` for a reserved operation blocked by selected or ancestor authority; `ready_to_reserve` for a current persisted exact allowed decision; `source_approval_ready_for_grant` for a usable or cleanly materializable exact source; `source_authority_defect` for an internally inconsistent source/grant projection; `source_authority_exhausted` for a source whose existing IDs cannot be reused; then `needs_user_approval` for a genuine remaining wait. Never let a lower-precedence stale wait override a higher-precedence lifecycle or authority fact.

A released reservation is terminal only when status correlates its exact reservation ref/digest with a release receipt whose effect status is `not_started` or `verified_no_effect`, or a reconciliation receipt whose outcome is `confirmed_no_effect`. Return that receipt in `workflow_basis.settlement_receipt`, use `already_released`, and never dispatch the operation again. Apply the corresponding exact-receipt rule to consumed state. A reserved operation whose selected grant or any ancestor is suspended, revoked, expired, not yet active, or otherwise unusable must remain reserved and return `reserved_authority_recovery`; do not call it resumable and do not automatically release units while effect certainty is unresolved.

For each exact covering source approval, classify every declared grant ID. A syntactically valid ID is materializable only if neither its immutable grant path nor mutable state path exists and neither path is a symlink. An existing ID is reusable only if the exact source-approval binding, operation, subject, capabilities, risk/decision/cardinality scope, lineage, time window, status, session, and remaining budget cover the request. A missing clean ID or at least one existing reusable ID yields `source_approval_ready_for_grant` with `materialize_grant` or `evaluate_existing_grant`. An orphan state, conflicting path, invalid ID, or impossible projection yields `source_authority_defect` and a system repair action. An exhausted, revoked, expired, suspended, not-yet-active, or source-binding-conflicted existing ID is not rematerializable: return `source_authority_exhausted`, set `should_prompt=false`, supersede the former generic wait, expose no active wait identity, derive a separate recovery identity from the exact request/source/state evidence, and route `prepare_exact_recovery_recipe`.

`prepare-source-recovery` is the only publisher for that repair step. It consumes the exact immutable exhausted decision binding and one explicit preparation time, revalidates the operation manifest and current exhausted evidence, and publishes at most one immutable recipe at the recovery-identity path. The closed recipe binds the old decision/source/grant/state evidence and contains six mutually distinct, old-ID-disjoint replacement identities: request, attempt, source approval, grant, lineage, and exact replay. It also contains the exact replacement request and digest, non-artifact source-approval requirements, non-artifact grant requirements, and a deterministic recovery approval projection that explicitly names `authority.grant.issue`. Exact replay returns the same artifact; different content at the same recovery path is a conflict.

The recipe has `authority_status=non_authoritative_prepare_only`. No nested recipe object may validate as `authority_source_approval` or `authority_grant`; it must not contain a precomputed source-snapshot binding, `integrity_status=verified`, or a substitute evidence ID. The actual explicit user decision must supply its own evidence ID, after which the source bytes are materialized and snapshotted and only that actual binding may complete a separately validated grant. Recipe publication does not express user approval, issue authority, consume a budget, or permit dispatch. Once the recipe validates, `status` and `resolve` replace the repair route with exactly one `needs_user_approval` wait and action `approve_exact_recovery_projection`, using the recipe projection and a new wait identity. Never expose the old approval projection as active and never reuse an exhausted request, attempt, source, grant, lineage, or replay ID.

`prepared_at` is T1 preparation time, not approval evidence. The actual explicit user decision establishes T2 with T2 >= T1. Source `not_before`, grant `not_before`, and grant `created_at` must be T2 or later under the normal source/grant validators. A replayed evaluation at T1 remains non-allowed; no recipe field may backdate prospective authority.

Prepare, status, and resolve expose the same non-authoritative `post_approval_handoff`. It names only existing public commands: `snapshot-source` for a source artifact derived from the actual explicit user-decision evidence, `register-grant` after substituting that actual snapshot binding into a newly validated grant, and `evaluate` for the closed replacement request. It also binds `continuation_request_sha256`. After exact approval and materialization, consumers must switch their status/resolve filter to that replacement digest; continued polling of the exhausted original digest is historical recovery observation, not forward progress.

Recipe discovery precedes current covering-source wait classification. Reopen a recipe by its exact historical decision binding and by reproducing its T1 source/grant/state exhaustion evidence; do not require the old source to remain currently covering. If its continuation window is still open, keep the recovery projection as the sole active prompt. If its expiry ceiling is closed, return the existing `source_authority_exhausted` state with reason `source_recovery_window_closed`, action `prepare_fresh_recovery_plan`, `should_prompt=false`, the exact recipe binding, and a closed-window handoff. In both cases the original projection and wait identity remain historical. All non-prompt resolver outcomes return `approval_projection=null` rather than falling back to a persisted decision projection.

Publish every authority-owned snapshot, immutable artifact, and mutable state projection through a stable directory descriptor. Traverse owned parent components with `O_NOFOLLOW`, bind the opened parent identity before publication, recheck it after publication, and remove a just-published artifact before failing when an ancestor swap is detected. A symlinked or swapped parent must never redirect an authority write outside the intended workspace path.

`resolve` evaluates the exact request without mutating authority state, then classifies it as one of:

- `ready_to_resume`, `effect_reconciliation`, `already_consumed`, or `already_released`: system action, no prompt;
- `reserved_authority_recovery`: preserve the reservation and run effect/authority recovery, no prompt;
- `ready_to_reserve`: allowed decision, no prompt;
- `source_approval_ready_for_grant`: an exact effective closed source approval can materialize a grant, no prompt;
- `source_authority_defect`: repair inconsistent local authority projections, no prompt;
- `source_authority_exhausted`: prepare one non-authoritative exact recovery recipe with distinct replacement IDs, no prompt;
- recovery recipe present: return one `needs_user_approval` / `approve_exact_recovery_projection` wait;
- `needs_user_approval`: no existing lifecycle or exact effective source approval, prompt once;
- `decision_<typed-decision>`: route the separate decision without relabeling it as authority approval.

Use a stable wait identity derived from `projection_id`, `exact_replay_key`, and `effective_authority_fingerprint`. Use a separately named, evidence-derived recovery identity for non-user source repair; it is not an approval replay key. `no_single_covering_active_grant` is an evaluator reason, not proof that a user must approve again. Return specific grant near-miss reason codes and a closed structured error envelope with `retryable`, `user_action_required`, and `next_action`.

Status and resolve share one interaction projection: `outcome`, `workflow_state`, `should_prompt`, `user_action`, and `next_action`. Set `outcome` and `workflow_state` to the same selected workflow/resolution state. Set `user_action` to the exact `next_action` only when `next_action.actor=user`; otherwise set it to `null`. Preserve command-specific aliases such as `resolution` for backward compatibility.

Every reserve, consume, release, and transition artifact carries `state_changes`. Each change binds a workspace-relative projection path and exact `before`/`after` JSON objects. Write the immutable artifact before applying projections. Before every later lifecycle or transition entry, deterministically scan all immutable intents and finish any exact, uniquely connected partial projection—not only an identical idempotency replay. Current equal to `before` may advance; current equal to `after` or an exact descendant in the immutable state graph is already satisfied; competing branches or unconnected state require quarantine/manual resolution. This prevents one reservation from consuming another reservation's aggregate counter after a crash.

Validate the complete intent set before changing any projection. Load intent directories and files without following symlinks, require workspace containment and regular files, and reject an intent JSON document larger than 1 MiB. Match each directory to its one closed artifact kind; prove its deterministic identity and path; rehash every immutable decision, reservation, execution-result, no-effect, source-approval, and grant binding; and derive the only permitted state-change refs and counter/status deltas from those bindings. Reject unknown or duplicate refs, duplicate or competing graph edges, and incomplete transition cascades. An exact lifecycle replay after recovery must not reapply its stale `before -> after` changes: succeed only when every current projection equals that intent's exact `after` or is reachable from it through the already validated unique graph.

## Transition and revocation

Require `expected_version`, exact `event_id`, and immutable typed source approval for every transition. Make a duplicate identical event idempotent and a conflicting event invalid. `suspended` is recoverable only through the explicit `reactivated` transition: the target must still be suspended, the CAS version and source binding must match, the source approval must still be effective, and the grant must not have reached `expires_at`. Reactivation changes only that grant projection back to `active`; it does not revive a separately suspended or terminal descendant. Never infer reactivation from a policy edit. Apply `expired` only at or after the exact non-null `expires_at`. Cascade `revoked` and `expired` to descendants; both are terminal. A suspended ancestor invalidates descendant evaluation even if descendant projection states remain `active`.

Check current policy/grant/revocation/task/subject/usage bindings again immediately before dispatch and commit. Treat a mismatch as stale authority, not as an invitation to broaden scope.

## Typed decisions

Keep these questions independent:

| Question | Correct artifact/owner | Never substitute |
|---|---|---|
| May this actor perform this operation? | Authority decision/grant | Task status or advice |
| Is this core goal true/accepted? | Goal-owner ratification | Authority grant |
| Is this risk/cost accepted? | Risk/cost acceptance | Operation permission |
| Is required input available? | Input availability/supply evidence | Approval |
| Which bounded design option is selected? | Design decision/autonomy rule | Executor convenience |

## Operation compilation

`compile-operation` accepts a closed semantic seed and emits an `authority_operation_compilation` schema-v1. The seed selects one manifest operation, an exact workspace subject, scope IDs, actor/cardinality/budget, the four independent decision axes, a session ceiling, a goal-autonomy envelope, and optional upward-only runtime classification.

The compiler derives request/attempt/idempotency IDs, current subject and manifest digests, manifest-owned effect/data/decision/mutation/reversibility fields, request/context digests, provenance, and a compilation fingerprint. Identical seed, subject/manifest bytes, and explicit compile time must produce identical bytes.

The default command emits the full object for compatibility. `--publish` immutably writes it to `.task/authorization/operation_compilations/operation_compilation-<compilation_fingerprint>.json` and emits the compact `{ref, sha256, compilation_fingerprint}` receipt. Exact replay returns the same receipt; different bytes at that content-addressed path fail closed. Publication does not call source, grant, decision, reservation, or settlement issuance.

The result is `non_authoritative_compilation`: it never satisfies source approval, grant, reservation, or settlement. Seed-provided session and goal envelopes are asserted-untrusted narrowing inputs, not authority evidence; the compiler never expands them to fit a request. `evaluate` and `resolve` reopen the subject and manifest and run the independent request/context and authority validators before consuming it. Subject or manifest drift returns `recompile_required`; ambiguous manifest choices, malformed nested input, and any classification downgrade fail closed.

## CLI surface

Invoke through:

```bash
PYTHONPATH="<skills-root>/manage-agent-authority/scripts" \
  python3 -m manage_agent_authority authority <command> ...
```

Use:

- `compile-operation` for mechanical request/context preparation;
- `snapshot-policy`, `snapshot-source`;
- `register-grant`, `delegate`, `compose`;
- `evaluate`, `resolve`, `prepare-source-recovery`, `reserve`, `verify`, `consume`, `release`, `prepare-reconciliation-evidence`, `reconcile`;
- `transition`, `status`.

Supply all times explicitly as RFC3339 for reproducible artifacts. Supply all CAS versions explicitly for mutable transitions.

## Migration

Do not rewrite a legacy receipt or grant in place.

1. Classify it as verified legacy, partial historical, invalid, or unclassified.
2. Preserve v1 current-file digest semantics when validating a v1 receipt.
3. Issue v2 only prospectively from immutable snapshots.
4. Reconstruct historical authority only from immutable contemporaneous evidence.
5. Never turn later completion, validation, current approval, or a migration script into an earlier permission.
6. Mark legacy interview policy without authority questions as migration-needed; do not claim retroactive user confirmation.

## Required invariants

- Session ceiling, GT envelope, operation manifest, and one exact grant all cover the request.
- Administrative operations use their declared typed-source or bound-lifecycle mechanism without recursive self-authorization.
- Dynamic classification never lowers manifest requirements.
- Unknown mutating operations fail closed.
- Grants never union implicitly.
- Delegation never expands capability, subject, operation, risk, time, budget, or rank.
- No child may amplify or survive the invalidity of its ancestor lineage.
- Approval, GT ratification, risk acceptance, external input, and design selection remain separate.
- A single-use grant cannot be spent twice.
- Mutable projections change only under lock and expected-version checks.
- Exact idempotent replay succeeds; conflicting replay fails.
- Partial projection updates recover only from immutable exact before/after intents.
- Snapshot digests name the bytes copied from one stable source-file acquisition; a source mutation during acquisition fails before publication.
- Current policy edits do not invalidate v2 receipts or unrelated waits.
- Revocation/expiry propagates through lineage.
- Unknown execution effect quarantines budget.
