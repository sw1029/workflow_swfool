---
name: manage-agent-authority
description: Manage deterministic workspace authority policy, grants, leases, exact operation settlement, exhausted-source recovery recipes, and workflow-aware approval state without expanding active permissions. Use when Codex must summarize or update `.agent_goal/agent_authority.md`; distinguish approval from goal truth, risk acceptance, external input, and design choice; evaluate or resolve a versioned operation; reserve, verify, consume, release, or reconcile authority; prepare a non-authoritative exact recovery projection; resume an existing reservation instead of re-prompting; transition a grant; or validate legacy and immutable receipts.
---

# Manage Agent Authority

## Non-negotiable boundary

Treat the active system, developer, user, tool, sandbox, network, and approval constraints as the hard ceiling. Use stored policy and grants only to narrow or clarify that ceiling. Never let a policy, grant, advice file, adapter, receipt, or higher source-rank label create a capability that the active session lacks.

Keep goal truth, authority, evidence, and mutable state separate:

- Store durable goal-level policy in `.agent_goal/agent_authority.md`.
- Store content-addressed policy/source snapshots and immutable grants, decisions, reservations, and receipts under `.task/authorization/`.
- Store only current pointers and usage projections under `.task/authorization/state/`.
- Treat `.agent_advice/active/*.md` as non-GT, non-authority input.
- Preserve historical uncertainty. Never use current ratification to backdate permission.

Read [agent-authority-template.md](references/agent-authority-template.md) before drafting policy. Read [authority-v2-contract.md](references/authority-v2-contract.md) before issuing grants, evaluating operations, delegating, or changing lifecycle state. Read [operation-authority-receipt.md](references/operation-authority-receipt.md) before using the legacy-compatible `receipt` command.

## Authority model

Classify each operation on independent axes:

- Source rank: `S4` platform/session ceiling, `S3` user goal owner, `S2` delegated policy steward, `S1` cycle coordinator, `S0` executor.
- Risk: `R0` observation, `R1` reversible bounded local effect, `R2` consequential bounded effect, `R3` external, sensitive, destructive, goal-changing, or authority-changing effect.
- Decision: `D0` core goal, `D1` bounded design, `D2` task topology, `D3` execution tactic.
- Cardinality: `single_use`, `bounded_reusable`, `task_lease`, `improvement_lease`, or `standing_policy`.

Assign requirements per versioned operation, not per whole skill. Load `authority.operations.json` from the owning skill. Permit runtime classification only to add capabilities or increase risk/mutation/reversibility severity; reject a request that understates its manifest. Fail closed for an unknown mutating operation.

Declare one `authorization_mechanism` per operation. Use `grant` for ordinary governed effects, `typed_source_approval` for grant issuance/composition/transition, `bound_lifecycle_artifact` for delegation and reserve/verify/consume/release, and `none` only when authority is not applicable. This is the bootstrap boundary: authority administration is authorized by its closed source or lifecycle artifact, not by recursively requiring a grant that can only be issued by the same administration path.

Do not merge grants implicitly. Require one active grant to cover the complete capability set, exact subject, exact operation, actor rank, risk, decision class, time window, lease scope, and available use budget. Use an explicit, source-bound composition receipt only when a deliberately approved set of grants must cover the request together.

## Separate decision types

Set exactly one `intent_type` and route it to its actual owner:

- `grant_authority`: evaluate with this skill.
- `ratify_goal_truth`: require goal-owner ratification; a grant is not ratification.
- `accept_risk_or_cost`: require separate risk/cost acceptance; a grant is not consent.
- `supply_external_input`: report availability independently; permission does not create missing data.
- `select_design_option`: require design selection when the autonomy envelope does not already decide it.

Return one closed decision: `allowed`, `approval_required`, `denied`, `waiting_external_input`, `capability_unavailable`, `blocked_by_goal_truth`, `classification_repair`, `conflict`, or `not_applicable`.

Route unsupplyable external input to a local-data alternative, descope, or an explicit external-input limitation. Do not relabel it as a GT blocker or keep converting it into approval work.

## Deterministic workflow

1. Resolve the workspace and current ceiling.
   - Read current instructions and tool/sandbox permissions first.
   - Read `.agent_goal/final_goal.md`, `.agent_goal/conventions.md`, `.agent_goal/agent_authority.md`, and relevant goal theory/architecture when present.
   - Load adapter classifications only as narrowing evidence.

