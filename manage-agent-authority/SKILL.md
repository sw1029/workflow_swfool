---
name: manage-agent-authority
description: Manage exact workspace authority, session-scoped approval reuse, compiler-owned operation batches, plan-bound grants, reservations, settlement, and workflow-aware approval state without expanding active permissions. Use when Codex must inspect or advance governed authority, start or stop a bounded workflow session, distinguish approval from goal truth or risk acceptance, recover an existing reservation, or maintain `.agent_goal/agent_authority.md`.
---

# Manage Agent Authority

## Hard boundary

Active system, developer, user, tool, sandbox, network, and approval constraints are
the ceiling. Stored policy, grants, activations, and session receipts may only narrow
that ceiling. They never create a capability the current host session lacks.

Keep these stores distinct:

- Durable policy: `.agent_goal/agent_authority.md`.
- Immutable policy/source/grant/decision/reservation/receipt evidence:
  `.task/authorization/`.
- Session leases and continuation state:
  `.task/authorization/sessions/<producer-derived-session-id>/`.
- Advice: `.agent_advice/active/*.md`; it is neither goal truth nor authority.

Read [authority-v2-contract.md](references/authority-v2-contract.md) for exact
request, grant, evaluator, reservation, and settlement contracts. Read
[authority-interaction-mode.md](references/authority-interaction-mode.md) before
using signed activation or session approval. Use
[agent-authority-template.md](references/agent-authority-template.md) for policy
editing and [root-authorization-host-contract.md](references/root-authorization-host-contract.md)
for isolated signer administration.

## Classification

Classify each versioned operation independently:

- Source: `S4` platform/session ceiling, `S3` user goal owner, `S2` delegated
  steward, `S1` coordinator, `S0` executor.
- Risk: `R0` observe, `R1` reversible local, `R2` consequential bounded,
  `R3` external, sensitive, destructive, goal-changing, or authority-changing.
- Decision: `D0` core goal, `D1` design, `D2` task topology, `D3` tactic.
- Cardinality: `single_use`, `bounded_reusable`, `task_lease`,
  `improvement_lease`, or `standing_policy`.

Load the owning skill's [authority.operations.json](authority.operations.json)-style
manifest. Runtime classification may only raise requirements. Unknown mutating
operations fail closed. Do not union grants implicitly: one active grant must cover
the full exact request, or an explicitly approved composition receipt must bind the
deliberate set.

Keep decision types separate: `grant_authority`, `ratify_goal_truth`,
`accept_risk_or_cost`, `supply_external_input`, and `select_design_option`.
Authority does not ratify goal truth, accept risk, create external data, or select
an undecided design.

## Compiler-first operation flow

For new work, publish one cycle-shared semantic context and one canonical operation
set, then compile the batch. The compiler derives versions, manifest floors,
subjects, IDs, request hashes, evaluation contexts, and CAS paths.

```bash
SKILLS_ROOT="${CODEX_HOME:-$HOME/.codex}/skills"
PYTHONPATH="$SKILLS_ROOT/orchestrate-task-cycle/scripts" \
  python3 -P -m orchestrate_task_cycle workflow authority \
  compile-semantic-context --root . \
  --initialization '{"ref":"...","sha256":"..."}' \
  --semantic semantic-context.json

PYTHONPATH="$SKILLS_ROOT/orchestrate-task-cycle/scripts" \
  python3 -P -m orchestrate_task_cycle workflow authority \
  publish-operation-set --root . --operations operation-seeds.json

PYTHONPATH="$SKILLS_ROOT/orchestrate-task-cycle/scripts" \
  python3 -P -m orchestrate_task_cycle workflow authority \
  compile-operation-batch --root . \
  --semantic-context '{"ref":"...","sha256":"..."}' \
  --operation-set '{"ref":"...","sha256":"..."}' --at <RFC3339>
```

`workflow authority compile-operation` is a historical diagnostic path. Its output
is non-authoritative preparation, even with `--publish`; it never creates approval,
a grant, a reservation, or settlement.

For an S3 root decision, run the isolated TTY preflight, prepare one plan-bound
approval from the operation batch and current policy snapshot, obtain the signed
host outbox evidence, publish it, compile the root decision seed, and materialize
the exact projected grants. Never accept caller-authored decision JSON, a
caller-selected trust registry, or a stale policy snapshot. The full signer
sequence and retry rules live in
[root-authorization-host-contract.md](references/root-authorization-host-contract.md).

Selected-successor and other multi-operation flows must use their public
`prepare-authority` compiler. The compact packet is transport, not new authority:
the canonical evaluator must still accept an exact source approval or grant before
reservation. Preserve `trusted_request_idempotency_key`; do not substitute a
caller-invented identity.

## Session-scoped approval UX

A session lease amortizes repeated approval checks inside one host thread. It does
not widen the signed activation, survive drift, or authorize R3. Platform host
receipt is primary; one exact foreground TTY confirmation is the fallback.

