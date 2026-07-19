# Task-doctor workflow coordination

## Contents

- Ownership and user-interaction invariant
- Compiler-first preparation and bounded advance
- Exact owner-plan and workflow-plan contract
- Declared authorization and consolidated review
- Authority materialization bridge
- Reservation resolution and dispatch
- Typed owner completion and settlement
- Resume, already-settled recovery, and replay
- State and reporting contract

## Ownership and user-interaction invariant

`$task-doctor` is the only user-interaction owner for one doctoring workflow. Child
owners return machine states and artifacts; they do not ask the user for authority.
Group genuinely missing decisions into one review, while preserving one exact v2
request, grant, reservation, pre-commit verification, and settlement per governed
owner effect.

Keep truth ownership separate:

- `$manage-agent-authority` owns source snapshots, grants, decisions, reservations,
  verification, use/release/reconciliation receipts, effective state, and quarantine.
- Each artifact skill owns its immutable owner plan and typed execution result.
- `$task-doctor` owns only dependency ordering, the immutable coordination journal,
  one consolidated interaction, and exact result projection.
- The journal is saga evidence. It is neither permission nor cross-owner atomicity.

Never replace exact operation authority with a wildcard, standing lease, broad
composition, or reusable approval budget. Approval, goal ratification, risk/cost
acceptance, external input, and design selection remain separate typed decisions.

## Compiler-first preparation and bounded advance

Prefer the task-doctor compiler surface over hand-authoring the full workflow plan.
The compact intent contains semantic choices and content-addressed owner-plan or
compiled-operation bindings; the compiler derives request digests, operation order,
dependency edges, materialization identities, exact review scope, and the normalized
workflow-plan envelope. It remains non-authoritative: compilation never creates a
user decision, source approval, grant, reservation, owner result, or settlement.
The `compiled_operation` field accepts an inline compilation, an exact
`{ref, sha256}` binding, or the unmodified
`{ref, sha256, compilation_fingerprint}` receipt returned by authority
`compile-operation --publish`; the latter also cross-checks the published object's
internal fingerprint.

Use the package entry point directly or route it through the orchestrator's
`workflow task-doctor` launcher. The representative sequence is:

```bash
python3 -m task_doctor_workflow_lib compile-intent \
  --root . --intent compact-intent.json --at '<rfc3339>'
python3 -m task_doctor_workflow_lib prepare-intent \
  --root . --intent compact-intent.json --at '<rfc3339>'
```

`compile-intent` is read-only. `prepare-intent` publishes either one immutable
workflow plan when every exact decision source already exists, or one immutable,
content-addressed consolidated review containing only uncovered operations. Compact
output is the default; use `--detail full` only for diagnostics. Replaying identical
inputs returns the same review or plan identity instead of rotating IDs.

After the actual user decision has been represented by pre-existing closed authority
source-approval snapshots, accept the exact review binding:

```bash
python3 -m task_doctor_workflow_lib accept-review \
  --root . --review-ref '<workspace-ref>' --review-sha256 '<sha256>' \
  --decision review-decision.json
```

The decision file is a binding to an actual decision and its typed source snapshots;
it is not permission by itself. The command must reject a missing snapshot, an
uncovered or extra operation, a stale review, a pre-decision source, a source whose
evidence/request/grant/lineage scope differs, or any attempt to manufacture approval
from the review. The accepted plan uses schema-v2 reservation windows. It fixes the
post-decision source/grant/evaluation identities while leaving `reserved_at` to the
later dependency-ready instant. Legacy schema-v1 plans retain their exact planned
`reserved_at` and remain readable without rewriting.

For an existing journal, derive a small resolution bundle and advance only across
deterministic system-owned transitions:

```bash
python3 -m task_doctor_workflow_lib build-resolution-bundle \
  --root . --workflow-id '<workflow-id>' --publish
python3 -m task_doctor_workflow_lib advance \
  --root . --workflow-id '<workflow-id>' --max-steps 8
python3 -m task_doctor_workflow_lib advance \
  --root . --workflow-id '<workflow-id>' --max-steps 8 --apply --at '<rfc3339>'
```

