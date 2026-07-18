---
name: manage-agent-authority
description: Manage deterministic workspace authority policy, grants, leases, and subject-bound receipts without expanding active permissions. Use when Codex must summarize or update `.agent_goal/agent_authority.md`; distinguish approval, goal ratification, risk acceptance, external-input supply, and design choice; evaluate a versioned skill operation against S0-S4 source rank, R0-R3 risk, D0-D3 decision class, exact subject scope, capability namespace, and use budget; reserve/consume/release authority; delegate, suspend, explicitly reactivate, expire, or revoke a grant; or validate legacy and immutable operation receipts.
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
   - Bind skill/operation IDs and versions, cycle/task/pack/attempt IDs, actor rank, exact subject `{kind, ref, digest, revision}`, namespaced capabilities, effect/data/mutation/reversibility, risk, decision class, requested cardinality/use budget, and idempotency key.
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

When the decision is `approval_required`, present the deterministic `approval_projection`: typed intent, exact operation/subject/capabilities/effect, bounded scope and budget, excluded effects, safe alternative, reason codes, and replay key. An approval of that projection does not authorize any excluded effect or broader reuse.

6. Reserve before dispatch.
   - Bind the persisted allowed decision by path and SHA-256.
   - Re-evaluate under a lock, verify the subject, operation manifest, selected grant and every lineage ancestor state/version, policy snapshot, expiry, scope, and available budget, then create a reservation and CAS-update usage across the lineage.
   - Treat an exact idempotent replay as the same reservation. Reject a conflicting replay.
   - Treat immutable event `state_changes` as a write-ahead recovery intent. Before every lifecycle/transition entry, scan all intents, complete each uniquely connected exact `before -> after` projection, accept an already-applied `after` or exact recorded descendant, and quarantine competing/unconnected state.

7. Verify before commit, then consume or release.
   - Run `authority verify --stage pre_commit` before committing effects.
   - Bind an immutable execution-result artifact and run `authority consume` after a known effect.
   - Run `authority release` only with evidence of `not_started` or `verified_no_effect`.
   - Quarantine `unknown_effect`; do not restore its reserved budget automatically.

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

Return the operation, typed intent, decision/reasons, exact subject, required and covering capabilities, source/risk/decision axes, cardinality and remaining budget, immutable artifact refs/digests, lifecycle state/version, effective scoped fingerprint, open questions, and conflicts. For orchestration, also return a compact Korean summary without embedding raw private or copyrighted source text.

## Guardrails

- Do not bypass active sandbox, approval, network, filesystem, model, tool, credential, cost, or higher-priority instruction limits.
- Do not use advice, task completion, validation success, issue status, silence, or a tier label as authority evidence.
- Do not use wildcard capabilities, wildcard subjects, implicit grant unions, self-delegation, circular delegation, rank escalation, retroactive receipts, or current mutable policy hashes for new receipts.
- Do not let task authority imply action authority, improvement authority rewrite core GT, authority imply risk consent, or approval imply external-input availability.
- Do not retry an unchanged approval wait as a new task. Replay the exact request and wake only when its scoped authority fingerprint or separate required input changes.
- Do not release a reservation with unknown effects. Quarantine it for evidence-backed recovery.
- Do not store secrets, credentials, tokens, raw private transcripts, or large copyrighted excerpts in authority artifacts.
