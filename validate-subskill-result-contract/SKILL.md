---
name: validate-subskill-result-contract
description: "Validate result contracts from `$orchestrate-task-cycle` subskills. Use before advancing cycle stages to check required fields such as task IDs, verdicts, changed files, blockers, evidence paths, running-state details, issue status, commit status, and final-report fields; default to warn except final report or explicit block mode."
---

# Validate Subskill Result Contract

## Overview

Use this skill as a stage gate between orchestration phases. It checks whether the previous owning skill returned enough structured evidence for the coordinator to continue.

Use `/home/swfool/.codex/skills/orchestrate-task-cycle/scripts/result_contract.py` for deterministic validation.

## Workflow

1. Choose the target: `governance`, `validation_set_plan`, `run`, `qualitative_review`, `validation_set_build`, `schema_pre_derive`, `derive`, `schema_post_derive`, `index`, `validate`, `issue`, `commit`, `report`, or `closeout_commit`.
2. Validate the owning skill result in `warn` mode by default.
3. Treat a missing or mismatched top-level canonical `step` as a ledger-envelope warning. Use `block` mode, or pass an explicit `--step <canonical-step>` to `$maintain-cycle-ledger`, before using the result JSON directly as a ledger event.
4. Use `block` mode when missing fields would corrupt the cycle transition, especially final report fields, `running` execution details, task-pack promotion provenance, candidate deletion, issue closure, or commit creation.
5. Append the contract result to the cycle ledger through `$maintain-cycle-ledger`.
6. Pass warnings downstream in the next subskill packet.

## Required Evidence

- `task_id` or a clear `not_applicable` reason for stages tied to a task.
- Top-level `step` matching the target when a result may be appended directly as a ledger event.
- `changed_files` for implementation/governance, validation, issue, commit, and report stages when files changed.
- `validation_verdict` and `progress_verdict` from validation onward.
- Owning-skill result statuses such as run `success` belong in the result contract; cycle ledger lifecycle status normalization belongs to `$maintain-cycle-ledger`.
- `blockers` as an explicit list, using an empty list when no blockers remain.
- `evidence_paths` for run, schema, index, validation, issue, commit, dashboard, and report stages.
- For `qualitative_review`, require reviewer routing, reviewed artifacts, direct read scope, qualitative findings, direction recommendations, output-delta handoff fields, blocker taxonomy delta, no-overclaim flags, and evidence paths. Do not accept a main-coordinator substitute as the reviewer; when reviewer delegation is unavailable, require a blocked, partial, or not-applicable result with `reviewer_delegation_unavailable_reason`.
- `commit_role`, `commit_status`, and `evidence_paths` for commit results.
- `commit_hash` and `commit_subject` for created commits; `commit_skipped_reason` for skipped, blocked, or failed commits.
- `task_pack_status`, `task_pack_path`, and `task_pack_item_id` or `promoted_item_id` when derivation or reporting promotes the next task from `.task/task_pack/`.
- `has_supplied_input_delta` plus `supplied_input_artifact_paths` or `produced_domain_delta=true` when a derive result relies on positive input delta.
- `provider_reattempt_disposition` when `provider_reattempt_required=true`; terminal/provider-family sealing is invalid while bounded retry/probe is still required.
- Dual-track terminal blocker evidence when `detect_progress_loop status=block` forces terminal state.
- `consolidation_candidate_registered` or selected consolidation work when `command_surface_budget.consolidation_candidate_required=true`.
- `tracked_artifacts` for `closeout_commit` results.

## Guardrails

- Do not infer success from missing data.
- Do not use this skill to override an owning skill verdict.
- Treat contract output as orchestration evidence only; it is not a replacement for validation or issue tracking.
