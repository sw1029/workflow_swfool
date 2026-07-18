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
- [Transition and revocation](#transition-and-revocation)
- [Typed decisions](#typed-decisions)
- [CLI surface](#cli-surface)
- [Migration](#migration)
- [Required invariants](#required-invariants)

## Artifact layout

Use this workspace-local layout:

```text
.task/authorization/
├── policy_snapshots/       immutable content-addressed policy bytes and metadata
├── source_snapshots/       immutable content-addressed approval/evidence bytes
├── grants/                 immutable closed grant contracts
├── compositions/           immutable explicit multi-grant composition receipts
├── decisions/              immutable evaluator decisions
├── reservations/           immutable reserve events
├── verifications/          immutable pre-dispatch/pre-commit checks
├── use_receipts/           immutable consume receipts
├── release_receipts/       immutable release or quarantine receipts
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

Keep cardinality and scope internally consistent: `single_use` requires `use_budget_requested=1`, `task_lease` requires an exact non-null `task_id`, and `improvement_lease` requires an exact non-null `pack_id`. Reject the request before grant matching when any relation is missing.

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
```

Reserve under an exclusive workspace lock. Re-evaluate the exact request, resolve its subject as an existing workspace-relative non-symlink regular file, verify the scoped fingerprint, exact subject digest, raw-manifest binding, selected and lineage grant digest/state/version, policy snapshot, expiry, session/task/improvement scope, and budget. Increment `reserved_uses` and the CAS version for every de-duplicated grant in the lineage.

Before dispatch or commit, write an immutable `authority_verification` binding:

- reservation ref/digest;
- reservation-state ref/digest/version/status;
- current grant digest/version/status/remaining/reserved counters;
- exact request ID and scoped fingerprint;
- verification stage and time.

Consume only with an immutable execution-result binding. Decrement remaining/reserved uses, increment consumed uses and state version, and exhaust a finite grant at zero.

Release only with immutable evidence of `not_started` or `verified_no_effect`. For `unknown_effect`, preserve reserved use and set reservation state to `quarantined_unknown_effect`.

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

## CLI surface

Invoke through:

```bash
PYTHONPATH="<skills-root>/manage-agent-authority/scripts" \
  python3 -m manage_agent_authority authority <command> ...
```

Use:

- `snapshot-policy`, `snapshot-source`;
- `register-grant`, `delegate`, `compose`;
- `evaluate`, `reserve`, `verify`, `consume`, `release`;
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
