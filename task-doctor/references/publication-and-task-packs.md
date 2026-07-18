# Canonical task publication and extension boundaries

## Contents

- Implemented publication boundary
- Prospective task and immutable plan
- Task transition transaction
- Predecessor-byte archive
- Read-only phase verification
- No-effect settlement
- Crash recovery
- Final task-index reconciliation
- Canonical task shape
- Unsupported task-pack and adjacent effects
- Handoff checks

## Implemented publication boundary

Task doctor currently owns one closed canonical task transaction. It can:

- bind existing or absent `task.md` as the exact before state;
- bind exact prospective task bytes as the after state;
- preserve predecessor bytes in a deterministic transaction archive;
- preserve planned successor bytes in a deterministic immutable snapshot;
- publish an immutable plan-bound intent;
- atomically replace canonical `task.md` after a final CAS check;
- publish and reopen an immutable effect receipt;
- preserve a locked canonical observation and publish a safe pre-intent no-effect
  receipt;
- recover the same transaction after interruption; and
- coordinate a later, separately owned task-index transition.

It does not publish task packs, work-log entries, schema contracts, implementation
issues, candidate dispositions, Git commits, or remote effects. Those are not hidden
substeps of task publication. Do not claim they occurred.

## Prospective task and immutable plan

Write prospective bytes only to:

```text
.task/task_doctor/prospective/<transition-id>.md
```

The transition ID must be a bounded safe identifier. Do not use a raw prompt,
source title, corpus locator, personal identifier, or secret in the ID.

Publish the exact JSON plan only to:

```text
.task/task_doctor/transition-plans/<transition-id>.json
```

The filename must match `transition_id`. Use the public
`publish_task_transition_plan` API; direct JSON writes are not a supported
publication path. Publication is canonical-byte, immutable, collision-detecting,
and replay-safe. All path spellings are canonical POSIX workspace-relative refs.
Absolute paths, dot segments, aliases, symlink ancestors, unstable ancestor
identities, and non-regular files fail closed.

The closed plan binds:

- `transition_id` and one supported `transition_kind`;
- exact task-doctor operation identity and version;
- `before_task.ref`, existence, and SHA-256;
- exact prospective ref and SHA-256;
- exact canonical after ref and SHA-256;
- deterministic predecessor archive requirement, ref, and SHA-256; and
- `plan_sha256` over the full body without that digest field.

Use `initial_task` only when canonical `task.md` is absent. Every other supported
transition kind requires an existing regular canonical task. The prospective and
after digests must match. For replacement, the archive digest must equal the exact
before-task digest.

Plan preparation may create prospective bytes, a plan file, workflow coordination
metadata, and unused authority evidence. None of these proves task selection or
canonical publication.

## Task transition transaction

After journal dispatch, call the public task-doctor owner API:

```python
apply_task_transition_plan(root, plan_ref)
```

Do not copy prospective bytes directly to `task.md`. Do not hand-author a result
JSON. The public owner transaction performs these ordered checks and effects under
one transition-specific lock:

1. Reopen the canonical plan file and compare its exact file digest.
2. Reject a changed plan, aliased plan ref, unsafe path, conflicting intent, receipt,
   archive, or ambiguous canonical state.
3. Reopen exact prospective bytes when a new write or before-state recovery needs
   them.
4. Publish one immutable intent under the owner transaction root.
5. Publish exact successor bytes to the deterministic immutable successor snapshot.
6. For a replacement, publish exact predecessor bytes to the deterministic archive.
7. Recheck canonical before-state existence and digest immediately before replace.
8. Write the prospective payload to a same-directory temporary file, flush it, and
   atomically replace canonical `task.md`.
9. Reopen canonical after bytes and require the planned SHA-256.
10. Publish one immutable effect receipt binding plan, intent, successor snapshot,
    canonical after digest, and archive.
11. Reopen every terminal artifact through the public read-only verifier.

The return value's `execution_result_binding` is the only task-scope owner artifact
that may be embedded in the outer task-doctor owner-effect result. It points to the
canonical owner receipt, not the plan, prospective file, a narrative note, or a
caller-created surrogate.

An idempotent replay returns the same receipt binding and performs no mutation.

## Predecessor-byte archive

When `before_task.exists=true`, archive exact predecessor bytes at:

```text
.task/task_doctor/transitions/archives/<transition-id>.md
```

