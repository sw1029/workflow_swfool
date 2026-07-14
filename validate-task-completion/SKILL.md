---
name: validate-task-completion
description: "Run a common pre-close task completion gate combining repository/OOM audits, environment checks, execution logs, task_miss and issue state, advice usage, code conventions, semantic structure movement, task-index traceability, and agent logs into a `complete`, `partial`, or `failed` candidate. Use before declaring task completion, closing a workflow cycle, promoting or deleting artifacts, or reporting final completion; governed cycles require orchestrator finalization and a verified receipt before consumption."
---

# Validate Task Completion

## Overview

Use this skill as the final evaluation gate before saying a repository task is done. It gathers evidence from the task lifecycle, runs or verifies required audits, and produces one verdict candidate: `complete`, `partial`, or `failed`.

In a governed cycle, evaluate without publishing current registry, ledger, seal, index, or final report truth. Emit the final candidate described in [completion-gates.md](references/completion-gates.md); `$orchestrate-task-cycle` is the sole owner of revision assignment, supersession, atomic current-state publication, and the content-bound finalization receipt. A candidate or draft report is not authoritative and cannot be consumed by derive, dashboard, handoff, or completion reporting.

Also report task progress separately from validation correctness. A task can be validly complete for its narrow scope while still making only safety or no-live progress toward the final goal.

The validation report is evidence, not implementation. If the verdict is `partial` or `failed`, preserve the blockers in `.task/task_miss/` or the task index so the next workflow cycle can act on them.

ID consistency is a required validation concern when a task-state index exists. If no ID context exists and the task did not require indexed governance, continue the completion validation and mark ID traceability `not_applicable` or `missing` as appropriate.

When `task.md`, a caller packet, or active workflow evidence references `.agent_advice`, validate it as non-GT direction evidence. Confirm the advice was incorporated, deferred, rejected, or left active with a rationale; never count advice as `.agent_goal` goal truth or authority.

## Agent Routing Policy

- When called from `$orchestrate-task-cycle`, consume the canonical orchestration reference [workflow-routing.md](../orchestrate-task-cycle/references/workflow-routing.md) as caller context, but keep completion validation's own routing below.
- Treat completion validation repository audits as Tier 4 important work review. Invoke `$inspect-repo-with-agents` with `profile_id: completion_review`, `model_ref: model_ref:balanced`, and `reasoning_effort: xhigh`; resolve the runtime model only from caller or repository configuration.
- Treat relevant completion OOM audits the same way through `$inspect-oom-risk`.
- Keep ID-only traceability correction routed through `$manage-task-state-index` with fixed `reasoning_effort: medium`.
- If a tool cannot enforce model/effort, encode the profile/reference request in the prompt and record reference-only, prompt-only, or inherited-unverified routing in the validation report. Do not claim configured-model execution or use delegated `ultra`.

## Domain Adapter Contract

Prefer repository-owned adapter outputs or caller packets over validation-local domain assumptions. The validator may consume these optional Part N and Part O hooks:

- `substance_density(metric_id, **context) -> dict`: N1 helper returning `referent_meaning_ratio`, `opaque_surrogate_ratio`, and adapter-owned `floor`. Missing hook is fail-quiet and preserves existing progress classification while recording `substance_density_unchecked` when supplied.
- `producer_source_paths(artifact_family, **context) -> list|dict`: N2 helper returning producer/verifier source paths or globs for primary deliverables.
- `output_fingerprint(...) -> str|dict`: N2 helper returning opaque output fingerprint and optional freshness metadata.
- `persistence_policy_map(**context) -> dict`: N3 helper returning opaque storage-policy classes, actually persisted classes, leak indicators, and resolution-depth enums.
- `proxy_population(proxy_id, **context) -> dict`: O4 helper returning opaque proxy-population fields such as `measures_new_behavior`, `new_behavior_sample_count_field`, `min_sample_k`, and sample-count/evaluation status. Missing hook is fail-quiet and preserves existing completion behavior unless caller acceptance explicitly requires proxy non-triviality.
- `producer_execution_evidence(run_id, **context) -> dict`: P2 helper returning whether a run performed fresh producer execution plus opaque evidence fields. Missing hook is fail-quiet and records freshness unverifiability unless caller acceptance requires this gate.
- `hook_registry(**context) -> dict`: Q3 helper returning `defined_hooks` and optional opaque source ids for repository-defined adapter hooks. If absent or malformed, fail quiet with `provenance_unverifiable`; do not invent hook existence from filenames or domain vocabulary. If supplied, any artifact that labels an `adapter_hook` or `domain_meaning_owner` as its provenance must reference a hook in `defined_hooks`; otherwise completion fail-closes with `fabricated_provenance_label`.
- `target_metric_delta(acceptance_spec, prev_artifact, curr_artifact, **context) -> dict`: optional S7/S11 helper returning `metric`, `before`, `after`, `moved`, `artifact_class`, `current_artifact_id`, `body_projection_fingerprint`, `baseline_fingerprint`, and recomputed-field/source ids when available. Use it immediately before completing a measurable target. Independently recomputed actual-artifact values outrank verifier, current-transform, producer, carried-forward, and workflow claims. If `moved=false` and the current artifact only adds measurement/proxy/observed fields for that metric, return `partial` or `failed` with `measurement_without_movement`. Fixture/unit-scalar movement cannot satisfy a required real-artifact class. If required body projection cannot be recomputed, return `actual_body_truth_basis=not_evaluated`; do not close.

Do not define identifier surfaces, meaning floors, regeneration commands, storage policy thresholds, privacy leak equivalence, proxy populations, new-behavior samples, sample thresholds, producer-execution meaning, input-generation classes, hook registries, target metrics, artifact-class meanings, measurement-only field classes, or hook provenance labels in this skill. If hooks are absent, fail quiet to legacy validation behavior unless a caller acceptance contract explicitly requires the missing gate. Q3 fail-quiet applies only when an artifact does not claim hook-produced provenance; a false hook label is fail-close when the registry is available.

## Workflow

1. Collect local evidence.
   - Read `task.md`, `.task/index.jsonl`, `.task/index.md`, `.task/task_miss/`, `.task/candidate_task/`, `.issue/`, `.agent_log/`, `.agent_goal/goal_schema_contract.md`, `.agent_advice/`, `.schema/`, and `.contract/` when present.
   - Read caller-supplied Part N fields when present: `constraint_forced_vacuity`, `substance_density_unchecked`, `referent_meaning_ratio`, `opaque_surrogate_ratio`, `substance_density_floor`, `vacuity_cause`, `deliverable_stale`, `contract_only`, `changed_producer_source_paths`, `producer_source_paths`, `output_fingerprint`, `output_fingerprint_updated`, `anonymization_theater`, `mutually_unsatisfiable_persistence_contract`, `persistence_policy_axes`, `adapter_hook_demand`, `hook_demand_unaccounted`, `hook_supply_required`, and `demanded_hooks`.
   - Read caller-supplied Part O/O4' fields when present: `trivially_satisfiable_proxy`, `proxy_population`, `measures_new_behavior`, `new_behavior_sample_count`, `new_behavior_sample_count_field`, `proxy_evaluation_status`, and `proxy_not_applicable`.
   - Read caller-supplied Part P fields when present: `required_freshness_class`, `producer_executed`, `freshness_class_unverifiable`, `condition_unsatisfiable_for_input_generation`, `feature_regression_count`, `feature_regressed_artifact`, `feature_manifest_missing`, `frozen_input_consumption_streak`, and `diminishing_reprocess`.
   - Read caller-supplied Part Q provenance fields when present: `adapter_hook`, `domain_meaning_owner`, `defined_hooks`, `hook_registry_status`, `provenance_unverifiable`, and `fabricated_provenance_label`.
   - Read caller-supplied S7/S11 target-movement fields when present: `target_metric_delta`, `metric`, `before`, `after`, `moved`, `artifact_class`, `artifact_class_unverified`, `movement_unverified`, `measurement_without_movement`, `movement_on_fixture_only`, and `required_artifact_class`.
   - Read exact decision artifact identity, gate compatibility, actual-truth, and axis-scoped source-separation fields when present. Exclude incompatible or scope-unverified gates from completion and preserve `self_grounded` separately from independent semantic verification.
   - When the caller supplies session governance, consume only the validated privacy-safe packet from [$audit-session-governance](../audit-session-governance/SKILL.md). Never inspect raw/slim transcript text as validation evidence. Treat missing, incomplete, quarantined, or transcript-only capture as advisory/`not_evaluated` unless acceptance or the caller independently declared it required.
   - Read adapter consumer conformance rows when present. Required project-owned consumers must prove load, hook resolution/callability, signature bind, invocation, valid return, exact artifact echo, decision consumption, and probe evidence ref. Adapter self-attestation and repository-root import are insufficient.
   - Use the bundled collector for a compact inventory:

     ```bash
     python3 "${CODEX_HOME:-$HOME/.codex}/skills/validate-task-completion/scripts/collect_completion_evidence.py" --root . --include-git
     ```