Dry-run is the default. Mutating advance requires explicit `--apply` and `--at`, uses
the already verified source snapshot, registers/evaluates the exact grant, and
reserves only a dependency-ready governed operation. It must stop on owner/model
judgment, genuine approval, goal truth, external input, risk/cost, design selection,
effect settlement, stale evidence, or an exhausted step budget. A repeated state
fingerprint is `no_progress_replay`, not an excuse to regenerate JSON or ask again.

## Exact owner-plan and workflow-plan contract

Prepare every owner effect before the first canonical lifecycle mutation. Publish
the exact owner plan as a regular non-symlink workspace JSON file. Bind its raw file
bytes with `plan_binding.ref` and `plan_binding.sha256`. The workflow helper parses
that file and requires its JSON value to equal the embedded `plan`; it uses the raw
file digest as `plan_sha256`. Do not substitute an owner's internal body digest for
the exact file digest.

Use the owner's real plan schema:

- `$manage-external-advice` intake uses `plan_kind=external_advice_intake_plan`.
- `$manage-task-state-index` batch projection uses
  `plan_kind=task_state_transition_plan`, a nonempty ordered `events` list, and the
  owner's ledger/Markdown/artifact-anchor contracts. Do not use a coordinator-only
  abstract index-plan surrogate.
- A task-scope request binds the closed immutable `task_transition_plan`, including
  exact before/prospective/after and deterministic predecessor-archive fields. A
  task-pack transition is unsupported and must fail closed.

Separate `workflow_role` from authority `effect_class`. `workflow_role` expresses
coordination semantics such as `external_advice_intake`, `task_scope_transition`,
or `task_index_transition`. `effect_class` must be the exact
value declared by the owner's authority manifest. A coordinator-only manifest
operation cannot masquerade as a task or index mutation by changing a label.

The following is a non-executable structural excerpt. Its abbreviated owner plan
and v2 request placeholders must be replaced with their complete closed values;
they are explanatory, not wildcards.

```json
{
  "schema_version": 2,
  "execution_mode": "execute_with_declared_authorization",
  "complete_effect_inventory": true,
  "max_user_approval_interactions": 0,
  "authorization_basis": {
    "schema_version": 1,
    "basis_kind": "task_doctor_declared_authorization",
    "approvals": [
      {
        "operation_id": "task-op-id",
        "source_approval": {
          "ref": ".task/authorization/source_snapshots/source_approval-<sha256>.json",
          "sha256": "<sha256>"
        }
      }
    ]
  },
  "authorized_local_effects": ["retarget_or_replace_task"],
  "excluded_effects": [
    "implementation",
    "goal_truth_change",
    "risk_acceptance",
    "external_input",
    "design_selection",
    "remote_push",
    "destructive_change"
  ],
  "git_finalization": "deferred",
  "task_index_transition": {
    "status": "planned",
    "operation_id": "index-op-id"
  },
  "operations": [
    {
      "operation_id": "task-op-id",
      "workflow_role": "task_scope_transition",
      "owner_skill": "$task-doctor",
      "effect_class": "retarget_or_replace_task",
      "effect_summary": "Publish the exact prepared task transition.",
      "required": true,
      "dependencies": [],
      "plan": {"plan_kind": "task_transition_plan", "transition_id": "id-1"},
      "plan_binding": {
        "ref": ".task/task_doctor/transition-plans/id-1.json",
        "sha256": "<exact-file-sha256>"
      },
      "authority": {
        "applicability": "required",
        "request": {"schema_version": 2, "request_kind": "authority_operation"},
        "materialization": {
          "evaluation_context": {
            "schema_version": 2,
            "context_kind": "authority_evaluation",
            "session_ceiling": {},
            "goal_autonomy_envelope": {}
          },
          "evaluated_at": "<rfc3339>",
          "policy_snapshot": {
            "ref": ".task/authorization/policy_snapshots/policy-<sha256>.md",
            "sha256": "<sha256>"
          },
          "grant_spec": {
            "grant_id": "grant-id",
            "lineage_id": "lineage-id",
            "holder_rank": "S0",
            "cardinality": "single_use",
            "max_uses": 1,
            "not_before": "<rfc3339>",
            "expires_at": "<rfc3339>",
            "idempotency_key": "grant-key-id"
          },
          "reservation": {
            "not_before": "<rfc3339>",
            "expires_at": "<rfc3339>",
            "idempotency_key": "reservation-key-id"
          }
        }
      }
    }
  ],
  "reporting": {"detail": "concise", "language": "auto"}
}
```

