---
name: record-visible-increment
description: "Record visible user-facing or workflow progress deltas for a task cycle. Use after implementation/run/schema evidence exists to create `.task/delta/cycle-id-visible-delta.md` and `.json` with `not_validation_evidence: true`; never use it as a substitute for tests, validation, or completion evidence."
---

# Record Visible Increment

## Overview

Use this skill to capture what visibly changed in a cycle: CLI behavior, API output shape, generated artifacts, workflow state, dashboard/report output, or user-observable guardrails.

The artifact is progress context only. It must include `not_validation_evidence: true` and must not be cited as the validation command result.

## Workflow

1. Identify the cycle ID and completed task ID from the ledger or validation packet; both `--cycle-id` and `--task-id` are required by the formal helper envelope.
2. Classify the visible delta as one or more of: `cli`, `api`, `workflow_artifact`, `schema_contract`, `dashboard`, `report`, or `none`.
   - When output artifacts are named and an output-delta contract exists, run `PYTHONPATH="${CODEX_HOME:-$HOME/.codex}/skills/orchestrate-task-cycle/scripts" python3 -m orchestrate_task_cycle output-delta` first and copy `produced_domain_delta`, `metadata_only`, and `effective_progress_kind` into the visible-delta JSON.
   - When loop-breaker evidence includes `observed_output_class`, copy it into the visible-delta JSON and let it override self-declared delta fields for progress wording.
   - When Part L fields are present, copy only scalar/id evidence such as `pass_on_stale_lane`, `decision_metadata_revision`, `axis_starved_by_missing_producer`, `portfolio_quota_exceeded`, `unreachable_within_cycle`, `basis_overclaim`, and `surface_field_defect_matrix` into the visible-delta JSON as context.
   - If the output-delta result is metadata-only or `produced_domain_delta=false`, record the increment as workflow/context progress only. Do not describe it as `advanced`.
3. Record the before/after surface, changed files, artifact paths, and any user-visible behavior.
4. Write `.task/delta/<cycle-id>-visible-delta.json` and `.task/delta/<cycle-id>-visible-delta.md`.
5. Append the delta paths to the cycle ledger under `visible_increment`.

## Guardrails

- Always set `not_validation_evidence: true`.
- Use one path-safe cycle ID token. Keep both outputs under the resolved workspace `.task/delta` directory and write them atomically; reject parent traversal or child/directory symlink redirection.
- Do not claim a visible delta when the evidence only shows internal planning.
- Do not let metadata-only, repeated terminal-record, sidecar-only, or workflow-only output satisfy `progress_verdict: advanced`; leave that verdict to `$validate-task-completion` and the observed output-delta gate.
- Treat annotation fields, report wording, honesty labels, and the same delta already counted as safety/metadata progress as non-semantic. Preserve the existing progress axes and never count one delta in both semantic and metadata/safety categories.
- Do not describe Part L stale-lane pass, decision metadata revision, producer-starved axis, warn-only quota, cycle-unreachable launch/heartbeat, basis downgrade, or surface-field defect accounting as `advanced`; they are routing context unless validation records the required current-lane rerun, fresh measurement, producer supply, harvest, basis-compatible input, or field repair.
- Do not replace `$run-task-code-and-log`, `$validate-task-completion`, or issue closure evidence.