2. Classify the operation.
   - Bind skill/operation IDs and versions, cycle/task/pack/attempt IDs, actor rank, exact subject `{kind, ref, digest, revision}`, namespaced capabilities, effect/data/mutation/reversibility, risk, decision class, requested cardinality/grant budget, per-dispatch `reservation_units`, and idempotency key.
   - Under schema v2, treat `subject.ref` as a workspace-relative existing regular file. Reject a missing, symlinked, or non-regular subject and require its current bytes to match `subject.digest` again before reserve, dispatch, and commit.
   - Require `single_use` budget 1, an exact task ID for `task_lease`, and an exact pack/improvement ID for `improvement_lease`.
   - Build a session ceiling and goal-autonomy envelope. Bind the envelope to exact concept/subject/operation IDs and evidence digest.
   - Keep external-input, GT-alignment, risk-acceptance, and design-selection status explicit.
   - Bind asserted available/missing external input, resolved risk acceptance, and resolved design selection to exact immutable `{ref, sha256}` evidence. Keep the evidence field `null` for unverified, unresolved, or not-required states.

3. Snapshot mutable authority sources before issuing prospective authority.

```bash
SKILLS_ROOT="${CODEX_HOME:-$HOME/.codex}/skills"
PYTHONPATH="$SKILLS_ROOT/manage-agent-authority/scripts" \
  python3 -m manage_agent_authority authority snapshot-policy \
  --root . --policy-ref .agent_goal/agent_authority.md --expected-version 0

PYTHONPATH="$SKILLS_ROOT/manage-agent-authority/scripts" \
  python3 -m manage_agent_authority authority snapshot-source \
  --root . --source-ref .task/authorization/source-id.json
```

`snapshot-source` accepts only a closed `authority_source_approval` JSON document for authority issuance. It must bind the source kind/rank, exact grant and lineage IDs, capabilities, subjects, operations, risk/decision/cardinality ceilings, use limit, validity window, and any delegated approval binding. Before using an S1/S2 source, resolve and rehash its exact higher-rank source-approval binding, require a finite strictly rank-increasing lineage to S3/S4, and prove that every scope and time window only narrows. It cannot encode goal ratification, risk acceptance, design selection, or external-input supply.

4. Register one closed grant or a valid subset delegation.
   - Require immutable policy/source bindings.
   - Require issuer rank above holder rank.
   - For a child, preserve lineage and make capabilities, subjects, operations, risk ceiling, decision classes, expiry, task/improvement scope, and budget no broader than the parent.

```bash
PYTHONPATH="$SKILLS_ROOT/manage-agent-authority/scripts" \
  python3 -m manage_agent_authority authority register-grant --root . --grant grant.json
```

5. Evaluate and persist the decision.

```bash
PYTHONPATH="$SKILLS_ROOT/manage-agent-authority/scripts" \
  python3 -m manage_agent_authority authority evaluate --root . \
  --request request.json --context evaluation-context.json \
  --at 2026-01-01T00:00:00Z
```

Use `effective_authority_fingerprint` for approval-wait wakeup and exact replay. It contains only operation-relevant projections and selected immutable grant/policy bindings. Do not substitute a hash of the mutable whole policy or goal context.

Before prompting, run `authority resolve` or inspect `authority status`. For replayable diagnostics, pass `authority status --at <RFC3339>` and the same `--skills-root` used for evaluation; omission uses the current UTC time and default skills root, and every status result reports `evaluated_at`. Judge both the selected grant and every ancestor against that one time, including `not_before` and `expires_at`, while preserving each raw projection state separately from effective usability. Status and resolve must rehash and validate the bound operation manifest and fail closed if it is missing, changed, invalid for the exact operation identity, or if any decision, reservation, grant/reservation state, or lifecycle receipt is not a closed, deterministic, fully settled artifact. Reject symlinks in every component of authority-owned decision, source-snapshot, grant, state, and receipt directories; acquire inspected JSON as stable bytes and bind the reported digest to those same bytes. Publish authority-owned snapshots, immutable artifacts, and mutable state through stable directory descriptors with `O_NOFOLLOW` and pre/post parent-identity checks so an ancestor swap fails closed instead of redirecting a write.

Select workflow state in this order: unknown-effect quarantine; settled consumed or released reservation; usable reserved operation; reserved operation whose selected or ancestor authority is no longer usable; current exact allowed decision; exact source approval with a usable or cleanly materializable grant ID; source-authority defect; exhausted source authority; genuine approval wait. Return `should_prompt=false` for every system-recovery or reusable-authority state. A released reservation is terminal only with an exact release or reconciliation receipt proving no effect; return `already_released` and never redispatch it. Keep an unusable reserved projection reserved, preserve unknown-effect safety, return `reserved_authority_recovery`, and do not silently release it.

