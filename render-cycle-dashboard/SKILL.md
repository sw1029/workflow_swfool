---
name: render-cycle-dashboard
description: "Render a human-readable task-cycle dashboard from ledger, validation, issue, commit, and blocker evidence. Use near the end of `$orchestrate-task-cycle` to write `.task/cycle/cycle-id/dashboard.md` without changing implementation code."
---

# Render Cycle Dashboard

## Overview

Use this skill to summarize a cycle's current state for handoff and final reporting. The dashboard is workflow state, not a validation verdict.

The deterministic `publish_cycle_dashboard` projection is declared in `authority.operations.json` with no independent grant requirement. This status never authorizes source, task, issue, or cycle-finalization changes and remains bounded by the active session ceiling and shared [authority v2 contract](../manage-agent-authority/references/authority-v2-contract.md).

Use `PYTHONPATH="${CODEX_HOME:-$HOME/.codex}/skills/orchestrate-task-cycle/scripts" python3 -m orchestrate_task_cycle dashboard` when possible. The default output remains Korean Markdown; use `--format json` or `--result-output <path>` to emit the directly validatable dashboard result contract.

## Domain Adapter Contract

This skill normally consumes ledger-supplied Part O fields. If direct adapter access is available, it may consume `goal_axis_map(targets=None, quality_vector=None, **context) -> list|dict` only to render adapter-owned axis ids, `axis_delta`, and `axis_stall_streak`. The adapter owns axis definitions and thresholds. If the hook or ledger fields are absent, fail quiet and keep the existing dashboard layout.

## Workflow

1. Load `.task/cycle/<cycle-id>/stage.jsonl` and `current_stage.json`. Malformed UTF-8/JSON or a non-object ledger row is a blocking input error; never skip it. A missing/stale/malformed derived `current_stage.json` is rendered as snapshot warning evidence because the canonical JSONL can rebuild it. A snapshot is current only when both its event count and latest event ID match the ledger; versionless legacy rows may use count-only compatibility when neither side has an event ID.
2. Derive phase status, task IDs, validation/progress verdicts, blockers, changed files, evidence paths, issue state, and commit results only from structurally valid, cycle-matching, non-duplicate events. Keep rejected events visible as diagnostics, but never consume their truth fields.
3. Highlight blocked, running, partial, skipped, or malformed/noncanonical stages with reasons.
   - When ledger events include Part L fields, show unresolved stale-lane pass, stale decision measurement, producer-starved gating axis, restrictive quota, cycle-unreachable target, basis overclaim, and surface-field defect evidence under blockers or progress-axis notes. Preserve field names exactly; keep lane keys and source/body details out of the dashboard unless already present in redacted packet paths.
   - When ledger events include Part O/O2' fields, always show each supplied `axis_id`, `axis_delta`, and `axis_stall_streak`, and mark `goal_axis_stall` as a blocker/routing note when present. Do not infer missing axes from the task text.
4. Write `.task/cycle/<cycle-id>/dashboard.md` in Korean, preserving canonical step/status tokens, paths, IDs, commands, and hashes in their original language.
5. Emit the result-contract fields `task_id`, `dashboard_status`, ledger `event_count`, `valid_event_count`, explicit `current_stage_event_count`, ledger/current latest event IDs, `snapshot_status`, validation/progress verdicts, blockers, `dashboard_path`, and evidence paths. Preserve supplied task-acceptance, artifact-truth, semantic, pack-transition, historical-index, and goal-readiness verdict axes separately. Include bounded `unchanged_refs` and `unchanged_ref_count` without embedding referenced packet bodies. Link the dashboard from the ledger under `dashboard`.

## Guardrails

- Do not hide failed, partial, skipped, or running stages.
- Do not present malformed or `unknown` ledger events as normal canonical stages; show them in a separate malformed-events section.
- Do not infer missing verdicts from current `task.md`.
- Do not hide Part L unresolved fields behind a generic "workflow complete" note. The dashboard is not a validation verdict, but it must not make stale-lane, stale-measurement, producer-starvation, cycle-reachability, basis, or surface-field defects look consumed.
- Do not hide Part O/O2' axis-stall fields behind aggregate progress. Missing `goal_axis_map` is fail-quiet, but supplied axis streaks must remain visible and must not be double-counted as B/G or N1' findings.
- Keep `.agent_advice` separate from `.agent_goal` GT in summaries.
