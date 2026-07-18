---
name: optimize-task-slice
description: "Classify next-task granularity before `$derive-improvement-task`. Use to advise whether candidates should be state-transition work, batched no-live micro-contracts, evidence-supply/preflight work, narrowed work, semantic consolidation, reuse extraction, coupling reduction, or a blocker; never use it to replace `$derive-improvement-task` xhigh synthesis or final task selection."
---

# Optimize Task Slice

`authority.operations.json` declares this advisory classification as read-only under the shared [authority v2 contract](../manage-agent-authority/references/authority-v2-contract.md). It cannot publish or reorder task state; those effects remain with derive/task-pack owners.

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
   - `verifier_completion`: implement or repair a required live verifier for a measurable acceptance target that is currently `not_evaluated`.
   - `independent_revalidation`: re-run or recalculate evidence after a verifier source changed in the same change set.
   - `gate_hook_supply`: supply or repair a required adapter hook for an acceptance-referenced gate that is currently absent or `not_evaluated`.
   - `quality_axis_supply`: supply adapter-owned quality/vector axes for active measurable goals whose review pass has `pass_with_unobserved_axes=true`.
   - `classification_stage_repair`: repair terminal classification or same-input comparison contracts when observed execution stages contradict the terminal family or input sets mismatch.
   - `diagnostic_instrumentation`: supply scalar diagnostics for a repeated `diagnostics_unavailable` failure surface, unless the task records why existing evidence already observes success/failure.
   - `verification_source_repair`: supply disjoint verification inputs or downgrade affected independent fields to attested when verification inputs are missing or overlap verified artifacts.
   - `envelope_thaw_item`: reserve thaw condition/schedule, constraint relaxation, residual descope, terminal blocker, or user escalation for unreachable acceptance under a frozen envelope.
   - `current_lane_revalidation`: rerun or revalidate the current decision lane when a pass belongs to a stale production lane.
   - `fresh_decision_measurement`: rerun measurement or prove no-impact when a decision update only relabels artifacts from before an upstream contract change.
   - `producer_supply`: implement or fire the producer path for a starved gating axis before more verifier/report work.
   - `long_run_or_throughput`: launch/monitor/harvest a long run or improve throughput when target scale is unreachable inside one cycle.
   - `metric_basis_repair`: supply basis-compatible inputs or downgrade a metric contract when claimed basis is not derivable.
   - `surface_field_repair`: repair producer-written surface field classes or preserve residual scope after qualitative field defects.
   - `descope_with_residual`: preserve explicit partial acceptance plus residual scope when residual gap marginal value is below the adapter policy threshold.
   - `cost_disproportionate_residual`: preserve residual scope or move to the next rung when residual-gap value per cycle cost is below policy.
   - `stop_with_blocker`
   - `root_cause_repair_or_stop`
3. Explain the blocker-state transition the next task should unlock.
4. When recommending `narrow_current_only` for a measurable directive-derived item, include `narrowing_of_measurable_target=true`, the `directive_id`, the original target summary, and whether an explicit residual item is required.
5. When a measurable target includes `acceptance_envelope_contract`, classify slices below `envelope_floor` as envelope-incomplete. Recommend envelope expansion, evidence supply, explicit descope with residual scope, or `stop_with_blocker`; do not recommend `narrow_current_only` merely to make a too-small envelope look successful.
6. When a measurable target includes `acceptance_verifier_contract` and the required verifier is `not_evaluated`, classify the slice as `verifier_completion` or `stop_with_blocker`. Recommend verifier-hook implementation, explicit descope with residual scope, or user escalation; do not recommend consuming the target.
7. When a measurable target depends on an acceptance-referenced gate whose required adapter hook is absent or `not_evaluated`, classify the slice as `gate_hook_supply` or `stop_with_blocker`. Do not recommend consuming the target through fail-quiet.
8. When anti-loop evidence includes `pass_with_coupled_verifier=true`, classify the slice as `independent_revalidation` or `stop_with_blocker`; do not recommend consuming the coupled verifier pass.
9. When anti-loop evidence includes `attested_only_movement=true`, keep it as no high-water movement and recommend independent recalculation, goal-productive correction, forced retarget, or blocker handling rather than another producer-attested scalar.
10. When review evidence includes `pass_with_unobserved_axes=true`, classify the slice as `quality_axis_supply`, output-producing work that supplies the missing axis through the adapter, `descope_with_residual`, or `stop_with_blocker`. Do not recommend consuming the review pass for the affected measurable goal.
11. When a measurable target includes `residual_gap_policy` and the residual gap ratio is below the adapter threshold, classify another same-gap repair as `marginal_repair` and recommend `descope_with_residual` plus the next capability-ladder rung unless the evidence shows higher marginal value. If cycle-cost evidence is supplied and value per cycle cost is below policy, classify it as `cost_disproportionate_residual`.
12. When anti-loop evidence includes `root_dominant_parameter_key`, keep the collapsed root plus that parameter as the same blocker family in the advisory packet even if proximate labels changed.
13. When anti-loop evidence includes generation-dependent key contamination, keep the effective root-family key in the advisory packet and mark the raw key trace-only.
14. When anti-loop evidence includes `primary_metric_stalled=true` or `c4_user_escalation_backstop_required=true`, preserve the forced-retarget or user-escalation recommendation as advisory evidence for `$derive-improvement-task`; do not replace it with another measurement or label-only repair.
15. When anti-loop evidence includes `terminal_classification_stage_contradiction=true`, `terminal_classification_invalid_for_counting=true`, or `same_input_contract_violation=true`, classify the slice as `classification_stage_repair`, `diagnostic_instrumentation`, `stop_with_blocker`, or escalation; do not recommend ordinary same-family repair as progress.
16. When anti-loop evidence includes `instrumentation_supply_required=true`, classify the slice as `diagnostic_instrumentation` unless the candidate includes a concrete observability rationale proving success/failure is already measurable without new instrumentation.
17. When validation or loopback evidence includes non-disjoint independent verification (`independent_source_separation_status=missing|overlap|blocked` or `independently_verified_downgraded_fields`), classify the slice as `verification_source_repair`, attested-only consumption with residual scope, or `stop_with_blocker`; do not recommend high-water consumption.
18. When acceptance evidence includes `envelope_thaw_item_required=true`, classify the slice as `envelope_thaw_item`, constraint relaxation, descope-with-residual, terminal blocker, or user escalation; do not recommend another frozen-envelope-internal repair as progress.
19. When Part L evidence is present, classify the slice as one of the matching advisory kinds above: current-lane revalidation for `pass_on_stale_lane`, fresh decision measurement or no-impact proof for `decision_metadata_revision`, producer supply for `axis_starved_by_missing_producer`, producer/envelope/long-run/descope/terminal/escalation for restrictive `portfolio_quota_exceeded`, long-run/throughput/descope/terminal/escalation for `unreachable_within_cycle`, metric-basis repair for `basis_overclaim`, or surface-field repair/residual for nonzero `surface_field_defect_matrix`.
20. When recommending a structure class, include `recommended_task_kind` using the same stable value (`semantic_consolidation`, `reuse_extraction`, or `coupling_reduction`) so `$derive-improvement-task` can compare it with gate-constrained `allowed_task_kinds`.
21. When recommending a structure class, include `structure_slice_basis` with the triggering evidence: code-structure audit packet fields, `structure_metrics_gate`, convention violation, task_miss, active advice, or repo-local adapter gap.
22. When `structure_metrics_gate.structure_high_water_key_scope=global_invariant`, state whether the proposed slice can move the global invariant. If not, classify it as local/governance-only or require residual global scope.
23. Preserve original measurable structure targets. Do not let `semantic_consolidation`, `reuse_extraction`, or `coupling_reduction` shrink a directive into a pilot unless a residual item remains open.
24. Pass the advisory packet to `$derive-improvement-task`.