Apply these invariants:

- Topologically order operations and list every dependency.
- Set `complete_effect_inventory=true` only when all required effects are fixed.
- Use one final `workflow_role=task_index_transition` when task scope changes.
- Make that index operation depend on every earlier supported lifecycle effect.
- Set `task_index_transition.status=not_applicable` only when there is no
  task-scope transition and no advice effect requires reconciliation against an
  existing live task-index store.
- Keep `git_finalization` at `deferred` or `not_applicable`; no closed Git owner
  adapter is currently registered.
- A plan-declared runtime state such as `ready_to_resume`, `projection_repair`, or
  `already_settled` is invalid. Those states require live v2 evidence.
- An authority-free operation must bind an exact owner manifest operation whose
  `authority_applicability` and `authorization_mechanism` are both `none`; it starts
  as `authority_not_applicable` and carries no reservation evidence.
- Any changed operation, owner plan bytes, subject, dependency, manifest digest,
  effect, risk, context, grant recipe, or reservation key requires a new workflow.

## Declared authorization and consolidated review

Use `execute_with_declared_authorization` only when an initiating user decision
already covers every governed local effect. Set the interaction budget to zero.
`authorization_basis` is not a free-form evidence binding. It is a closed mapping
from every governed workflow operation to the authority owner's immutable,
content-addressed source-approval snapshot.

The helper requires each snapshot to:

- use `.task/authorization/source_snapshots/source_approval-<digest>.json`;
- have matching snapshot metadata;
- parse as a closed v2 `authority_source_approval`;
- represent verified `explicit_user_instruction` / `S3` / `grant_authority`;
- bind the exact request digest, subject, owner operation, capability set, decision
  class, risk ceiling, cardinality, use budget, grant ID, and lineage ID;
- be effective at the planned evaluation time.

`already_covered` therefore means only “the exact decision source exists.” It is
not dispatchable. Materialize exact grants and decisions without another prompt,
but create and bind a reservation only when that operation's dependencies are
terminal and its public owner verifier reports a new `ready` dispatch.

Use `consolidated_review` when one or more exact local effects genuinely lack that
decision source. Set the interaction budget to one, prepare every downstream item
first, display one stable approval bundle, snapshot the resulting typed user
decision through `$manage-agent-authority`, and materialize each exact operation's
source/grant contract. Reserve each operation just in time at its dependency-ready
frontier.
The user approves one presentation; the system still retains separate grants,
reservations, and settlements.

Before returning that first presentation, persist its exact prompt-required operation
inventory as the journal's single `semantic_approval_scope_bound` event. Its bundle ID
and fingerprint are recomputed from the immutable plan during journal validation.
`resolve-all` accepts exactly that durable scope even after the approved source
snapshots make live status prompt-free. A caller cannot omit one displayed row, and a
row that was already covered when the bundle was displayed cannot be inserted into the
semantic mutation.

A scope-excluded row may still retain the journal classification
`needs_user_approval` while public authority status proves prompt-free progress. In
that case status exposes an `authority_materialization_bundle`, not an
`approval_bundle` or wait. A system-only `resolve-all` may bind that row's exact source
snapshot as `already_covered`, or its current dependency-ready reservation as
`ready_to_resume`, with `user_interaction=false`. This transition is checked against
the current public live projection and cannot consume another review interaction.
If that row later loses its covering authority and becomes a genuine approval wait,
the immutable old scope cannot expand: project `plan_changed` / `prepare_new_plan`
without prompting.

Keep semantic acceptance and reservation resolution as two distinct mutations:

1. The one user-interaction bundle covers every prompt-required governed operation in
   the journal-bound semantic scope, including downstream rows whose dependencies are
   incomplete. Validate those owner plans structurally. Each resolution is
   `already_covered` and binds that operation's exact immutable source-approval
   snapshot. It binds no reservation and increments `approval_interactions_used`
   exactly once. A live-covered row outside the displayed scope keeps its existing
   journal state and evidence.
2. Later system-only bundles include only the dependency-complete, public-owner
   `ready` frontier. Each resolution is `ready_to_resume` and binds one current
   exact reservation. These bundles never increment the interaction counter.

Do not combine the source snapshot and reservation into one early downstream
resolution. A semantic decision may cover the full chain, but authority budget is
reserved only when the corresponding effect becomes dispatchable.

