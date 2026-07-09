---
name: manage-schema-contracts
description: Maintain workspace `.schema/` records, plus `.contract/` auxiliary records when present, for shared data schemas, module contracts, script contracts, versions, target modules/scripts, producer-consumer compatibility, and causal dependency maps in service of `.agent_goal/goal_schema_contract.md`. Use when Codex adds, changes, audits, indexes, or derives tasks that may affect cross-module interfaces, serialized artifacts, CLI/script inputs and outputs, data validation rules, or compatibility between repository components.
---

# Manage Schema Contracts

## Overview

Use this skill to keep repository interface knowledge explicit under `.schema/`. Treat `.schema/` as the durable contract registry for shared schemas, module/script boundaries, versions, and causal compatibility links. Treat `.contract/` as an optional auxiliary or legacy contract area when the repository already uses it or a caller explicitly requests it.

When `.agent_goal/goal_schema_contract.md` exists, it is the governing goal-level requirement for schema/contract management. `.schema/` and `.contract/` records should be created, updated, or audited to satisfy that document's minimum fields, application intent, mandatory rules, target module/script guidance, versioning expectations, and required causal relationships.

The goal is not to document every implementation detail. Capture the contract elements future agents need to avoid breaking module compatibility when deriving tasks or changing code.

When called from `$orchestrate-task-cycle`, perform deterministic contract management directly where possible. Before delegation, classify `final_direction_ownership: true|false`; omission blocks routing. If delegated analysis is needed, request Tier 3 `gpt-5.6-terra/high`, or Tier 4 `gpt-5.6-terra/xhigh` when the review controls compatibility, blockers, or irreversible version decisions. Promote to Tier 5 `gpt-5.6-sol/xhigh` only when one agent owns a final architecture-direction change, `final_direction_ownership` is true, the structured `architecture_direction_change` signal is true, and `signal_evidence.architecture_direction_change` is a structured reference to the controlling architecture evidence; recommendation-only schema review remains capped at Tier 4. Record routing applicability and enforcement; do not use delegated `ultra` or claim Terra/Sol execution when routing was prompt-only or inherited-unverified.

When `.agent_advice/active/*.md` names schema, module, script, validation, or design-contract concerns, treat it as non-GT contract evidence. Advice can influence a `needs_review` note, task requirement, or schema planning edge, but it cannot override `.agent_goal/goal_schema_contract.md` or repository facts.

For the canonical file layout and contract fields, read [contract-format.md](references/contract-format.md).

## Domain Adapter Contract

Prefer repository-owned adapter policy over schema-author local assumptions. The module or caller packet may expose:

- `persistence_policy_map(**context) -> dict`: optional N3 helper returning opaque storage-axis classes, actually persisted classes, leak indicators, required resolution-depth enum, and any capability-preserving alternative ids. The adapter owns what counts as identifier surface, leak equivalence, allowed storage class, and resolution floor.
- `field_authority_map(artifact_family, **context) -> dict`: optional Part O/O3' helper returning opaque field ids, producer row fields, validator aggregate inputs, merge-rule class, authority formula id/status, and contradiction evidence for row-vs-aggregate same-sample checks. The adapter owns field meanings, formulas, and sampled-population rules.
- `adapter_hook_contracts(**context) -> list|dict`: optional Q5 helper listing Part P/Q hook contracts such as `landed_feature_inventory`, `producer_execution_evidence`, `input_source_lineage`, `governance_packet_budget`, `self_resolvable_input_probe`, `feature_presence_evidence`, `hook_registry`, and `reason_code_rank`, plus consumer task ids when known. If absent, fail quiet for ordinary schema work.
- `hook_registry(**context) -> dict`: optional Q5 helper returning `defined_hooks` for contract-debt accounting only. When a consumer attempts to use a hook that is absent from the registry, report `adapter_hook_debt(hook_id, consumer_task)` and mark hook-dependent clauses `unenforced` instead of silently treating the clause as pass or hard failure.
- `policy_consumption_sites(policy_id, **context) -> list|dict`: optional S8 helper returning opaque judgment sites and `reflects_policy: bool` for a changed goal-truth policy, acceptance meaning, cap, or pass condition. If any site reports `reflects_policy=false`, record `policy_propagation_incomplete` debt and a derive/update backlog item for that site; do not declare the contract-facing policy applied from producer-layer changes alone. If absent or malformed, fail quiet for ordinary schema work and record `propagation=unverified` only when a caller attempts to claim policy propagation.
- `consumption_state(advice_clause_id, **context) -> dict`: optional S6 helper returning `state: pending|wired|verified`, the affected opaque contract or blocker-signature family when known, and evidence refs for a workflow/skill advice clause that changed a contract-facing judgment. If absent or malformed, fail quiet for ordinary schema work and record `consumption_state_unverified` only when a caller attempts to verify that clause.

