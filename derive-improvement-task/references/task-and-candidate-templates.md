# Task And Candidate Templates

## `task.md` Template

Use this shape for the final selected task:

```markdown
# Task

## Execution Environment

- Status: selected | unresolved | not_applicable
- Source: previous_task | find-local-python-envs | repository_manifest | manual_inference
- Type: conda | venv | local | non_python | unknown
- Name:
- Python:
- Run Prefix:
- Dependency Notes:
- Progress Target: advanced | safety_only | no_progress | regressed
- Progress Kind: goal_productive | governance_only
- Validation Profile: current_only | affected_chain | full_chain
- Authority Policy: `$manage-agent-authority` result (`.agent_goal/agent_authority.md` | default_current_agent_permissions)
- External Advice: <adv-id/path | none>
- Task Pack: <pack-id/path | none>
- Task Pack Item: <item-id | none>
- Pack Position: <order/total | none>
- Pack Source: planned | inserted | reordered | none
- Prerequisite Manifest: <path/status/hash summary, or none>

## Objective

<One concrete improvement objective.>

## Background

- Goal alignment:
- Issue link:
- Architecture/theory link:
- Authority policy link:
- External advice link:
- Schema contract link:
- Task miss or candidate source:

## Requirements

- <Specific requirement>

## Acceptance Criteria

- <Observable completion condition>

## Validation

- <Test, command, metric, review, or evidence required>

## Constraints

- <Relevant convention, forbidden action, compatibility or safety rule>

## Out Of Scope

- <What this task should not attempt>

## Open Questions

- <Unknowns that must be resolved before or during implementation>
```

Environment section rules:

- Put `## Execution Environment` immediately after `# Task`.
- Prefer the previous `task.md` environment section when it is explicit and still applicable.
- If it is absent for a Python task, use `$find-local-python-envs` and choose in this priority order: conda, venv, local/system Python.
- `Run Prefix` must be directly usable, such as `conda run -n ENV`, `/path/to/.venv/bin/python`, or `python3`.
- Use `Status: unresolved` when no usable environment is found; include the blocker in `Dependency Notes`.
- Use `Status: not_applicable` only when the task requires no Python/code execution.
- Include `Progress Target` for every task. Use `advanced` only when the task is expected to unlock a new execution/readiness/goal state or materially reduce a blocker.
- Include `Progress Kind` for every task. Use `goal_productive` only when the task is expected to produce goal-relevant output, quality evidence, source-backed validation, or another non-sidecar artifact that reduces goal distance.
- Include `Validation Profile` for every executable or verifiable task. Use `full_chain` only for live dispatch, readiness promotion, issue closure, shared validator/runtime changes, or explicit user request.
- Include `Authority Policy` for every task from `$manage-agent-authority`. Use `.agent_goal/agent_authority.md` when present; otherwise use `default_current_agent_permissions` and do not infer API/network/destructive authority.
- Include `External Advice` as `none` unless an `.agent_advice/active` document influenced selection, requirements, constraints, or validation. When used, list the `adv-*` ID or path and keep it separate from goal truth.
- Include task-pack fields as `none` for standalone tasks. When a pack item is promoted, list the pack ID/path, item ID, item position, and whether it was planned, inserted, or reordered.
- When a measurable target has a required verifier, include the abstract verifier contract in acceptance or validation. Do not mark `evaluation_status: not_evaluated` as a passing condition.
- When a measurable target depends on an acceptance-referenced gate with required adapter hooks, include required hook status in acceptance or validation. Missing, fail-quiet, or `not_evaluated` hook status means `unverifiable_acceptance_contract`, not pass.
- When a verifier pass came from a verifier source modified in the same change set, include `pass_with_coupled_verifier` evidence and require later non-coupled revalidation or independent recalculation; do not consume it as `pass`.
- When review evidence reports `pass_with_unobserved_axes` or non-empty `unobserved_goal_axes`, include adapter axis-supply, explicit residual scope, terminal blocker, or user escalation in the task; do not consume that review as pass.
- When loopback reports generation-dependent count-key material, include the effective adapter-collapsed count key or terminal-outcome family fallback. Do not use task/advice/pack/cycle/run/date/hash/version labels as family novelty or stall reset.
- When loopback reports failure-surface or same-input Part H blockers, include `failure_surface_stage`, `terminal_classification_stage_contradiction`, and/or `same_input_contract_violation` evidence and select classification/input-contract repair, instrumentation supply, terminal blocker, or user escalation rather than ordinary repair.
- When loopback reports `instrumentation_supply_required`, include instrumentation supply acceptance or a concrete observability rationale proving success/failure is already measurable without new instrumentation.
- When loopback reports `hook_supply_required`, use `selected_task_kind: adapter_hook_batch_supply` when `demanded_hooks` has two or more entries. Supply all `demanded_hooks` in one task item, and consume the item only after a fresh packet shows each supplied hook fired at least once with a non-empty scalar or adapter-owned non-empty value; code existence alone is not acceptance.
- When independently verified evidence lacks disjoint `verification_input_paths`, include source-separation repair or treat the fields as attested; do not claim high-water or `goal_productive` from them.
- When frozen-envelope reachability reports `envelope_thaw_item_required`, include `envelope_thaw_item` with thaw condition/schedule, constraint relaxation, explicit residual descope, terminal blocker, or user escalation.
- When metric movement is producer-attested, include `evidence_provenance_gate`, `producer_attested_fields`, and `attested_only_movement` evidence and require independent verification before claiming high-water movement or `goal_productive`.
- When a residual measurable gap is below adapter policy, include `residual_gap_ratio`, `residual_gap_policy`, `marginal_repair`, cycle-cost fields when supplied, and either explicit descope-with-residual plus the next capability rung or higher marginal-value-per-cycle-cost evidence.
- When a verifier/review/metric pass is on a stale lane, include `production_lane_identity`, `current_decision_lane`, `pass_on_stale_lane`, and current-lane rerun/residual requirements; do not consume it as current-lane progress.
- When a decision/adoption/reclassification update reused stale artifacts after upstream production-contract changes, include `decision_metadata_revision`, `stale_measurement_artifact`, and a fresh run or no-impact proof requirement.
- When a gating axis is starved by missing producer supply, include `axis_starved_by_missing_producer`, the abstract gating axis id, and producer-supply requirement before another verifier/report item.
- When portfolio quota evidence restricts verifier-like work, include `portfolio_quota_exceeded`, quota mode, and the allowed producer/envelope/long-run/descope/terminal/escalation path.
- When a target is unreachable within the cycle, include `acceptance_scale`, `throughput_evidence`, `unreachable_within_cycle`, and long-run launch/monitor/harvest, throughput improvement, descope, terminal, or escalation acceptance.
- When a metric basis is overclaimed, include `basis_overclaim`, `actual_basis_class`, and basis-compatible measurement or downgrade-aware residual requirements.
- When qualitative review found surface field defects, include `surface_field_defect_matrix`, affected field classes, and producer/field repair or residual handling.