2. Ensure task-state traceability.
   - If `.task/index.jsonl` or `.task/index.md` is missing or stale, use `$manage-task-state-index` to initialize, scan, and link the current artifacts.
   - The active task should link to relevant execution logs, audit logs, validation reports, and active or resolved task_miss files.
   - Active or resolved issue records should link to relevant tasks, execution logs, validation reports, task_miss files, and issue resolution evidence when present.
   - Run `$manage-task-state-index` deterministic global `audit`. Use `audit --write-report` when this validation report is closing a workflow cycle.
   - If the workflow authorizes agents and ID context exists, spawn one additional read-only ID consistency agent. This agent is separate from repo/OOM/env/run validation and must only inspect ID relationships and lifecycle status.

3. Verify execution environment.
   - Use `$find-local-python-envs` before execution when the task uses Python, notebooks, package imports, tests, model code, or dependency-constrained scripts.
   - Record the selected interpreter/environment and any unresolved dependency gaps.
   - If no environment is needed, mark the environment gate `not_applicable`.

4. Verify execution evidence.
   - Use `$run-task-code-and-log` when the task specifies code, commands, scripts, notebooks, tests, or a required run procedure.
   - Require factual evidence: command line, exit status, output summary, artifacts, failures, and saved `.agent_log` entry.
   - If the task changes a runtime gate, router, validator, dispatch decision, or other judgment whose expected output changes, require fresh live before/after evidence that the changed path actually changed result, or record an explicit defer rationale and cap completion at `partial`.
   - If execution cannot be run, classify the execution gate as `missing` or `blocked` and explain why.
   - When execution failed, require the safe failure autopsy fields when available: `execution_stage_ladder_status`, `last_successful_stage`, `failure_surface_stage`, `post_failure_scalar_diagnostics`, and either safe scalar diagnostics or `diagnostics_unavailable=true`. Do not validate an opaque terminal classification when a stage ladder was available but omitted.
   - When execution failed and a caller/adapter exposes runtime settings, preserve `runtime_config_echo`, `config_origin`, and `config_overrides`. Treat plausible `code_default` overrides as self-inflicted gate/default repair evidence, not as a terminal environment blocker.
   - When execution evidence includes `run_disposition`, keep disposition separate from command status. `failed_closed` means unsafe output was discarded. `candidate_degraded` is preserved quality-miss evidence and cannot satisfy canonical baseline, completion, or `advanced` progress unless later independent verification explicitly permits the consumed axes.
   - Treat execution-log `observed_producer_claim` fields as producer self-report only. They may explain what the producer claimed, but they must not satisfy execution success, completion, progress, or goal-distance movement without adapter recomputation or strict changed-and-semantic output-delta evidence.
   - Verify `command_argv` for live execution. If only a summarized command, `...`, or missing flags are logged, set `command_provenance_missing=true` and do not use that run for baseline, A/B, comparison, or reproduction claims.
   - For gate/validator failures, verify blocker actionability. A blocker with only a state or reason code is `blocker_opacity`; warn on first occurrence and preserve repeated same-gate opacity as blocker-contract repair work.

5. Run repository audit.
   - Use `$inspect-repo-with-agents` to audit requirement coverage, regressions, maintainability, tests, and generalization gaps.
   - Invoke this repository audit with the configured `completion_review` profile at `reasoning_effort: xhigh`.
   - Include both existing code and changed code when implementation occurred.
   - Include `.agent_goal/goal_schema_contract.md`, `.schema/`, and `.contract/` when the task touches shared schemas, module/script contracts, serialized artifacts, CLI/script I/O, producers, consumers, versions, or compatibility.
   - Include task-referenced `.agent_advice` when present. Audit whether implementation and task artifacts handled the advice as non-GT planning evidence and did not use it to override GT, authority, or repository facts.
   - Check whether schema/contract records satisfy the goal schema-contract minimum fields, application intent, mandatory rules, validation evidence, and causal-map expectations when relevant.
   - Include ID-based audit concerns or reuse the `$manage-task-state-index` ID audit: active task linkage, candidate/past_task lineage, run/log/audit/validation links, task_miss resolution links, and stale digest conflicts.
   - If multi-agent inspection is unavailable, state that limitation and cap the final verdict at `partial` unless the task is purely documentary and independently verifiable.

6. Run OOM-risk audit when relevant.
   - Use `$inspect-oom-risk` when the task touches large data loading, model inference/training, batching, concurrency, caches, build/test memory pressure, containers, GPU/VRAM, or unbounded accumulation.
   - Invoke relevant OOM-risk audit with the configured `completion_review` profile at `reasoning_effort: xhigh`.
   - If no plausible memory-risk surface exists, mark the OOM gate `not_applicable`.
   - If OOM audit is relevant but not run, cap the verdict at `partial`.

7. Evaluate `.task/task_miss`.
   - Treat active `open`, `still_open`, `partially_resolved`, or unverified miss files linked to the current task as blockers.
   - Treat resolved/deleted reports as closed only when they cite concrete resolution evidence.
   - If a miss is resolved during validation, do not delete it here unless the owning workflow requested cleanup; instead record the resolution evidence and update the index.

8. Evaluate `.issue`.
   - Treat active issue records linked to the current task as completion context, not automatic blockers.
   - If an issue describes unresolved validation, implementation, or goal-fit blockers for the current task, classify the relevant gate as `partial` or `failed`.
   - If the task appears to resolve an issue, do not close or archive it here; require `$manage-implementation-issues` after validation so `$run-task-code-and-log` evidence is attached before close/archive.

9. Evaluate `.agent_advice`.
   - If `task.md` includes `External Advice`, the caller supplied `used_advice`, or active advice exists, add an `External advice` gate to the validation report.
   - `passed`: task/audit/log/schema/issue evidence shows the advice was incorporated, rejected, deferred, or intentionally left active with a rationale, and no advice was reported as GT.
   - `partial`: advice relevance is plausible but lifecycle evidence or links are incomplete.
   - `failed`: a task-referenced advice directive was ignored without rationale, applied despite a higher-priority conflict, or used as GT/authority.
   - Use `$manage-external-advice mark-applied` only when the advice is fully consumed or retired by durable evidence. Otherwise keep it active and record the remaining gate.

