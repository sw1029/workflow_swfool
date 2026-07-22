---
name: task-doctor
description: Review and retarget a repository's active `task.md` from explicit user direction before an orchestrated task cycle. Use when Codex must prepare and govern exact external-advice intake, one canonical task transition, and one final task-index reconciliation while acting as the sole user-interaction owner. Supports crash-safe task publication, predecessor-byte archival, durable no-effect settlement, authority recovery, and interruption recovery. Do not use for implementation, task-pack publication, schema or issue mutation, Git finalization, or ordinary agent-derived next-task selection.
---

# Task Doctor

Adjust workflow direction without implementing the resulting task. Keep one active
`task.md`, preserve exact lifecycle evidence, and hand the published task to a later
task cycle only after its owner receipts and final index transition verify.

## Load the bounded references

- Read [context-and-routing.md](references/context-and-routing.md) before selecting
  direction inputs or write scope.
- Read [workflow-coordination.md](references/workflow-coordination.md) before
  preparing, dispatching, settling, or resuming a governed workflow.
- Read [task-shaping-rules.md](references/task-shaping-rules.md) only for the task
  shape, measurable acceptance, or terminal family present in the request.
- Read [publication-and-task-packs.md](references/publication-and-task-packs.md)
  before publishing `task.md` or reconciling the task index. Despite the compatibility
  filename, that reference marks task-pack mutation as unsupported.

Keep the references one level from this file. Do not reconstruct their closed
contracts from memory.

## Stay inside the implemented owner surface

The workflow coordinator has closed plan and result adapters only for:

| Workflow role | Owner | Terminal evidence |
|---|---|---|
| `external_advice_intake` | `manage-external-advice` | Public apply or no-effect receipt |
| `task_scope_transition` | `task-doctor` | Public receipt plus immutable successor/observation snapshot, archive, and intent verification |
| `task_index_transition` | `manage-task-state-index` | Public apply or no-effect receipt |

Fail closed for every unregistered owner role. In particular, do not represent a
task pack, schema record, implementation issue, candidate deletion, work-log entry,
or Git operation as one of the supported roles. If the user's request requires one
of those effects, complete this bounded workflow only when that effect is genuinely
out of scope; otherwise report `plan_incomplete` and route it to its owner as a
separate future workflow after a closed public adapter exists.

The task transition itself archives exact predecessor bytes at
`.task/task_doctor/transitions/archives/<transition-id>.md`. This transaction-owned
archive is recovery evidence. Do not describe it as a `record-agent-work-log`
`past_task` entry or claim broader work-log lifecycle semantics.

## Own the user interaction

Act as the sole user-interaction owner for the bounded workflow. Child owners return
machine states and never request authority independently.

Let each supported owner retain its own truth:

- Let `manage-agent-authority` own decisions, grants, reservations, pre-commit
  verification, settlement, reconciliation, and quarantine.
- Let `manage-external-advice` own advice identity, materialization, and lifecycle.
- Let the task-transition owner transaction own canonical task replacement,
  predecessor-byte archival, intent, effect/no-effect receipt, and recovery.
- Let `manage-task-state-index` own the final event batch and rendered projection.

Group user review, not authority semantics. Keep one exact single-use grant,
reservation unit, pre-commit verification, and settlement per governed operation.
Never replace them with a wildcard, standing lease, reusable approval budget, or
one cross-operation reservation.

## Enforce the authority boundary

Treat explicit doctoring direction as a decision source only for the named local
effects. Do not infer authority for implementation, goal-truth change, risk or cost
acceptance, external input, design selection, remote push, destructive action, or a
later rebuilt plan.

Use [authority.operations.json](authority.operations.json) and the shared
[authority-v2-contract.md](../manage-agent-authority/references/authority-v2-contract.md)
for every governed operation.

Freeze each exact owner plan, plan-file digest, subject, target, before/after digest,
effect, exclusion, and risk before reservation. Reverify exact authority before
calling the owner. Consume only after the owner transaction returns a typed effect
receipt. After dispatch, release only against a public durable owner no-effect
receipt. Before dispatch, an invalidated dependent plan may release its exact
reservation only against the coordinator's durable `not_started` dependency-
cancellation intent. Route a possible effect to reconciliation or quarantine;
never convert uncertainty into no effect.

Keep approval, goal ratification, risk acceptance, external-input availability, and
bounded design selection as separate typed decisions.

## Compile before coordinating

Prefer a compact task-doctor intent over a hand-authored workflow plan. First publish each owner plan through its public builder; use `prepare-task-transition` for the canonical task transition. Compile each governed operation with `$manage-agent-authority --publish`, then place its returned `{ref, sha256, compilation_fingerprint}` receipt directly in the compact intent. Legacy inline compilations and two-field `{ref, sha256}` bindings remain accepted.

