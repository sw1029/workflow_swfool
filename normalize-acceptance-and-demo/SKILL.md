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
4. Treat a proposed execution slice below the adapter-supplied `envelope_floor` as an acceptance-incomplete slice, not as a later runtime/tool/prompt blocker. Do not lower the measurable acceptance target to fit the smaller slice; require envelope expansion, explicit descope with residual scope, or user escalation by downstream selection.
5. Mark unclear or missing criteria as blockers or assumptions rather than silently widening scope.
6. Save the normalized packet under `.task/cycle/<cycle-id>/packets/acceptance.md` when a cycle ledger exists.
7. Pass the packet to `$task-md-agent-governance` and `$plan-validation-scope`.

## Guardrails

- Do not add new product requirements that are not implied by the task, goal truth, or active non-GT advice.
- Do not edit implementation files.
- Do not treat demo evidence as validation evidence unless the task explicitly defines it as the validation command.
- Do not hardcode project-specific metric names, capacities, work counts, model limits, hardware limits, file paths, or thresholds in this skill. Keep them behind `min_envelope_for` or project-owned contracts, and fail quiet when that hook is absent.
