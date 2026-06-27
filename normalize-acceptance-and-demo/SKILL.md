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
3. Mark unclear or missing criteria as blockers or assumptions rather than silently widening scope.
4. Save the normalized packet under `.task/cycle/<cycle-id>/packets/acceptance.md` when a cycle ledger exists.
5. Pass the packet to `$task-md-agent-governance` and `$plan-validation-scope`.

## Guardrails

- Do not add new product requirements that are not implied by the task, goal truth, or active non-GT advice.
- Do not edit implementation files.
- Do not treat demo evidence as validation evidence unless the task explicitly defines it as the validation command.