10. Evaluate acceptance provenance, convention conformance, and structure effect.
   - When `task.md`, `.task/task_pack`, active advice, or caller packets provide `scope_fidelity`, compare the original measurable target against actual achievement before allowing close.
   - When acceptance or caller packets report Part O/O4' `trivially_satisfiable_proxy=true`, require evidence that the adapter-owned new-behavior sample precondition was met or that the proxy was replaced with a new-behavior population. If the new-behavior sample count is zero and the proxy otherwise passed, reclassify that proxy as `not_applicable` and downgrade dependent progress to `contract_only`. If `proxy_population` is absent, fail quiet and keep existing acceptance gates. Do not double-count O4' as G-OENV, N1', or B without separate tautology, vacuity, or dilution evidence.
   - When normalized acceptance or caller packets supply S7/S11 `target_metric_delta`, require real movement of the acceptance-owned target metric before completing the target. A measurement matrix, proxy status, observed field, or predicted after-value is not completion evidence when `moved=false`; set `measurement_without_movement` and preserve a derive follow-up for the real movement. If `moved=true` only on `artifact_class=fixture` or `artifact_class=unit_scalar` while the acceptance/caller contract requires movement on a non-fixture artifact class, set `movement_on_fixture_only=true`, return `partial`, and preserve a derive follow-up for movement on the required artifact class. If the hook is absent or malformed, keep existing completion behavior, emit `movement_unverified`, and do not infer target metrics or measurement-only fields locally. If `artifact_class` is absent, keep existing S7 behavior and emit `artifact_class_unverified` warning evidence; do not infer artifact classes locally.
   - When a normalized acceptance packet provides `acceptance_envelope_contract`, verify that the executed or selected envelope satisfied the adapter-owned `envelope_floor`. If the execution envelope is below the floor, classify the acceptance as unmet or partial; do not reframe the planned-failure result as a tool, prompt, runtime, or schema blocker.
   - When a normalized acceptance packet or loopback packet provides `acceptance_verifier_contract` or `unverifiable_acceptance_contract=true`, verify that each required live verifier evaluated to `pass`. If a required verifier is `not_evaluated`, classify the measurable acceptance as unmet or partial, preserve the verifier-hook follow-up or residual scope, and do not mark the source directive applied or consumed.
   - When a measurable acceptance target depends on a gate's required adapter hook, verify that the hook was supplied and evaluated. If the hook is missing, unloaded, fail-quiet, or `not_evaluated`, treat it as `unverifiable_acceptance_contract=true`; preserve hook-supply follow-up or residual scope and do not mark the source directive applied or consumed.
   - When a loopback packet provides `pass_with_coupled_verifier=true`, treat the affected verifier pass as not-pass for completion. Classify the measurable or verifier-backed acceptance as partial unless a later non-coupled revalidation or independent evidence recalculation is present.
   - When normalized acceptance or validation-set evidence provides `acceptance_scenarios`, require scenario coverage: a premise-satisfying fixture or live run plus observed terminal state equal to the expected state. If no evidence satisfies the premise, set `scenario_uncovered=true` and return `partial`. If a premise-satisfying item observes or asserts the opposite state, set `acceptance_inversion=true`, return `partial`, and route code/contract repair regardless of green tests.
   - When producer output or `observed_producer_claim` truthfully reports a residual blocker showing that a scenario premise cannot reach the expected terminal state, treat it as an `acceptance_inversion_candidate` for the acceptance-scenario gate. It is not completion evidence, but it is enough to block green-test close until scenario evidence resolves or confirms the inversion.
   - When a loopback packet provides `evidence_provenance_gate` or `attested_only_movement=true`, verify that claimed high-water movement and goal-progress evidence came from `independently_verified_fields`. Producer-attested scalar movement cannot satisfy acceptance, progress, or goal-distance movement by itself.
   - When review or loopback evidence reports `constraint_forced_vacuity=true`, treat the affected metric as not goal-productive even if it passed. Use this flow: metric passed -> `substance_density` absent means fail quiet; density below adapter floor means N1; `vacuity_cause=production_constraint` requires persistence-policy repair or residual scope, while `vacuity_cause=missing_producer_capability` requires producer supply or residual scope. G-OENV remains responsible for metrics that pass by construction.
   - When the task changed files intersecting `producer_source_paths` and `output_fingerprint_updated` is false or `deliverable_stale=true`, return `partial` or `failed` for close claims that consume the affected deliverable. Require regeneration/reharvest and revalidation before close; code, tests, schema records, and verifier passes alone are `contract_only`.
   - When schema or policy evidence reports `anonymization_theater=true` or `mutually_unsatisfiable_persistence_contract=true`, do not complete the storage-policy or schema-contract task until same-task reconciliation, explicit residual descope, terminal blocker, or user escalation is recorded. Prefer an adapter-supplied opaque-id plus transient-merge-key alternative before stored-surface relaxation.
   - When a qualitative review packet provides `pass_with_unobserved_axes=true`, `goal_axis_completeness_gate.evaluation_status=fail`, or nonempty `unobserved_goal_axes`, do not consume that review as pass evidence for the affected measurable goals. Classify the relevant acceptance as partial unless adapter axis-supply work, explicit descope, terminal blocker, or user escalation is recorded.
   - When loopback or derive evidence shows generation-dependent count-key material, do not accept "new family" or "stall reset" claims based on raw task/advice/pack/cycle/run/date/hash/version labels. Validate against the effective root-family/dominant-parameter key or terminal-outcome family.
   - When loopback reports `failure_surface_stage_gate.terminal_classification_stage_contradiction=true`, `terminal_classification_invalid_for_counting=true`, or `same_input_contract_gate.same_input_contract_violation=true`, return `partial`/`failed` for any completion that depends on that classification or comparison. Contradictory terminal classification and same-input mismatch cannot support close, stall reset, or family seal.
   - When loopback reports `diagnostics_unavailable_gate.instrumentation_supply_required=true`, do not mark a hypothesis repair complete as progress unless instrumentation was supplied or the validation result records why success/failure is already observable without new instrumentation.
   - When loopback, task-pack, or validation evidence reports `instrumentation_exercise_required=true`, do not mark dependent measurement, comparison, adoption, baseline, or close work complete unless a fresh run id after the instrumentation supply item recorded non-empty scalar fields per `instrumentation_field_map`, or a concrete observability rationale proves the supplied fields are unnecessary. `derived_from_existing_artifacts=true` is not exercise evidence.
   - When acceptance encoding reports `evidence_kind=live_run`, require a satisfying run id created after `item_created_at` or task creation. If the evidence used is `derived_artifact`, `code_contract`, or `report_only`, set `acceptance_diluted=true`, return `partial`, and preserve residual live-run scope.
   - When acceptance encoding reports `required_freshness_class=fresh_producer_execution`, require `producer_execution_evidence` or caller evidence showing `producer_executed=true` for the satisfying run. If `producer_executed=false`, keep the item `partial`, preserve scalar facts as `derived_artifact` evidence only, and record residual producer re-execution or input-generation refresh scope. If the hook is absent, set or preserve `freshness_class_unverifiable=true` and do not count the evidence as fresh producer execution unless a higher-priority caller contract supplies equivalent proof.
   - When evidence reports `condition_unsatisfiable_for_input_generation=true`, do not consume the conditional criterion as `not_applicable`; return `partial` unless input-generation refresh, producer re-execution, explicit descope with residual scope, terminal blocker, or user escalation is recorded.
   - When evidence reports `feature_regressed_artifact=true` or `feature_regression_count>0`, do not classify artifact-derived progress as `advanced` or `goal_productive`; preserve inheritance repair as residual scope. Do not double-count this as Part L stale-lane consumption or N2 deliverable staleness.
   - When an artifact or report claims an `adapter_hook` or `domain_meaning_owner` provenance label, verify it against Q3 `hook_registry` if available. If the labeled hook is not defined, return `partial` or `failed` with `fabricated_provenance_label=true` for any completion that consumes the label. If the registry is absent, record `provenance_unverifiable` and keep legacy validation; if the artifact did not claim hook provenance, missing hook evidence remains fail-quiet. Q3 provenance truth is distinct from Q2 body materialization; when both appear, fabricated hook provenance is the primary blocker.
   - When evidence reports `diminishing_reprocess=true`, do not classify another post-processing pass over the same frozen input as `advanced` unless producer re-execution, input-generation refresh, explicit descope, terminal blocker, or user escalation resolves the exhaustion. Do not double-count this as O2 axis stall or F-series feasibility.
   - When loopback reports `verifier_surface_hardening=true` and `guard_stacking_cap_reached=true`, do not accept another same-target guard/verifier/report task as `goal_productive` or `advanced`. Require execution-producing evidence, explicit descope with residual scope, terminal blocker, or user escalation.
   - When profile evidence reports `execution_starvation=true`, treat another no-run guard/report/contract completion as `safety_only` or `no_progress` unless safety, authority, or terminal evidence proves execution was blocked.
   - When evidence provenance reports `independently_verified_fields`, require `verification_input_paths` that are disjoint from the verified artifacts unless the adapter marks the axis `self_grounded=true`. If `independent_source_separation_status=missing|overlap|blocked` or `independently_verified_downgraded_fields` is nonempty, treat affected fields as attested and do not use them for `complete` or `advanced`.
   - When reachability evidence reports `envelope_thaw_item_required=true`, do not complete frozen-envelope-unreachable acceptance without `envelope_thaw_item`, thaw condition/schedule, explicit descope with residual scope, terminal blocker, or user escalation.
   - When residual-gap evidence includes cycle-cost fields, verify that same-gap repair was selected because value per cycle cost outranked explicit descope-with-residual plus the next rung, or classify the remaining target as partial with residual scope.
   - When stochastic output evidence reports `outcome_variance`, reject exact equality completion if `predetermined_unreachable=true`, and reject floor-edge envelope completion if `floor_edge_envelope=true`. Preserve contract revision, interval/ratio/intersection criteria, envelope expansion, residual descope, terminal blocker, or user escalation as follow-up.
   - When run or loopback evidence reports `instrumentation_first_fire=true`, count it only as instrumentation evidence. It can make an instrumentation-exercise or evidence-supply task partial/advanced as appropriate, but it cannot also prove goal progress or consume the instrumentation supply item.
   - When acceptance, task-pack, loopback, derive, or run evidence reports `expectation_lineage_stale=true`, do not complete the task from the stale expected scalar. Require rebaseline against the current `designated_baseline`, explicit residual/descope, terminal blocker, or user escalation. `expectation_anchor_missing=true` is warn-only, but it cannot support a lineage-verified expectation claim.
   - When comparison/adoption evidence reports `parity_unverified=true`, missing `parity_axes`, or any parity axis status `unknown`, do not complete final adoption, baseline promotion, or comparison-winner work. Classify it as partial unless parity-axis resolution, explicit provisional status plus residual scope, terminal blocker, or user escalation is recorded.
   - When adoption evidence lacks `adoption_axis_classification` or reports `majority_vote_adoption=true`, do not complete final adoption unless a later packet classifies axes and proves all `gating` axes passed. A failed `gating` axis or `measured_but_disqualified=true` blocks adoption regardless of tradable-axis wins; preserve the candidate as measured evidence only.
   - When evidence reports `resolution_downgrade=true`, do not complete a task whose acceptance required the higher resolution unless the task explicitly revised the contract, restored the resolution, or preserved residual high-resolution scope. A first downgrade can be warning/provisional evidence; repeated downgrade for the same contract should route follow-up repair.
   - When evidence reports `report_key_divergence=true`, return `partial` or `failed` for any pass/close/adoption/baseline/comparison/high-water claim that consumes that report. Divergent duplicate keys in one report are blocking until the report is repaired or a single source with matching values is declared.
   - Separately, when `report_body_divergence=true`, the canonical actual artifact projection disagrees with the report. Return `partial` or `failed` until independently recomputed actual-body truth and the current report converge. Keep carried-forward values under `source_*` and current transform values under `current_*`.
   - If any acceptance-required actual body truth, report convergence, artifact class, freshness/current lane, consumer context, or verifier completeness field is `not_evaluated`, `advanced` and completion-oriented close are invalid.
   - When `refactor_effect_required=true`, an outer packet cannot waive the existing structure repair because the debt predates the current task. Require `structure_high_water_moved=true` at the adapter-owned scope or explicit residual/descope handling.
   - When evidence reports `pass_on_stale_lane=true`, return `partial` or `failed` for any current-lane capability, adoption, comparison-winner, baseline, next-rung, close, or progress claim that consumes that pass. Preserve current-lane rerun/revalidation, residual descope, terminal blocker, or user escalation.
   - When evidence reports `decision_metadata_revision=true` or `stale_measurement_artifact=true`, do not classify the task as measurement progress, adoption consumption, or high-water movement unless a fresh current-lane run id or no-impact proof exists. Preserve residual fresh measurement or terminal/user escalation.
   - When evidence reports `axis_starved_by_missing_producer=true`, do not complete another verifier/guard/report item for that gating axis as `advanced` or `goal_productive`. Require producer-supply evidence, residual descope, terminal blocker, or user escalation.
   - When evidence reports restrictive `portfolio_quota_exceeded=true`, do not validate another verifier-like item as goal-productive unless the selected work is producer, envelope, long-run, descope, terminal, escalation, or the quota recovered.
   - When evidence reports `unreachable_within_cycle=true`, do not complete the original scale acceptance from a small smoke, launch-only handoff, or heartbeat. Require long-run harvest validation, throughput improvement evidence, explicit descope with residual scope, terminal blocker, or user escalation.
   - When evidence reports `harvest_contract_preflight` with non-degradable `lane_incompatible`, `scale_incompatible`, or `contract_conflict`, do not complete launch or harvest consumption unless repair/mitigation evidence exists or the launch packet explicitly recorded `harvest_risk_accepted=true`. A missing adapter inventory is fail-quiet only when recorded as `harvest_gate_unaudited=true`.
   - When evidence reports `high_cost_artifact=true` and `destructive_disposition_blocked=true`, reject completion that deleted, overwrote, or failed to quarantine non-safety artifacts. Require `quarantine_path` or an explicit safety-policy exception. If verifier/governance defects dominate and `reharvest_before_rerun_required=true`, do not count rerun work as goal-productive before reharvest is terminal-blocked or attempted.
   - When evidence reports `mutually_unsatisfiable_contract=true`, do not complete a predicate or producer-directive change until the same task revises one side or records residual blocked scope. Green tests against one side of the contradiction are insufficient.
   - When evidence reports `sample_as_universe_misuse=true`, do not complete pass/close evidence based on absence from a truncated, partial, capped, or sampled collection. Require full untruncated collection evidence or downgrade to included-element consistency only.
   - When evidence reports `basis_overclaim=true`, downgrade affected metrics to `actual_basis_class`; do not use them for independently verified high-water, completion, or `advanced` progress until basis-compatible input evidence exists.
   - When qualitative review reports nonzero `surface_field_defect_matrix`, do not consume the review as pass for affected field classes unless producer/field repair, explicit residual descope, terminal blocker, or user escalation resolves the defects.
   - If the item inherited a measurable target and actual achievement is below the original target, set `acceptance_diluted=true`, return `partial`, and preserve or require an open residual follow-up. Do not mark the original directive applied or the pack item consumed.
   - Accept a narrower result only when there is an explicit descope decision with reason plus residual item/link. A weak item label such as `pilot`, `plan`, or `slice` is not descope evidence.
   - If a provided `code_convention_contract` applies and governance/code-structure audit reports an unresolved contract-backed violation, return `partial` or `failed` according to severity. If the contract is absent, record the convention gap as warn-only and preserve a repo-local adapter/convention-contract follow-up when repeated.
   - For behavior-preserving refactor tasks, require adapter-supplied structure high-water movement, such as reduced entrypoint burden, reduced command/flat-file/function burden, reduced mechanical shard count, reduced duplicate definitions, reduced global coupling, improved reuse ratio, reduced depth/fan-out, or another project-owned structure metric. Treat adapter `structure_metrics` as the structure-progress truth source; producer-local structure reports, file-count growth, relocated helpers, token/pattern avoidance, or green tests alone are insufficient for `complete` when the refactor objective was structural reduction. If the adapter reports `structure_high_water_key_scope=global_invariant`, selected-scope improvement alone is insufficient unless the global invariant moved or explicit residual/descope evidence remains open.
   - If caller packets include `disposition_intersection_basis.allowed_task_kinds`, verify that any claimed `goal_productive` completion used a matching `selected_task_kind`; otherwise cap the verdict at `partial` and preserve the allowed correction as residual work.
   - If structure metrics worsen on a relevant axis, such as shard count up, duplicate count up, depth/fan-out beyond contract, reuse ratio down, or max LOC up against the task objective, cap the verdict at `partial` and preserve residual work unless the task explicitly scoped that regression out with evidence.
   - Record `acceptance_provenance_gate`, `acceptance_scenario_gate`, `acceptance_verifier_gate`, `acceptance_encoding_gate`, `instrumentation_exercise_gate`, `instrumentation_first_fire_gate`, `coupled_verifier_gate`, `evidence_provenance_gate`, `goal_axis_completeness_gate`, `count_key_hygiene_gate`, `verifier_surface_hardening_gate`, `run_disposition_gate`, `runtime_config_echo_gate`, `command_provenance_gate`, `blocker_actionability_gate`, `stochastic_feasibility_gate`, `expectation_lineage_gate`, `comparison_parity_gate`, `adoption_axis_gate`, `resolution_downgrade_gate`, `report_key_integrity_gate`, `lane_identity_gate`, `decision_freshness_gate`, `gating_axis_producer_gate`, `portfolio_quota_gate`, `cycle_reachability_gate`, `metric_basis_gate`, `surface_field_review_gate`, `harvest_contract_preflight_gate`, `disposal_proportionality_gate`, `contract_satisfiability_gate`, `collection_consumption_gate`, `execution_starvation_gate`, `residual_gap_marginality_gate`, `convention_conformance_gate`, `structure_metrics_gate`, and `execution_evidence_gate` fields in the validation result when applicable so `$orchestrate-task-cycle` result contracts can enforce them.

