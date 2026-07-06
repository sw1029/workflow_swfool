---
name: plan-validation-scope
description: "Plan validation scope for task-cycle changes. Use when Codex must choose `current_only`, `affected_chain`, or `full_chain`, record changed surfaces, required commands, reused prerequisites, and escalation reasons before `$run-task-code-and-log` or `$validate-task-completion`."
---

# Plan Validation Scope

## Overview

Use this skill to choose the cheapest valid validation profile without skipping necessary prerequisite evidence.

Use `changed_surface.py` to classify changed files and `validation_scope.py` to render a validation manifest.

## Workflow

1. Collect changed files from Git, the cycle ledger, or a subskill result.
2. Classify surfaces: `source`, `tests`, `runtime_config`, `schema`, `contract`, `task_state`, `issue`, `docs`, or `unknown`.
3. Choose:
   - `current_only` when only the current validator and direct predecessor hash/status checks are needed.
   - `affected_chain` when changed surfaces can affect selected prerequisites.
   - `full_chain` for live dispatch, readiness promotion, issue closure, shared validator/runtime changes, explicit user request, or high-risk contract logic.
   - Require a fresh or affected-chain profile when Part L evidence says the consumed lane, upstream production contract, metric basis input class, or surface-field class map changed. Do not plan reuse-only validation for current-lane capability, adoption, comparison, high-water, or close claims under `pass_on_stale_lane`, `decision_metadata_revision`, or `basis_overclaim`.
   - Require affected-chain or full-chain validation when Part M changes shared harvest gates, terminal disposition policy, reharvest paths, producer directives, validation predicates, or closed-world collection consumers. Do not plan reuse-only validation for long-run harvest, high-cost disposition, predicate/directive close, or collection-membership pass claims under `lane_incompatible`, `scale_incompatible`, `contract_conflict`, `mutually_unsatisfiable_contract`, or `sample_as_universe_misuse`.
4. Record required commands, reusable prerequisites, fingerprints or hashes, and escalation reason.
5. Save the manifest as a workflow artifact when the caller needs durable evidence.

## Guardrails

- Do not use `full_chain` by default merely because it is more exhaustive.
- Do not reuse prerequisite evidence when environment, schema, dependency, command, or input fingerprints are stale.
- Do not reuse stale production-lane, stale-measurement, basis-overclaimed, or field-class-incomplete evidence as the validation basis for completion or advanced progress.
- Do not reuse harvest validation, terminal disposition, predicate/directive compatibility, or collection-membership evidence after the corresponding Part M contract changed unless the affected-chain manifest proves the consumed surface is still compatible.
- Do not invent commands; use task instructions, repository scripts, governance output, or validation policy.
