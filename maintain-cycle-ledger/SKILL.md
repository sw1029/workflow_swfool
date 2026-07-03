---
name: maintain-cycle-ledger
description: "Maintain durable task-cycle ledgers for `$orchestrate-task-cycle`. Use when Codex needs to initialize a cycle ID, append stage events, update `.task/cycle/cycle-id/current_stage.json`, preserve subskill packets, or render `final_report.md` and `dashboard.md` without editing implementation code."
---

# Maintain Cycle Ledger

## Overview

Use this skill to record orchestration state as durable workflow evidence under `.task/cycle/<cycle-id>/`. The ledger is workflow state, not validation proof and not implementation code.

Use `/home/swfool/.codex/skills/orchestrate-task-cycle/scripts/cycle_ledger.py` for deterministic writes whenever possible.

## Workflow

1. Initialize the cycle before authority or governance work:
   - Create `.task/cycle/<cycle-id>/stage.jsonl`.
   - Create `.task/cycle/<cycle-id>/current_stage.json`.
   - Create `.task/cycle/<cycle-id>/packets/`.
2. Append one event after each major stage: `context`, `ledger_init`, `authority`, `acceptance`, `governance`, `result_contract`, `ledger_append`, `run`, `schema_pre_derive`, `visible_increment`, `derive`, `schema_post_derive`, `index`, `validate`, `issue`, `commit`, `dashboard`, `report`, and `closeout_commit`.
3. Include the minimum event fields when known: `cycle_id`, `event_id`, `step`, `status`, `reason`, `task_id`, `completed_task_id`, `next_task_id`, `changed_files`, `artifacts`, `artifact_refs`, `unchanged_refs`, `validation_verdict`, `progress_verdict`, `blockers`, `authority_policy`, `authority_policy_source`, and `created_at`.
   - Treat `status` as the canonical workflow-stage lifecycle status. Preserve owning subskill statuses such as run `success` in the subskill result artifact or `source_status`/`result_status`, not as the ledger stage status.
   - When using `cycle_ledger.py`, rely on its normalization of incoming stage `success` or `succeeded` to `complete`.
   - When appending from a raw subskill result JSON, either require a top-level canonical `step` in that JSON or pass `--step <canonical-step>` explicitly. The result contract can warn about ledger-envelope readiness, but the append call owns the final event envelope.
   - Preserve task-pack routing fields when present: `selected_task_source`, `task_pack_id`, `task_pack_path`, `task_pack_status`, `task_pack_item_id`, `promoted_item_id`, and `completed_item_id`.
4. Save generated subskill packets under `packets/*.md` or `packets/*.json` and link them from the relevant event.
5. When an event links an artifact whose path and hash are identical to a previous ledger artifact, use `artifact_refs[].unchanged_ref: {path, sha256}` and `unchanged_refs` instead of reserializing the same packet content in the ledger body. The deterministic writer computes this automatically for existing files.
6. Render `dashboard.md` in Korean and `final_report.md` from ledger/stage evidence near the end of the cycle. Treat dashboard/profile files as snapshots with an `event_count`; if closeout appends another ledger event after rendering, do not claim those files are post-closeout snapshots unless they were regenerated after that event.

## Guardrails

- Do not mark a stage `complete` unless the owning skill produced the evidence.
- Do not loosen transition validators to accept raw subskill result vocabulary as lifecycle status; normalize at the ledger writer boundary.
- Do not append a missing, empty, or noncanonical `step`; noncanonical steps require explicit malformed-event intent and must not appear as normal dashboard stages.
- Do not rely on `$validate-subskill-result-contract` alone to supply a missing `step`; either fix the event JSON or overlay `--step` at append time.
- Do not treat a `running` execution as `success`; record it as `running` with monitor and stop evidence.
- Do not overwrite existing stage history. Append a corrective event with a reason.
- Do not reserialize identical packet bodies across cycle events when the path/hash are unchanged. Preserve `unchanged_ref(path+hash)` so cycle-efficiency profiling can distinguish fixed-cost work from repeated artifact payloads.
- Do not edit repository source, tests, notebooks, runtime/build configuration, or other behavior-changing files from this skill.