## Candidate Task Template

Store unapplied candidates under `.task/candidate_task/YYYYMMDD-HHMMSS-<slug>.md`.

```markdown
# Candidate Task

- Status: candidate | blocked | deferred
- Source: goal_alignment | task_miss | prior_candidate | synthesis
- Candidate Class: state_transition | batchable_micro_contract | safety_only | goal_progress
- Expected Progress: advanced | safety_only | no_progress | regressed
- Progress Kind: goal_productive | governance_only
- Semantic Signature:
- Effective Count Key:
- Count-Key Hygiene: generation-dependent raw keys trace-only | not_applicable
- Supplied Input Delta Needed: yes | no
- Validation Profile: current_only | affected_chain | full_chain
- Authority Policy: `$manage-agent-authority` result (`.agent_goal/agent_authority.md` | default_current_agent_permissions)
- External Advice: <adv-id/path | none>
- Created:
- Supersedes:

## Candidate Objective

<Concrete improvement candidate.>

## Why Not Applied Now

- <Reason this was not selected as the current task.md>

## Evidence

- <Goal, issue, authority, external advice, architecture, theory, task_miss, or repo evidence>

## Potential Requirements

- <Requirement if promoted later>

## Validation Idea

- <How to verify if later applied>

## Blocking Questions

- <Unknowns or dependencies>

## Part G Gates

- Required Gate Hooks:
- Goal Axis Completeness:
- Residual Value Per Cycle Cost:

## Part H Gates

- Failure Surface Stage:
- Same Input Contract:
- Instrumentation Supply:
- Verification Source Separation:
- Envelope Thaw:

## Part L Gates

- Lane Identity:
- Decision Freshness:
- Gating-Axis Producer:
- Portfolio Quota:
- Cycle Reachability:
- Metric Basis:
- Surface Field Review:
```

`adapter_hook_batch_supply` candidate variant:

Use this candidate variant when G-ADAPTER emits `hook_supply_required=true` and `demanded_hooks` contains two or more opaque hook ids.

