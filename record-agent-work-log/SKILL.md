---
name: record-agent-work-log
description: Create standardized agent work records under a repository or workspace `.agent_log` directory. Use when the user asks Codex to record, archive, log, summarize, or formalize an agent task using fields such as task intent, work performed, result, shortcomings, gaps, follow-ups, or retrospective notes; when a session needs a durable handoff note; or when an agent-assisted normalization pass should turn rough task notes into a consistent `.agent_log` Markdown and JSONL entry.
---

# Record Agent Work Log

## Overview

Use this skill to turn task notes into a durable `.agent_log` record with four required fields: task intent, work performed, result, and shortcomings. Prefer a single normalization subagent when the user requests agent-assisted logging; otherwise normalize locally.

The main agent owns the final record. The subagent, when used, only rewrites and structures the provided facts; it must not invent work, inspect unrelated files, or write files.

When a task-state index exists, link the new `.agent_log` entry through `$manage-task-state-index`. If no ID context exists, write the log normally.

Keep session capture separate. `.agent_log` may cite a validated privacy-safe `$audit-session-governance` packet ID/path and summarize its finding, but it must not contain raw/slim transcript bodies or treat session observation as validation, progress, completion, or authority evidence.

## Domain Adapter Contract

Work logs may consume this optional Part O hook only as retention metadata:

- `record_retention_policy(**context) -> dict`: O5 helper returning adapter-owned retention class boundaries, large-record policy, archive manifest policy, and immutable evidence categories. The adapter owns retention boundaries and thresholds. If absent or malformed, fail quiet and do not rotate or summarize logs beyond existing behavior.

Do not hardcode retention periods, packet-size thresholds, or archive locations. O5 is record hygiene only and must not change task, validation, progress, or advice lifecycle claims.

## Workflow

1. Gather source facts.
   - Require enough information to fill: `task_intent`, `work_performed`, `result`, and `shortcomings`.
   - If any field is missing, infer only from the current conversation and tool evidence. If still unknown, write `Not specified`.
   - Capture optional metadata when available: status, repo/workspace path, changed files, commands/tests, agents involved, follow-ups, tags, retention class, archive reference, and retention exclusion reason.

2. Normalize the record.
   - If the user explicitly requested agent-assisted logging or independent normalization, spawn one subagent with the prompt in [normalization-agent.md](references/normalization-agent.md).
   - Pass only the raw notes and relevant tool/result facts. Do not pass hidden conclusions or ask the subagent to inspect unrelated code.
   - If subagents are unavailable or not explicitly requested, normalize locally using the same schema.
   - Review the normalized content before writing; the main agent is responsible for accuracy.

3. Write to `.agent_log`.
   - Use the bundled script for deterministic filenames and JSONL indexing:

     ```bash
     python3 "${CODEX_HOME:-$HOME/.codex}/skills/record-agent-work-log/scripts/write_agent_log.py" \
       --root . \
       --title "short title" \
       --status informational \
       --intent "..." \
       --work "..." \
       --result "..." \
       --shortcomings "..." \
       --retention-class unspecified \
       --sensitivity unspecified
     ```

   - The script requires an explicit status from `completed`, `partial`, `blocked`, `failed`, or `informational`; it never defaults an omitted status to completed.
   - The script creates a collision-safe `.agent_log/YYYY-MM-DD/HHMMSSffffff-title-token.md` with a stable `log_id`, then appends `.agent_log/index.jsonl` under a workspace-local lock.
   - Use `--agent-note` for the normalization subagent's concise review, `--command`, `--changed-file`, `--follow-up`, and `--tag` as needed.
   - Record `--retention-class`, optional `--archive-reference` / `--retention-exclusion-reason`, and `--sensitivity public|internal|confidential|restricted|unspecified`. These fields are hygiene metadata, not completion evidence.
   - If `record_retention_policy` is supplied, record only opaque retention metadata in the log or index; do not remove required record sections or provenance while writing the log.
   - Validate existing JSONL before writing. New rows carry `format_version` and `schema_version`; legacy versionless rows remain readable, while malformed or future-version JSONL fails closed before a log is published.

4. Update task-state IDs when possible.
   - After the log file is written, run `$manage-task-state-index` `scan`.
   - Add or reuse the `.agent_log` artifact ID. Use `past_task` when the log title or purpose is `past_task`; otherwise use `agent_log`.
   - If an active task, run, audit, validation, candidate, or miss ID is known, link the log with the most specific relationship, such as `archived_as`, `produced`, `run_for`, `audit_for`, `validates`, or `related_to`.
   - If the workflow authorizes agents and ID context exists, a separate read-only ID insight agent may suggest links. This agent is additional to any normalization subagent and must not rewrite the log.
   - If no usable ID context exists, skip indexing and mention that the log was still written.

5. Report the saved path.
   - Tell the user which log file was written and whether `index.jsonl` was updated.
   - Tell the user whether `.task/index` was updated or skipped.
   - Mention unresolved gaps only if they matter for later readers.

## Required Record Shape

Every log entry must include these sections:

```text
# <title>

- Log ID:
- Timestamp:
- Status:
- Workspace:
- Retention class:
- Archive reference:
- Retention exclusion reason:
- Sensitivity:

## Task Intent
...

## Work Performed
...

## Result
...

## Shortcomings
...

## Follow-ups
...
```

Keep entries factual. Do not make the record more successful than the evidence supports.

## Guardrails

- Do not overwrite existing log files. Create a new timestamped entry.
- Do not infer success or completion from empty intent/work/result/shortcomings. Require all four to be explicitly non-empty and require the caller to choose the status.
- Serialize log publication and index replacement through `.agent_log/index.lock`; keep filenames and IDs collision-safe under concurrent writers.
- Do not use `.agent_log` for secrets, credentials, private keys, raw tokens, or raw/slim transcript bodies. Store session capture only through `$audit-session-governance`; cite its validated privacy-safe packet rather than copying the packet or transcript body.
- Do not let the normalization subagent write files; only the main agent runs the writer script.
- Do not let an ID insight agent normalize the log or write files; it can only recommend task-state links.
- Do not record claims of tests passing, commits, deployments, or file edits unless they actually happened.
- Do not use Part O/O5 retention policy to delete, overwrite, or summarize away required log sections, validation scalars, visible-delta records, loop/progress ledgers, or disposition provenance. Missing `record_retention_policy` is fail-quiet no-op.
- Do not treat retention metadata as completion, validation, advice lifecycle, or progress evidence; avoid double-counting O5 as Part M disposition or Part N persistence policy.
- If the user asks to log confidential details, summarize at a safe level and mark sensitive details omitted.
