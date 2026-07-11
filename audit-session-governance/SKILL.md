---
name: audit-session-governance
description: Capture and inspect repository-local Codex or Claude Code conversation projections as privacy-safe, non-authoritative workflow observations. Use for safe Stop-hook projection, session-capture integrity audits, malformed/raw/tool-bearing quarantine, packet validation, or derived-index rebuilding without promoting transcript claims to goal truth, validation evidence, completion, or progress.
---

# Audit Session Governance

Treat session logs as optional observations. Never make this sidecar a canonical
workflow phase or positive completion/progress authority.

## Capture a safe projection

Configure an optional Stop hook to pass its JSON object on stdin and invoke:

```bash
python3 scripts/capture_projection.py \
  --root /absolute/path/to/repo --tool codex
```

Use `--tool claude-code` for Claude Code. The producer accepts an explicit safe
`session_id` and absolute `transcript_path` from the hook input, then atomically
overwrites `logs/<tool>/<session-id>.jsonl` with normalized user/assistant text only.
It emits no stdout, fails quiet with exit code 0 and stderr diagnostics, rejects
symlinked paths and bounded-input violations, and never copies raw input as fallback.

Keep these sensitive off-chain artifacts narrowly repository-ignored when that is the
repository's retention policy:

```gitignore
/logs/codex/
/logs/claude-code/
/.task/session_audit/
```

Adding ignore rules does not untrack files already present in the Git index. Handle
any index removal as a separate, explicitly reviewed operation.

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

`rebuild-index` is the explicit/manual path. For unattended reconstruction, first
resolve the tracked `audit-index-repair` mode with non-default caller/user/authority
activation, save that body-free resolution inside the repository, then run:

```bash
python3 scripts/session_audit.py auto-rebuild-index \
  --root /path/to/repo --mode-resolution .task/mode-resolution.json
```

The auto path revalidates the content-derived resolution against the tracked registry
and emits a before/after-hash repair receipt. Route source, semantic, task, and
workflow changes as proposals through their owning governed skills and fresh
validation.

## Preserve trust

- Allow an observation to raise a review candidate or lower confidence only.
- Never upgrade validation, progress, completion, authority, or blocker resolution.
- Treat missing events as `absence_unknown`.
- Keep capture optional and fail-quiet unless the caller or acceptance explicitly
  requires completeness.
- Require the trusted collector to re-run the bundled deterministic source validator
  before a packet can satisfy caller-required audit. A directly supplied packet is
  advisory even when it is structurally valid and says `complete`.
- Interpret a `block` finding as blocking this packet's consumption only.
- Route every session-owned cross-source or canonical claim to review. Only a
  separate comparator contract may establish a semantic mismatch or close blocker.
- Never let a packet self-authorize a close gate or semantic repair.

Read [the contract](references/session-observation-contract.md) before integrating a
packet. Use [`scripts/capture_projection.py`](scripts/capture_projection.py) for
Stop-hook projection and [`scripts/session_audit.py`](scripts/session_audit.py) for
inspection, validation, and index reconstruction.
