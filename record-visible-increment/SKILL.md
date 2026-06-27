---
name: record-visible-increment
description: "Record visible user-facing or workflow progress deltas for a task cycle. Use after implementation/run/schema evidence exists to create `.task/delta/cycle-id-visible-delta.md` and `.json` with `not_validation_evidence: true`; never use it as a substitute for tests, validation, or completion evidence."
---

# Record Visible Increment

## Overview

Use this skill to capture what visibly changed in a cycle: CLI behavior, API output shape, generated artifacts, workflow state, dashboard/report output, or user-observable guardrails.

The artifact is progress context only. It must include `not_validation_evidence: true` and must not be cited as the validation command result.

## Workflow

1. Identify the cycle ID and completed task ID from the ledger or validation packet.
2. Classify the visible delta as one or more of: `cli`, `api`, `workflow_artifact`, `schema_contract`, `dashboard`, `report`, or `none`.
   - When output artifacts are named and an output-delta contract exists, run `/home/swfool/.codex/skills/orchestrate-task-cycle/scripts/output_delta_contract.py` first and copy `produced_domain_delta`, `metadata_only`, and `effective_progress_kind` into the visible-delta JSON.
   - When loop-breaker evidence includes `observed_output_class`, copy it into the visible-delta JSON and let it override self-declared delta fields for progress wording.
   - If the output-delta result is metadata-only or `produced_domain_delta=false`, record the increment as workflow/context progress only. Do not describe it as `advanced`.
3. Record the before/after surface, changed files, artifact paths, and any user-visible behavior.
4. Write `.task/delta/<cycle-id>-visible-delta.json` and `.task/delta/<cycle-id>-visible-delta.md`.
5. Append the delta paths to the cycle ledger under `visible_increment`.

## Guardrails

- Always set `not_validation_evidence: true`.
- Do not claim a visible delta when the evidence only shows internal planning.
- Do not let metadata-only, repeated terminal-record, sidecar-only, or workflow-only output satisfy `progress_verdict: advanced`; leave that verdict to `$validate-task-completion` and the observed output-delta gate.
- Do not replace `$run-task-code-and-log`, `$validate-task-completion`, or issue closure evidence.