## Authority materialization bridge

The `authority_materialization_bundle` is an executable bridge, not a prose hint.
It exposes only the current dependency-complete, public-owner-`ready` frontier. For
every included governed item it exposes:

- the exact normalized v2 request and request digest;
- exact subject ref, kind, digest, and revision;
- owner operation-manifest binding;
- exact evaluation context, context digest, and evaluation time;
- exact policy snapshot;
- declared source-approval snapshot, or closed S3 source-approval requirements for
  consolidated review;
- a full deterministic `register_grant_recipe` derived from the request and fixed
  grant specification;
- exact `reserve` timestamp and idempotency key.

Materialize in this order:

```text
typed user decision
  -> snapshot_file(kind=source_approval)
  -> register_grant(exact register_grant_recipe with snapshot binding)
  -> evaluate(exact request, exact context, exact evaluated_at)
  -> persist immutable allowed decision
  -> wait until dependencies are terminal and owner apply phase is ready
  -> reserve(exact decision binding, exact reserved_at, exact idempotency_key)
  -> resolve-all(exact reservation file bindings)
```

For declared authorization, `register_grant_recipe.source_approval` is already an
exact binding. For consolidated review it is null until the one user decision is
captured; fill only that field from the newly produced content-addressed snapshot
and require it to meet `source_approval_requirements`. Do not alter any request,
subject, operation, grant, context, policy, time, or reservation field while doing
so.

## Reservation resolution and dispatch

Run the prompt-free helper through its stable facade:

```bash
python3 <skill-dir>/scripts/task_doctor_workflow.py prepare \
  --root . --plan <exact-workflow-plan.json>

python3 <skill-dir>/scripts/task_doctor_workflow.py status \
  --root . --workflow-id <tdw-id>

python3 <skill-dir>/scripts/task_doctor_workflow.py resolve-all \
  --root . --workflow-id <tdw-id> --expected-revision <n> \
  --bundle-ref <binding-ref> --bundle-sha256 <binding-sha256>

python3 <skill-dir>/scripts/task_doctor_workflow.py apply \
  --root . --workflow-id <tdw-id> --expected-revision <n>
```

`ready_to_resume` and `projection_repair` accept only the deterministic v2
`authority_reservation` file for that operation. The helper uses the authority
owner's public validators and additionally requires:

- exact request and request digest;
- exact evaluation context and time;
- exact owner operation-manifest binding;
- exact grant recipe and source/policy bindings;
- exact reservation timestamp and idempotency key;
- current reservation projection equal to `reserved`, version `0`, with the
  reservation ID as its last event.

An arbitrary JSON file, a reservation for another owner/operation/request/plan, or
a consumed, released, quarantined, stale, or superseded reservation fails closed.
`apply` repeats this current-state verification immediately before dispatch. It
only returns the exact owner dispatch; it never executes a command itself.

For a dependency-blocked index operation, use public `phase=planning`. Accept
`materializing` only while different dependency artifacts have independently moved
from their before digests to their exact expected digests. It is internal progress,
not no effect, not dispatchable, and not a prompt. After dependencies are terminal,
use `phase=apply` and require `ready` before owner dispatch.

Retain the public status instead of reducing verification to pass/fail:

| Public owner status | Coordinator route | User prompt |
|---|---|---|
| `ready` | Resolve exact authority and dispatch once | Only if exact source authority is truly absent |
| `materializing` | Internal wait and recheck | Never |
| `already_applied` | Effect/authority reconciliation | Never |
| `settled_no_effect` | Reopen owner receipt, release or recover completion | Never |
| `recovery_required` | Owner forward recovery | Never |
| `stale` | Cancel or replace the never-dispatched plan | Never |
| `conflict` | Contract repair/fail-close | Never |

If a required upstream operation settles `confirmed_no_effect`, a speculative final
index plan anchored to that operation is no longer dispatchable. Publish an exact
dependency-cancellation intent and receipt, mark the index row `plan_changed`, and
prepare a replacement index plan before any new authority prompt. If an old workflow
already reserved that never-dispatched index operation, release only that exact
reservation with the cancellation intent as `not_started` evidence. This path is
available only when the public index verifier reports `stale` and explicitly proves
no plan intent, effect, receipt, or historical completion. `materializing`,
`already_applied`, `settled_no_effect`, `recovery_required`, and `conflict` retain
their typed routes and must never be cancelled as not started. This is a
coordinator cancellation, not an index-owner no-effect outcome; never create a fake
index no-effect receipt or consume its reservation.

