---
name: normalize-acceptance-and-demo
description: "Normalize task acceptance criteria and demo evidence before governance. Use in `$orchestrate-task-cycle` after authority resolution and before `$task-md-agent-governance` to make acceptance checks, expected visible behavior, demo artifacts, validation commands, and non-goals explicit."
---

# Normalize Acceptance And Demo

## Overview

Use this skill to turn an active `task.md` into a concise acceptance packet that code-writing and validation steps can follow.

## Workflow

1. Read only workflow-level task context: `task.md`, authority summary, non-GT advice packet, schema/contract summaries, and existing cycle ledger.
2. Extract acceptance criteria, non-goals, expected visible/demo surfaces, required validation commands, and forbidden shortcuts.
3. When an acceptance criterion has an abstract measurable target, bind the criterion to the minimum executable envelope when a repository adapter or caller packet exposes `min_envelope_for(target) -> {envelope_floor, deficit_axis}`. Record this as `acceptance_envelope_contract` in the packet. If the hook is absent or cannot compare the target, keep the existing acceptance wording and emit only a warning.
4. For measurable targets, also bind the criterion to a live verifier when a repository adapter or caller packet exposes a target-to-verifier mapping such as `target_required_verifier(target, **context) -> {required_verifier, verifier_required}`. Record this as `acceptance_verifier_contract`.
   - If the required verifier is present and evaluated, preserve its `evaluation_status: pass|fail|not_evaluated`.
   - If the required verifier is absent or fail-quiet, normalize the target as `unverifiable_acceptance_contract=true`; `not_evaluated` is not a pass and downstream close must be `partial` unless an explicit descope plus residual follow-up exists.
   - If the mapping hook is absent, fail quiet and keep existing acceptance rules. Do not invent verifier names in this generic skill.
5. When a measurable criterion names or depends on a gate whose SKILL.md contract lists required adapter hooks, treat those hooks as verifier completeness for that criterion. If a required hook is absent, unloaded, fail-quiet, or reports `evaluation_status: not_evaluated`, set `unverifiable_acceptance_contract=true` and preserve a hook-supply follow-up. If no acceptance/caller contract requires that gate, keep the existing fail-quiet behavior.
6. Treat a proposed execution slice below the adapter-supplied `envelope_floor` as an acceptance-incomplete slice, not as a later runtime/tool/prompt blocker. Do not lower the measurable acceptance target to fit the smaller slice; require envelope expansion, explicit descope with residual scope, or user escalation by downstream selection.
7. When a repository adapter or caller packet reports the target is unreachable under a frozen envelope, preserve `acceptance_unreachable_under_frozen_config=true`, `frozen_envelope`, `deficit_axis`, and a reserved `envelope_thaw_item` when one is supplied. If no thaw item is supplied, set `envelope_thaw_item_required=true` so `$audit-cycle-loopback` and `$derive-improvement-task` must reserve an envelope thaw, constraint relaxation, explicit descope, terminal blocker, or user escalation instead of continuing envelope-internal repair.
8. For measurable targets with a residual acceptance gap, preserve adapter-owned residual-gap comparison inputs when a repository adapter or caller packet exposes `residual_gap_policy(target, **context) -> {threshold, basis}` or equivalent fields. Record abstract fields such as `residual_gap_ratio`, `residual_gap_policy`, and `marginal_repair_candidate`; keep domain thresholds and metric definitions in the adapter. If a cycle-efficiency/profile packet supplies cost evidence, also record `cycle_fixed_cost`, `alternative_cycle_cost`, `marginal_gap_value`, `marginal_value_per_cycle_cost`, and `alternative_value_per_cycle_cost`. If cost evidence is absent, use denominator `1` and preserve the existing F3 comparison.
9. Mark unclear, missing, or unverifiable criteria as blockers or assumptions rather than silently widening scope.
10. Save the normalized packet under `.task/cycle/<cycle-id>/packets/acceptance.md` when a cycle ledger exists.
11. Pass the packet to `$task-md-agent-governance` and `$plan-validation-scope`.

## Guardrails

- Do not add new product requirements that are not implied by the task, goal truth, or active non-GT advice.
- Do not edit implementation files.
- Do not treat demo evidence as validation evidence unless the task explicitly defines it as the validation command.
- Do not hardcode project-specific metric names, capacities, work counts, model limits, hardware limits, file paths, or thresholds in this skill. Keep them behind `min_envelope_for` or project-owned contracts, and fail quiet when that hook is absent.
- Do not treat a missing required verifier as successful validation. Preserve `not_evaluated` and `unverifiable_acceptance_contract` for `$derive-improvement-task` and `$validate-task-completion`.
- Do not treat a missing required gate hook as successful validation when measurable acceptance depends on that gate. Route it through the same `unverifiable_acceptance_contract` path.
- Do not continue frozen-envelope-internal repair as ordinary progress when the acceptance minimum is unreachable. Preserve `envelope_thaw_item_required` or the concrete `envelope_thaw_item` so downstream selection can thaw/relax/descope/escalate explicitly.
- Do not make residual gap repair the default merely because a gap exists. Preserve adapter residual-gap policy fields for `$derive-improvement-task`; if the adapter is absent, do not invent a threshold.
- Do not ignore cycle fixed cost when it is supplied. Residual repair must be compared by value per cycle cost before another same-gap repair is made the default.
