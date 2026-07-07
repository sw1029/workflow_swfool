---
name: plan-validation-scope
description: "Plan validation scope for task-cycle changes. Use when Codex must choose `current_only`, `affected_chain`, or `full_chain`, record changed surfaces, required commands, reused prerequisites, and escalation reasons before `$run-task-code-and-log` or `$validate-task-completion`."
---

# Plan Validation Scope

## Overview

Use this skill to choose the cheapest valid validation profile without skipping necessary prerequisite evidence.

Use `changed_surface.py` to classify changed files and `validation_scope.py` to render a validation manifest.

## Domain Adapter Contract

Use repository adapter hooks only to decide validation freshness; do not infer domain policy in this skill.

- `producer_source_paths(artifact_family, **context) -> list|dict`: optional N2 helper returning producer/verifier source paths or globs for primary deliverables.
- `output_fingerprint(...) -> str|dict`: optional N2 helper returning opaque output fingerprint/freshness metadata.
- `persistence_policy_map(**context) -> dict`: optional N3 helper returning opaque storage-policy classes, persisted classes, leak indicators, and resolution-depth enums.
- `field_authority_map(artifact_family, **context) -> dict`: optional Part O/O3' helper mapping opaque field ids to producer row fields, validator aggregate input fields, merge-rule class, and authority-formula status. The adapter owns field meanings, formulas, contradiction thresholds, and what counts as the same sampled population.

Missing hooks fail quiet to existing validation-scope rules. The manifest may carry unchecked-hook warnings, but it must not invent reharvest commands, identifier classes, or thresholds.

## Workflow

1. Collect changed files from Git, the cycle ledger, or a subskill result.
2. Classify surfaces: `source`, `tests`, `runtime_config`, `schema`, `contract`, `task_state`, `issue`, `docs`, or `unknown`.
3. Choose:
   - `current_only` when only the current validator and direct predecessor hash/status checks are needed.
   - `affected_chain` when changed surfaces can affect selected prerequisites.
   - `full_chain` for live dispatch, readiness promotion, issue closure, shared validator/runtime changes, explicit user request, or high-risk contract logic.
   - Require a fresh or affected-chain profile when Part L evidence says the consumed lane, upstream production contract, metric basis input class, or surface-field class map changed. Do not plan reuse-only validation for current-lane capability, adoption, comparison, high-water, or close claims under `pass_on_stale_lane`, `decision_metadata_revision`, or `basis_overclaim`.
   - Require affected-chain or full-chain validation when Part M changes shared harvest gates, terminal disposition policy, reharvest paths, producer directives, validation predicates, or closed-world collection consumers. Do not plan reuse-only validation for long-run harvest, high-cost disposition, predicate/directive close, or collection-membership pass claims under `lane_incompatible`, `scale_incompatible`, `contract_conflict`, `mutually_unsatisfiable_contract`, or `sample_as_universe_misuse`.
   - Require fresh or affected-chain validation when Part N evidence reports producer-source changes without refreshed output fingerprints, `deliverable_stale`, storage-policy/resolution-depth changes, `anonymization_theater`, or `mutually_unsatisfiable_persistence_contract`. Flow: adapter hook absent -> fail quiet; changed files intersect `producer_source_paths` and `output_fingerprint` did not update -> plan regeneration/revalidation before reuse; `persistence_policy_map` reports unresolved storage/ability conflict -> plan contract reconciliation validation before close.
   - For producer-path repairs, when `field_authority_map` shows that changed producer row fields and validator aggregate inputs can diverge or a merge rule can override the changed field, set `dual_bookkeeping_risk=true` and require a row-vs-aggregate same-sample comparison in the manifest. If that comparison reports contradictions, close is invalid until `$manage-schema-contracts` records a single authority formula or residual blocker. If the hook is absent, fail quiet and keep existing scope rules.
4. Record required commands, reusable prerequisites, fingerprints or hashes, and escalation reason.
5. Save the manifest as a workflow artifact when the caller needs durable evidence.

## Guardrails

- Do not use `full_chain` by default merely because it is more exhaustive.
- Do not reuse prerequisite evidence when environment, schema, dependency, command, or input fingerprints are stale.
- Do not reuse stale production-lane, stale-measurement, basis-overclaimed, or field-class-incomplete evidence as the validation basis for completion or advanced progress.
- Do not reuse harvest validation, terminal disposition, predicate/directive compatibility, or collection-membership evidence after the corresponding Part M contract changed unless the affected-chain manifest proves the consumed surface is still compatible.
- Do not reuse deliverable, schema, or privacy-policy evidence after a Part N producer path or persistence-policy contract changed unless the manifest proves refreshed output fingerprints and resolved storage/ability axes. Do not double-count a reharvest/disposition issue as both M2 and N2; N2 only covers whether the repaired producer path reached the deliverable.
- Do not reuse aggregate validation evidence under Part O/O3' `dual_bookkeeping_risk` unless the same-sample row-vs-aggregate comparison passed. Do not double-count O3' as N2 deliverable staleness or F1 verifier coupling: O3' only covers producer and validator using different authority formulas for the same meaning.
- Do not invent commands; use task instructions, repository scripts, governance output, or validation policy.