The closed compact contract uses `schema_version=1`,
`intent_kind=task_doctor_compact_intent`, and only
`git_finalization=deferred|not_applicable`. Do not guess capability or operation
enums: read the selected owner's `authority.operations.json`; for example, the
task-doctor scope owner declares capability `task.scope.mutate` and operation
identity `task-doctor:2.2.0:mutate_task_scope:1`.

```bash
python3 -P -m task_doctor_workflow_lib compile-intent \
  --root . --intent task-doctor-intent.json --at 2026-01-01T00:00:00Z
python3 -P -m task_doctor_workflow_lib prepare-intent \
  --root . --intent task-doctor-intent.json --at 2026-01-01T00:00:00Z
```

`compile-intent` is read-only. `prepare-intent` either prepares a prompt-free workflow when every exact source already exists, or publishes one content-addressed review for only the uncovered operations. Do not create a grant, evaluation, or reservation before the actual decision.

After a genuine decision, call `accept-review` only with exact pre-existing typed source snapshots whose evidence IDs bind that review and whose `not_before` is not earlier than the decision. The compiler then emits workflow plan schema-v2: source/grant/evaluation time is fixed after the decision, while each reservation stores a finite `not_before|expires_at` window so JIT reservation records its real later time. Continue reading legacy schema-v1 plans without rewriting them.

Use `build-resolution-bundle` to derive classifications and evidence bindings from live status, and use bounded `advance` or read-only `replay-or-route` to reuse settled state. These commands may prepare coordinator/authority state, but they stop at the exact owner dispatch, genuine approval, GT/risk/design/external-input decision, unknown effect, stale plan, recovery, or terminal result. Never rotate IDs to redispatch a released, consumed, or settled-no-effect owner plan.

## Run the prepare-all workflow

1. Confirm an explicit direction source.
   - Accept a user objective, constraint, priority, named advice artifact, named
     candidate or diagnostic record, or explicit narrow/expand/defer/replace
     instruction.
   - Read-only diagnose material ambiguity. Do not infer a replacement solely from
     repository state.

2. Inspect without implementing.
   - Read the active task and applicable goal, convention, repository-rule, advice,
     task-index, terminal, and loopback evidence.
   - Treat unsupported stores such as task packs, issues, and schemas as read-only
     context. Do not schedule their mutation through this coordinator.
   - Stop on unsafe paths, malformed live stores, duplicate identifiers, broken
     plan bindings, or incompatible goal truth.

3. Prepare every supported effect before canonical mutation.
   - Prepare advice intake or its exact plan-bound no-effect disposition.
   - Write exact prospective task bytes only under
     `.task/task_doctor/prospective/<transition-id>.md`.
   - Build and publish one immutable `task_transition_plan` under
     `.task/task_doctor/transition-plans/<transition-id>.json` through the public
     publisher. Do not serialize plan JSON directly.
   - Prepare one final immutable `task_state_transition_plan` whenever task scope
     changes. Also require it for advice lifecycle changes when a live, complete
     `.task/index.jsonl` plus `.task/index.md` store exists.
   - Mark `complete_effect_inventory=true` only after all supported required effects
     and dependencies are fixed. A later discovered required effect is
     `plan_incomplete`, not a second approval opportunity.

4. Select one execution mode.
   - Use `execute_with_declared_authorization` only when the initiating typed user
     decision covers every exact governed local effect. Set the interaction budget
     to zero.
   - Use `consolidated_review` otherwise. Prepare all exact operations first and
     present one stable bundle for the unresolved subset. Set the budget to one.
   - Bind the first displayed prompt-required operation inventory into the immutable
     workflow journal. A row that public authority status already resolves without a
     prompt remains outside that semantic bundle and cannot be added by the caller.

5. Create or replay the immutable workflow journal.
   - Run `task_doctor_workflow.py prepare` with the exact workflow plan.
   - Treat the journal as coordination evidence, not permission or cross-store
     atomicity.
   - Reuse its workflow ID and bundle fingerprint while plan bytes remain unchanged.

6. Resolve authority without repeated prompts.
   - In consolidated review, accept the one semantic decision for every unresolved
     prompt-required governed row in the journal-bound approval scope, including
     dependency-incomplete downstream rows. Journal each as `already_covered` with
     its operation-exact source snapshot and no reservation. Increment the interaction
     count only for this bundle. Already-covered live rows stay outside the mutation;
     accepting the displayed bundle cannot widen their authority or alter their state.
   - Materialize exact source snapshots, grants, and decisions for an
     `already_covered` operation without prompting, but reserve only the current
     dependency-complete owner frontier.
   - If a journal row still says `needs_user_approval` but its durable live authority
     state is already prompt-free, expose an `authority_bundle`, never an
     `approval_bundle`. Resolve its exact source or current reservation as system work
     with `user_interaction=false`; do not spend the semantic-review budget again.
   - Do not reserve or resolve the final index operation while an upstream owner is
     nonterminal or its public apply-phase status is not `ready`.
   - Prompt only for the consolidated `needs_user_approval` subset.
   - If an operation outside the immutable semantic scope later regresses to a genuine
     approval wait, route the old workflow to `plan_changed` / `prepare_new_plan`
     instead of opening a new prompt.
   - Treat `ready_to_resume`, `reserved_authority_recovery`, consumed, released,
     exhausted-source, and reconciliation states as system work.
   - Route an exhausted fixed grant recipe, and any later
     `approve_exact_recovery_projection` wait for replacement source/grant identities,
     to `plan_changed` / `replanning_required` and `prepare_new_plan`; the old plan
     cannot adopt replacement authority identities in place. Require a new immutable
     plan before any new prompt and do not spend the old workflow's interaction budget.

