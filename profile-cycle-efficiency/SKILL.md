---
name: profile-cycle-efficiency
description: "Profile `$orchestrate-task-cycle` efficiency. Use to detect repeated `safety_only` cycles, duplicate logs, unnecessary full-chain validation, stale pre-commit hashes, long stage duration, and repeated no-live micro-contracts before deriving or reporting a cycle."
---

# Profile Cycle Efficiency

## Overview

Use this skill to find avoidable orchestration cost without weakening validation. Most findings are advisory, but `command_surface_budget.consolidation_candidate_required=true`, `artifact_sprawl_budget.consolidation_candidate_required=true`, or `hard_gate=true` is a derive hard gate: the next task must select/register consolidation, select goal-productive work, or record terminal state.

Use `/home/swfool/.codex/skills/orchestrate-task-cycle/scripts/profile_cycle_efficiency.py`.

## Workflow

1. Load cycle ledger events, `.task/index.jsonl`, validation artifacts, run logs, task misses, and active issues when available.
2. Detect repeated `safety_only`, metadata-only, no-live/fail-closed-only cycles, duplicate evidence artifacts, repeated blockers, stale output-delta absence, `vacuous_untried_streak`, `hypothesis_exhausted`, `forward_mutation_vacuous` signals, run-directory growth, processed-candidate growth, versioned command-family growth, and full-chain runs without an escalation reason.
3. When `detect_progress_loop.py` emits `feature_symbol_gate`, treat repeated no-delta feature symbols and terminal-history matches as efficiency debt that must route to consolidation, goal-productive work, terminal blocking, or user escalation.
4. When run-directory, processed-candidate, version-family, or command-surface sprawl exceeds budget, register consolidation candidates as `governance_only`; do not describe sprawl accounting as primary-output progress.
5. Report recommended action: `continue`, `batch_micro_contracts`, `supply_evidence_path`, `bounded_preflight`, `resume_primary_output`, `root_cause_repair_or_stop_with_blocker`, `narrow_scope`, `register_consolidation_candidate`, or `stop_with_blocker`.
6. Pass the profile into `$derive-improvement-task` and final reporting.

## Guardrails

- Do not lower required validation scope when changed surfaces justify it.
- Do not replace `$derive-improvement-task` task selection.
- Do not treat efficiency findings as proof of task completion.
- Do not treat metadata-only measurements as primary-output progress when the output-delta contract reports `produced_domain_delta: false`.
- Do not treat self-declared `produced_domain_delta=true` as primary-output progress when observed output classification reports `metadata_only` or repeated `terminal_record`.
- Do not leave an over-budget version-suffixed command surface as a warning-only finding; pass `command_surface_budget` into derive and require an allowed disposition.
- Do not leave run-dir, processed-candidate, or versioned-family sprawl as a warning-only finding when `artifact_sprawl_budget.consolidation_candidate_required=true`; pass the budget into derive and require consolidation, goal-productive output, terminal blocking, or user escalation.
- Do not treat `vacuous_untried_streak`, `hypothesis_exhausted`, or `forward_mutation_vacuous` as progress; pass them as efficiency/advisory signals into derive.