For semantic acceptance, use `from_classification=needs_user_approval`,
`user_interaction=true`, and resolve every item in the durable
`semantic_approval_scope_bound` inventory to `already_covered` with its
operation-exact source snapshot. Do not add a live-covered row that the displayed
bundle excluded. For reservation resolution, use the shape below and include every
currently dependency-complete, public-owner-`ready` operation carrying
`already_covered` exactly once. Do not include a downstream index merely because its
source decision or grant is already materializable.

```json
{
  "kind": "task_doctor_authority_resolution_bundle",
  "schema_version": 1,
  "workflow_id": "tdw-id",
  "plan_sha256": "<workflow-plan-sha256>",
  "from_classification": "already_covered",
  "user_interaction": false,
  "resolutions": [
    {
      "operation_id": "task-op-id",
      "classification": "ready_to_resume",
      "evidence_ref": ".task/authorization/reservations/authz-id.json",
      "evidence_sha256": "<sha256>"
    }
  ]
}
```

Use `user_interaction=true` only for the semantic-acceptance bundle whose
`from_classification` is `needs_user_approval`; its item classification is
`already_covered`, never `ready_to_resume`. An exact replay of either bundle is a
zero-write replay.
The prompt-free live-progress bridge may also retain
`from_classification=needs_user_approval`, but it always uses
`user_interaction=false`, is exposed as `authority_bundle`, and must match the current
public live resolution for every included operation.

## Typed owner completion and settlement

Do not create a circular artifact in which the authority receipt and owner result
contain each other. Use three layers:

1. the artifact owner's actual result;
2. a closed `task_doctor_owner_effect_result` binding that artifact to the workflow,
   operation, owner skill, exact owner-plan file digest, and confirmed effect state;
3. a closed `task_doctor_owner_completion` that binds the effect result and actual
   authority settlement receipt.

Owner-effect binding:

```json
{
  "schema_version": 1,
  "artifact_kind": "task_doctor_owner_effect_result",
  "workflow_id": "tdw-id",
  "operation_id": "task-op-id",
  "owner_skill": "task-doctor",
  "plan_sha256": "<exact-owner-plan-file-sha256>",
  "effect_status": "confirmed_effect",
  "owner_artifact": {"ref": "<exact-public-owner-receipt-ref>", "sha256": "<sha256>"}
}
```

Completion binding:

```json
{
  "schema_version": 1,
  "artifact_kind": "task_doctor_owner_completion",
  "workflow_id": "tdw-id",
  "operation_id": "task-op-id",
  "plan_sha256": "<exact-owner-plan-file-sha256>",
  "outcome": "completed",
  "owner_result": {"ref": "<effect-result-ref>", "sha256": "<sha256>"},
  "authority_settlement": {
    "status": "settled",
    "receipt": {
      "ref": ".task/authorization/use_receipts/authu-id.json",
      "sha256": "<sha256>"
    }
  }
}
```

The helper accepts only these actual v2 settlements:

- `authority_use_receipt` for `confirmed_effect`, with its typed execution result
  and `owner_execution_result` bound to the exact owner-effect result;
- `authority_release_receipt` for `confirmed_no_effect`, only when
  `effect_status=verified_no_effect`, `release_applied=true`, and
  `no_effect_evidence` binds the exact owner-effect result;
- `authority_reconciliation_receipt` for a quarantined operation, with matching
  exact outcome and reconciliation evidence owner-result binding.

The receipt must bind the same operation reservation, and the current reservation
state must show that receipt as the last event with status `consumed` or `released`.
A regular JSON file with plausible fields is not a settlement.

A release with `effect_status=not_started` proves only that reserved budget was
returned before dispatch. It is not an owner no-effect result and must never route
to `recover_owner_completion`. Project `plan_changed` /
`replanning_required`, prepare a new immutable plan or fresh authority recipe, and
retain `should_prompt=false`. Only `verified_no_effect` or reconciled
`confirmed_no_effect` with the exact typed owner result may recover completion.

