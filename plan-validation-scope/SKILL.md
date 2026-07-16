---
name: plan-validation-scope
description: "Plan validation scope for task-cycle changes. Use when Codex must choose `current_only`, `affected_chain`, or `full_chain`, record changed surfaces, required commands, reused prerequisites, and escalation reasons before `$run-task-code-and-log` or `$validate-task-completion`."
---

# Plan Validation Scope

## Overview

Use this skill to choose the cheapest valid validation profile without skipping necessary prerequisite evidence.

Use the `changed-surface` module command to classify changed files. Use `plan` before governance and `finalize` after implementation/run evidence identifies the actual changed files. Finalization may retain or raise the planned profile; it must never lower it.

```bash
SKILLS_ROOT="${CODEX_HOME:-$HOME/.codex}/skills"
PYTHONPATH="$SKILLS_ROOT/plan-validation-scope/scripts" \
  python3 -m plan_validation_scope <changed-surface|plan|finalize> [arguments]
```

## Domain Adapter Contract

Use repository adapter hooks only to decide validation freshness; do not infer domain policy in this skill.

- `producer_source_paths(artifact_family, **context) -> list|dict`: optional N2 helper returning producer/verifier source paths or globs for primary deliverables.
- `output_fingerprint(...) -> str|dict`: optional N2 helper returning opaque output fingerprint/freshness metadata.
- `persistence_policy_map(**context) -> dict`: optional N3 helper returning opaque storage-policy classes, persisted classes, leak indicators, and resolution-depth enums.
- `field_authority_map(artifact_family, **context) -> dict`: optional Part O/O3' helper mapping opaque field ids to producer row fields, validator aggregate input fields, merge-rule class, and authority-formula status. The adapter owns field meanings, formulas, contradiction thresholds, and what counts as the same sampled population.
- `gate_artifact_compatibility(artifact_class, gate_id, **context) -> dict`: optional S9 helper returning `compatible: bool` and `unmet_precondition` before planning validation for an artifact/gate pair. If `compatible=false`, mark that gate `not_evaluated`/skipped for that artifact class, preserve `gate_compat=incompatible`, and do not plan residual or escalation validation for the impossible precondition. If absent or malformed, fail quiet to existing validation-scope rules and emit `gate_compat=unverified` when decision-relevant.

Missing hooks fail quiet to existing validation-scope rules. The manifest may carry unchecked-hook warnings, but it must not invent reharvest commands, identifier classes, artifact-class meanings, gate preconditions, or thresholds.

## Workflow

1. Before governance, collect planned files or surfaces from `task.md`, acceptance, and repository policy. Run the `plan` command; an unknown planned surface conservatively selects `affected_chain` and stays visibly unfinalized.
2. Classify surfaces: `source`, `tests`, `runtime_config`, `schema`, `contract`, `task_state`, `issue`, `docs`, or `unknown`.
3. Choose:
   - `current_only` when only the current validator and direct predecessor hash/status checks are needed.
   - `affected_chain` when changed surfaces can affect selected prerequisites.
   - `full_chain` for live dispatch, readiness promotion, issue closure, shared validator/runtime changes, explicit user request, or high-risk contract logic.
   - Require a fresh or affected-chain profile when Part L evidence says the consumed lane, upstream production contract, metric basis input class, or surface-field class map changed. Do not plan reuse-only validation for current-lane capability, adoption, comparison, high-water, or close claims under `pass_on_stale_lane`, `decision_metadata_revision`, or `basis_overclaim`.
   - Require affected-chain or full-chain validation when Part M changes shared harvest gates, terminal disposition policy, reharvest paths, producer directives, validation predicates, or closed-world collection consumers. Do not plan reuse-only validation for long-run harvest, high-cost disposition, predicate/directive close, or collection-membership pass claims under `lane_incompatible`, `scale_incompatible`, `contract_conflict`, `mutually_unsatisfiable_contract`, or `sample_as_universe_misuse`.
   - Require fresh or affected-chain validation when Part N evidence reports producer-source changes without refreshed output fingerprints, `deliverable_stale`, storage-policy/resolution-depth changes, `anonymization_theater`, or `mutually_unsatisfiable_persistence_contract`. Flow: adapter hook absent -> fail quiet; changed files intersect `producer_source_paths` and `output_fingerprint` did not update -> plan regeneration/revalidation before reuse; `persistence_policy_map` reports unresolved storage/ability conflict -> plan contract reconciliation validation before close.
   - For producer-path repairs, when `field_authority_map` shows that changed producer row fields and validator aggregate inputs can diverge or a merge rule can override the changed field, set `dual_bookkeeping_risk=true` and require a row-vs-aggregate same-sample comparison in the manifest. If that comparison reports contradictions, close is invalid until `$manage-schema-contracts` records a single authority formula or residual blocker. If the hook is absent, fail quiet and keep existing scope rules.
   - Before planning a gate for an artifact class, apply S9 `gate_artifact_compatibility` when supplied. If the artifact class cannot satisfy the gate's adapter-owned precondition, skip that gate in the manifest as category-incompatible and do not plan repeated failure, residual, or escalation validation for it. If the hook is absent, keep existing planning and record `gate_compat=unverified` only as warning evidence.
4. After governance and run/review evidence, collect the authoritative actual changed-file list and run `python3 -m plan_validation_scope finalize --task-id <active-task-id> --plan-json <plan>` under the package `PYTHONPATH`. Finalization accepts only the same task's `step: validation_scope_plan`, `mode: plan`, `finalized: false` manifest with a non-placeholder task ID. Treat missing actual-surface input, identity mismatch, a finalized/non-plan input, or missing final validation commands as blocking. Preserve the plan profile as a floor and raise it when actual surfaces or explicit risk flags require broader validation.
5. Record required commands, reusable prerequisites, fingerprints or hashes, escalation reasons, `profile_floor`, and whether finalization raised the profile.
6. Save both manifests as workspace-bounded workflow artifacts; `--output` must remain under `--root`, including through symlinks. Pass the finalized manifest to `$validate-task-completion`.

## Guardrails

- Do not use `full_chain` by default merely because it is more exhaustive.
- Do not run completion validation from the pre-change plan alone. `validation_scope_finalize` must bind the profile to an explicit actual changed-file list, including an explicit empty list when nothing changed.
- Do not lower the pre-change profile during finalization.
- Do not reuse prerequisite evidence when environment, schema, dependency, command, or input fingerprints are stale.
- Do not reuse stale production-lane, stale-measurement, basis-overclaimed, or field-class-incomplete evidence as the validation basis for completion or advanced progress.
- Do not reuse harvest validation, terminal disposition, predicate/directive compatibility, or collection-membership evidence after the corresponding Part M contract changed unless the affected-chain manifest proves the consumed surface is still compatible.
- Do not reuse deliverable, schema, or privacy-policy evidence after a Part N producer path or persistence-policy contract changed unless the manifest proves refreshed output fingerprints and resolved storage/ability axes. Do not double-count a reharvest/disposition issue as both M2 and N2; N2 only covers whether the repaired producer path reached the deliverable.
- Do not reuse aggregate validation evidence under Part O/O3' `dual_bookkeeping_risk` unless the same-sample row-vs-aggregate comparison passed. Do not double-count O3' as N2 deliverable staleness or F1 verifier coupling: O3' only covers producer and validator using different authority formulas for the same meaning.
- Do not treat S9 artifact/gate incompatibility as a failed validation scope. Skip the incompatible gate for that artifact class, keep any compatible partial validation, and preserve `gate_compat` warning/skipped evidence.
- Do not invent commands; use task instructions, repository scripts, governance output, or validation policy.