If a hook is absent, fail quiet and keep existing schema-contract rules, except Q5 hook-contract absence is visible debt only: record debt/warn evidence when a consumer attempted to use the missing hook, keep the underlying hook-dependent judgment as no-op, and do not force implementation from this skill. S8 propagation debt is visibility and backlog routing only. S6 advice-consumption debt is separate from Q5 adapter-hook debt: record `unconsumed_advice_regression` only for a named advice clause whose targeted recurrence reappears before `verified`, not for a missing hook alone. Do not infer privacy classes, identifier forms, merge depth, field authority, formulas, sampled populations, hook existence, hook debt thresholds, policy-consumption sites, consumption verification, or code-convention policy from project filenames, sample text, or domain vocabulary in this skill.

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
   - Record storage-policy contracts as two independent axes when `persistence_policy_map` is supplied: axis A is storage class (`plaintext`, `opaque_id`, or `not_stored` as adapter enums), and axis B is resolution depth (`none`, `same_surface`, or `cross_surface` as adapter enums). Treat these enum names as opaque policy values, not domain semantics.
   - Record field-authority contracts when `field_authority_map` is supplied: the durable contract must name one authority formula for each affected opaque field id and must link producer row fields to validator aggregate inputs without inventing domain-specific formulas.
   - Record Part P/Q adapter-hook contracts when `adapter_hook_contracts` or caller packets name hook-consuming clauses. For each attempted consumer, compare the hook id against `hook_registry.defined_hooks` when available. If the hook is missing, report `adapter_hook_debt(hook_id, consumer_task)`, mark the dependent clause `unenforced`, and leave the original judgment fail-quiet/no-op unless a separate acceptance contract requires the hook.
   - Record S8 policy propagation state when a policy, acceptance meaning, cap, or pass condition changes and caller evidence names a `policy_id`. Compare `policy_consumption_sites` when supplied; store each opaque site and `reflects_policy` status. Any false site is `policy_propagation_incomplete` debt plus a backlog item to update that site, not a schema fail-close by itself. If the hook is absent, preserve `propagation=unverified`.
   - Record S6 advice-consumption state when active advice or caller packets name a workflow/skill clause that changes a contract-facing judgment. Store `consumption_state: pending|wired|verified`, the opaque clause id, affected contract or blocker-signature family, and evidence refs. If a targeted recurrence appears while state is not `verified`, record `unconsumed_advice_regression` and preserve a derive backlog item to wire, verify, defer, reject, or retire the clause; do not change the underlying contract verdict solely from this debt.
   - Treat missing `code_convention_contract` that affects Q6 depth/fan-out enforcement as `adapter_hook_debt(code_convention_contract, code_structure_audit)` visibility evidence only. Do not create repo-specific depth, fan-out, reuse-root, inheritance-root, or dependency-direction rules in this skill.
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
   - When a task changes storage or privacy policy and `persistence_policy_map` is available, apply the N3 flow: hook absent -> fail quiet; hook present -> compare storage axis and resolution-depth axis independently; if the same adapter-classified identifier information leaks through another persisted class while only one class is anonymized, record `anonymization_theater`; if storage policy and required resolution depth cannot both hold, record `mutually_unsatisfiable_persistence_contract` and require same-task reconciliation, explicit residual scope, terminal blocker, or user escalation. Always present an ability-preserving opaque-id plus transient-merge-key alternative first when the adapter supplies it.
   - When `field_authority_map` and validation-scope evidence report row-vs-aggregate contradictions greater than zero, do not mark the contract or task close-compatible. Require a same-task or residual contract revision that establishes a single authority formula before close, terminal blocker, or user escalation. If the hook is absent, fail quiet and keep existing compatibility checks.
   - When a representative-output, validation, derive, or code-structure consumer attempts to consume a Part P/Q hook that is not defined, do not let the absence disappear as a silent pass. Emit hook debt, mark that hook-dependent clause `unenforced`, and preserve a derive backlog item for hook implementation or convention-contract supply. Keep this distinct from Q3 fabricated provenance: Q5 records honest missing-hook debt; Q3 fail-closes only a false claim that a missing hook produced an artifact.
   - When a policy change is claimed as applied, do not stop at producer-layer contract updates. If `policy_consumption_sites` reports any consumer with `reflects_policy=false`, record `policy_propagation_incomplete`, keep the dependent judgment marked as policy-unreflected, and preserve a derive backlog item for that site. If the hook is absent, record `propagation=unverified` and keep existing schema behavior.
   - When advice-consumption state is present, keep it in the relevant schema or contract note until `verified`, deferred, rejected, or retired with evidence. A recurrent targeted blocker with `state != verified` is `unconsumed_advice_regression` visibility debt only; do not fail-close schema compatibility from S6 alone and do not double-count it as adapter hook debt unless a separate missing-hook fact is present.
   - If a task batched several adjacent contract checks, refresh schema/contracts once for the combined durable interface change and list the covered subchecks or prerequisite artifacts.
   - If the code changed but contract impact is unclear, create a `needs_review` contract note under `.schema/contracts/` rather than inventing compatibility; include which `.agent_goal/goal_schema_contract.md` requirement could not yet be satisfied.

