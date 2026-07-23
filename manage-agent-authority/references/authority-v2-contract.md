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
- [Shared context, batches, and root approval](#shared-context-batches-and-root-approval)
  - [Legacy implement-seed migration](#legacy-implement-seed-migration)
- [CLI surface](#cli-surface)
- [Migration](#migration)
- [Required invariants](#required-invariants)

## Artifact layout

Use this workspace-local layout:

```text
.task/authorization/
├── operation_compilations/ immutable non-authoritative preparation artifacts
├── semantic_contexts/      producer-owned cycle-shared semantic context CAS
├── operation_sets/         producer-owned semantic operation-set CAS
├── operation_batches/      producer-owned compiled operation-batch CAS
├── root_approval_plans/    immutable ordinary root-grant projections
├── root_grant_materializations/ plan-bound source/grant transactions
├── root_decision_seeds/ producer-owned compact approval seeds
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

A root grant, explicit grant composition, or lifecycle transition must trace to a
closed, immutable authority source rather than to prose or an inferred user
preference. The following schema-v2 shape is historical and is shown only for
interpretation:

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

Treat the example above as historical schema v2. Read
`integrity_status=verified` only under that schema. Never snapshot a new schema-v2
source, register a new root grant from one, or use one for a transition. Exact replay
of an already registered byte-identical grant remains available.

Registered recovery producers may emit schema v3, remove `integrity_status`, and add:

```json
{
  "schema_version": 3,
  "decision_binding": {"ref":"immutable decision JSON","sha256":"64 lowercase hex"},
  "decision_trust_class": "caller_asserted_exact_echo"
}
```

That compatibility trust class proves exact equality to supplied recovery bytes, not
user identity, host mediation, runtime attestation, or verified provenance.

Before snapshotting or using a schema-v3/v4 source prospectively, reopen the decision
binding and run its registered producer verifier. Schema-v4 root decisions must be
producer-CAS compact seeds, rehash their plan, and derive every source field and
per-grant mapping from that plan. Schema-v3 recovery decisions must rehash their
producer-owned recipe and derive every source field from its exact requirements.
Reject a generic, missing, copied, or self-fingerprinted decision binding.

Historical root plans may contain schema-v4 source approvals with
`decision_trust_class=caller_asserted_plan_decision`. Keep them readable for exact
existing-grant replay, but never prospectively issue a grant from them.

Current ordinary root plans emit schema-v5 source approvals with
`decision_trust_class=host_user_signed_exact_plan`. The schema-v3 compact decision
seed binds a verified authorization-evidence CAS object signed for the exact plan
and `manage-agent-authority/root-grant` audience by an active public key in the
skill-owned trust registry. The default registry is empty and therefore fails
closed. The CLI cannot select another registry, and unsigned approval flags,
timestamps, evidence IDs, workspace markers, or self-fingerprints cannot substitute
for the signed binding. Every current source binds the producer-CAS decision seed
and an exact per-grant projection list. Every projection binds its own
grant/lineage/replay IDs, request digest, capabilities, subject, operation, risk,
decision class, cardinality/budget, task/improvement/session scope, policy snapshot,
and deterministic materialization receipt ref. Aggregate coverage is only the exact
union of those projections and cannot authorize a cross-product recombination.

Schema-v2 sources remain structurally readable. No mutable workspace inventory,
timestamp, or self-fingerprint can make one prospective. Existing exact grants remain
usable and replayable; a missing grant ID under a schema-v2 source is read-only
exhaustion, not a materialization opportunity.

The `source_kind`/rank pairs are fixed: `platform_session_ceiling/S4`, `explicit_user_instruction/S3`, `delegated_policy_steward/S2`, and `cycle_coordination_grant/S1`. Require `decision_type=grant_authority`; another typed decision cannot be smuggled through this object. Root-grant issuance requires `authority.grant.issue` in the effective source approval. S1/S2 approvals require an immutable `delegation_binding`. Resolve that exact workspace-relative source-approval artifact, rehash its bytes, and require a strictly higher rank. Follow the lineage until S3 or S4 while rejecting a repeated approval/binding, a missing artifact, digest mismatch, equal/lower rank, or an approval that is not effective at the administrative action time. Every delegated approval must be an exact subset of its parent across capabilities, subjects, operations, grant IDs, request digests, lineage IDs, risk, decision classes, cardinalities, budget, and validity window; therefore the issuance capability must also be present in every parent. This rank-monotone, finite lineage prevents an S1/S2 label or self-reference from becoming a new root of trust. Root grant creation must occur during the complete approval-lineage window and may only narrow it.

For composition, additionally require capability `authority.grant.compose`, source
rank at least S3, the exact base-request digest in `request_digests`, and every
composed grant ID. Prospective composition accepts only a producer-owned
operation-batch binding plus the selected base-request digest, exact grant IDs, a
producer-verifiable typed-source binding, and an explicit time. The compiler reopens
and rehashes those inputs and derives the composition ID, idempotency key, grant
digests, closed receipt, and CAS path. Caller-authored full composition receipts are
not prospective inputs. For transition, require `authority.grant.transition`, exact
grant and lineage IDs, and a source rank above the holder. A source below the
original issuer is valid only when its immutable higher-rank delegation binding
covers that same transition capability, grant, lineage, and time window. These
typed-source checks are the root of trust for authority administration; do not
recursively ask the ordinary grant evaluator to authorize them.

## Grant and delegation

The following is the closed historical/read contract, not a prospective
caller-authored workflow input. Root and recovery materializers render root grants;
the delegation compiler renders child grants. `register-grant` accepts this full
object only when the same grant and state are already registered and the object is
an exact replay:

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

For prospective delegation, supply only the closed child semantics
`holder_rank`, `capabilities`, `subjects`, `operations`, `risk_ceiling`,
`decision_classes`, `cardinality`, `max_uses`, `expires_at`, `session_id`,
`task_id`, and `improvement_id`, together with parent grant ID and explicit
delegation time. The compiler derives every envelope, identity, parent/source/policy
binding, issuer, lineage, creation time, idempotency key, and artifact path. Require:

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

Release only with immutable evidence of `not_started` or `verified_no_effect`. For a registered owner operation, direct release is forbidden even when the caller supplies a valid-looking owner receipt. Use `settle`; its private release branch must reopen the canonical owner-validation receipt, validate the exact current pre-commit CAS state, and reproduce the fixed owner validator before accepting `verified_no_effect` or `unknown_effect`. For `unknown_effect`, preserve reserved use and set reservation state to `quarantined_unknown_effect`.

## Execution settlement and reconciliation

Prefer the registered owner-settlement path for every new supported operation. The static registry is keyed by exact `(skill_id, skill_version, operation_id, operation_version)` and names checked-in modules and fixed subcommands only; neither a workspace manifest nor an owner result may supply a callable, module, or raw argv. Resolve executable validator imports only from the installed skills root co-located with `manage-agent-authority`; reject any explicit skills root that resolves elsewhere. Before validator dispatch or lifecycle writes, acquire and hash the exact registered owner-result bytes under a 1 MiB limit. Capture the fixed subprocess through bounded pipes of 256 KiB stdout and 64 KiB stderr. Reopen a canonical owner-validation path only after its ref matches the exact content-addressed shape, then acquire, hash, and parse it once under a 256 KiB limit; registered release-evidence classification uses one exact bound acquisition capped at 1 MiB. These registered-path limits do not narrow the historical unregistered schema-v2 compatibility reader. The owner validator reopens the owner result, reservation, and pre-commit verification. Settlement requires its current validation first, then persists the replay-stable historical form as a closed `owner_validation_receipt` schema-v1. `confirmed_effect` consumes, `confirmed_no_effect` releases, and `unknown_effect` quarantines. A legacy opaque owner result can only produce `unknown_effect`.

Schema-v3 authority execution results add the exact immutable `owner_validation` binding to the existing fields:

```text
schema_version, artifact_kind=authority_execution_result, result_id,
reservation, pre_commit_verification, owner_result, effect_status=confirmed_effect,
owner_validation, subject_before, subject_after, expected_subject_after_sha256,
completed_at
```

Derive `result_id` and its `execution_results/<result_id>.json` path from the canonical body. Require `subject_after.sha256=expected_subject_after_sha256`; in schema v3 both are derived from the validated owner boundary rather than caller-authored expected JSON. Append-only current descendants remain valid when the owner proves the committed historical boundary. Preserve read validation of immutable schema-v2 execution results and use receipts.

Direct `consume` and caller-evidenced `release` reject a new settlement when the exact operation identity is present in the registered owner-validator table. Existing unregistered schema-v2 receipts remain readable and replayable, while operations without a registered validator retain the compatibility path until they are migrated.

Registry rollout is reader-first and never rewrites historical authority artifacts. Inventory and status may classify a pre-registry schema-v2 use or release receipt for a now-registered operation as historical, legacy-unattested evidence only after the normal closed path, digest, schema, deterministic-ID, reservation/decision, grant-accounting, and state-change validators pass and every current projection equals that receipt's exact terminal `after` object. This exception is observation-only. It does not authorize lifecycle replay, does not create schema-v3 evidence, and does not permit recovery to apply any `before -> after` edge. Recovery may skip such an already exact-settled receipt; a missing projection, `before` state, descendant instead of the exact terminal state, malformed binding, forged transition, or owner-validation-shaped evidence outside its canonical path fails closed before every write. Do not rewrite, delete, or backfill the historical receipt merely to satisfy the new registry.

Before replaying an existing schema-v3 registered settlement event or applying its pending projection intent, reopen its reservation and bound decision; require the canonical historical owner-validation receipt; validate the typed pre-commit reservation, reserved status, and exact before-version with `require_current_state=false`; rerun the co-located fixed owner validator; and require byte-for-byte-equivalent receipt content. Perform all of these checks before any state projection changes. A manually assembled chain that is structurally valid but unsupported by the fixed owner must leave every authority projection unchanged. A historical schema-v2 registered receipt is never an applicable recovery edge.

Prepare reconciliation evidence with `prepare-reconciliation-evidence`; do not hand-author paths or IDs. Settle a quarantined reservation only with the resulting closed `authority_effect_reconciliation_evidence` at its deterministic content-derived path. Bind its evidence ID, exact reservation, versioned operation, subject before, observed subject digest, outcome, observation time, and a typed owner result for a confirmed effect or confirmed no-effect. Require confirmed no-effect to preserve the exact subject-before digest. Reject arbitrary JSON, mismatched outcomes, stale observed subjects, or a missing typed owner result.

Write an immutable reconciliation receipt before applying its CAS projections:

- `confirmed_effect`: consume retained units and mark the reservation `consumed`; require the original exact pre-commit verification.
- `confirmed_no_effect`: release retained units and mark the reservation `released`.
- `still_unknown`: preserve units and advance the quarantined reservation version without changing its status.

Reconciliation settles evidence about an existing effect. It does not create a new approval for the original operation.

## Workflow status and resolution

`status` must include `evaluated_at`, an optional exact `request_sha256_filter`, grants, reservations, quarantines, pending versus superseded waits, verifications, typed execution results, use/release/reconciliation receipts, `workflow_state`, `should_prompt`, and one machine-readable next action. It must also include a `workflow_basis` carrying the exact decision, reservation and reservation-state, source-approval, settlement-receipt, and blocker bindings that justify the selected state. Accept an optional explicit RFC3339 `--at` for deterministic diagnosis and replay; otherwise capture the current UTC time once. Use only that captured time for the selected grant and every ancestor. Report each grant's raw state separately from `effective_usable`, effective status, and lineage blocker codes. A raw `active` grant is effectively unusable before its `not_before`, at or after its `expires_at`, or under any ancestor that is inactive, not yet active, or time-expired.

Before deriving workflow state or suppressing a prompt, validate the complete immutable lifecycle intent graph and prove every intent projection is at its exact `after` state or a validated descendant. Public closed validators must recheck deterministic identities, paths, bindings, and schemas for every historical decision, reservation, use/release/reconciliation receipt, grant, and current grant/reservation state. Historical inventory validation is reader-first: it validates the persisted decision body and its immutable bindings without requiring the current operation-manifest digest to remain equal, so a later skill release does not make valid history unreadable or require a history rewrite. Resolve the current manifest separately from the same explicit skills root used for evaluation (or the declared default), validate its closed contents and exact requested identity, and expose a missing, changed, unreadable, or identity-incompatible manifest as a current-candidacy blocker. Classify an affected old allowed decision as stale and an affected old approval wait as historical; neither may become `ready_to_reserve` or a live prompt. Add the same blocker to any affected reserved operation and select `reserved_authority_recovery`, never `ready_to_resume`. Reserve, verify, settlement replay, recovery application, and every new action keep strict current-manifest validation before any write. A malformed historical artifact or unsettled intent remains an error rather than evidence that a wait was superseded or an operation can resume. Reject a symlink at any component of every authority-owned decision, source-snapshot, grant, state, and receipt directory. Read status-visible JSON through a stable no-follow acquisition and report the digest of the same bytes that were parsed. Suppress an approval wait only when the same request digest has a validated reserved, consumed, released, or quarantined lifecycle artifact, a current exact allowed decision, or an exact usable/materializable source candidate.

Choose the public state using this precedence, after applying the optional exact request filter: `effect_reconciliation` for quarantine; `already_consumed` or `already_released` for settled lifecycle state; `ready_to_resume` for a reserved operation whose complete authority lineage remains usable; `reserved_authority_recovery` for a reserved operation blocked by selected or ancestor authority; `ready_to_reserve` for a current persisted exact allowed decision; `source_approval_ready_for_grant` for a usable or cleanly materializable exact source; `source_authority_defect` for an internally inconsistent source/grant projection; `source_authority_exhausted` for a source whose existing IDs cannot be reused; then `needs_user_approval` for a genuine remaining wait. Never let a lower-precedence stale wait override a higher-precedence lifecycle or authority fact.

A released reservation is terminal only when status correlates its exact reservation ref/digest with a release receipt whose effect status is `not_started` or `verified_no_effect`, or a reconciliation receipt whose outcome is `confirmed_no_effect`. Return that receipt in `workflow_basis.settlement_receipt`, use `already_released`, and never dispatch the operation again. Apply the corresponding exact-receipt rule to consumed state. A reserved operation whose selected grant or any ancestor is suspended, revoked, expired, not yet active, or otherwise unusable must remain reserved and return `reserved_authority_recovery`; do not call it resumable and do not automatically release units while effect certainty is unresolved.

For each exact covering source approval, classify every declared grant ID. A syntactically valid ID is materializable only if neither its immutable grant path nor mutable state path exists and neither path is a symlink. An existing ID is reusable only if the exact source-approval binding, operation, subject, capabilities, risk/decision/cardinality scope, lineage, time window, status, session, and remaining budget cover the request. A missing clean ID or at least one existing reusable ID yields `source_approval_ready_for_grant` with `materialize_grant` or `evaluate_existing_grant`. An orphan state, conflicting path, invalid ID, or impossible projection yields `source_authority_defect` and a system repair action. An exhausted, revoked, expired, suspended, not-yet-active, or source-binding-conflicted existing ID is not rematerializable: return `source_authority_exhausted`, set `should_prompt=false`, supersede the former generic wait, expose no active wait identity, derive a separate recovery identity from the exact request/source/state evidence, and route `prepare_exact_recovery_recipe`.

`prepare-source-recovery` is the only publisher for that repair step. It consumes the exact immutable exhausted decision binding and one explicit preparation time, revalidates the operation manifest and current exhausted evidence, and publishes at most one immutable recipe at the recovery-identity path. The closed recipe binds the old decision/source/grant/state evidence and contains six mutually distinct, old-ID-disjoint replacement identities: request, attempt, source approval, grant, lineage, and exact replay. It also contains the exact replacement request and digest, non-artifact source-approval requirements, non-artifact grant requirements, and a deterministic recovery approval projection that explicitly names `authority.grant.issue`. Exact replay returns the same artifact; different content at the same recovery path is a conflict.

The recipe has `authority_status=non_authoritative_prepare_only`. No nested recipe object may validate as `authority_source_approval` or `authority_grant`; it must not contain a precomputed source-snapshot binding, `integrity_status=verified`, or a substitute evidence ID. The actual explicit user decision must supply its own evidence ID, after which the source bytes are materialized and snapshotted and only that actual binding may complete a separately validated grant. Recipe publication does not express user approval, issue authority, consume a budget, or permit dispatch. Once the recipe validates, `status` and `resolve` replace the repair route with exactly one `needs_user_approval` wait and action `approve_exact_recovery_projection`, using the recipe projection and a new wait identity. Never expose the old approval projection as active and never reuse an exhausted request, attempt, source, grant, lineage, or replay ID.

`prepared_at` is T1 preparation time, not approval evidence. The actual explicit user decision establishes T2 with T2 >= T1. Source `not_before`, grant `not_before`, and grant `created_at` must be T2 or later under the normal source/grant validators. A replayed evaluation at T1 remains non-allowed; no recipe field may backdate prospective authority.

Prepare, status, and resolve expose the same non-authoritative `post_approval_handoff`. It names `materialize-approved-recovery` and binds `continuation_request_sha256`. The command requires a separately supplied, exact, immutable `authority_recovery_user_decision` echoing the complete approval projection and recipe binding; it cannot infer consent. It deterministically renders and validates source approval, source snapshot, grant, replacement request, and decision. After exact approval and materialization, consumers switch their status/resolve filter to the replacement digest; continued polling of the exhausted original digest is historical recovery observation, not forward progress.

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

The Python API permits `compile_operation(...,
trusted_request_idempotency_key=...)` only for a trusted owner renderer that is
replaying an exact immutable owner binding, such as a selected-successor bundle row.
The trusted key participates in the seed and compilation fingerprints and must satisfy
the ordinary request identifier validator. It is not a `SEED_KEYS` member, JSON seed
field, or CLI flag; reject a caller that attempts to place it in the semantic seed.
Without this Python-only argument, retain the ordinary fingerprint-derived request key.

The default command emits the full object for compatibility. `--publish` immutably writes it to `.task/authorization/operation_compilations/operation_compilation-<compilation_fingerprint>.json` and emits the compact `{ref, sha256, compilation_fingerprint}` receipt. Exact replay returns the same receipt; different bytes at that content-addressed path fail closed. Publication does not call source, grant, decision, reservation, or settlement issuance.

The result is `non_authoritative_compilation`: it never satisfies source approval, grant, reservation, or settlement. Seed-provided session and goal envelopes are asserted-untrusted narrowing inputs, not authority evidence; the compiler never expands them to fit a request. `evaluate` and `resolve` reopen the subject and manifest and run the independent request/context and authority validators before consuming it. Subject or manifest drift returns `recompile_required`; ambiguous manifest choices, malformed nested input, and any classification downgrade fail closed.

An owner-specific batch renderer may coordinate compilation with the existing evaluator
and lifecycle only when its input is closed and its authority boundary remains explicit.
For new work, the selected-successor renderer accepts one exact bundle and only the
producer-owned request/evaluation CAS bindings emitted together by
`selected-successor prepare-authority-context`, plus exactly one present/absent grant
choice for each of the three bundle operations. The context producer receives the
complete actual semantic session ceiling and goal-autonomy envelope, validates that the
bundle and current manifests fit within them, and never constructs or widens those
asserted scopes from request requirements. Both generated contexts are canonical,
bounded, content-addressed artifacts; canonical bytes copied to an arbitrary path are
not an equivalent input. There is no mutation-capable legacy-location opt-out.
Standalone legacy contexts may be inspected only through explicit historical
audit/recovery validation and cannot bootstrap a new decision or reservation.
The renderer derives three closed requests using
the bundle's exact operation, subject, and idempotency-key rows. It must not create a
source approval or grant, union grants, or substitute a selection artifact for
authority. It must not derive an asserted session ceiling or goal envelope from those
requirements.
Bind one exact semantic `actor_rank` in the self-sealed request context and require
every present grant's `holder_rank` to equal it. Never derive actor identity from a
manifest `source_rank_floor`, from absence, or from the strongest available row.

Run the canonical evaluator independently for all three requests. The renderer may
publish decisions, reservations, and `pre_commit` verifications only after all results
are `allowed` and every supplied grant binding is exact, current, and selected by the
evaluator. Publish a canonical decision only through
`manage_agent_authority.decision_publication.evaluate_and_publish(...)` and publish
the typed pre-commit artifact only through
`manage_agent_authority.verification_publication.verify_and_publish_precommit(...)`.
The fixed `verify_and_publish_predispatch(...)` helper remains compatibility-only for
the existing `verify --stage pre_dispatch` CLI. The renderer then publishes a compact
packet binding the three request/decision/reservation/verification/version chains. That
packet is transport and replay evidence; it is not a fourth decision and cannot broaden
or repair one chain.

Treat genuine no-covering authority or any other non-allowed evaluator result as an
atomic batch stop. Emit one deterministic minimum-scope approval projection with the
exact non-authoritative compilation bindings and publish zero decisions, reservations,
and verifications. An absent declaration that canonical evaluation resolves to allowed,
or a supplied grant that is not exactly selected, is an input conflict rather than an
approval wait. Do not publish the allowed prefix of a mixed result, fabricate a dummy
grant, or turn a request context into source approval. Bind the three manifest digests
into the input index and pre-index packet locator; preserve any custom skills root in
generated replay argv. Exact input replay may return the same packet or projection. Drift in a
bundle, context, subject, manifest, grant, or grant state requires reevaluation.

## Shared context, batches, and root approval

### Legacy implement-seed migration

Treat a legacy
`.task/cycle/<cycle-id>/authority/implement-seed.json` as read-only historical
semantic input, never as a producer artifact or an authorization decision. Migrate
its fields through the compiler-first pipeline as follows:

| Legacy field | Compiler-first destination |
|---|---|
| `actor_rank` | `compile-semantic-context` input `actor_rank` |
| `context` | Rename to the shared semantic input `request_context`; the compiler reopens and hashes every required evidence ref |
| `session_ceiling` | Shared semantic input `session_ceiling` |
| `goal_autonomy_envelope` | Shared semantic input `goal_autonomy_envelope`; the compiler replaces `source_ref` with its exact binding |
| `skill_id`, `operation_id`, `subject` | One compact `publish-operation-set` row |
| `scope`, `cardinality_requested`, `use_budget_requested`, `reservation_units`, `composition_receipt` | The same compact operation-set row |
| `intent_type` | Drop it; batch compilation fixes the intent to `grant_authority` |
| Any caller classification | Put only justified upward overrides under `classification`; omit it to use the current manifest |

Bind the canonical `.task/cycle/<cycle-id>/initialization.json` when compiling the
shared context. The compiler derives cycle and task identity from that binding.
Legacy `scope.cycle_id` and `scope.task_id` may be carried only as exact compact
scope echoes and must match the derived identity; they cannot establish it.

Do not copy, rename, or re-publish the legacy JSON into a CAS directory. Extract the
two bounded semantic inputs, then run `compile-semantic-context`,
`publish-operation-set`, and `compile-operation-batch`. The producers derive
skill/operation versions, fixed intent, schema and provenance fields, current
manifest classifications and digest, subject/evidence/goal-source digests, request
and idempotency identities, fingerprints, bindings, and canonical CAS paths. A
legacy seed remains useful as contemporaneous evidence only; neither its filename
nor its former full-object shape grants authority.

Use `compile-semantic-context` for every new cycle, including a one-operation cycle.
Require the exact canonical `.task/cycle/<cycle-id>/initialization.json` binding and
derive both cycle and task ID from it. Reject an arbitrary-path copy or a caller
cycle/task echo that conflicts. Accept one closed semantic input containing `actor_rank`,
`request_context`, `session_ceiling`, and `goal_autonomy_envelope`. Let the compiler
hash evidence and the goal source, normalize ordering, add schema/provenance fields,
derive the fingerprint, and publish the result under
`.task/authorization/semantic_contexts/sha256/<fingerprint>.json`. Enforce a 64 KiB
canonical payload bound. The artifact is non-authoritative.

Use `publish-operation-set` to normalize a non-empty semantic JSON list into
`.task/authorization/operation_sets/sha256/`. Use `compile-operation-batch` only with
that exact operation-set binding and the shared-context binding. Each seed may contain
only `skill_id`, `operation_id`, subject/revision, scope, cardinality/budgets,
upward-only classification, and composition receipt. Derive skill/operation versions
from the current manifest and fix intent to `grant_authority`. Reject an arbitrary copied set,
repeated context/ceiling fields, cross-cycle/task scope, duplicate compiled identity,
stale evidence, stale subjects, and stale manifests. Publish each ordinary
operation compilation first, then one batch that references those producer bindings
under `.task/authorization/operation_batches/sha256/`. A copied context, compilation,
batch, or plan at an arbitrary path is not producer output even when its bytes match.
`evaluate|resolve --compiled-operation` accepts only the compact published binding,
reopens the canonical compilation filename under its producer CAS, and revalidates
one bounded regular-file payload against its digest, JSON contract, filename, and
fingerprint before extracting request/context. A full compilation path or JSON body
is not a compact binding and cannot bypass provenance.
Treat the operation input as a true set: sort by canonical bytes, reject duplicates,
cap it at 128 operations and 256 KiB, and cap the compiled batch at 2 MiB. Validation
must recompile every row from the exact set/context/timestamp, including defaults,
upward classification, and fixed provenance.

Use `prepare-root-approval` only with a producer batch and the exact policy snapshot
selected by `.task/authorization/state/current_policy.json`. Reject a stale but
otherwise valid snapshot. Accept closed grant semantics:

```json
{
  "source_kind": "explicit_user_instruction",
  "holder_rank": "S0",
  "expires_at": "RFC3339",
  "session_id": "exact ID or null"
}
```

Require `explicit_user_instruction/S3`, a lower holder rank matching every compiled
actor, and an expiry after preparation. The ordinary plan-bound path must reject
`platform_session_ceiling/S4`; S4 requires a distinct platform-owned producer and
attestation. Derive cardinality, use budget, task/improvement scope,
capabilities, subject, operation, risk, and decision class separately from each
compilation. Emit one grant projection and unique grant/lineage/replay IDs per
compilation. Never create one grant from the batch-wide capability × subject ×
operation union. The schema-v5 source preserves the exact per-grant mapping in
addition to its aggregate coverage. The plan creates no authority.
Treat aggregate `grant_ids` and `lineage_ids` as exact sets: the schema-v5 source
canonicalizes them lexicographically before source-decision comparison. The signed
plan may retain producer request order, but order alone neither widens authority nor
invalidates identical membership; the request-bound grant projections remain the
mapping authority.

`publish-root-authorization-evidence` accepts a closed host/user-signed envelope,
verifies its exact plan/audience/window and RSA/SHA-256 signature against an active
skill-owned trust anchor, and publishes the verified bytes in producer CAS.
`compile-root-decision-seed` accepts only that exact evidence binding plus the same
plan, derives the approval/time/evidence ID, canonicalizes the closed schema-v3 seed,
and publishes it under
`.task/authorization/root_decision_seeds/sha256/`; stdout contains only its compact
binding. `materialize-plan-bound-root-grant` accepts only that producer-CAS binding
and the same exact plan. It never accepts hand-authored decision JSON or a caller
projection echo.

The materializer revalidates the batch, subjects, current manifests, policy snapshot,
plan, and decision seed before writes. It preflights every target, publishes an
immutable write-ahead prepare, stages every grant as `draft`, activates the exact
states, and publishes the completion receipt. A schema-v3 root grant carries its
deterministic receipt ref; all loaders project it as `draft` until that exact receipt
and full signed chain verifies. The transaction writer accepts only plan and
decision-seed CAS bindings; inside its lock it boundedly reopens the exact plan,
host/user-signed evidence, and seed, then deterministically re-derives source
approval, capability coverage, source binding, per-request grants, and
materialization identity. Caller-supplied source/grant bytes and importable
producer-capability objects are not authority. Before activation it reopens every
staged immutable byte. Receipt visibility independently performs bounded reads,
repeats that derivation, and requires exact prepare, source materialization,
source snapshot/metadata, all grant artifacts, and receipt bytes. Thus a crash
between grant activations or a structurally resealed forged transaction exposes no
usable partial authority, and exact replay completes the transaction.

## CLI surface

Invoke through:

```bash
PYTHONPATH="<skills-root>/orchestrate-task-cycle/scripts" \
  python3 -P -m orchestrate_task_cycle workflow authority <command> ...
```

Use:

- `compile-semantic-context` for the cycle-shared producer CAS context;
- `publish-operation-set` for one producer-owned semantic operation set;
- `compile-operation-batch` for one or more operation seeds;
- `compile-operation` only for historical compatibility or contract diagnostics;
- `prepare-root-approval`, `publish-root-authorization-evidence`,
  `compile-root-decision-seed`, and
  `materialize-plan-bound-root-grant` for ordinary root grants;
- owner batch renderers such as `selected-successor prepare-authority` for closed
  compile/evaluate/reserve/verify orchestration over explicit existing grants;
- `snapshot-policy`, `snapshot-source`;
- `delegate` and `compose` for compiler-owned prospective child/composition
  artifacts; `register-grant` only for exact already-registered replay;
- `evaluate`, `resolve`, `prepare-source-recovery`, `reserve`, `verify`, `consume`, `release`, `prepare-reconciliation-evidence`, `reconcile`;
- `transition`, `status`.

Supply all times explicitly as RFC3339 for reproducible artifacts. Supply all CAS versions explicitly for mutable transitions.

## Migration

Do not rewrite a legacy receipt or grant in place.

1. Classify it as verified legacy, partial historical, invalid, or unclassified.
2. Preserve v1 current-file digest semantics when validating a v1 receipt.
3. Preserve schema-v2 and caller-asserted schema-v4 source approvals as read-only
   historical artifacts. Ordinary roots use schema v5 with signed exact-plan
   schema-v3 decision seeds; registered recovery compatibility may use schema-v3
   exact-echo source decisions.
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
