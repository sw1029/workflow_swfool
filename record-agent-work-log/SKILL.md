---
name: record-agent-work-log
description: Create standardized agent work records under a repository or workspace `.agent_log` directory. Use when the user asks Codex to record, archive, log, summarize, or formalize an agent task using fields such as task intent, work performed, result, shortcomings, gaps, follow-ups, or retrospective notes; when a session needs a durable handoff note; or when an agent-assisted normalization pass should turn rough task notes into a consistent `.agent_log` Markdown and JSONL entry.
---

# Record Agent Work Log

## Overview

Use this skill to turn task notes into a durable `.agent_log` record with four required fields: task intent, work performed, result, and shortcomings. Prefer a single normalization subagent when the user requests agent-assisted logging; otherwise normalize locally.

The main agent owns the final record. The subagent, when used, only rewrites and structures the provided facts; it must not invent work, inspect unrelated files, or write files.

When a task-state index exists, link the new `.agent_log` entry through `$manage-task-state-index`. If no ID context exists, write the log normally.

## Workflow

1. Gather source facts.
   - Require enough information to fill: `task_intent`, `work_performed`, `result`, and `shortcomings`.
   - If any field is missing, infer only from the current conversation and tool evidence. If still unknown, write `Not specified`.
   - Capture optional metadata when available: status, repo/workspace path, changed files, commands/tests, agents involved, follow-ups, tags.

2. Normalize the record.
   - If the user explicitly requested agent-assisted logging or independent normalization, spawn one subagent with the prompt in [normalization-agent.md](references/normalization-agent.md).
   - Pass only the raw notes and relevant tool/result facts. Do not pass hidden conclusions or ask the subagent to inspect unrelated code.
   - If subagents are unavailable or not explicitly requested, normalize locally using the same schema.
   - Review the normalized content before writing; the main agent is responsible for accuracy.

3. Write to `.agent_log`.
   - Use the bundled script for deterministic filenames and JSONL indexing:

     ```bash
     python3 /home/swfool/.codex/skills/record-agent-work-log/scripts/write_agent_log.py \
       --root . \
       --title "short title" \
       --intent "..." \
       --work "..." \
       --result "..." \
       --shortcomings "..."
     ```

   - The script creates `.agent_log/YYYY-MM-DD/HHMMSS-title.md` and appends `.agent_log/index.jsonl`.
   - Use `--agent-note` for the normalization subagent's concise review, `--command`, `--changed-file`, `--follow-up`, and `--tag` as needed.

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

- Timestamp:
- Status:
- Workspace:

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
- Do not use `.agent_log` for secrets, credentials, private keys, raw tokens, or full sensitive transcripts.
- Do not let the normalization subagent write files; only the main agent runs the writer script.
- Do not let an ID insight agent normalize the log or write files; it can only recommend task-state links.
- Do not record claims of tests passing, commits, deployments, or file edits unless they actually happened.
- If the user asks to log confidential details, summarize at a safe level and mark sensitive details omitted.
