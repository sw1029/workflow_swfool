---
name: profile-cycle-efficiency
description: "Profile `$orchestrate-task-cycle` efficiency. Use to detect repeated `safety_only` cycles, duplicate logs, unnecessary full-chain validation, stale pre-commit hashes, long stage duration, and repeated no-live micro-contracts before deriving or reporting a cycle."
---

# Profile Cycle Efficiency

## Overview

Use this skill to find avoidable orchestration cost without weakening validation. Treat repository-global command-surface and artifact-sprawl findings as dashboard/advisory debt. Let only a separately verified current-family verdict constrain current-family selection; never turn a global aggregate into that hard gate.

When residual-gap policy is in scope, this skill is also the default source for the G4 denominator. Pass cycle fixed-cost evidence to `$derive-improvement-task` so residual repair can be ranked by value per cycle cost. If cost evidence is missing, downstream skills use denominator `1` and preserve legacy F3. Repeated unchanged ledger artifacts should be represented as `unchanged_ref(path+hash)` and subtracted from the fixed-cost denominator instead of counted as fresh packet work.

Use `PYTHONPATH="${CODEX_HOME:-$HOME/.codex}/skills/orchestrate-task-cycle/scripts" python3 -m orchestrate_task_cycle efficiency --task-id <canonical-task-id>`. The helper directly emits the formal `cycle_efficiency_profile` envelope (`step`, task, status, cost basis, recommendation, blockers, and evidence paths).

When a task pack or blocker family has no fresh run id for the adapter/config-owned recent-cycle window, expose `execution_starvation_status: present` and `execution_starvation: true`. Decide this only after the window, mapped goal axis, producer lineage, artifact class, and current decision lane are all known. If any is missing or the window is malformed, emit `execution_starvation_status: scope_unknown`, a null boolean, and `scope_evidence_required`; recover that producer-run scope before automatic continue. `scope_unknown` is neither starvation absence nor a global terminal signal. Starvation remains a derive ranking input that raises execution-producing candidates above another guard, verifier, contract, lineage, or report candidate while preserving safety, authority, and terminal constraints.

## Workflow

Scope terminal and exhaustion evidence to the current `goal_axis`, stable `root_family_key`, `producer_lineage`, `artifact_class`, `decision_lane`, and `input_cohort`. Exclude task/run/date/version/generation labels from family identity. If any required scope component is unavailable, emit `profile_scope_unverified=true`; do not derive current-family hard stops, exhaustion, or terminal state from global `any`/`max` history. Global aggregates remain dashboard and long-term debt observations only.

Keep family recurrence and goal-axis stagnation as parallel projections. Family-scoped counters retain the full family identity above. The goal-axis projection follows the adapter-mapped `goal_axis` across root-family changes and records producer-run, semantic-movement, and safety/governance cycle counts separately. A family change does not reset its no-semantic-movement streak. Only a fresh producer run with independently consumable semantic movement resets that semantic streak; safety, governance, metadata, or measurement movement remains visible but cannot become semantic high-water.

Compute current-cycle cost from separate identity sets: `unique_new_artifact_ids`, `unique_unchanged_artifact_ids`, and `fresh_stage_event_ids`. Never subtract raw counts measured in different units. Preserve observable current-cycle event cost when family scope is unverified; do not replace it with an empty basis or an arbitrary minimum. Keep global sprawl evidence advisory and separate from family-scoped decisions.

When profile inputs depend on an adapter, consume the same external `consumer_context_conformance` row for the profile loader. A repository-root import or adapter self-report cannot establish profile wiring; an acceptance-required missing row leaves the profile axis `not_evaluated` and prevents family exhaustion/hard-stop use.

1. Load cycle ledger events, `.task/index.jsonl`, validation artifacts, run logs, task misses, and active issues when available.
2. Detect repeated `safety_only`, metadata-only, no-live/fail-closed-only cycles, duplicate evidence artifacts, missing `unchanged_ref` for duplicate artifacts, repeated blockers, stale output-delta absence, `vacuous_untried_streak`, `hypothesis_exhausted`, `forward_mutation_vacuous` signals, run-directory growth, processed-candidate growth, versioned command-family growth, pack/family windows with zero fresh run ids, and full-chain runs without an escalation reason.
   - When Part L packet fields are present, preserve verifier/report/metadata versus producer/envelope/long-run counts as portfolio evidence; if an adapter supplied restrictive quota evidence, pass it through unchanged rather than recomputing thresholds here.