For an exact source approval, classify a missing grant ID as materializable only when both its grant and state paths are absent and safe. Reuse an existing grant only when its exact source binding, scope, lineage, time, status, and budget remain usable. Treat an orphan or conflicting projection as `source_authority_defect`. Treat an exhausted, revoked, expired, or source-binding-conflicted existing ID as `source_authority_exhausted`: supersede the old wait, do not prompt, and route the system to `prepare_exact_recovery_recipe`.

Run `authority prepare-source-recovery` against the exact persisted exhausted decision binding. It publishes one immutable, prepare-only `authority_source_recovery_recipe` under `.task/authorization/recovery_recipes/`. The recipe binds the old decision, source snapshot, exhausted grant, and exact grant-state evidence; allocates distinct unused replacement request, attempt, source-approval, grant, lineage, and replay IDs; and includes a closed replacement request plus non-artifact source-approval and grant requirements. Exact replay is idempotent, while conflicting content for the same recovery identity fails closed. The recipe is neither approval nor authority. It must not contain any nested object accepted as `authority_source_approval` or `authority_grant`, any projected source-snapshot binding, or any claim that approval integrity is already verified. Materialize a source only from the actual later user-decision evidence and bind a grant only to the resulting immutable snapshot bytes; until then snapshot, registration, reserve, dispatch, and commit must fail closed.

Treat recipe `prepared_at` as T1 preparation evidence, never as the later user-decision time. The actual explicit decision supplies T2, with T2 greater than or equal to T1. A materialized source must set `not_before` to T2 or later; its grant must set both `not_before` and `created_at` to T2 or later. Evaluation at T1 must therefore remain non-allowed even if post-approval artifacts have subsequently been registered.

After a valid recipe exists, `status` and `resolve` supersede the system repair state with exactly one `needs_user_approval` result whose action is `approve_exact_recovery_projection`. Use the recovery projection, replay key, and effective-authority fingerprint as its new wait identity. Never revive the old projection or reuse an exhausted request, attempt, source, grant, lineage, or replay identity.

Preserve the machine-readable `post_approval_handoff` in prepare, status, and resolve output. After the exact user decision arrives, use the existing public commands in order: create a source artifact from that actual decision evidence and run `snapshot-source`; complete the grant requirements with that resulting binding and run `register-grant`; then run `evaluate` with the recipe's replacement request. From that point, poll `status` or `resolve` with `continuation_request_sha256`, not the exhausted original request digest. The handoff is guidance, not authority, and remains blocked until the actual user-decision evidence exists.

Discover an existing recipe from its immutable historical decision/source/grant/state evidence before classifying a current generic approval wait. A later source expiry or other loss of current coverage must never revive the original approval projection or wait identity. If the recipe remains within its exact continuation window, preserve its one recovery prompt. If its expiry ceiling has closed, reuse `source_authority_exhausted` with reason `source_recovery_window_closed`, `should_prompt=false`, action `prepare_fresh_recovery_plan`, the exact recipe binding, and a non-authoritative closed-window handoff. Every non-prompt status or resolution exposes `approval_projection=null`.

```bash
PYTHONPATH="$SKILLS_ROOT/manage-agent-authority/scripts" \
  python3 -m manage_agent_authority authority prepare-source-recovery \
  --root . --decision-ref .task/authorization/decisions/authd-id.json \
  --decision-sha256 <sha256> --at 2026-01-01T00:00:00Z
```

When the decision is `approval_required`, present the deterministic `approval_projection`: typed intent, exact operation/subject/capabilities/effect, bounded scope and budget, excluded effects, safe alternative, reason codes, and replay key. An approval of that projection does not authorize any excluded effect or broader reuse.

6. Reserve before dispatch.
   - Bind the persisted allowed decision by path and SHA-256.
   - Re-evaluate under a lock, verify the subject, operation manifest, selected grant and every lineage ancestor state/version, policy snapshot, expiry, scope, and available budget, then create a reservation and CAS-update usage across the lineage.
   - Treat an exact idempotent replay as the same reservation. Reject a conflicting replay.
   - Treat immutable event `state_changes` as a write-ahead recovery intent. Before every lifecycle/transition entry, scan all intents, complete each uniquely connected exact `before -> after` projection, accept an already-applied `after` or exact recorded descendant, and quarantine competing/unconnected state.

7. Verify before commit, then consume or release.
   - Run `authority verify --stage pre_commit` before committing effects.
   - Pass that exact verification binding, a typed owner-result binding, and the exact expected subject-after digest to `authority consume` after a known effect. Consume creates a closed `authority_execution_result`; it does not require the pre-effect subject digest to remain current after a legitimate mutation.
   - Run `authority release` only with evidence of `not_started` or `verified_no_effect`.
   - Quarantine `unknown_effect`; do not restore its reserved budget automatically.
   - Run `authority prepare-reconciliation-evidence` to deterministically bind the quarantined reservation, operation, observed subject, outcome, time, and typed owner result. Pass its exact binding to `authority reconcile`. Map `confirmed_effect` to consumed, `confirmed_no_effect` to released, and `still_unknown` to a versioned quarantined state. Do not ask the user to approve the original operation again.