6. Link with task-state indexing.
   - Run `$manage-task-state-index` `scan` after writing or updating `.schema/`, `.contract/`, or `.agent_goal/goal_schema_contract.md` artifacts.
   - Link schema contracts to tasks, candidates, misses, logs, audits, advice, and goal artifacts when the relationship is known, including links from `.agent_goal/goal_schema_contract.md` to contracts that implement it.
   - Use relation names from `$manage-task-state-index`, especially `contract_for`, `schema_for`, `module_contract_for`, `script_contract_for`, `depends_on`, `produces_schema`, `consumes_schema`, `compatible_with`, `breaks_contract`, and `supersedes_contract`.

7. Report contract status.
   - Summarize created or changed `.schema/` and `.contract/` files, affected contract IDs, version changes, target modules/scripts, causal-map changes, compatibility risks, validation evidence, and how the changes satisfy `.agent_goal/goal_schema_contract.md`.
   - Report `agent_routing_applicability: deterministic_only` unless analysis was delegated; delegated results include `policy_id`, `profile_id`, `routing_tier`, `final_direction_ownership`, requested model/effort, reason codes, signals/evidence, `routing_violations` even when empty, and routing enforcement or limitation.
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
- Do not record a storage-policy contract as closed when `anonymization_theater` or `mutually_unsatisfiable_persistence_contract` is unresolved. Do not double-count it as Part M predicate/directive unsatisfiability unless a separate M3 predicate/directive conflict is present; Part N covers storage policy versus resolution ability.
- Do not record a producer/validator field contract as closed when Part O/O3' row-vs-aggregate contradictions remain. Do not double-count the same contradiction as N2 deliverable freshness or F1 verifier coupling unless packets separately report those facts; O3' covers authority-formula divergence only.
- Do not treat a missing Part P/Q adapter hook or missing `code_convention_contract` as a hidden pass. Record `adapter_hook_debt` and `unenforced` only when a consumer attempted to use that hook or contract; otherwise fail quiet and keep existing schema behavior.
- Do not mark a policy, acceptance meaning, cap, or pass-condition change fully propagated while S8 reports any `reflects_policy=false` consumer site. Missing propagation evidence is `propagation=unverified` warning/debt, not fail-close.
- Do not mark advice-consumption clauses `verified` from contract presence alone. Require recurrence-free evidence, explicit retirement, or current evidence that the targeted bypass no longer applies. Keep `unconsumed_advice_regression` separate from `adapter_hook_debt`.
