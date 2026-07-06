---
name: manage-schema-contracts
description: Maintain workspace `.schema/` records, plus `.contract/` auxiliary records when present, for shared data schemas, module contracts, script contracts, versions, target modules/scripts, producer-consumer compatibility, and causal dependency maps in service of `.agent_goal/goal_schema_contract.md`. Use when Codex adds, changes, audits, indexes, or derives tasks that may affect cross-module interfaces, serialized artifacts, CLI/script inputs and outputs, data validation rules, or compatibility between repository components.
---

# Manage Schema Contracts

## Overview

Use this skill to keep repository interface knowledge explicit under `.schema/`. Treat `.schema/` as the durable contract registry for shared schemas, module/script boundaries, versions, and causal compatibility links. Treat `.contract/` as an optional auxiliary or legacy contract area when the repository already uses it or a caller explicitly requests it.

When `.agent_goal/goal_schema_contract.md` exists, it is the governing goal-level requirement for schema/contract management. `.schema/` and `.contract/` records should be created, updated, or audited to satisfy that document's minimum fields, application intent, mandatory rules, target module/script guidance, versioning expectations, and required causal relationships.

The goal is not to document every implementation detail. Capture the contract elements future agents need to avoid breaking module compatibility when deriving tasks or changing code.

When `.agent_advice/active/*.md` names schema, module, script, validation, or design-contract concerns, treat it as non-GT contract evidence. Advice can influence a `needs_review` note, task requirement, or schema planning edge, but it cannot override `.agent_goal/goal_schema_contract.md` or repository facts.

For the canonical file layout and contract fields, read [contract-format.md](references/contract-format.md).

## Efficiency Guidance

- When several adjacent no-live/check-only tasks update the same script/module contract surface, prefer one consolidated schema refresh or one planned batch contract note instead of one near-identical contract artifact per micro-step.
- Distinguish safety-contract progress from dataset/KG goal progress. A no-live/fail-closed schema record may be valid and compatible while still not proving source-backed KG quality, readiness, or final-goal progress.
- When contract evidence depends only on unchanged prerequisite artifacts, record their paths/status/hash summary rather than requiring every historical prerequisite command to rerun.
- Mark unclear future impact as `needs_review`; do not create `.contract/` or new schema files solely to mirror a sequential version number when the prior contract already covers the unchanged surface.

## Workflow

1. Load current contract context.
   - Read `.agent_goal/goal_schema_contract.md` when present and treat it as the goal-level contract policy.
   - Read `.schema/index.md`, `.schema/causal_map.md`, `.schema/contracts.jsonl`, and contract files under `.schema/schemas/`, `.schema/modules/`, `.schema/scripts/`, and `.schema/contracts/` when present.
   - Read `.contract/` files when present; reconcile them with `.schema/` instead of silently ignoring or duplicating them.
   - Read relevant `.agent_advice/active/*.md` or a `$manage-external-advice` packet when the caller supplied advice or the advice names contract surfaces; record it as non-GT evidence.
   - Read relevant source modules, scripts, tests, schemas, manifests, CLIs, data loaders, serializers, and task/goal files affected by the current work.
   - If `.schema/` is missing, create it only when the task involves shared interfaces, `.agent_goal/goal_schema_contract.md` requires tracking, or the caller explicitly requests schema/contract tracking.

2. Identify contract surfaces.
   - Record shared data shapes, serialized files, JSON/JSONL/YAML/CSV fields, database tables, CLI flags, script inputs/outputs, public functions/classes, and module-level invariants.
   - Record shared execution-context contracts when they affect consumers: harvest-gate anchor kind and scale assumptions, terminal disposition/quarantine semantics, reharvest availability, producer directives, validation predicates/floors/inclusion checks, and collection truncation/sample flags.
   - For each contract, identify target modules/scripts, owners or producing code paths, consuming code paths, validation commands, and known compatibility assumptions.
   - Compare each record against `.agent_goal/goal_schema_contract.md` minimum fields and mandatory application rules. Mark missing required data as `not_applicable` or `needs_review` with a reason; do not omit it silently.
   - Distinguish stable public contracts from internal implementation details.

