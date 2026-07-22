---
name: record-agent-work-log
description: Create standardized agent work records under a repository or workspace `.agent_log` directory, or migrate a legacy agent-log store into an integrity-bound appendable form without changing historical bodies. Use when the user asks Codex to record, archive, log, summarize, formalize, or safely migrate agent task records with task intent, work performed, result, shortcomings, gaps, follow-ups, or retrospective notes.
---

# Record Agent Work Log

## Overview

Use this skill to turn task notes into a durable `.agent_log` record with four required fields: task intent, work performed, result, and shortcomings. Prefer a single normalization subagent when the user requests agent-assisted logging; otherwise normalize locally.

The factual `publish_agent_work_log` projection is declared in `authority.operations.json` with no independent grant requirement. It remains bounded by the active session ceiling and shared [authority v2 contract](../manage-agent-authority/references/authority-v2-contract.md), and cannot authorize or prove the work it records.

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
     PYTHONPATH="${CODEX_HOME:-$HOME/.codex}/skills/record-agent-work-log/scripts" \
     python3 -P -m record_agent_work_log write \
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
   - Validate the complete `.agent_log` store before writing. New rows use `format_version: 3` and `schema_version: 2`, bind the immutable Markdown bytes with `body_sha256` and `content_id`, and bind the index row with content-derived `record_id`. Legacy rows remain readable but explicitly lack this body-integrity guarantee; malformed/future-version rows, duplicate IDs or paths, orphan Markdown, body tampering, and missing current-version bodies fail closed before publication.
   - If that strict preflight exposes a legacy store that must be made appendable, stop normal writing and follow [legacy-migration.md](references/legacy-migration.md). Use the bundled migration helper; never hand-edit the index or relax the reader.

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
- Require `.agent_log`, its date directories, lock, index, and Markdown files to remain regular non-symlink paths beneath the resolved workspace. Never follow a symlink component for writing or collection.
- Treat `body_sha256`, `content_id`, and `record_id` as immutable bindings for current-version rows. Do not rewrite a bound Markdown body or repair an integrity mismatch by silently replacing index evidence; surface the duplicate, orphan, missing, or tampered record for governed resolution.
- Require a valid migration marker, receipt, source snapshot, plan, exact status map, resolution manifest, and commit-boundary prefix hash for migration-derived rows. Standard appends after that boundary remain strict current rows. Never treat an unsealed malformed/legacy prefix as migrated.
- Before using migration evidence as a governed trust-boundary pass, run the source-separated `python3 -P -m record_agent_work_log verify-migration` command described in [legacy-migration.md](references/legacy-migration.md). Producer/self-declared success and the producer's own `validate` result are not independent verification.
- Require context/completion collectors and `$manage-task-state-index` discovery to use the shared integrity inspector before reading Markdown. Any workflow that creates a handoff log, including external-advice retirement, must use the standard writer rather than creating orphan `.agent_log/*.md` directly.
- Do not use `.agent_log` for secrets, credentials, private keys, raw tokens, or raw/slim transcript bodies. Store session capture only through `$audit-session-governance`; cite its validated privacy-safe packet rather than copying the packet or transcript body.
- Do not let the normalization subagent write files; only the main agent runs the writer script.
- Do not let an ID insight agent normalize the log or write files; it can only recommend task-state links.
- Do not record claims of tests passing, commits, deployments, or file edits unless they actually happened.
- Do not use Part O/O5 retention policy to delete, overwrite, or summarize away required log sections, validation scalars, visible-delta records, loop/progress ledgers, or disposition provenance. Missing `record_retention_policy` is fail-quiet no-op.
- Do not treat retention metadata as completion, validation, advice lifecycle, or progress evidence; avoid double-counting O5 as Part M disposition or Part N persistence policy.
- If the user asks to log confidential details, summarize at a safe level and mark sensitive details omitted.