The archive is immutable and its SHA-256 is fixed in the plan. It is written before
canonical replacement. A retry accepts an existing archive only when its bytes are
exact. A missing or conflicting archive after the canonical effect is
`recovery_required`; it is never silently reconstructed from unrelated text.

When `before_task.exists=false`, no predecessor archive is permitted. An archive at
the deterministic ref is a conflict.

This file is transaction recovery evidence. It is not a work-log `past_task`
record, not a task-index event, and not a guarantee that a separate archival
workflow ran. Use those labels only if their actual owner later returns a closed
receipt through a supported adapter.

## Read-only phase verification

Use:

```python
verify_task_transition_execution(root, plan_ref, phase="planning")
verify_task_transition_execution(root, plan_ref, phase="apply")
```

Both calls are read-only. `planning` validates the exact before state, exact
prospective bytes, and absence of transaction activity. `apply` evaluates terminal
historical receipts and separately reports whether mutable canonical `task.md` is
still the receipt's current projection.

Important statuses are:

| Status | Meaning |
|---|---|
| `ready` | Exact before/prospective state exists and no transaction started |
| `not_applied` | Apply-phase query sees an intact but unexecuted plan |
| `already_applied` | Effect receipt, intent, immutable successor snapshot, and archive all verify |
| `settled_no_effect` | Pre-intent no-effect receipt and its live proof verify |
| `recovery_required` | Intent or partial effect exists without a complete receipt |
| `stale` | No intent/effect exists, but before or prospective state changed |
| `conflict` | Effect or owner artifacts are ambiguous or contradictory |

Do not treat `ready` as a no-effect result. Do not treat `stale` as terminal until
the owner publishes and reopens a no-effect receipt. Do not treat
`recovery_required` or `conflict` as user-approval states.

The verifier reports separate observations for prestate currentness, plan intent,
plan effect, receipt presence, and verified no effect. Preserve these distinctions
in recovery logic.

## No-effect settlement

The owner may settle no effect only before a plan-bound intent exists and before any
transaction archive or planned effect is observed.

Eligible examples include:

- canonical before state changed to unrelated bytes before owner execution;
- prospective task bytes disappeared before intent publication; or
- prospective bytes no longer match the planned digest before intent publication.

The owner captures the exact canonical and prospective observations under its lock,
stores present canonical observation bytes in an immutable snapshot, and publishes
an immutable `pre_intent_no_effect` receipt. Terminal revalidation
requires:

- the exact plan and plan-file binding;
- the exact canonical no-effect receipt ref and digest;
- no task-transition intent;
- no transaction archive;
- the receipt-bound canonical observation snapshot when the observed task existed;
- `no_effect_verified=true` from the public verifier.

Only then may authority release bind the outer owner result as
`confirmed_no_effect`.

Later unrelated canonical publication may make `current_projection_healthy=false`
without invalidating this historical receipt. Never use a still-ready plan binding
as no-effect evidence. Never release because
an exception occurred. If an intent exists, any partial state is recovery work,
even when canonical before bytes still remain.

## Crash recovery

Resume the same immutable plan and transaction ID.

Use this decision table:

| Observed state | Action |
|---|---|
| Intent + before state + exact prospective | Reuse/create exact archive, then apply |
| Intent + after state + exact required archive | Publish missing effect receipt |
| Intent + before state + missing/stale prospective | Restore exact prospective bytes, then retry |
| Intent + canonical state matching neither side | Reconcile; do not publish no effect |
| After state without intent | Conflict; determine provenance before settlement |
| After state + missing/conflicting required archive | Recovery required |
| Receipt + missing/changed immutable successor/archive/intent evidence | Terminal evidence is stale or conflicting |
| Receipt valid + mutable canonical task later changed | Historical completion remains valid; current projection is false |
| No intent/effect + stale safe prestate | Publish exact no-effect receipt |

The task-doctor journal's interrupted `in_progress` state should become
`effect_reconciliation`. The owner verifier decides artifact truth; authority owns
reservation settlement. Do not renew approval merely because the coordinator
restarted.

## Final task-index reconciliation

A task-scope transition requires exactly one final
`workflow_role=task_index_transition`. It must depend on the task-scope operation
and every other preceding supported lifecycle effect.

