# Tiered Configured Model And Effort Routing

Use [model-effort-profiles.json](model-effort-profiles.json) as the executable policy and `scripts/model_effort_router.py` as the deterministic selector. Keep role/tier policy global and keep runtime model bindings in caller configuration or a repository adapter.

## Tier Contract

| Tier | Model reference | Effort | Work class |
| --- | --- | --- | --- |
| `1` | `model_ref:balanced` | `low` | Mechanical, reversible finalization |
| `2` | `model_ref:balanced` | `medium` | Routine bounded implementation or bookkeeping |
| `3` | `model_ref:balanced` | `high` | Complex analysis, planning, or high-reliability implementation |
| `4` | `model_ref:balanced` | `xhigh` | Decisive review, completion control, or cross-contract analysis without final direction authority |
| `5` | `model_ref:direction` | `xhigh` | Final core-direction, architecture, task topology, or terminal arbitration |

Treat model references as abstract routing identities, not runnable provider model names. Deterministic scripts and direct shell commands are outside Tiers 1-5; record them as `agent_routing_applicability: deterministic_only`.

## Direction Boundary

Use the Tier 5 direction profile only when the agent owns a final direction-changing decision, not merely because the work is difficult.

Suitable Tier 5 surfaces:

- final next-`task.md` synthesis and candidate selection;
- final GT/authority conflict resolution;
- task-pack insertion, reordering, supersession, or terminal disposition selection;
- final architecture direction that changes future module or contract ownership;
- security direction decisions or terminal/user-escalation arbitration.

Keep code writing, analysis, review, candidate generation, ID/index work, and Git finalization on the bounded non-direction profiles even when important. Tier 4 is the boundary for agents that judge evidence but do not own the final future direction.

## Model Binding Contract

Resolve abstract model references through `model_bindings` supplied by the caller or a repository adapter. Do not put provider names or deployment-specific model identifiers in this global skill.

Each binding is keyed by a policy model reference and contains:

```json
{
  "model_ref:balanced": {
    "model": "runtime-model-alpha",
    "binding_id": "binding-alpha",
    "source": "caller_configuration"
  }
}
```

Use only `caller_configuration` or `repository_adapter` as `source`. Treat binding identifiers as opaque. The selector emits:

- `requested_model_ref`: stable abstract policy identity;
- `requested_model`: the resolved runtime value, or the abstract reference when no binding was supplied;
- `model_configuration_status`: `resolved`, `reference_only`, or `invalid`;
- `model_binding_receipt` when resolved, including a SHA-256 of the resolved model value and a canonical receipt hash bound to the model reference, binding ID, source, and model digest.

Allow `reference_only` for planning and prompt-only evidence. Reject `routing_enforcement: enforced` unless the model configuration is `resolved` and the content-bound binding receipt revalidates against the selected model reference and requested model value. Invalid, incomplete, unknown, conflicting, or tampered bindings fail closed.

## Dynamic Selection

Select the role profile first. Each profile defines `default_tier`, `min_tier`, and `max_tier`. Then apply only structured routing input from:

```text
model_effort_routing.profiles.<profile_id>
```

Accepted fields are `final_direction_ownership`, `signals`, `signal_evidence`, `request_max`, `max_escalation_reason`, `prior_tier5_evidence`, `agent_count`, and the caller-owned `model_bindings`. The selector may promote within profile bounds; it never bypasses the role maximum. Direct `requested_tier` overrides are prohibited.

Promotion signals:

- Tier 3 floor: `high_reliability`, `durable_state_mutation`, `security_sensitive`.
- Tier 4 floor: `completion_controlling`, `compatibility_controlling`, `irreversible_cleanup`, `cross_contract_conflict`.
- Tier 5 floor: both `direction_setting` and `final_decision`, or one of `gt_authority_conflict`, `terminal_disposition`, `task_pack_topology_change`, `architecture_direction_change`, `security_direction_decision`.

Do not infer signals from prose, file names, task labels, or model self-assessment. A profile capable of optional Tier 5 promotion must explicitly classify `final_direction_ownership: true|false`. Every Tier 5 signal requires `signal_evidence.<signal>` as a structured reference object containing an opaque `event_id`, `run_id`, `artifact_id`, or `ledger_event_id`; a bare string is invalid. Unknown signals, direct tier overrides, ownership/signal contradictions, missing signal evidence, and requests outside profile bounds are routing violations.

Use the selector directly when needed:

```bash
python3 scripts/model_effort_router.py \
  --profile schema_planning \
  --request '{"final_direction_ownership":true,"signals":{"architecture_direction_change":true},"signal_evidence":{"architecture_direction_change":{"artifact_id":"evidence-004"}}}'
```

## Bounded Maximum And Prohibited Delegation

Tier 5 defaults to the direction model reference at `xhigh`. Use `max` only when all conditions hold:

- the selected profile allows max;
- a Tier 5 direction-profile `xhigh` pass already ran;
- `prior_tier5_unresolved=true`;
- `prior_tier5_evidence` contains an opaque locator, `profile_id: derive_synthesis`, `routing_tier: 5`, `requested_model_ref: model_ref:direction`, `requested_reasoning_effort: xhigh`, and `unresolved_finding_id`;
- `max_escalation_reason` names the unresolved high-impact ambiguity;
- exactly one arbitration agent runs.

Do not use `max` as a phase default or parallel fanout. Do not use delegated `ultra`; automatic delegation conflicts with orchestrator-owned fanout, write scopes, reviewer counts, and ordering. A caller-selected root `ultra` session is outside this skill's enforceable child routing and must not propagate to children.

## Evidence Contract

For agent-capable phases, record `agent_routing_applicability: delegated|deterministic_only|delegation_unavailable`. Delegated results record:

- `policy_id`, `profile_id`, `routing_tier`;
- `requested_model_ref`, `requested_model`, `model_configuration_status`, and optional `model_binding_receipt`;
- `requested_reasoning_effort`;
- `routing_reason_codes`, non-empty `routing_signals` plus `routing_signal_evidence` when dynamically promoted, and `routing_violations` even when empty;
- `routing_enforcement: enforced|prompt_only|inherited_unverified`;
- optional `actual_model` and `actual_reasoning_effort` when exposed;
- `routing_limitation` when not enforced;
- max precondition evidence when bounded `max` ran.

Do not claim the requested model or effort actually ran without runtime evidence. Do not claim enforced routing from `reference_only` configuration. Higher tiers do not grant broader authority, write scope, network permission, validation ownership, or permission to weaken acceptance.

## Default Phase Mapping

- Governance: code worker Tier 2; high-reliability worker and analysis Tier 3; important review Tier 4.
- Validation set: planning/labeling Tier 3; final adjudication Tier 4.
- Qualitative and completion review: Tier 4.
- Loopback: deterministic first; optional threshold reviewer Tier 4.
- Derive: inspectors/candidate agents Tier 3; cross-contract analysis Tier 4; final synthesis Tier 5; bounded max only after unresolved Tier 5.
- Schema planning: Tier 3 by default; Tier 5 only for final architecture-direction ownership.
- ID/index: Tier 2. Commit: Tier 1.