7. Dispatch one owner at a time.
   - Use journal `apply` only for the projected next operation after dependencies
     complete.
   - Invoke exactly the returned owner plan. Do not let the journal execute an
     arbitrary command.
   - For task scope, call the public `apply_task_transition_plan` API with the exact
     plan binding. It publishes an immutable intent, archives predecessor bytes when
     present, rechecks before-state CAS, atomically replaces `task.md`, and publishes
     an immutable receipt.
   - Reopen the exact receipt and its immutable successor or no-effect observation
     snapshot, predecessor archive, and effect intent before building the outer
     owner-effect result. Report mutable canonical-task projection health separately;
     a later legitimate transition must not erase historical completion.

8. Settle and record truthfully.
   - Record `completed` only after the exact public effect receipt and authority use
     receipt both verify.
   - Record `confirmed_no_effect` only after the public owner verifier returns
     `settled_no_effect` with an immutable plan-bound receipt and authority releases
     against that same owner result.
   - Never use a still-ready plan, an arbitrary JSON result, or absence of an error as
     no-effect evidence.
   - Apply the final task-index owner exactly once after all dependencies complete.
   - If an upstream required effect settles no effect and thereby invalidates the
     speculative final-index plan, publish the coordinator's exact dependency-
     cancellation intent and receipt, release any never-dispatched early reservation
     as `not_started`, and mark the immutable index plan `plan_changed`. Require the
     index public verifier to prove `stale` with no intent, effect, receipt, or
     historical completion first. Every other public state keeps its typed
     effect/recovery route. Rebuild before any prompt and never manufacture an index
     no-effect owner receipt.

9. Resume conservatively.
   - Run `status`, then `resume` at the current revision after interruption.
   - A plan-bound intent without a receipt is `recovery_required`. If canonical after
     bytes and the exact archive are present, recover the receipt; if before bytes
     remain and prospective bytes are exact, resume the same transaction.
   - Intent/effect ambiguity, archive conflict, or a canonical state matching neither
     planned side is never a no-op. Reconcile or fail closed.
   - Revalidate terminal owner and authority evidence before every later mutation and
     every completion report.

## Preserve state distinctions

Do not collapse these states into “approval required”:

| Classification | Meaning | User action |
|---|---|---|
| `authority_not_applicable` | Exact owner manifest declares no authority | None |
| `needs_user_approval` | Exact decision source is absent | Approve once |
| `already_covered` | Exact source exists; internal materialization remains | None |
| `ready_to_resume` | Exact live reservation is current | None |
| `reserved_authority_recovery` | Reservation needs system recovery | None |
| `already_settled` | Exact effect/no-effect settlement is terminal | None |
| `effect_reconciliation` | A prior dispatch may have changed state | None by default |
| `owner_materializing` | Public owner reports bounded partial materialization | None; wait/recheck |
| `owner_effect_reconciliation` | Public owner reports `already_applied` outside the journal | None; reconcile |
| `owner_settled_no_effect` | Public owner reports receipt-bound no effect | None; settle/release |
| `owner_recovery_required` | Public owner intent/effect needs forward recovery | None; recover |
| `owner_plan_stale` | Never-dispatched owner plan no longer matches apply state | None; cancel/replan |
| `plan_changed` | Immutable target or authority recipe changed | Prepare a new plan |
| `blocked_by_defect` | Owner/workflow contract is defective | Internal repair |

Use `awaiting_exact_approval` only for `needs_user_approval`. A missing active grant
alone is not proof that another user decision is needed.

## Report concisely

Use the surrounding language. Report:

- `outcome`: prepared, published, recovered, no effect, or fail-closed;
- `workflow`: ID, state, and classification;
- `changes`: advice, canonical task, transaction archive, owner receipts, and index;
- `user_action`: none, approve, choose, or supply input;
- `next_action`: one exact resume, repair, approval, or later orchestration action.

Keep full digests, authority matrices, and recovery observations in machine artifacts
unless a mismatch requires diagnosis. Never claim implementation or later task
completion; those belong to subsequent workflows.