8. Transition grants explicitly.
   - Use CAS-bound `suspended`, `reactivated`, `revoked`, or `expired` transitions with immutable typed source approval.
   - Reactivation is the deliberate recovery path only from `suspended`: require a fresh exact event ID, the suspended state's expected version, and a still-effective source approval, and reject reactivation at or after the grant's expiry. A policy edit alone never reactivates a grant.
   - Apply `expired` only at or after the grant's exact `expires_at`; a grant without an expiry cannot take that transition.
   - Cascade revoke/expire to descendants. Suspension need not mutate every descendant projection, but an inactive ancestor makes every child unusable while that lineage remains invalid.

## Policy operations

Use these human-policy operations without conflating them with runtime leases:

- `summarize`: return effective policy and open questions.
- `ensure_default`: create the template only when a caller requires durable policy and no file exists.
- `draft_for_interview`: write `.interview/drafts/agent_authority.md` from interview evidence.
- `finalize_from_interview`: write final policy only after interview review, user confirmation, and agent write-confirmation gates.
- `update`: preserve supported user decisions and make only explicitly authorized changes.
- `validate`: reject capability expansion, unsupported sources, sensitive content, and precedence violations.

## Domain adapter contract

Accept optional project-owned hooks:

- `authority_axis_classify(...)`: classify a candidate as `already_granted`, `self_resolvable`, or `genuine_authority` with opaque evidence. Treat malformed or absent output as `authority_axis_unclassified`.
- `policy_consumption_sites(...)`: list opaque consumer sites and `reflects_policy`. Record false sites as `policy_propagation_incomplete` debt. Treat missing evidence as `propagation=unverified`.

Never let an adapter grant authority, lower a manifest requirement, manufacture external input, or define a broader generic capability. Use it only to narrow escalation through domain semantics.

## Legacy bridge

Keep `python3 -m manage_agent_authority receipt issue|validate` compatible with schema v1. Preserve v1 validation against the exact current file binding; do not silently reinterpret old receipts. Issue schema-v2 receipts with immutable policy/source snapshots so later policy edits do not invalidate them. Treat an unprovable legacy decision as historical partial/unverified, not retroactively allowed.

## Report contract

Return the same compact interaction projection from both status and resolve: `outcome`, `workflow_state`, `should_prompt`, nullable `user_action`, and one `next_action`. Set `outcome=workflow_state` to the selected machine state. Set `user_action=next_action` only when its actor is `user`; otherwise use `null`. Keep operation-specific detail, typed intent, reasons, exact subject, capabilities, axes, grant budget versus reservation units, immutable bindings, lifecycle version, scoped fingerprint, and conflicts in structured detail. Do not embed raw private or copyrighted source text.

For exact-request consumers, preserve `request_sha256_filter`, `workflow_basis`, and the exact decision, reservation/state, source-approval, recovery-recipe, settlement-receipt, and blocker bindings that justify the selected state. Public system states include `effect_reconciliation`, `already_consumed`, `already_released`, `ready_to_resume`, `reserved_authority_recovery`, `ready_to_reserve`, `source_approval_ready_for_grant`, `source_authority_defect`, and `source_authority_exhausted`. The only user-prompt state is `needs_user_approval`; its recovery variant uses `approve_exact_recovery_projection`. `idle` and `decision_<typed-decision>` remain non-prompt routing states.

## Guardrails

- Do not bypass active sandbox, approval, network, filesystem, model, tool, credential, cost, or higher-priority instruction limits.
- Do not use advice, task completion, validation success, issue status, silence, or a tier label as authority evidence.
- Do not use wildcard capabilities, wildcard subjects, implicit grant unions, self-delegation, circular delegation, rank escalation, retroactive receipts, or current mutable policy hashes for new receipts.
- Do not let task authority imply action authority, improvement authority rewrite core GT, authority imply risk consent, or approval imply external-input availability.
- Do not retry an unchanged approval wait as a new task. Replay the exact request and wake only when its scoped authority fingerprint or separate required input changes.
- Do not expose internal missing-grant state as a user approval when an exact effective source approval can materialize the grant.
- Do not turn an exhausted, revoked, expired, or source-conflicted existing grant ID into another approval for the same projection. Rebuild a new exact grant recipe first.
- Do not release a reservation with unknown effects. Quarantine it for evidence-backed recovery.
- Do not store secrets, credentials, tokens, raw private transcripts, or large copyrighted excerpts in authority artifacts.