## Guardrails

- Do not write `task.md`.
- Do not delete or apply candidates.
- Do not alter `$derive-improvement-task` profiles under `configured-tiered-routing-v3`: Tier 3 `model_ref:balanced`/high inspectors, Tier 4 `model_ref:balanced`/xhigh cross-contract analysis, Tier 5 `model_ref:direction`/xhigh synthesis, Tier 2 `model_ref:balanced`/medium ID-only work, and bounded evidence-backed Tier 5 `model_ref:direction`/max arbitration only. Runtime bindings belong to caller configuration or a repository adapter; `reference_only` cannot prove enforced or actual-model execution.
- Do not claim final next-task choice authority.
- Do not recommend another same-family untried repair when `hypothesis_exhausted=true`; recommend `stop_with_blocker` unless a supplied input delta or explicit user override exists.
- Do not treat `pilot`, `plan`, `slice`, or `bounded` wording as permission to weaken a measurable target. Emit the narrowing warning and leave final descope/residual handling to `$derive-improvement-task`.
- Do not turn an adapter-reported envelope deficit into a weaker target. Keep `envelope_floor`, `deficit_axis`, and residual scope as advisory fields for derive.
- Do not treat `evaluation_status: not_evaluated` as a passing verifier for a measurable target.
- Do not treat a missing required gate hook as pass when measurable acceptance depends on that gate.
- Do not treat `pass_with_coupled_verifier` as a passing verifier.
- Do not treat `pass_with_unobserved_axes` as a consumable review pass for the affected measurable goal.
- Do not treat `attested_only_movement` as high-water progress.
- Do not recommend repeated marginal repair for a below-threshold residual gap when explicit descope with residual scope and a higher rung are available.
- Do not recommend repeated same-gap repair when value per cycle cost is below the adapter policy and no higher value case is recorded.
- Do not let generation-dependent task/advice/pack/cycle/run labels reset same-family counters in the advisory packet.
- Do not treat contradictory terminal classification, same-input mismatch, repeated unavailable diagnostics, non-disjoint independent verification, or missing frozen-envelope thaw as ordinary repair candidates.
- Do not omit instrumentation supply from the advisory option set when `instrumentation_supply_required=true`, unless you include the existing-observability rationale.
- Do not treat zero-disagreement independent verification as clean when the verification inputs are missing or overlap verified artifacts.
- Do not bury an `envelope_thaw_item` requirement inside a generic scope or micro-repair recommendation.
- Do not recommend verifier, guard, report, metadata-only, or small-smoke work as the next slice when Part L evidence requires current-lane rerun, fresh measurement, producer supply, restrictive quota routing, long-run/throughput routing, metric-basis repair, or surface-field repair.
- Do not recommend structure work as goal-productive solely because it creates more files or modules. Require a credible path to lower coupling, remove mechanical shards, reduce duplication, improve reuse ratio, reduce LOC/depth/fan-out pressure, or unblock a named task transition.
- Do not recommend local structure churn as global progress when the adapter keyed structure high-water to global invariants and those invariants are flat.
- Do not invent project-specific naming, depth, fan-out, kernel, or dependency rules. Consume the repo-owned `code_convention_contract` or mark the structure recommendation warn-only.