```bash
# The host may inject CODEX_SESSION_APPROVAL_RECEIPT and CODEX_THREAD_ID.
PYTHONPATH="$SKILLS_ROOT/manage-agent-authority/scripts" \
  "$SKILLS_ROOT/manage-agent-authority/scripts/authority-mode" \
  session-start --workspace /absolute/workspace

PYTHONPATH="$SKILLS_ROOT/manage-agent-authority/scripts" \
  "$SKILLS_ROOT/manage-agent-authority/scripts/authority-mode" \
  session-status --workspace /absolute/workspace
```

The producer derives the session ID from workspace, provider, thread, activation,
trust class, and a hashed approval receipt. Never accept a caller-selected session
ID or store the raw thread/receipt. Reuse is valid only while:

- the signed activation remains eligible and unexpired;
- goal, policy, manifest, operation group, and risk envelope still match;
- the host thread is live;
- budgets remain within 3 cycles, 72 agent actions, 1 concurrent long run, and
  1 closeout commit per cycle.

Both host and TTY session paths cap risk at R2. Always require a separate exact
decision for R3, push, external/destructive effects, credentials, authority or goal
design changes, and policy/mode changes. A historical grant with `session_id=null`
is reader-only and cannot be upgraded by rewriting it.

Stop explicitly when the user stops, the host receipt disappears, the activation
expires, drift occurs, an unknown effect appears, or a budget is exhausted:

```bash
PYTHONPATH="$SKILLS_ROOT/manage-agent-authority/scripts" \
  "$SKILLS_ROOT/manage-agent-authority/scripts/authority-mode" \
  session-stop --workspace /absolute/workspace
```

## Inspect versus advance

Use `authority inspect` for status rendering. It is pure read-only: no CAS
publication, child materialization, evaluation, reservation, or settlement.

Use `authority advance` for one bounded effectful resolution step. The deprecated
`authority resolve` alias has the same effectful meaning and exists only for
compatibility. Never call `advance` merely to display status.

Return one compact interaction projection: `outcome`, `workflow_state`,
`should_prompt`, nullable `user_action`, and one `next_action`. Only
`needs_user_approval` may set `should_prompt=true`. Keep
`already_covered`, `ready_to_resume`, `ready_to_reserve`,
`source_approval_ready_for_grant`, recovery, reconciliation, consumed, and released
states as system work.

## Runtime lifecycle

For each exact request:

1. Reopen the producer-owned context, operation batch, current policy/source, and
   owning operation manifest.
2. Inspect before mutating. Reuse exact source, grant, reservation, and settlement
   state when valid.
3. Call the canonical evaluator. Use `evaluate_and_publish` only through its public
   producer path.
4. Reserve before the first effect. Never reserve speculative downstream work whose
   dependencies are incomplete.
5. Run `verify_and_publish_precommit` immediately before the exact effect.
6. Consume only after a typed effect receipt. Release only after a typed durable
   no-effect receipt or a pre-dispatch cancellation.
7. Quarantine unknown effects; reconcile with evidence instead of re-prompting or
   relaunching.
8. Treat exhausted/revoked/expired/source-conflicted grant identities as immutable.
   A replacement requires a new exact plan and projection.

Source schema 5 root projections and schema 6 activation children are producer
contracts. Validate their exact request projection and reuse the materialized
schema 3/4 grant. Do not synthesize a prospective schema 2 source or grant. Legacy
schema 1/2 evidence remains readable only under its historical verification rules.

## Policy operations

Use:

- `summarize` for effective policy and open questions.
- `ensure_default` only when durable policy is required and absent.
- `draft_for_interview` for `.interview/drafts/agent_authority.md`.
- `finalize_from_interview` only after user and agent confirmation gates.
- `update` only for explicitly authorized policy changes.
- `validate` to reject expansion, unsupported sources, secrets, and precedence
  violations.

Optional project adapters may classify an axis or report policy-consumption sites,
but may only narrow escalation. They cannot grant authority or lower a manifest
floor.

## Legacy and reporting

Keep `receipt issue|validate` schema-v1 compatibility without reinterpreting old
evidence. Preserve historical uncertainty; current ratification never backdates
permission.

Report exact subject, capabilities, axes, grant budget, reservation units, immutable
bindings, lifecycle version, request SHA filter, conflicts, and the next actor. Do
not embed secrets, raw private transcripts, or copyrighted bodies.

## Guardrails

- Never bypass current sandbox, approval, network, filesystem, tool, credential,
  cost, or higher-priority limits.
- Never treat advice, validation success, silence, issue state, or a rank label as
  authority.
- Never use wildcards, implicit unions, self/circular delegation, rank escalation,
  retroactive receipts, or mutable-current hashes as historical proof.
- Never retry an unchanged approval wait as a new task.
- Never expose a missing grant as a user prompt when an exact effective source can
  materialize it.
- Never release a reservation after an unknown effect; quarantine and reconcile.