3. Manage versions.
   - Use semantic versioning when the project already does; otherwise use `vYYYYMMDD-N` as the local contract version.
   - Bump major for breaking changes, minor for backward-compatible field or behavior additions, and patch for clarifications or non-semantic documentation corrections.
   - Preserve previous contract history in `.schema/contracts.jsonl` or a superseded contract section instead of silently rewriting compatibility history.
   - Mark deprecated or superseded contracts explicitly.
   - Avoid version churn for text-only or timestamp-only no-live validation artifacts when the durable interface did not change. Record the validation evidence under the existing compatible contract instead.

4. Maintain the causal map.
   - Update `.schema/causal_map.md` with directed relationships such as `module A produces schema X`, `script B consumes schema X`, `contract C constrains module D`, and `change E breaks or preserves compatibility for F`.
   - Capture why the relationship matters, the version range, and the validation evidence.
   - Include required relationships named by `.agent_goal/goal_schema_contract.md`, especially target module/script, producer/consumer, dependency, compatibility, breaking-change, and supersession edges.
   - Prefer a concise adjacency-list or table form over prose paragraphs.

5. Check compatibility before and after changes.
   - Before implementation or task derivation, read `.agent_goal/goal_schema_contract.md`, `.schema/`, and `.contract/` to identify compatibility risks, stale contracts, and unmet goal-level requirements.
   - After code/task changes, update `.schema/` and, when applicable, `.contract/` for any changed inputs, outputs, invariants, target scripts/modules, or validation requirements.
   - When a task changes a validation predicate or producer directive, record whether the pair is mutually satisfiable or mark `needs_review`/residual repair. When a task changes collection fields consumed as closed-world evidence, record the truncation/sample flag contract or full-collection requirement.
   - If a task batched several adjacent contract checks, refresh schema/contracts once for the combined durable interface change and list the covered subchecks or prerequisite artifacts.
   - If the code changed but contract impact is unclear, create a `needs_review` contract note under `.schema/contracts/` rather than inventing compatibility; include which `.agent_goal/goal_schema_contract.md` requirement could not yet be satisfied.

6. Link with task-state indexing.
   - Run `$manage-task-state-index` `scan` after writing or updating `.schema/`, `.contract/`, or `.agent_goal/goal_schema_contract.md` artifacts.
   - Link schema contracts to tasks, candidates, misses, logs, audits, advice, and goal artifacts when the relationship is known, including links from `.agent_goal/goal_schema_contract.md` to contracts that implement it.
   - Use relation names from `$manage-task-state-index`, especially `contract_for`, `schema_for`, `module_contract_for`, `script_contract_for`, `depends_on`, `produces_schema`, `consumes_schema`, `compatible_with`, `breaks_contract`, and `supersedes_contract`.

7. Report contract status.
   - Summarize created or changed `.schema/` and `.contract/` files, affected contract IDs, version changes, target modules/scripts, causal-map changes, compatibility risks, validation evidence, and how the changes satisfy `.agent_goal/goal_schema_contract.md`.
   - Call out unresolved compatibility questions clearly.

## Guardrails

- Do not store secrets, credentials, private data, or large copyrighted excerpts in `.schema/` or `.contract/`.
- Do not mark a breaking change as compatible because tests happen to pass.
- Do not treat generated examples as canonical unless the repository already treats them as fixtures/contracts.
- Do not remove old contract history without recording the superseding version and reason.
- Do not use `.schema/` as a substitute for tests; record validation commands or evidence when available.
- Do not invent target modules, producers, consumers, or causal links. Mark uncertain relationships as `needs_review`.
- Do not manage `.schema/` or `.contract/` contrary to `.agent_goal/goal_schema_contract.md`. If the goal-level requirement cannot be met with current evidence, create or report a `needs_review` contract gap instead of guessing.
- Do not treat `.agent_advice` as schema-contract GT. If advice affects contracts, cite it as non-GT evidence and mark conflicts with GT/authority/repo facts.
- Do not write final goal schema-contract policy under `.schema/` or `.contract/`; final policy belongs at `.agent_goal/goal_schema_contract.md`.
- Do not bump schema/contract versions only because a sequential no-live task number changed when the actual interface, producer, consumer, invariant, or validation requirement is unchanged.
- Do not record validation predicates, producer directives, or closed-world collection consumers as compatible when current evidence shows `mutually_unsatisfiable_contract` or `sample_as_universe_misuse`; mark the contract gap instead of guessing a domain-specific fix.