3. When `python3 -m orchestrate_task_cycle progress-loop` emits `feature_symbol_gate`, treat repeated no-delta feature symbols and terminal-history matches as efficiency debt that must route to consolidation, goal-productive work, terminal blocking, or user escalation.
4. When run-directory, processed-candidate, version-family, or command-surface sprawl exceeds budget, expose a global consolidation candidate as `governance_only`; do not force the current-family task from that evidence or describe sprawl accounting as primary-output progress.
5. Report recommended action: `continue`, `batch_micro_contracts`, `supply_evidence_path`, `bounded_preflight`, `resume_primary_output`, `root_cause_repair_or_stop_with_blocker`, `narrow_scope`, `register_consolidation_candidate`, or `stop_with_blocker`.
6. When available, expose abstract cost fields such as `cycle_fixed_cost`, `stage_count`, `validation_command_count`, `artifact_count`, `unchanged_ref_count`, `duration_seconds`, `repeated_micro_contract_count`, and a compact `cycle_cost_basis`. Also expose `execution_scope_status`, `execution_starvation_status`, nullable `execution_starvation`, `scope_evidence_required`, `recent_cycle_run_id_count`, `execution_starvation_window`, `execution_candidate_priority_boost`, and `goal_axis_stagnation_projection`. Do not encode project-specific metric thresholds in this skill.
   - Include Part L routing evidence only as compact scalar/id fields: `portfolio_quota_exceeded`, `portfolio_quota_mode`, `unreachable_within_cycle`, `observed_cycle_throughput`, `required_scale`, and `cycle_execution_cap` when supplied.
7. Pass the profile into `$derive-improvement-task`, `$normalize-acceptance-and-demo`, and final reporting.

## Guardrails

- Do not lower required validation scope when changed surfaces justify it.
- Accept only a path-safe `--cycle-id` token and resolve ledger inputs under the workspace `.task/cycle` directory; reject parent or symlink escape before profiling.
- Do not replace `$derive-improvement-task` task selection.
- Do not treat efficiency findings as proof of task completion.
- Do not treat metadata-only measurements as primary-output progress when the output-delta contract reports `produced_domain_delta: false`.
- Do not treat self-declared `produced_domain_delta=true` as primary-output progress when observed output classification reports `metadata_only` or repeated `terminal_record`.
- Do not hide over-budget version-suffixed command surfaces; pass `command_surface_budget` as global dashboard debt without making it a current-family disposition constraint.
- Do not hide run-dir, processed-candidate, or versioned-family sprawl; preserve `artifact_sprawl_budget.consolidation_candidate_required` as a global consolidation candidate, not a current-family hard gate.
- Do not treat `vacuous_untried_streak`, `hypothesis_exhausted`, or `forward_mutation_vacuous` as progress; pass them as efficiency/advisory signals into derive.
- Do not let a tiny residual gap bypass cost accounting when cycle fixed-cost evidence is available; pass value-per-cycle-cost context to derive instead of recommending another same-gap repair by default.
- Do not count identical repeated packet artifacts as fresh fixed cost when the ledger supplies `unchanged_refs`; use `max(1, event_count - unchanged_ref_count)` as the conservative denominator basis.
- Do not empty the current-cycle cost basis because family scope is unverified. Cost evidence and family decision scope are independent facts.
- Do not emit `hard_gate=true` or `constrains_current_family=true` from repository-global command-surface or artifact-sprawl debt.
- Do not ignore duplicate artifact paths without `unchanged_ref`; report `unchanged_ref_missing_for_duplicate_artifacts` so `$maintain-cycle-ledger` can stop reserializing identical content.
- Do not leave recent-cycle zero-run starvation as a warning-only note. Pass `execution_starvation` to `$derive-improvement-task` so execution-producing candidates can be ranked ahead of another guard/report/contract cycle.
- Do not coerce `scope_unknown` to either zero-run starvation or a clean continue. Route scope evidence recovery first and keep terminal state unchanged.
- Do not let family changes, safety-only work, governance-only work, or metric/report movement reset adapter-mapped goal-axis semantic stagnation.
- Do not compute project-specific portfolio thresholds, scale units, or throughput limits in this skill. Preserve adapter-supplied Part L quota/reachability evidence for derive instead.
