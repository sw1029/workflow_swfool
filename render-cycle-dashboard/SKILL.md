---
name: render-cycle-dashboard
description: "Render a human-readable task-cycle dashboard from ledger, validation, issue, commit, and blocker evidence. Use near the end of `$orchestrate-task-cycle` to write `.task/cycle/cycle-id/dashboard.md` without changing implementation code."
---

# Render Cycle Dashboard

## Overview

Use this skill to summarize a cycle's current state for handoff and final reporting. The dashboard is workflow state, not a validation verdict.

Use `/home/swfool/.codex/skills/orchestrate-task-cycle/scripts/render_cycle_dashboard.py` when possible.

## Workflow

1. Load `.task/cycle/<cycle-id>/stage.jsonl` and `current_stage.json`.
2. Include phase status, task IDs, validation/progress verdicts, blockers, changed files, evidence paths, and commit result.
3. Highlight blocked, running, partial, skipped, or malformed/noncanonical stages with reasons.
4. Write `.task/cycle/<cycle-id>/dashboard.md` in Korean, preserving canonical step/status tokens, paths, IDs, commands, and hashes in their original language.
5. Link the dashboard from the ledger under `dashboard`.

## Guardrails

- Do not hide failed, partial, skipped, or running stages.
- Do not present malformed or `unknown` ledger events as normal canonical stages; show them in a separate malformed-events section.
- Do not infer missing verdicts from current `task.md`.
- Keep `.agent_advice` separate from `.agent_goal` GT in summaries.
