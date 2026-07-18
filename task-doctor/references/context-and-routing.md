# Context and routing

## Contents

- Purpose and trigger
- Implemented scope
- Direction sources
- Read-only context
- Privacy and identifier policy
- Goal and terminal routing
- Advice routing
- Unsupported effects
- Environment and handoff

## Purpose and trigger

Use task doctor as a pre-cycle intervention when an explicit human direction must
change the active canonical task. It reviews and shapes direction, coordinates
supported lifecycle effects, publishes exact `task.md` bytes through the owner
transaction, and reconciles an existing task index.

Do not use it for normal implementation, ordinary agent-selected next work, broad
repository cleanup, or speculative task generation. A weak task discovered by an
agent does not itself authorize canonical replacement.

Proceed only when the user clearly asks to replace, retarget, narrow, expand,
defer, or otherwise doctor the active task direction, or names an exact direction
source that should drive such a change.

## Implemented scope

The closed coordinator supports these owner effects:

- external-advice intake through `manage-external-advice`;
- canonical task transition through task-doctor's public owner transaction; and
- one final task-index transition through `manage-task-state-index`.

It also coordinates exact `manage-agent-authority` lifecycle artifacts for those
effects. Read-only inspection of goals, rules, diagnostic files, and unsupported
stores is allowed when relevant.

The following are outside the implemented mutation surface:

- task-pack creation, replacement, promotion, or selection;
- work-log or `past_task` entries;
- schema and contract mutation;
- implementation-issue mutation;
- candidate, task-miss, or diagnostic-record deletion;
- Git staging, commit, branch, push, or remote mutation; and
- implementation of the doctored task.

Fail `plan_incomplete` when one of these effects is required for the requested
outcome. Do not disguise it as a generic owner role or a task-index event.

## Direction sources

Accept a bounded direction source such as:

- a direct user objective, constraint, priority, or replacement instruction;
- an exact user-named advice artifact;
- a user-named candidate, task miss, issue, or diagnostic record used read-only;
- a goal or convention clause named by the user; or
- an explicit instruction to preserve, remove, narrow, or expand a task clause.

Direction evidence is not blanket permission. Freeze the exact task/advice/index
plans first, then apply authority to each separately governed owner effect.

If multiple interpretations would materially change objective, acceptance, risk,
or excluded scope, stop before plan publication and request one choice. Do not use a
clarification request for internal grant materialization, reservation recovery,
receipt reconciliation, or an already typed exact decision.

## Read-only context

Read only the evidence needed to shape and verify the requested transition:

- active `task.md` when present;
- repository rule files such as `AGENTS.md`, conventions, and applicable README
  sections;
- applicable `.agent_goal/` goal architecture, theory, and convention records;
- the exact advice packet and required raw clauses when advice fidelity requires
  direct review;
- `.task/index.jsonl` and `.task/index.md` when present;
- relevant loopback, terminal, task-miss, candidate, issue, schema, or task-pack
  records as context only; and
- local execution-environment evidence only when the new task needs it.

Do not scan large unrelated stores merely because they exist. Do not solve the
implementation while deciding task direction.

Run read-only validation before plan publication. Unsafe paths, symlink ancestors,
malformed live task-index data, duplicate IDs, broken links, or incompatible goal
truth are fail-closed findings unless the exact prepared supported transition is
designed to repair them.

## Privacy and identifier policy

Keep raw prompts, source bodies, credentials, personal details, corpus metadata,
and proprietary locators out of body-safe plans and durable reports.

Use:

- opaque content-derived source IDs;
- safe transition and operation IDs;
- canonical bounded workspace refs;
- exact SHA-256 digests; and
- short summaries that do not reconstruct protected source text.

Never place raw source titles or private metadata in transition IDs, archive names,
receipt IDs, authority idempotency keys, task-index titles, or final status output.
The transaction archive contains predecessor task bytes because they are directly
required for recovery; do not duplicate them into JSON receipts or logs.

## Goal and terminal routing

Task doctor may change task direction but does not alter goal truth. Compare the new
objective with the current goal architecture and theory before publication.

When terminal or escalation evidence is involved:

- preserve existing goal truth;
- distinguish verified external dependency from unverified scope;
- keep locally resolvable or offline-recomputable residual work nonterminal;
- do not convert repeated workflow friction into goal exhaustion; and
- require a separate typed goal decision for any actual goal change.

A user-directed task retarget may override a prior task-level quiescence decision,
but the new task should bind an opaque direction ID and state the changed material
delta. It does not automatically reopen or alter goal-level terminal truth.

## Advice routing

Treat normalized advice as non-goal-truth direction evidence. Preserve the owner
skill's exact advice identity and lifecycle.

If an advice packet says raw review is required, fidelity is incomplete, or its
directive list is warning-only, inspect the bounded raw source through the advice
owner contract before using that clause. Do not silently treat incomplete
normalization as a complete executable plan.

Advice intake may be part of the same coordinated workflow only through its public
immutable plan and effect/no-effect verifier. If a live complete task-index store
exists, include one final task-index transition that depends on the advice effect.
If the index store is partial or malformed, repair it in a separate supported owner
workflow before doctoring.

## Unsupported effects

Existing task packs, issues, schemas, work logs, and candidates may inform the new
task. They remain unchanged.

Do not claim that task doctor:

- promoted a task-pack item;
- archived a predecessor as a work-log entry;
- closed or deferred an implementation issue;
- created or changed a schema contract;
- consumed or deleted a candidate or task miss; or
- committed repository changes.

The deterministic predecessor archive created by task publication is explicitly a
task-transition recovery artifact. Use that name in reports.

New owner roles require an actual public plan/apply/verify/recovery contract and
registered authority operation before documentation may present them as supported.

## Environment and handoff

Preserve valid execution-environment information from the previous task when it is
still applicable. If the new task changes runtime needs, derive them from local
evidence and record unknowns honestly. Do not install dependencies or execute the
new task during doctoring.

After terminal owner and authority evidence verify:

- report canonical task and transaction receipt state;
- report the deterministic archive only when a predecessor existed;
- report the final task-index status when applicable;
- report unsupported requested effects as deferred or blocked, never completed;
- give one exact next action; and
- invoke a later orchestration workflow only when the user explicitly requested
  both doctoring and implementation.
