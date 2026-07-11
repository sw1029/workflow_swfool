---
name: audit-session-governance
description: Inspect repository-local Codex or Claude Code JSONL logs as privacy-safe, non-authoritative workflow observations. Use when auditing session-capture integrity, quarantining malformed or raw/tool-bearing logs, validating a session-audit packet, or rebuilding its derived index without promoting transcript claims to goal truth, validation evidence, completion, or progress.
---

# Audit Session Governance

Treat session logs as optional observations. Never make this sidecar a canonical
workflow phase or positive completion/progress authority.

## Inspect

1. Confirm the source is a repository-local regular JSONL file.
2. Run:

   ```bash
   python3 scripts/session_audit.py inspect \
     --root /path/to/repo --source logs/codex/session.jsonl --tool codex
   ```

3. Supply both `--cycle-id` and `--task-id` only when a canonical caller establishes
   that binding. Never infer identifiers from message text.
4. Read `.task/session_audit/<audit-id>.json`. Treat `partial`, `quarantined`, and
   `failed` packets as non-consumable.

Use `--tool claude-code` for Claude Code projections. Never copy raw input into the
packet or fall back to raw transcript storage.

## Validate and rebuild

```bash
python3 scripts/session_audit.py validate \
  --root /path/to/repo --packet .task/session_audit/audit-....json
python3 scripts/session_audit.py rebuild-index --root /path/to/repo
```

Allow automatic repair only for deterministic index reconstruction. Route source,
semantic, task, and workflow changes as proposals through their owning governed
skills and fresh validation.

## Preserve trust

- Allow an observation to raise a review candidate or lower confidence only.
- Never upgrade validation, progress, completion, authority, or blocker resolution.
- Treat missing events as `absence_unknown`.
- Keep capture optional and fail-quiet unless the caller or acceptance explicitly
  requires completeness.
- Interpret a `block` finding as blocking this packet's consumption only.
- Never let a packet self-authorize a close gate or semantic repair.

Read [the contract](references/session-observation-contract.md) before integrating a
packet. Use [`scripts/session_audit.py`](scripts/session_audit.py) instead of
rewriting parsing, validation, or index reconstruction.