```markdown
# Candidate Task

- Status: candidate | blocked | deferred
- Source: anti_loop_progress_gate
- Candidate Class: state_transition
- Expected Progress: advanced | safety_only
- Progress Kind: goal_productive | governance_only
- Selected Task Kind: adapter_hook_batch_supply
- Demanded Hooks: [<opaque-hook-id>, <opaque-hook-id>]
- Hook Demand Threshold: <hook_demand_threshold>
- Evidence: <loopback packet path or registry row reference>

## Candidate Objective

Supply all demanded adapter hooks in one batch without adding repo-specific hook semantics to the generic skill body.

## Potential Requirements

- Implement the demanded opaque hooks in the repository-owned adapter or repair adapter loading if the hooks are registered but unreachable.
- Keep hook meanings, paths, thresholds, and metric semantics adapter-owned.

## Acceptance Criteria

- A fresh loopback packet records each demanded hook firing at least once with a non-empty scalar or adapter-owned non-empty value.
- The fresh packet no longer emits `hook_supply_required=true` for those demanded hooks, or records an explicit observability-without-hook rationale.
- Code presence alone does not consume the candidate; this follows the I1 instrumentation exercise principle.

## Validation Idea

- Run the loopback provider on the relevant artifact family and cite the fresh packet fields `adapter_hook_demand`, `hook_supply_required`, and `demanded_hooks`.
```

## Task Pack JSON Template

Store task packs under `.task/task_pack/pack-YYYYMMDD-HHMMSS-<slug>.json`. The JSON queue is canonical; render a same-name `.md` file in the user's requested language after every JSON change.

```json
{
  "schema_version": 1,
  "pack_id": "pack-YYYYMMDD-HHMMSS-slug",
  "status": "active",
  "language": "ko",
  "goal": "Long-range task goal.",
  "current_item_id": "item-001",
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601",
  "items": [
    {
      "item_id": "item-001",
      "order": 1,
      "status": "planned",
      "title": "Promotable task title",
      "objective": "One concrete task objective.",
      "acceptance": ["Observable condition"],
      "validation_profile": "current_only",
      "progress_target": "advanced",
      "dependencies": [],
      "source_evidence": [],
      "blocker_signature_expected": "taxonomy|issue|surface|missing_input",
      "semantic_signature_expected": "stable-goal-axis-family",
      "progress_kind_expected": "goal_productive",
      "effective_count_key_expected": "adapter-root|dominant-parameter",
      "count_key_hygiene": {
        "generation_dependent_count_key": false,
        "trace_only_keys": []
      },
      "goal_axis_contract": {
        "goal_axis_map_status": "not_supplied",
        "active_goal_axes": [],
        "quality_vector_axes": [],
        "unobserved_goal_axes": [],
        "pass_with_unobserved_axes": false
      },
      "lane_identity_contract": {
        "production_lane_identity": null,
        "current_decision_lane": null,
        "pass_on_stale_lane": false
      },
      "decision_freshness_contract": {
        "required_new_run_id": false,
        "stale_measurement_artifact": false,
        "decision_metadata_revision": false
      },
      "gating_axis_producer_contract": {
        "axis_starved_by_missing_producer": false,
        "producer_supply_required": false
      },
      "cycle_reachability_contract": {
        "unreachable_within_cycle": false,
        "long_run_launch_required": false,
        "harvest_validation_required": false
      },
      "metric_basis_contract": {
        "basis_overclaim": false,
        "actual_basis_class": null
      },
      "surface_field_review_contract": {
        "surface_field_defect_matrix": {},
        "field_class_map_missing": false
      },
      "positive_input_delta_required": false,
      "required_new_input_kinds": [],
      "scope_fidelity": [
        {
          "directive_id": "adv-...#directive-id",
          "original_target": {"metric": "abstract_metric", "comparator": ">=", "target": "original target"},
          "item_acceptance": ["Acceptance copied from or traceable to the original directive target."],
          "acceptance_envelope_contract": {"envelope_floor": "adapter-owned abstract floor", "deficit_axis": "adapter-owned axis", "status": "provided|not_provided|indeterminate"},
          "acceptance_verifier_contract": {
            "required_verifier": "adapter-owned abstract verifier",
            "verifier_required": true,
            "required_gate_hooks": [],
            "gate_hook_status": "pass|fail|not_supplied|absent|fail_quiet|not_evaluated",
            "evaluation_status": "pass|fail|not_evaluated"
          },
          "residual_gap_ratio": null,
          "residual_gap_policy": null,
          "envelope_thaw_item_required": false,
          "envelope_thaw_item": null,
          "cycle_fixed_cost": null,
          "marginal_gap_value": null,
          "marginal_value_per_cycle_cost": null,
          "marginal_repair": false,
          "narrowed": false,
          "narrow_reason": null,
          "residual_item_id": null
        }
      ],
      "promotion": {
        "task_id": null,
        "task_path": null,
        "promoted_at": null
      },
      "result": {
        "validation_verdict": null,
        "progress_verdict": null,
        "progress_kind": null,
        "semantic_signature": null,
        "blocker_signature": null
      }
    }
  ],
  "mutation_log": [],
  "terminal_blocker": null
}
```

