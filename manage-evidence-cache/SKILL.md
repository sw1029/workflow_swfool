---
name: manage-evidence-cache
description: "Fingerprint and classify reusable task-cycle evidence. Use when Codex needs to compare commands, inputs, environment, schema, dependencies, or artifacts and return only `reuse`, `fresh_required`, `stale`, or `unsafe_to_reuse` candidates; never use cached evidence as automatic success."
---

# Manage Evidence Cache

## Overview

Use this skill to avoid duplicate expensive checks while preserving validation integrity. The cache suggests whether prior evidence might be reused; the owning validator decides whether reuse is acceptable.

Use `${CODEX_HOME:-$HOME/.codex}/skills/orchestrate-task-cycle/scripts/evidence_cache.py`.

## Workflow

1. Build a fingerprint from command, input paths, environment summary, schema/contract files, dependency files, and relevant artifact hashes.
   - Require a non-empty command plus at least one hashed input/schema/dependency/source artifact, schema-contract version, environment value, or non-empty structured context. Missing or unhashable declared paths fail closed instead of forming a reusable empty fingerprint.
   - Include abstract Part L cache inputs when supplied: production/current lane ids, upstream contract version or measurement run id, gating-axis producer status, quota mode, required scale and throughput evidence, metric consumed-input classes, and surface-field class maps. Hash or summarize these values; do not store raw source bodies or secrets.
2. Query `.task/evidence_cache/index.jsonl`. Resolve an explicit relative `--cache` path against `--root`; use an absolute path only when the caller supplies one explicitly. New records use `format_version: 1`; versionless legacy rows are readable but are unsafe to reuse until they contain verifiable evidence hashes.
3. Classify the candidate:
   - `reuse`: all fingerprints match and prior result is not failed.
   - `fresh_required`: no comparable prior evidence exists.
   - `stale`: comparable evidence exists but an input, env, schema, dependency, or command fingerprint changed.
   - `unsafe_to_reuse`: prior evidence failed, was partial/running, lacks required fields, or the requested profile requires a fresh run.
4. Store new evidence after the owning run/validation skill returns. Require at least one existing evidence path and store its event-time path kind and SHA-256. Recompute those hashes on every reuse check; missing or changed evidence is `unsafe_to_reuse`.

## Guardrails

- Do not convert `reuse` into `passed`.
- Do not skip malformed JSONL, unsupported format versions, or duplicate record IDs. Fail closed before appending, and use the helper's lock plus fsync-backed append for concurrent writers.
- Do not return `reuse` for current-lane capability, adoption, comparison, high-water, or close evidence when lane identity, upstream contract, measurement run id, metric basis input class, or surface-field class-map fingerprints differ. Return `stale` or `fresh_required`.
- Preserve failed rerun records; do not overwrite them with successful summaries.
- Treat secrets and raw sensitive data as non-cacheable; hash paths/content metadata instead.
