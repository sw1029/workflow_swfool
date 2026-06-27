---
name: manage-evidence-cache
description: "Fingerprint and classify reusable task-cycle evidence. Use when Codex needs to compare commands, inputs, environment, schema, dependencies, or artifacts and return only `reuse`, `fresh_required`, `stale`, or `unsafe_to_reuse` candidates; never use cached evidence as automatic success."
---

# Manage Evidence Cache

## Overview

Use this skill to avoid duplicate expensive checks while preserving validation integrity. The cache suggests whether prior evidence might be reused; the owning validator decides whether reuse is acceptable.

Use `/home/swfool/.codex/skills/orchestrate-task-cycle/scripts/evidence_cache.py`.

## Workflow

1. Build a fingerprint from command, input paths, environment summary, schema/contract files, dependency files, and relevant artifact hashes.
2. Query `.task/evidence_cache/index.jsonl`.
3. Classify the candidate:
   - `reuse`: all fingerprints match and prior result is not failed.
   - `fresh_required`: no comparable prior evidence exists.
   - `stale`: comparable evidence exists but an input, env, schema, dependency, or command fingerprint changed.
   - `unsafe_to_reuse`: prior evidence failed, was partial/running, lacks required fields, or the requested profile requires a fresh run.
4. Store new evidence after the owning run/validation skill returns.

## Guardrails

- Do not convert `reuse` into `passed`.
- Preserve failed rerun records; do not overwrite them with successful summaries.
- Treat secrets and raw sensitive data as non-cacheable; hash paths/content metadata instead.