Pack rules:

- Keep at most one active task pack unless a caller explicitly authorizes multiple packs.
- Prefer 2-5 items. Use a standalone task when only one item is known.
- Promote only one item into the active `task.md` per derivation.
- Preserve measurable directive scope with `scope_fidelity`. If a pack item narrows an original target, set `narrowed=true`, record `narrow_reason`, and create an open residual item rather than consuming the target under a weaker acceptance criterion.
- Preserve adapter-owned `acceptance_envelope_contract` when it exists. If the planned item envelope is below the floor, keep the original target open and represent the item as envelope expansion, explicit descope with residual scope, terminal blocker, or user escalation rather than a weakened acceptance target.
- Preserve adapter-owned `acceptance_verifier_contract` when it exists. If the required verifier is `not_evaluated`, keep verifier work or residual target scope open; do not consume the target under an unverified acceptance criterion.
- Preserve acceptance-required gate-hook status when it exists. If a required hook is absent, fail-quiet, or `not_evaluated`, keep hook-supply work or residual target scope open; do not consume the target under fail-quiet.
- Preserve `adapter_hook_demand`, `hook_supply_required`, and `demanded_hooks` when supplied. If two or more hooks are demanded, batch them as one `adapter_hook_batch_supply` item rather than serializing one hook per cycle.
- Preserve goal-axis completeness fields when supplied. If `pass_with_unobserved_axes=true`, keep adapter axis-supply work, residual target scope, terminal blocker, or user escalation open.
- Preserve count-key hygiene fields when supplied. Generation-dependent raw keys are trace-only; use `effective_count_key_expected` or terminal-outcome fallback for repeated-family decisions.
- Preserve Part F fields when present. `pass_with_coupled_verifier` is not a passing verifier, `attested_only_movement` is not high-water progress, and `marginal_repair` for a below-threshold residual gap should stay behind explicit descope plus the next capability rung unless higher marginal value is recorded.
- Preserve Part G residual cost fields when present. If cycle-cost evidence is supplied, same-gap repair must justify marginal value per cycle cost; otherwise keep denominator `1` legacy behavior.
- Preserve Part H fields when present. Terminal-classification/stage contradictions and same-input mismatches cannot close or count work; repeated diagnostics unavailable must force instrumentation or explicit observability; independently verified fields need disjoint verification inputs or become attested; frozen-envelope unreachable acceptance needs `envelope_thaw_item`, residual/descope, terminal blocker, or user escalation.
- Preserve Part L fields when present. Stale-lane passes cannot consume current-lane work; stale decision measurements need fresh runs or no-impact proof; producer-starved gating axes need producer supply before more verifier-like work; restrictive portfolio quota changes task ordering; cycle-unreachable targets need long-run/throughput/descope/terminal/escalation; basis-overclaimed metrics are downgraded; surface-field defect matrices preserve producer/field repair or residual scope.
- Use `terminal_blocked` when no viable item remains and no supplied input delta, authority change, or external-state change exists. Include `semantic_signature`, `root_cause_attempted_for_family`, authorized-alternative-path status, provider re-attempt status, and dual-track attempt evidence when a hard loop gate applies, so later derivation can seal the family rather than only the current target surface.
- Refresh the Markdown render with `$orchestrate-task-cycle/scripts/task_pack_queue.py --root . render --language <language>` after any JSON edit.

## Candidate Application Rule

When a candidate becomes the real `task.md`:

1. Log the old `task.md` as `past_task`.
2. Write the candidate-derived final `task.md`.
3. Delete the applied candidate file from `.task/candidate_task/`.
4. Mention the deleted candidate path in the final response and `past_task` log note.

If no previous `task.md` exists, treat the write as `initial_init`: skip `past_task` logging, write the initial `task.md`, index it when possible, and only delete an applied candidate after the new task is written and the candidate transition is recorded.