11. Decide the verdict.
   - Use [completion-gates.md](references/completion-gates.md) for the gate matrix.
   - `complete`: acceptance criteria are met; required execution passed; relevant repo/OOM audits have no blockers; environment is known or not needed; active task_miss has no blockers; logs and index are updated.
   - If schema/module/script contracts are relevant, `complete` also requires `.agent_goal/goal_schema_contract.md` compliance or a documented non-applicable reason, plus updated `.schema/` or `.contract/` evidence.
   - If advice was referenced, `complete` also requires the `External advice` gate to be `passed` or `not_applicable`.
   - If measurable acceptance provenance, structure-effect, or behavior-change live evidence gates are applicable, `complete` also requires those gates to pass or a recorded explicit descope/defer decision that leaves residual work open and normally caps the verdict at `partial`.
   - If a required gate has `evaluation_status: not_evaluated`, `complete` is invalid for the measurable target unless the task explicitly scoped verifier implementation out and preserves residual scope.
   - If a required gate pass is `pass_with_coupled_verifier`, `complete` is invalid for the verifier-backed target unless independent recalculation or a later verifier-source-independent run passed.
   - If a review-backed measurable target has `pass_with_unobserved_axes=true`, `complete` is invalid for that target unless axis-supply work landed, explicit descope/residual scope remains open, or the task explicitly did not consume the review as pass evidence.
   - If the task's family novelty, stall reset, or seal decision relies on generation-dependent raw keys, `complete` is invalid for that workflow claim unless the effective count key preserves the same family or records an explicit override with user-supplied input/authority/external-state change.
   - If terminal classification contradicts the observed failure surface stage, or the same-condition input set differs, `complete` is invalid for any close/counting claim based on that terminal classification.
   - If instrumentation supply is still required after repeated `diagnostics_unavailable`, `advanced` progress is invalid unless instrumentation landed or a concrete observability rationale is recorded.
   - If instrumentation exercise is still required for supplied fields, `complete` and `advanced` are invalid for dependent measurement/adoption work unless a fresh run id exercised those fields or an observability rationale explicitly removes the dependency.
   - If a scenario-shaped acceptance criterion lacks a premise-satisfying fixture/live run, `complete` is invalid for that criterion. If premise-satisfying evidence asserts the opposite terminal state, `complete` is invalid and the verdict remains `partial` with code/contract repair.
   - If a `live_run` acceptance criterion was satisfied only by derived artifacts, code contracts, or report-only evidence, `complete` is invalid and `advanced` is invalid for that criterion.
   - If `required_freshness_class=fresh_producer_execution` and `producer_executed=false`, `complete` is invalid for that criterion; scalar observations may remain useful only as `derived_artifact` evidence and producer re-execution remains residual scope.
   - If `condition_unsatisfiable_for_input_generation=true` remains unresolved, `complete` is invalid for the affected conditional criterion unless explicit descope, terminal blocker, or user escalation records the residual scope.
   - If guard-stacking collapse reached its cap, another same-target verifier/guard/report task cannot be `advanced` without fresh execution-output evidence.
   - If the only new output is `candidate_degraded`, `advanced` is invalid unless independently verified axes prove a valid blocker-state transition and no canonical promotion is claimed.
   - If independently verified evidence lacks disjoint verification inputs, `complete`/`advanced` is invalid for the affected metric unless the axis is adapter-marked `self_grounded`.
   - If a frozen envelope makes acceptance unreachable and no `envelope_thaw_item` or explicit residual/descope path is recorded, `complete` is invalid.
   - If a residual gap is below value-per-cycle-cost policy and the task consumes another same-gap repair without higher value evidence, `complete` is invalid for that measurable target.
   - If live-run command provenance is missing, `complete` may still be possible only for tasks that do not rely on reproducibility, baseline, A/B, or comparison evidence. Otherwise cap at `partial`.
   - If blocker opacity repeats for the same gate and the task claims the blocker is actionable or resolved, `complete` is invalid without blocker-contract repair evidence.
   - If stochastic feasibility findings show the acceptance contract is predetermined unreachable or floor-edge, `complete` is invalid until the contract is revised, explicitly descoped with residual scope, or escalated.
   - If first-fire instrumentation credit is counted, ensure it is not double-counted as goal progress or instrumentation supply consumption.
   - If `expectation_lineage_stale=true` and no rebaseline/descope/terminal path is recorded, `complete` is invalid for any criterion depending on that expectation.
   - If `parity_unverified=true` or any required parity axis is `unknown`, `complete` is invalid for final adoption, baseline promotion, or comparison-winner claims.
   - If a failed `gating` adoption axis or `measured_but_disqualified=true` is present, `complete` is invalid for adoption of that candidate.
   - If unresolved Part M findings are present, `complete` is invalid for affected launch, harvest, terminal disposition, predicate/directive, or collection-consumption claims: risky harvest preflight without repair or explicit risk acceptance, destructive high-cost disposition without safety exception, rerun before required reharvest, mutually unsatisfiable contract, or sample-as-universe misuse.
   - If unresolved Part N findings are present, `complete` is invalid for affected progress, deliverable, or persistence-policy claims: constraint-forced vacuity below adapter floor, deliverable staleness after producer-source change, anonymization theater, mutually unsatisfiable persistence contract, or unaccounted decision-relevant hook demand.
   - If unresolved Part O/O4' findings are present, `complete` or `advanced` is invalid for claims depending on a proxy whose measured population does not include new behavior. A passed proxy with zero new-behavior samples is `not_applicable`, and dependent progress remains `contract_only` unless explicit descope/residual scope, terminal blocker, or user escalation resolves it.
   - If unresolved Part P/P1/P2/P4 findings are present, `complete` or `advanced` is invalid for claims depending on regressed representative artifacts, fresh-producer-execution evidence that did not execute the producer, impossible input-generation conditions routed as not-applicable, or diminishing reprocess over frozen inputs.
   - If S7/S11 `target_metric_delta` reports `moved=false` for the measurable acceptance target and the current artifact only added metric-measurement, proxy, or observed fields, `complete` is invalid for that target. If `moved=true` is limited to `artifact_class=fixture` or `artifact_class=unit_scalar` while the acceptance/caller contract requires a non-fixture artifact class, `complete` is invalid and the verdict must be `partial` with `movement_on_fixture_only` and a real-artifact-class movement follow-up. Missing S7 hook evidence is `movement_unverified` and warning/debt only unless another acceptance contract requires movement verification; missing `artifact_class` keeps legacy S7 behavior with `artifact_class_unverified` warning evidence.
   - If `resolution_downgrade=true` and the task required the original high-resolution evidence, `complete` is invalid unless the contract was revised, resolution restored, or residual scope remains open.
   - If `report_key_divergence=true`, `complete` is invalid for any claim consuming that report, and `advanced` is invalid when the claimed progress depends on the divergent value.
   - If convention conformance is applicable, `complete` also requires unresolved contract-backed code convention violations to be absent or intentionally deferred with open residual scope. Missing convention contract evidence is warn-only unless the task explicitly required contract creation/update.
   - `partial`: core work appears useful but one or more nonfatal gates are missing, unverified, degraded, or have follow-up risks.
   - `failed`: implementation is absent, required execution fails, audit finds blocking defects, severe task_miss remains open, or the task cannot be safely validated.
   - If ID audit finds high-severity broken links, multiple active tasks, missing validation/run/audit evidence links, or unsafe candidate/miss deletion ambiguity, cap the verdict at `partial` or `failed` depending on whether the missing traceability blocks the task objective.
   - Separately decide `progress_verdict` and emit the unique close-time `authoritative_progress_verdict`. Also preserve evidence-bound task acceptance, artifact truth, artifact semantic, pack transition, historical index, and goal readiness verdict axes; a transition failure does not erase implementation acceptance, and semantic failure cannot become goal progress. `$audit-cycle-loopback` owns the earlier `authoritative_semantic_progress`; validation may preserve or downgrade it but never upgrade `false` or a hard stop to `advanced`.
   - A session-audit finding is advisory even when it names canonical evidence. Only a separate deterministic comparator contract may establish a cross-source mismatch that downgrades or blocks. Session audit cannot create pass/completion/progress, expand authority, or validate itself as required for close.
     - `advanced`: the task unlocked a new execution/readiness/goal state, supplied or validated previously missing evidence, produced useful primary goal artifacts, improved qualitative output, or materially reduced an active blocker, and the evidence includes `terminal_outcome_changed=true` or strict observed `changed_vs_previous=true` plus `semantic_progress=true`.
     - `safety_only`: the task passed by proving fail-closed, no-live, non-dispatchable, or guardrail behavior without supplying source-backed evidence, producing primary goal artifacts, advancing readiness, or reducing the final-goal blocker.
     - `no_progress`: the task produced no new durable evidence or repeated already-proven safety checks without a new blocker-state transition.
     - `regressed`: the task weakened or broke a required state, contract, validation gate, safety boundary, or goal requirement.
   - Do not classify progress as `advanced` merely because a new input kind was named. Evidence-family progress requires a non-empty supplied artifact path, `produced_domain_delta=true`, or another validated positive domain/output artifact.
   - Do not classify progress as `advanced` from `observed_producer_claim`, self-declared `produced_domain_delta`, non-empty counts, fixture-only success, `producer_attested_fields`, `attested_only_movement`, or a blocker-state label unless adapter-recomputed quality/substance/structure evidence, `terminal_outcome_changed=true`, or strict observed changed-and-semantic output-delta evidence is present. Otherwise cap progress at `safety_only`.
   - Do not classify progress as `advanced` from a passed metric whose measured target is `constraint_forced_vacuity=true`, from a producer/verifier repair that is `deliverable_stale=true`, or from a storage-policy change with unresolved `anonymization_theater` or `mutually_unsatisfiable_persistence_contract`.
   - If `observed_producer_claim` reports `goal_productive`, `advanced`, or equivalent while adapter recomputation or strict output-delta evidence is missing or negative, record `split_brain_progress_claim=true`, ignore the producer claim for the verdict, and preserve residual work or blockers.
   - Do not classify progress as `advanced` when the run evidence is `self_inflicted_gate_defect` unless the task actually corrected the gate contract/code or supplied a valid alternative evidence source. Rechecking the same unsatisfiable gate is `no_progress` or `safety_only` at most.
   - Do not classify repeated `terminal_blocked`/recheck closeout as `advanced`. If `terminal_escalation_gate.escalation_required=true`, a valid completion must record `user_escalation`, exactly one missing input, and family seal evidence; otherwise cap the verdict at `partial` or `failed` depending on the task objective.
   - Do not let `validation_verdict: complete` imply final-goal progress when `progress_verdict` is `safety_only` or `no_progress`.

