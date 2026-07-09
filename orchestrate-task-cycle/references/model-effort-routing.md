# Tiered GPT-5.6 Model And Effort Routing

Use [model-effort-profiles.json](model-effort-profiles.json) as the executable policy and `scripts/model_effort_router.py` as the deterministic selector. Use this file for selection semantics and ownership boundaries.

## Tier Contract

| Tier | Model | Effort | Work class |
| --- | --- | --- | --- |
| `1` | `gpt-5.6-terra` | `low` | Mechanical, reversible finalization |
| `2` | `gpt-5.6-terra` | `medium` | Routine bounded implementation or bookkeeping |
| `3` | `gpt-5.6-terra` | `high` | Complex analysis, planning, or high-reliability implementation |
| `4` | `gpt-5.6-terra` | `xhigh` | Decisive review, completion control, or cross-contract analysis without final direction authority |
| `5` | `gpt-5.6-sol` | `xhigh` | Final core-direction, architecture, task topology, or terminal arbitration |

Deterministic scripts and direct shell commands are outside Tiers 1-5. Record them as `agent_routing_applicability: deterministic_only`.

## Sol Boundary

Use Tier 5 Sol only when the agent owns a final direction-changing decision, not merely because the work is difficult.

Suitable Tier 5 surfaces:

- final next-`task.md` synthesis and candidate selection;
- final GT/authority conflict resolution;
- task-pack insertion/reordering/supersession or terminal disposition selection;
- final architecture direction that changes future module or contract ownership;
- security direction decisions or terminal/user-escalation arbitration.

Keep these on Terra even when important:

- code writing, including high-reliability core logic;
- repository, OOM, issue, task-miss, validation-set, or code analysis;
- qualitative review and completion validation;
- candidate generation and recommendation-only architecture analysis;
- ID/index work and Git finalization.

Tier 4 is the boundary for agents that judge evidence but do not own the final future direction. Do not upgrade an ordinary worker or reviewer to Sol.

## Dynamic Selection

Select the role profile first. Each profile defines `default_tier`, `min_tier`, and `max_tier`. Then apply only structured routing input from:

```text
model_effort_routing.profiles.<profile_id>
```

Accepted fields are `final_direction_ownership`, `signals`, `signal_evidence`, `request_max`, `max_escalation_reason`, `prior_tier5_evidence`, and `agent_count`. The selector may promote within the profile bounds; it never bypasses the role maximum. Direct `requested_tier` overrides are prohibited so a caller cannot bypass the signal contract.

Promotion signals:

- Tier 3 floor: `high_reliability`, `durable_state_mutation`, `security_sensitive`.
- Tier 4 floor: `completion_controlling`, `compatibility_controlling`, `irreversible_cleanup`, `cross_contract_conflict`.
- Tier 5 floor: both `direction_setting` and `final_decision`, or one of `gt_authority_conflict`, `terminal_disposition`, `task_pack_topology_change`, `architecture_direction_change`, `security_direction_decision`.

Do not infer these signals from prose, file names, task labels, or model self-assessment. A profile capable of optional Tier 5 promotion must explicitly classify `final_direction_ownership: true|false`; omission is a routing violation. The caller or owning skill must supply booleans with evidence. Every Tier 5 signal requires `signal_evidence.<signal>` as a structured reference object containing `path`, `event_id`, `run_id`, `artifact_id`, or `ledger_event_id`; a bare string is invalid. Without valid evidence the signal is disabled and the selector emits `tier5_signal_evidence_missing`. Unknown signals, direct tier overrides, ownership/signal contradictions, and requests outside profile bounds produce routing violations.

Use the selector directly when needed:

```bash
python3 scripts/model_effort_router.py \
  --profile schema_planning \
  --request '{"final_direction_ownership":true,"signals":{"architecture_direction_change":true},"signal_evidence":{"architecture_direction_change":{"path":".schema/decision-004.md"}}}'
```

## Max And Ultra

Tier 5 defaults to Sol `xhigh`. Use Sol `max` only when all conditions hold:

- the selected profile allows max;
- a Tier 5 Sol/xhigh pass already ran;
- `prior_tier5_unresolved=true`;
- `prior_tier5_evidence` is a structured reference containing a path/event locator, `profile_id: derive_synthesis`, `routing_tier: 5`, `requested_model: gpt-5.6-sol`, `requested_reasoning_effort: xhigh`, and `unresolved_finding_id`;
- `max_escalation_reason` names the unresolved high-impact ambiguity;
- exactly one arbitration agent runs.

Do not use `max` as a phase default or parallel fanout. Do not use delegated `ultra`; automatic delegation conflicts with orchestrator-owned fanout, write scopes, reviewer counts, and ordering. A caller-selected root `ultra` session is outside this skill's enforceable child routing and must not propagate to children.

## Evidence Contract

For agent-capable phases, record `agent_routing_applicability: delegated|deterministic_only|delegation_unavailable`. Delegated results record:

- `policy_id`, `profile_id`, `routing_tier`;
- `requested_model`, `requested_reasoning_effort`;
- `routing_reason_codes`, non-empty `routing_signals` plus `routing_signal_evidence` when dynamically promoted, and `routing_violations` even when empty;
- `routing_enforcement: enforced|prompt_only|inherited_unverified`;
- optional `actual_model` and `actual_reasoning_effort` when exposed;
- `routing_limitation` when not enforced;
- max precondition evidence when Sol `max` ran.

Do not claim the requested model or effort actually ran without runtime evidence. Higher tiers do not grant broader authority, write scope, network permission, validation ownership, or permission to weaken acceptance.

## Default Phase Mapping

- Governance: code worker Tier 2; high-reliability worker and analysis Tier 3; important review Tier 4.
- Validation set: planning/labeling Tier 3; final adjudication Tier 4.
- Qualitative and completion review: Tier 4.
- Loopback: deterministic first; optional threshold reviewer Tier 4.
- Derive: inspectors/candidate agents Tier 3; cross-contract analysis Tier 4; final synthesis Tier 5; bounded max only after unresolved Tier 5.
- Schema planning: Tier 3 by default; Tier 5 only for final architecture-direction ownership.
- ID/index: Tier 2. Commit: Tier 1.
