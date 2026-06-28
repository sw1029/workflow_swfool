---
name: optimize-task-slice
description: "Classify next-task granularity before `$derive-improvement-task`. Use to advise whether candidates should be state-transition work, batched no-live micro-contracts, evidence-supply/preflight work, narrowed work, or a blocker; never use it to replace `$derive-improvement-task` xhigh synthesis or final task selection."
---

# Optimize Task Slice

## Overview

Use this skill as an advisory pre-derive classifier. It helps prevent repeated tiny no-live tasks while leaving final task selection to `$derive-improvement-task`.

## Workflow

1. Review progress-loop output, active blockers, recent completed tasks, candidate tasks, validation scope, and anti-loop signals such as `vacuous_untried_streak`, `hypothesis_exhausted`, and `forward_mutation_vacuous`.
2. Classify the next slice:
   - `state_transition`
   - `batchable_micro_contract`
   - `evidence_supply`
   - `bounded_preflight`
   - `narrow_current_only`
   - `stop_with_blocker`
   - `root_cause_repair_or_stop`
3. Explain the blocker-state transition the next task should unlock.
4. Pass the advisory packet to `$derive-improvement-task`.

## Guardrails

- Do not write `task.md`.
- Do not delete or apply candidates.
- Do not downgrade `$derive-improvement-task` fixed `reasoning_effort: xhigh` routing.
- Do not claim final next-task choice authority.
- Do not recommend another same-family untried repair when `hypothesis_exhausted=true`; recommend `stop_with_blocker` unless a supplied input delta or explicit user override exists.