12. Prepare the final candidate and report projection.
   - Include task ID if known, validation verdict, progress verdict, gate statuses, opaque evidence IDs, command outcome summaries, audit summaries, active misses, and required follow-ups.
   - In a governed cycle, emit `schema_version: 1`, `kind: cycle_final_candidate`, `final_candidate: true`, stable cycle/attempt identity, the explicit expected-previous tuple, all six evidence-bound verdict axes, and one complete durable-state projection or typed-operation set. Do not assign revision, supersession, authoritative-final, token, commit-status, or receipt fields.
   - Keep report text, timestamps, labels, raw paths, quotations, and other trace-only material outside decision-bound candidate content. Do not write `.task/validation`, update the task index, or publish current state before finalization.
   - Let `$orchestrate-task-cycle` validate and finalize the exact candidate. After it issues and re-verifies a committed current receipt, materialize any validation report or index projection only as a receipt-bound consumer projection. On finalization failure, retain no new current report/index truth; a non-authoritative diagnostic draft may be discarded or kept outside current-state selectors.
   - For an explicitly standalone validation with no governed predecessor/final attempt, record `finalization_applicability: not_applicable` and an opaque reason. This exception cannot authorize derive, promotion, or a final completion claim for a governed cycle.

13. Report the outcome.
   - Lead with the verdict.
   - For `partial` or `failed`, list blockers before summarizing completed work.
   - Include completion-audit `policy_id`, `profile_id`, `routing_tier`, requested model/effort, routing reason codes/signals, `routing_violations` even when empty, routing enforcement, actual model/effort when exposed, and limitations; distinguish deterministic-only gates from delegated audits.
   - Include the verified finalization receipt/projection identity and receipt-bound validation report or task-index references when finalization applies. If only a candidate exists, state that finalization and final reporting remain pending.