When external advice changes and a live `.task/index.jsonl` plus `.task/index.md`
store exists, the advice workflow also requires exactly one final index transition.
If only one index file exists, a path is unsafe, the ledger is malformed, or the
render is not valid UTF-8, fail closed before creating the workflow journal.

The index owner public verifier has two phases:

- `planning`: ledger/Markdown before CAS and artifact `before_sha256`;
- `apply`: ledger/Markdown before CAS plus artifact `expected_sha256` after prior
  dependencies publish.

Use planning verification while dependencies remain untouched. During an upstream
owner effect that has not yet been recorded in the journal, downstream validation
is structural. Once dependencies are terminal, require apply-phase `ready` before
index dispatch.

Authority materialization follows the same frontier: source/grant preparation may
be known earlier, but do not reserve the index mutation until every dependency is
terminal and apply-phase verification is `ready`. Public `materializing`,
`already_applied`, `settled_no_effect`, `recovery_required`, `stale`, and `conflict`
are typed internal routes, not alternative spellings of approval required.

When an upstream required operation settles verified no effect, cancel a
never-dispatched speculative index plan with the task-doctor dependency-cancellation
intent/receipt. Release an already-created exact reservation only as `not_started`
against that intent and only after the public verifier proves `stale` plus absence
of intent, effect, receipt, and historical completion. Preserve every other typed
owner state for wait, settlement, reconciliation, recovery, or conflict repair.
Then mark the immutable plan `plan_changed` and rebuild from the terminal dependency
outcomes. Do not ask the index owner to invent a no-effect receipt for work that was
never eligible to dispatch.

For index no effect, require its public `settled_no_effect` status and exact
no-effect receipt binding. A ready plan file is not terminal proof.

## Canonical task shape

Use a compact task document that makes later execution unambiguous:

```markdown
# Task

## Execution Environment

- Status: selected | unresolved | not_applicable
- Source: previous_task | local_environment | repository_manifest | user_instruction | manual_inference
- Type: conda | venv | local | non_python | unknown
- Name:
- Python:
- Run Prefix:
- Dependency Notes:

## Objective

<One concrete externally adjusted objective.>

## Background

- Direction ID:
- Goal alignment:
- Advice ID:

## Requirements

- <Specific requirement>

## Acceptance Criteria

- <Observable completion condition>

## Validation

- <Command, review, metric, or evidence>

## Constraints

- <Relevant rule or forbidden action>

## Out Of Scope

- <What the next cycle must not attempt>

## Open Questions

- None
```

Replace raw source metadata with opaque IDs and bounded refs. Do not copy private
source bodies into plans, authority artifacts, receipts, index titles, or reports.

## Unsupported task-pack and adjacent effects

`task_pack_transition` has no registered closed task-doctor plan/result adapter,
and task-doctor publishes no task-pack authority operation. Generic authority
consumers therefore cannot propose, reserve, or dispatch task-pack mutation on
task-doctor's behalf. Reading a task pack as
direction context does not authorize or implement pack creation, replacement,
promotion, reordering, or retirement.

Likewise, this coordinator does not mutate:

- `.agent_log/` work-log records;
- `.schema/` or `.contract/` records;
- `.issue/` records;
- `.task/candidate_task/` dispositions;
- Git index, commits, branches, or remotes; or
- implementation files.

Do not add prose-only owner results for these surfaces. Add support only after the
actual owner exposes a closed immutable plan, typed effect/no-effect receipt,
read-only verifier, crash-recovery contract, and authority manifest operation.

Set Git finalization to `deferred` or `not_applicable` in the currently supported
workflow. A user request for a commit remains a separate future action, not a
task-doctor operation.

## Handoff checks

Before reporting publication:

1. Reopen the canonical task-transition plan file.
2. Reopen the exact task-transition receipt.
3. Reopen the immutable successor snapshot and required predecessor archive.
4. Reopen the plan-bound intent for a confirmed effect, or prove its absence for no
   effect.
5. Reopen the exact authority settlement and current reservation state.
6. Inspect mutable canonical `task.md` as current projection health, not historical
   receipt validity.
7. Reopen the final index owner receipt and current projection.
8. Run final read-only task/index validation.
9. Confirm no unsupported effect is claimed.
10. Remove prospective staging only after terminal receipt verification; its later
   absence must not invalidate a committed effect.

Report the new task summary, transition ID, receipt and archive refs, final index
status, recovery state if any, and one next action. Do not claim later task
completion or implementation progress.