Record `completed` for a confirmed effect. Record `confirmed_no_effect` (legacy
input name `no_effect` is accepted only with the same typed proof) for verified no
effect. Both are terminal for that operation and advance to the next dependency;
never redispatch a verified duplicate/no-op merely because its reservation was
released. An authority-free owner completion uses the same two result layers but
sets `authority_settlement={"status":"not_applicable"}`.

For every supported owner, `confirmed_no_effect` requires its public verifier to
return `settled_no_effect`, `no_effect_verified=true`, and the exact immutable
no-effect receipt ref/file digest. A still-ready plan binding is not owner evidence.
For task scope, `confirmed_effect` binds an immutable successor-task snapshot and
the predecessor archive when present; later legitimate canonical task transitions
may make `current_projection_healthy=false` without invalidating historical
completion.

An optional governed operation may be recorded as `skip` only after the owner has
proved `confirmed_no_effect` and the exact reservation has a matching
`verified_no_effect` release (or equivalent reconciliation receipt). A free-form
skip note is not a settlement. Likewise, once dispatch has begun,
`plan_changed`, `blocked_by_defect`, and a request to repair a projection may
replace the pending operation only after verified no-effect settlement. Route an
uncertain effect to `unknown_effect` and quarantine; settle a confirmed effect as
completed before preparing a new immutable plan. These rules prevent a workflow
label from silently abandoning a live or possibly consumed reservation.

## Resume, already-settled recovery, and replay

Run `status` and then `resume` with the observed revision after interruption. An
unchanged resume is zero-write. An interrupted `in_progress` operation becomes
`effect_reconciliation`; it is not sent back to approval or blind re-execution.

If authority status reports that the exact operation is already consumed or
released, locate its actual use/release/reconciliation receipt and bound owner
result. Resolve the operation as `already_settled` with the closed completion
binding. The helper revalidates the exact request, plan, reservation, receipt,
owner result, effect outcome, and current settled state, then materializes the
journal operation directly as terminal. This prevents recreated workflows from
looping into a new reservation or duplicate effect.

For an interrupted unknown effect, use only authority-owned reconciliation
evidence and receipts. `confirmed_effect` and `confirmed_no_effect` require the same
closed completion contract and become terminal. `still_unknown` remains recovery
required and must not be re-executed or re-prompted. A changed immutable plan starts
a new workflow; a workflow defect is repaired internally.

## State and reporting contract

Keep these states distinct:

| Classification | Meaning | User action |
|---|---|---|
| `authority_not_applicable` | Owner manifest closes authority as none | None |
| `needs_user_approval` | Exact decision source is absent | Approve once |
| `already_covered` | Exact decision source exists; materialization remains | None |
| `ready_to_resume` | Exact live reservation is bound and current | None |
| `reserved_authority_recovery` | Current reservation needs system repair | None |
| `already_settled` | Exact prior effect/no-effect settlement is terminal | None |
| `projection_repair` | Exact reservation permits the bounded projection repair | None |
| `effect_reconciliation` | A dispatch may have changed state | None by default |
| `plan_changed` | Target/effect/risk/design changed | Prepare a new exact plan |
| `blocked_by_defect` | Workflow or owner contract is defective | Repair internally |

If a fixed exact source grant ID is exhausted, revoked, expired, or otherwise
unmaterializable, project `plan_changed` / `replanning_required` with the system
action `prepare_new_plan`. Build a new immutable coordination plan with distinct
request, grant, lineage, and reservation identities before asking the user anything.
Reapproval cannot repair a stale plan that hard-codes an unusable grant ID.
The same route applies if the authority owner later exposes
`needs_user_approval` / `approve_exact_recovery_projection` for a replacement-source
recipe. That recovery projection belongs to a new authority identity set; the old
task-doctor plan must not expose it as its ordinary approval bundle, increment its
interaction counter, or adopt the replacement IDs in place.

Use the stable bundle fingerprint as the wait identity. Unchanged plan, resolution,
settlement, recovery, result, and resume replays must not create another prompt,
spend another grant, or increment the journal revision.

Report only outcome, workflow ID/state/classification, changed artifacts,
`user_action: none|approve|choose|supply_input`, and one exact next action. Keep
digests, authority matrices, recipes, and event history in machine artifacts unless
the user requests them or a mismatch needs diagnosis.