## Validation Report Shape

Use this concise structure:

```text
# Task Completion Validation

- Timestamp:
- Validation Verdict: complete | partial | failed
- Progress Verdict: advanced | safety_only | no_progress | regressed
- Workspace:
- Active task ID:
- Validation artifact ID:

## Gate Status
| Gate | Status | Evidence | Notes |
| --- | --- | --- | --- |

Include an `ID consistency` gate whenever `.task/index` exists or should have been created for the workflow.

Include an `Issue tracking` gate whenever `.issue/` exists or `$manage-implementation-issues` should track the active or next task.

Include a `Goal schema contract` gate whenever `.agent_goal/goal_schema_contract.md`, `.schema/`, `.contract/`, or schema/module/script contract surfaces are relevant.

Include an `External advice` gate whenever `.agent_advice/` exists, the caller supplied `used_advice`, or `task.md` references an advice ID/path.

Include an `Acceptance provenance` gate whenever `scope_fidelity`, measurable advice targets, or directive-derived acceptance criteria are present.

Include a `Proxy non-triviality` gate whenever `trivially_satisfiable_proxy`, `proxy_population`, `new_behavior_sample_count`, `proxy_not_applicable`, or proxy replacement/precondition fields are present.

Include a `Target metric movement` gate whenever `target_metric_delta`, `artifact_class`, `artifact_class_unverified`, `movement_unverified`, `movement_on_fixture_only`, or `measurement_without_movement` fields are present.

Include an `Acceptance verifier` gate whenever `acceptance_verifier_contract`, `unverifiable_acceptance_contract`, or required gate `evaluation_status` fields are present.

Include a `Coupled verifier` gate whenever `pass_with_coupled_verifier`, `coupled_verifier_gate`, or `changed_verifier_source_paths` fields are present.

Include an `Evidence provenance` gate whenever `evidence_provenance_gate`, `producer_attested_fields`, `independently_verified_fields`, or `attested_only_movement` fields are present.

Include a `Verification source separation` gate whenever `verification_source_separation_gate`, `verification_input_paths`, `verified_artifact_paths`, `independent_source_separation_status`, or `independently_verified_downgraded_fields` are present.

Include a `Goal-axis completeness` gate whenever `goal_axis_completeness_gate`, `goal_axis_map`, `unobserved_goal_axes`, or `pass_with_unobserved_axes` fields are present.

Include a `Count-key hygiene` gate whenever loopback reports generation-dependent raw keys, `legacy_family_key`, terminal-outcome fallback, or root/dominant-parameter key evidence that affects family novelty, stall reset, sealing, or hypothesis exhaustion.

Include a `Failure surface stage` gate whenever `execution_stage_ladder`, `last_successful_stage`, `failure_surface_stage`, terminal-classification stage mapping, or same-input contract fields affect counting or closure.

Include an `Instrumentation supply` gate whenever `diagnostics_unavailable`, `diagnostics_unavailable_streak`, or `instrumentation_supply_required` fields are present.

Include an `Instrumentation exercise` gate whenever `instrumentation_exercise_required`, `instrumentation_exercised`, `instrumentation_field_map`, `instrumentation_run_id`, or `derived_from_existing_artifacts` fields are present.

Include an `Instrumentation first fire` gate whenever `instrumentation_first_fire`, `first_fire_consumed_item_id`, or first-fire exercise evidence is present.

Include an `Acceptance scenario` gate whenever `acceptance_scenarios`, `scenario_coverage`, `scenario_uncovered`, or `acceptance_inversion` fields are present.

Include a `Command provenance` gate whenever live execution evidence is used for baseline, A/B, comparison, reproduction, or run-specific acceptance.

Include a `Blocker actionability` gate whenever a gate/validator blocker reason code is used to route or close work.

Include a `Stochastic feasibility` gate whenever `outcome_variance`, `predetermined_unreachable`, `floor_edge_envelope`, or comparable envelope `slack` fields are present.

Include an `Expectation lineage` gate whenever `expectation_anchor`, `designated_baseline`, `expectation_anchor_missing`, or `expectation_lineage_stale` fields are present.

Include a `Comparison parity` gate whenever `parity_axes`, `parity_axis_status`, or `parity_unverified` fields are present.

Include an `Adoption axis` gate whenever `adoption_axis_classification`, `required_output_classes`, `majority_vote_adoption`, `provisional_adoption`, `measured_but_disqualified`, or gating/tradable axis fields are present.

Include a `Resolution downgrade` gate whenever `required_evidence_resolution`, `observed_evidence_resolution`, `resolution_downgrade`, or `surrogate_resolution_basis` fields are present.

Include a `Report key integrity` gate whenever `report_key_divergence`, duplicate terminal key paths, or single-report key/value divergence fields are present.

Include a `Lane identity` gate whenever `production_lane_identity`, `current_decision_lane`, `lane_identity_missing`, or `pass_on_stale_lane` fields are present.

Include a `Decision freshness` gate whenever `decision_metadata_revision`, `stale_measurement_artifact`, `measurement_run_id`, or `upstream_contract_changed_since_measurement` fields are present.

Include a `Gating-axis producer` gate whenever `axis_starved_by_missing_producer`, `producer_supply_required`, `gating_axis_id`, or `producer_path_status` fields are present.

Include a `Portfolio quota` gate whenever `portfolio_quota_exceeded`, `portfolio_quota_mode`, verifier-like counts, or producer-like counts are present.

Include a `Cycle reachability` gate whenever `unreachable_within_cycle`, `acceptance_scale`, `throughput_evidence`, `long_run_launch_required`, or `harvest_validation_required` fields are present.

Include a `Harvest contract preflight` gate whenever `harvest_gate_inventory`, `harvest_contract_preflight`, `harvest_gate_unaudited`, `harvest_risk_accepted`, `lane_incompatible`, `scale_incompatible`, or `contract_conflict` fields are present.

Include a `Disposal proportionality` gate whenever `execution_cost_scalar`, `high_cost_artifact`, `destructive_disposition_blocked`, `quarantine_required`, `failure_check_provenance`, `reharvest_before_rerun_required`, or `rerun_before_reharvest` fields are present.

Include a `Contract satisfiability` gate whenever `validation_predicate_contract`, `producer_directives`, or `mutually_unsatisfiable_contract` fields are present.

Include a `Collection consumption` gate whenever `closed_world_collection_consumption`, `collection_truncated`, `sample_as_universe_misuse`, `full_collection_required`, or truncation/sample flag fields are present.

Include a `Substance density` gate whenever `constraint_forced_vacuity`, `substance_density_unchecked`, `referent_meaning_ratio`, `opaque_surrogate_ratio`, `substance_density_floor`, or `vacuity_cause` fields are present.

Include a `Deliverable freshness` gate whenever `producer_source_paths`, `changed_producer_source_paths`, `output_fingerprint`, `output_fingerprint_updated`, `deliverable_stale`, or `contract_only` fields are present.

Include a `Persistence policy` gate whenever `persistence_policy_axes`, `anonymization_theater`, `mutually_unsatisfiable_persistence_contract`, or adapter storage/resolution policy fields are present.

Include a `Hook demand accounting` gate whenever `adapter_hook_demand`, `decision_relevant_skip`, `hook_demand_unaccounted`, `hook_supply_required`, `demanded_hooks`, `hook_demand_threshold`, `hook_demand_threshold_unverified`, or `hook_registry_unverified` fields are present.

Include a `Metric basis` gate whenever `basis_overclaim`, `claimed_basis_class`, `consumed_input_classes`, `actual_basis_class`, or `basis_downgraded_fields` fields are present.

Include a `Surface field review` gate whenever `surface_field_classes`, `field_class_map_missing`, `surface_field_defect_matrix`, or `surface_field_review_status` fields are present.

Include an `Acceptance encoding` gate whenever `acceptance.quantifiers`, `evidence_kind`, `item_created_at`, `required_new_run_id`, `satisfying_run_id`, or `acceptance_diluted` fields are present.

Include an `Evidence freshness` gate whenever `required_freshness_class`, `freshness_class_unverifiable`, `producer_executed`, `condition_unsatisfiable_for_input_generation`, or producer-execution residual-scope fields are present.

Include a `Landed feature inheritance` gate whenever `feature_regression_count`, `feature_regressed_artifact`, `feature_manifest_missing`, or representative-output feature manifest fields are present.

Include an `Adapter hook provenance` gate whenever `adapter_hook`, `domain_meaning_owner`, `hook_registry_status`, `defined_hooks`, `fabricated_provenance_label`, or `provenance_unverifiable` fields are present.

Include a `Frozen input lineage` gate whenever `input_source_id`, `frozen_input_consumption_streak`, `generation_time_defect_dominant`, or `diminishing_reprocess` fields are present.

Include a `Verifier-surface hardening` gate whenever `verifier_surface_hardening`, `target_artifact_paths`, `change_set_kind`, or `guard_stacking_cap_reached` fields are present.

Include a `Run disposition` gate whenever `run_disposition`, `failed_closed`, `candidate_degraded`, `candidate_written`, or `disposition_unclassified` fields are present.

Include a `Runtime config echo` gate whenever `runtime_config_echo`, `config_origin`, or `config_overrides` fields are present.

Include an `Execution starvation` gate whenever `execution_starvation` or `recent_cycle_run_id_count` fields are present.

Include an `Envelope thaw` gate whenever `envelope_thaw_item_required`, `envelope_thaw_item`, thaw condition, or frozen-envelope reachability fields are present.

Include a `Residual gap marginality` gate whenever `residual_gap_policy`, `marginal_repair`, `cycle_fixed_cost`, `marginal_value_per_cycle_cost`, or value/cost policy fields are present.

Include a `Structure effect` gate whenever the task is a behavior-preserving refactor or consolidation intended to reduce structure burden.

Include a `Convention conformance` gate whenever implementation changed code and a repo-owned `code_convention_contract`, code-structure audit packet, or governance `convention_conformance` packet is present.

Include a `Behavior-change live evidence` gate whenever the task changes runtime gate, routing, validator, dispatch, or judgment outcomes.

## Blocking Findings
...

## Evidence
...

## Progress Assessment
...

## Follow-ups
...
```

