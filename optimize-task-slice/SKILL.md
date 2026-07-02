---
name: optimize-task-slice
description: "Classify next-task granularity before `$derive-improvement-task`. Use to advise whether candidates should be state-transition work, batched no-live micro-contracts, evidence-supply/preflight work, narrowed work, semantic consolidation, reuse extraction, coupling reduction, or a blocker; never use it to replace `$derive-improvement-task` xhigh synthesis or final task selection."
---

# Optimize Task Slice

## Overview

Use this skill as an advisory pre-derive classifier. It helps prevent repeated tiny no-live tasks while leaving final task selection to `$derive-improvement-task`.

## Workflow

1. Review progress-loop output, active blockers, recent completed tasks, candidate tasks, validation scope, and anti-loop signals such as `vacuous_untried_streak`, `hypothesis_exhausted`, and `forward_mutation_vacuous`.
   - Identify whether any candidate descends from a measurable user/advice/issue directive with an original target.
2. Classify the next slice:
   - `state_transition`
   - `batchable_micro_contract`
   - `evidence_supply`
   - `bounded_preflight`
   - `narrow_current_only`
   - `semantic_consolidation`: merge numbered/mechanical shards into meaningfully named modules while preserving public behavior.
   - `reuse_extraction`: extract duplicated or repeated logic into the repository-owned reuse/kernel layer and update callers to depend on it.
   - `coupling_reduction`: replace global rebinding, hidden import-time mutation, or cross-layer references with explicit parameters, dependency injection, or stable contracts.
   - `stop_with_blocker`
   - `root_cause_repair_or_stop`
3. Explain the blocker-state transition the next task should unlock.
4. When recommending `narrow_current_only` for a measurable directive-derived item, include `narrowing_of_measurable_target=true`, the `directive_id`, the original target summary, and whether an explicit residual item is required.
5. When a measurable target includes `acceptance_envelope_contract`, classify slices below `envelope_floor` as envelope-incomplete. Recommend envelope expansion, evidence supply, explicit descope with residual scope, or `stop_with_blocker`; do not recommend `narrow_current_only` merely to make a too-small envelope look successful.
6. When anti-loop evidence includes `root_dominant_parameter_key`, keep the collapsed root plus that parameter as the same blocker family in the advisory packet even if proximate labels changed.
7. When anti-loop evidence includes `primary_metric_stalled=true` or `c4_user_escalation_backstop_required=true`, preserve the forced-retarget or user-escalation recommendation as advisory evidence for `$derive-improvement-task`; do not replace it with another measurement or label-only repair.
8. When recommending a structure class, include `recommended_task_kind` using the same stable value (`semantic_consolidation`, `reuse_extraction`, or `coupling_reduction`) so `$derive-improvement-task` can compare it with gate-constrained `allowed_task_kinds`.
9. When recommending a structure class, include `structure_slice_basis` with the triggering evidence: code-structure audit packet fields, `structure_metrics_gate`, convention violation, task_miss, active advice, or repo-local adapter gap.
10. Preserve original measurable structure targets. Do not let `semantic_consolidation`, `reuse_extraction`, or `coupling_reduction` shrink a directive into a pilot unless a residual item remains open.
11. Pass the advisory packet to `$derive-improvement-task`.

## Guardrails

- Do not write `task.md`.
- Do not delete or apply candidates.
- Do not downgrade `$derive-improvement-task` fixed `reasoning_effort: xhigh` routing.
- Do not claim final next-task choice authority.
- Do not recommend another same-family untried repair when `hypothesis_exhausted=true`; recommend `stop_with_blocker` unless a supplied input delta or explicit user override exists.
- Do not treat `pilot`, `plan`, `slice`, or `bounded` wording as permission to weaken a measurable target. Emit the narrowing warning and leave final descope/residual handling to `$derive-improvement-task`.
- Do not turn an adapter-reported envelope deficit into a weaker target. Keep `envelope_floor`, `deficit_axis`, and residual scope as advisory fields for derive.
- Do not recommend structure work as goal-productive solely because it creates more files or modules. Require a credible path to lower coupling, remove mechanical shards, reduce duplication, improve reuse ratio, reduce LOC/depth/fan-out pressure, or unblock a named task transition.
- Do not invent project-specific naming, depth, fan-out, kernel, or dependency rules. Consume the repo-owned `code_convention_contract` or mark the structure recommendation warn-only.