## Guardrails

- Do not claim completion without execution evidence when the task required running code.
- Do not claim completion or progress from producer self-reported progress fields. Treat them only as `observed_producer_claim` and require adapter or strict output-delta truth.
- Do not claim repository audit coverage if `$inspect-repo-with-agents` did not run.
- Do not skip `$find-local-python-envs` for dependency-constrained Python tasks.
- Do not skip `$inspect-oom-risk` for data/model/batch/concurrency changes with plausible memory risk.
- Do not delete `.task/task_miss` files from this skill unless the user explicitly requested cleanup and evidence is already recorded.
- Do not mark unresolved task_miss as complete merely because implementation progressed.
- Do not mark `progress_verdict: advanced` merely because a no-live/fail-closed safety check passed; name the blocker-state transition or classify it as `safety_only`.
- Do not mark `progress_verdict: advanced` unless `terminal_outcome_changed=true` or strict observed `changed_vs_previous=true` and `semantic_progress=true` evidence is present.
- Do not mark named-only input changes as a positive input delta; require supplied artifact evidence or `produced_domain_delta=true`.
- Do not mark G2 terminal escalation complete without `selected_task_source: user_escalation`, `required_missing_input_count: 1`, a concrete `required_missing_input.kind`, and `.task/sealed_blocker_families.json` or equivalent pack-mutation evidence.
- Do not store secrets, credentials, private tokens, raw sensitive data, or large copyrighted excerpts in validation reports or logs.
- Do not count a repo, OOM, env, or execution agent as the ID consistency agent; ID validation is additional when agent-based insight is used.
- Do not mark schema/module/script contract changes complete when `.agent_goal/goal_schema_contract.md` applies but `.schema/` or `.contract/` evidence is stale, missing required fields, or lacks validation/causal-map coverage.
- Do not close, archive, or delete `.issue` records from this skill; issue lifecycle changes belong to `$manage-implementation-issues`.
- Do not treat `.agent_advice` as GT, authority, or completion evidence by itself.
- Do not mark advice applied without `$manage-external-advice` lifecycle evidence or a clear validation/report rationale.
- Do not return `complete` for `acceptance_diluted=true`; return `partial` and preserve residual scope.
- Do not complete measurable directive-derived work against a weaker criterion unless explicit descope and residual tracking exist.
- Do not complete or advance proxy-backed measurable work when Part O/O4' shows the proxy population excludes the task's new behavior. A passed proxy with zero new-behavior samples is `not_applicable`, not pass; dependent progress is `contract_only` unless residual/descope, terminal blocker, or user escalation is recorded.
- Do not complete measurable target work from measurement-only artifacts when S7 `target_metric_delta` reports no real target-metric movement. Do not complete real-artifact movement acceptance from `moved=true` on `artifact_class=fixture` or `artifact_class=unit_scalar`; return `partial` with `movement_on_fixture_only` and preserve the required artifact-class movement follow-up. Missing hook evidence is `movement_unverified`, not a hard failure and not a pass. Missing `artifact_class` is `artifact_class_unverified` warning evidence and preserves legacy S7 behavior.
- Do not complete measurable work when an adapter-supplied `acceptance_envelope_contract` proves the executed envelope was below the minimum needed for the target.
- Do not complete measurable work when a required verifier is `not_evaluated`; preserve verifier implementation, residual scope, terminal blocker, or user escalation.
- Do not complete measurable work when an acceptance-required gate hook is missing or `not_evaluated`; preserve hook-supply work, residual scope, terminal blocker, or user escalation.
- Do not complete verifier-backed work from `pass_with_coupled_verifier`; require later non-coupled revalidation, independent evidence recalculation, or residual scope.
- Do not complete or advance work from `attested_only_movement` or producer-attested scalar movement; require independently verified evidence.
- Do not complete or advance work from `independently_verified_fields` when verification inputs are missing, overlap verified artifacts, or were auto-downgraded to attested; require disjoint `verification_input_paths` or adapter `self_grounded=true`.
- Do not complete review-backed measurable work from `pass_with_unobserved_axes`; require adapter axis supply, explicit residual scope, terminal blocker, or user escalation.
- Do not complete workflow claims that reset counters or family novelty through generation-dependent task/advice/pack/cycle/run/date/hash/version keys.
- Do not complete workflow claims from a terminal classification that contradicts the observed `failure_surface_stage`, or from same-family comparisons whose input sets do not match.
- Do not advance progress while `instrumentation_supply_required=true` remains unresolved unless an explicit observability rationale proves success/failure is already measurable without new instrumentation.
- Do not advance or complete dependent work while `instrumentation_exercise_required=true` remains unresolved. Existing artifact reinterpretation is not fresh exercise.
- Do not complete scenario-shaped acceptance from tests that never satisfy the scenario premise. Do not treat green tests as evidence against `acceptance_inversion`.
- Do not discard producer-reported residual blockers that contradict a scenario terminal state. Preserve them as `acceptance_inversion_candidate` or explicit scenario-gate review evidence, while still excluding producer self-report from progress truth.
- Do not complete `evidence_kind=live_run` criteria from derived artifacts, code contracts, or reports; preserve the original quantifiers and residual live-run scope.
- Do not complete `required_freshness_class=fresh_producer_execution` criteria from reprocessing, aggregation, report, or code-contract runs when `producer_executed=false`; keep partial and preserve scalars as derived artifacts.
- Do not consume `condition_unsatisfiable_for_input_generation=true` as ordinary not-applicable; require input-generation refresh, producer re-execution, explicit descope with residual scope, terminal blocker, or user escalation.
- Do not advance same-target guard/verifier/report-only work past the verifier-surface hardening cap without fresh execution-output evidence.
- Do not promote `candidate_degraded` artifacts as canonical baseline or completion evidence without independent verification for the consumed axes.
- Do not treat `runtime_config_echo` by itself as completion evidence; use it only for failure/root-cause routing.
- Do not ignore `execution_starvation` when classifying another no-run guard/report/contract task; cap progress conservatively unless execution was blocked by safety, authority, or terminal evidence.
- Do not use a live run with missing full argv as reproduction, baseline, A/B, or comparison evidence.
- Do not treat a state-name-only blocker as actionable evidence. Preserve `blocker_opacity` and require relation/observed/expected/minimum-delta fields for blocker-contract closure.
- Do not retry exact-match or floor-edge stochastic contracts as if the next run could satisfy them when variance evidence says they are predetermined unreachable.
- Do not double-count `instrumentation_first_fire` as both first-fire evidence and goal progress or instrumentation-supply consumption.
- Do not complete or advance work from stale output-derived expectation anchors.
- Do not complete final comparison/adoption work while parity axes are missing or unknown.
- Do not complete adoption from majority vote when required output/gating axes are unclassified or failed.
- Do not complete a high-resolution evidence contract from a lower-resolution surrogate unless the contract was explicitly revised and residual scope is tracked.
- Do not complete or advance from a report that has divergent duplicate terminal keys.
- Do not complete or advance current-lane capability, adoption, comparison-winner, or next-rung work from `pass_on_stale_lane`.
- Do not complete measurement/adoption work from `decision_metadata_revision` or stale measurement artifacts without a fresh run id or no-impact proof.
- Do not complete another verifier-like item as goal-productive for a gating axis starved by missing producer supply.
- Do not ignore restrictive portfolio quota evidence when classifying verifier/guard/report/metadata work as progress.
- Do not complete a cycle-unreachable scale target from smoke, launch, startup, or heartbeat evidence without harvest validation, throughput improvement, residual descope, terminal blocker, or escalation.
- Do not complete launch or harvest work when non-degradable harvest checks are lane-, scale-, or contract-incompatible unless repair/mitigation evidence or explicit risk acceptance is recorded.
- Do not complete high-cost non-safety terminal disposition that destructively deleted or overwrote artifacts when quarantine was required, and do not classify rerun-before-reharvest as goal-productive while reharvest is available and not terminal-blocked.
- Do not complete predicate/directive contract changes that remain mutually unsatisfiable.
- Do not complete pass/close claims that use truncated, partial, capped, or sampled collections as closed-world universes.
- Do not complete a producer/verifier path repair without a refreshed deliverable fingerprint when adapter-owned producer paths changed. Use any supplied `reharvest_path` only as the route to regeneration; do not count the same stale deliverable as both M2 and N2.
- Do not complete or advance from a representative artifact with `feature_regressed_artifact=true`; inheritance repair must land and be revalidated before artifact-derived axis deltas count as progress.
- Do not complete or advance from an artifact that claims an adapter-hook provenance label not present in the supplied `hook_registry`. Set `fabricated_provenance_label=true` and fail-close the affected provenance claim. Do not convert missing registry evidence into failure when no hook provenance is claimed; record `provenance_unverifiable` and fail quiet to legacy validation.
- Do not complete or advance another post-processing pass over a frozen input when `diminishing_reprocess=true`; prefer producer re-execution/input refresh, explicit descope, terminal blocker, or user escalation.
- Do not complete a metric-backed progress claim when `constraint_forced_vacuity=true`; route production-constraint vacuity to persistence-policy repair and missing-producer-capability vacuity to producer supply.
- Do not complete storage-policy contract work with unresolved `anonymization_theater` or `mutually_unsatisfiable_persistence_contract`. Storage axis and resolution-depth axis must be reconciled independently, with opaque-id plus transient merge key preferred when adapter-supplied.
- Do not treat missing Part N adapter hooks as failures in unadapted repositories. Fail quiet unless an acceptance/caller contract requires the hook; preserve unchecked-hook evidence for derive.
- Do not treat missing Part O/O4' `proxy_population` as failure in unadapted repositories. Fail quiet unless an acceptance/caller contract requires proxy non-triviality; do not invent proxy populations or thresholds.
- Do not complete or advance from basis-overclaimed metrics as independently verified evidence.
- Do not consume qualitative review pass for affected field classes when the surface field defect matrix has unresolved nonzero counts.
- Do not complete frozen-envelope-unreachable acceptance without `envelope_thaw_item`, thaw condition/schedule, explicit residual/descope, terminal blocker, or user escalation.
- Do not complete another same-gap residual repair as goal-productive when value per cycle cost is below adapter policy and no higher value case is recorded.
- Do not complete behavior-preserving refactor work from module creation or green tests alone when the objective required structural reduction.
- Do not complete structure work from file-count growth, numbered shards, version-suffix modules, relocated helpers, import shims, token/pattern avoidance, or producer-local structure reports alone.
- Do not complete global structure work from local selected-scope movement when `structure_high_water_key_scope=global_invariant` and global invariants are flat.
- Do not complete a task as `goal_productive` when loopback/derive gates constrained allowed task kinds and the completed work used a different `selected_task_kind`.
- Do not complete code changes with unresolved contract-backed naming, reuse, placement, dependency-direction, depth/fan-out, duplicate-definition, or global-rebinding violations unless an explicit defer/descope leaves residual work open.
- Do not complete runtime behavior-change fixes without fresh live evidence or a documented defer that keeps follow-up work open.
