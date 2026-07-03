---
name: audit-cycle-loopback
description: "Compute conservative anti-loop progress packets for governed task cycles. Use after run and qualitative output review, before derivation, when Codex needs to detect same-family micro-hardening loops, distinguish jitter or lateral churn from semantic progress, derive root-cause actionability from repository-owned provenance instead of producer self-report, preserve adapter-supplied semantic structure metrics such as mechanical shard count, coupling, duplicate definitions, depth, reuse ratio, and max LOC, update `.task/anti_loop/family_progress_registry.jsonl`, and pass an `anti_loop_progress_gate` packet into `$derive-improvement-task` without treating self-declared progress or `produced_domain_delta` as truth."
---

# Audit Cycle Loopback

## Overview

Use this skill to fill anti-loop inputs that downstream derivation already consumes: `changed_vs_previous`, `semantic_progress`, `terminal_outcome_changed`, `same_family_micro_hardening_count`, `effective_allowed_dispositions`, root-cause hypothesis ledger state, and validator/output-delta disagreement flags.

The skill is workflow evidence only. It is not goal truth, authority, validation evidence, human review, issue closure evidence, or readiness/gold promotion evidence.

## Workflow

1. Collect raw artifact paths from the run, qualitative review, and output-delta packet.
2. Run `scripts/anti_loop_gate_provider.py` with the cycle id, artifact family, semantic signature, suffix-normalized root key when known, provider request count, and artifact paths. When available, also pass loop-detection or portfolio gates with `--gate-state-json`, recent progress items with `--recent-progress-json`, strict runner validation with `--runner-validation-json`, the output-delta packet with `--output-delta-json`, and changed-file evidence with `--changed-file` or `--changed-files-json` so verifier-source coupling can be evaluated.
   - Pass stable oracle/check identities with `--measurement-check-id` or `--measurement-check-ids-json` when the cycle introduces or first exercises a validator, oracle, metric, or reconstruction check.
   - Pass `--measurement-frontier` for first-observed frontiers such as `event_sequence_oracle`, `reconstruction_coverage`, `relation_class_filled`, or `story_vs_narrative_split`.
   - Pass `--blocker-signature` and `--blocker-rung` when qualitative review, loop detection, or a task pack identifies the current blocker and capability-ladder rung.
   - When the normalized acceptance packet includes `acceptance_envelope_contract`, pass it as packet context so root-cause and reachability decisions can use the adapter-owned `deficit_axis` without hardcoding domain metrics.
   - When a run packet includes `failure_autopsy`, pass it with `--failure-autopsy-json` so loopback can resolve `last_successful_stage`, `failure_surface_stage`, `diagnostics_unavailable`, scalar diagnostics, and same-input contract evidence before counting, closing, or selecting the next task.
   - Pass root-cause hypotheses with `--root-cause-hypotheses-json` or `--hypothesized-root-cause`; mark `--root-cause-repair-attempted` only when the active task explicitly targeted that hypothesis. Domain adapters may instead expose `root_cause_hypotheses(...)`.
   - Treat `--root-cause-actionable` or `actionable=true` as an assertion that still needs either all structural fields (`local`, `bounded`, `provider_free`, `in_scope`, `authority_allowed`) or at least one provenance reference such as advice, issue, run, or evidence path. Assertion-only hypotheses are `unverified` and are excluded from untried promotion.
   - Keep `--detection-only-streak-cap` at the default `2` unless the active workflow explicitly records a different cap. This cap is root-family scoped and only controls detection-only repetition.
3. Write the resulting packet under `.task/cycle/<cycle-id>/packets/loopback_audit_packet.json` when `$orchestrate-task-cycle` owns durable cycle artifacts.
4. Pass the packet into `$derive-improvement-task` as `anti_loop_progress_gate`.
5. If the packet is `insufficient_evidence` or near the hard-stop threshold, optionally ask exactly one read-only reviewer to inspect the same raw artifacts and registry. Use the more conservative disposition when reviewer and producer disagree.

## Domain Adapter Contract

Prefer a repository-supplied domain adapter over producer-local domain assumptions. Pass it with `--domain-adapter <path.py>` or set `TASK_CYCLE_DOMAIN_ADAPTER_PATH`. The module may expose these functions with keyword parameters such as `root`, `artifact_paths`, `quality_vector`, `output_delta`, and `runner_validation`:

- `quality_vector(...) -> dict`: domain quality/coverage vector. It may return either the vector directly or `{quality_vector, evidence_paths, insufficient_reason}`.
- `substance_metrics(...) -> dict`: primary-output substance vector used by G-SUBSTANCE.
- `corrective_resolution(...) -> list|dict`: corrective/backfill lanes with `attempted` and `resolved` counts for G-VACUOUS.
- `facet_root_map(...) -> dict`: facet labels mapped to root families for G-FACET.
- `min_envelope_for(target, **context) -> dict`: optional acceptance feasibility helper returning an adapter-owned `envelope_floor` and `deficit_axis` for measurable targets. The skill must not know the domain meaning of the target or envelope; when absent, keep legacy acceptance and root-key rules.
- `residual_gap_policy(target, **context) -> dict`: optional F3 helper returning adapter-owned residual gap threshold, comparison basis, and marginal-repair policy for measurable targets. The loopback packet may preserve these fields when supplied by caller packets, but task selection belongs to `$derive-improvement-task`.
- `output_fingerprint(...) -> str`: current primary-output fingerprint for G-ADVICE-FRESH.
- `previous_accepted_fp(...) -> str|dict`: previous accepted primary-output fingerprint, and optionally previous quality/high-water vector, for R-GCOV baseline selection.
- `structure_metrics(...) -> dict`: optional entrypoint/module structure metrics such as LOC, command count, function count, mechanical shard count, global-rebinding or coupling signal count, duplicate-definition count, tree depth, fan-out, reuse ratio, max LOC, consolidation recommendation, `structure_high_water_moved`, `improved_structure_axes`, and `refactor_effect_required` for S-STRUCT. It may also expose `global_invariants`, `global_*` numeric fields, `global_structure_high_water_moved`, and `structure_high_water_key_scope=global_invariant` so high-water cannot reset when a cycle chooses a new local scope. Treat this adapter output as the single source of truth for structure progress; do not trust producer-local structure/progress reports unless they are absorbed through this hook. The adapter owns repo-specific thresholds, kernel/reuse paths, dependency DAGs, and forbidden naming patterns.
- `producer_progress_claim_fields(...) -> list|dict`: optional producer-owned progress/completion field names that must be captured only as `observed_producer_claim`. If absent, consumers may downgrade conventional progress field names, but producer self-report is never the progress truth source.
- `adapter_load_status(...)` or packet fields `adapter_loaded` and `adapter_path`: optional status proving whether a registered adapter was injected and loaded. If a repository registers an adapter through a conventional path or declaration but the packet reports `adapter_loaded!=true`, classify this as `adapter_wiring_defect` and `self_inflicted_gate_defect`, not adapter absence.
- `capability_ladder(...) -> list|dict`: optional next-rung candidates with abstract task kinds, actionability, authority, local-data, and provider-bound prerequisites for G-CHAIN forced retargeting. Keep rung names and prerequisites domain-owned.
- `primary_metric(...) -> dict`: optional single north-star progress value for G-CHAIN/C4 trigger keying. The adapter owns the metric definition and comparison/high-water semantics. If absent, keep the existing chain-stall streak behavior.
- `verifier_source_paths(...) -> dict|list`: optional gate-to-verifier-source mapping for F1. Return abstract gate IDs mapped to source paths or globs. When the current change set modifies a mapped verifier source, that gate's pass is `pass_with_coupled_verifier`, not an effective pass. If absent, fail quiet and keep existing pass/fail semantics.
- `evidence_provenance(...) -> dict|list`: optional metric evidence provenance for F2. Return metric fields with `independently_verified` or `producer_attested`. When provided, untagged movement is treated as `producer_attested`; only independently verified fields can move high-water, reset stall counters, or support goal-productive evidence. If absent, fail quiet and keep existing progress accounting.
- `root_cause_hypotheses(...) -> list|dict`: domain-owned root-cause hypothesis slugs plus optional `target_surface`, `observed_delta_class`, `repair_attempted`, `repair_task_id`, `local`, `bounded`, `provider_free`, `in_scope`, `authority_allowed`, `actionable`, and provenance fields such as `advice_id`, `issue_id`, `run_id`, `evidence_paths`, or `provenance_refs`.
- `repo_owned_source_roots(...) -> list|dict`: optional repository-owned source glob roots used only to derive root-cause `local`, `in_scope`, and `actionable` from provenance. When a hypothesis provenance reference falls under these roots, reject conflicting self-report fields such as `local=false`, `in_scope=false`, or `actionable=false`. If this hook is absent or empty, fail quiet and keep legacy actionability rules.
- `partial_progress_axes(...) -> dict|list`: optional warn-only quality/substance axes that can explain high-water flatlining. Use it to recommend gate decomposition; do not gate progress from this hook alone.
- `acceptance_reachability(...) -> dict`: optional abstract comparison input for G-REACH with `acceptance_min_output`, `frozen_envelope`, and optional `reachability_verdict: reachable|unreachable|indeterminate`.
- `metric_validity_self_check(...) -> dict|list`: optional oracle/metric validity report for G-OENV. Return `metric_validity: tautological` or equivalent only when a metric can pass by construction and must not support goal-productive progress.
- `target_required_verifier(target, **context) -> dict`: optional target-to-verifier mapping for measurable acceptance. Return abstract fields such as `required_verifier`, `verifier_required`, and current `evaluation_status: pass|fail|not_evaluated` when the adapter can decide which live verifier is required. If the hook returns a required verifier without a passing evaluation status, treat that verifier as `not_evaluated`; if the hook is absent, fail quiet and keep existing acceptance rules.
- `goal_axis_map(targets, quality_vector, **context) -> dict`: optional target-to-quality-axis mapping used by review/validation consumers. Loopback preserves related caller/review fields when supplied; axis definitions remain adapter-owned.
- `execution_stage_ladder(**context) -> list|dict`: optional ordered execution stages for H1/H2 failure-surface resolution. The adapter may return a list of stages or `{stages, terminal_classification_stage_map}`. Loopback uses it with run autopsy `last_successful_stage` to derive `failure_surface_stage`; it must not infer the ladder from project-specific path names in this skill.
- `terminal_classification_stage_map(**context) -> dict`: optional terminal-classification-to-allowed-stage mapping. If the observed `failure_surface_stage` contradicts the terminal classification, that terminal classification is invalid for counting or close.
- `instrumentation_trigger_threshold(**context) -> int|dict`: optional threshold for repeated `diagnostics_unavailable` on the same failure surface. The default is `2`. When the threshold is reached, derive must enumerate/select instrumentation supply unless it records why success/failure is already observable without new instrumentation.
- `verification_input_paths(...) -> dict|list` or `evidence_provenance(...).verification_input_paths`: optional H4 source-separation metadata for independently verified fields. `independently_verified` requires verification inputs disjoint from verified artifacts unless the adapter marks the axis `self_grounded=true`.

The adapter must keep domain-specific file paths, metric names, lexicons, and thresholds outside this skill. If no adapter is registered, any compatibility fallback is legacy-only and must not be extended with new domain-specific paths; missing substance metrics fail closed for measurement or capability-ladder promotion.

Use conservative defaults:

- Do not infer semantic quality from self-declared `produced_domain_delta`.
- Treat missing adapter output, low-confidence quality, malformed artifacts, or stale fingerprint claims as workflow blockers or warnings rather than progress.
- Keep domain lexicons, thresholds, source-language handling, placeholder rules, and OCR handling inside the adapter or repository-owned shared module.
- Do not hardcode project module paths, metric names, lexicon paths, or artifact filenames into this skill body or producer logic.
- Prefer terminal-outcome family grouping over proximate blocker text. When `facet_root_map` is present, collapse blocker facets through it before root-family caps. When it is absent or empty, emit `facet_root_map_missing=true` and use the conservative fallback `artifact_family + terminal_outcome_key` as `family_key` and `root_family_key` so changing blocker labels cannot reset same-family micro-hardening counters. Preserve the old artifact/signature family as `legacy_family_key` for traceability only.
- Treat generation-dependent key material as trace-only. Plan/advice/task-pack IDs, cycle IDs, run IDs, dates, hashes, and version suffixes must not define `family_key`, `root_family_key`, root-cause distinctness, hypothesis exhaustion, family seals, or stall counters. Use the adapter-collapsed root plus dominant parameter when supplied, otherwise the terminal-outcome family fallback.

## Producer Command

```bash
python3 /home/swfool/.codex/skills/audit-cycle-loopback/scripts/anti_loop_gate_provider.py \
  --root . \
  --cycle-id cycle-YYYYMMDD-HHMMSS \
  --artifact-family primary_output \
  --semantic-signature source_to_output_execution \
  --root-key capability-ladder \
  --domain-adapter .task/domain_adapter.py \
  --provider-request-count 0 \
  --artifact-path path/to/primary-output.jsonl \
  --changed-files-json .task/cycle/cycle-YYYYMMDD-HHMMSS/changed_files.json \
  --gate-state-json .task/cycle/cycle-YYYYMMDD-HHMMSS/packets/loopback_audit_packet.json \
  --output-delta-json .task/cycle/cycle-YYYYMMDD-HHMMSS/packets/output_delta_result.json \
  --runner-validation-json .task/run/run-id/validation.json \
  --failure-autopsy-json .task/cycle/cycle-YYYYMMDD-HHMMSS/packets/failure_autopsy.json \
  --measurement-check-id event-sequence-oracle-v1 \
  --measurement-frontier event_sequence_oracle \
  --blocker-signature timeline_order_ambiguous \
  --blocker-rung pov_timeline \
  --acceptance-reachability-json .task/cycle/cycle-YYYYMMDD-HHMMSS/packets/acceptance_reachability.json \
  --metric-validity-json .task/cycle/cycle-YYYYMMDD-HHMMSS/packets/metric_validity.json \
  --hypothesized-root-cause prompt_candidate_row_gate \
  --root-cause-actionable \
  --untried-promotion-budget 2 \
  --adapter-mandate-streak-cap 3 \
  --cumulative-chain-streak-cap 3 \
  --write-registry \
  --output .task/cycle/cycle-YYYYMMDD-HHMMSS/packets/loopback_audit_packet.json
```

Use `--artifact-paths-json` when a run packet already lists artifact paths.

## Packet Semantics

- Treat `evidence_class: insufficient_evidence` as `hard_stop_required: true` and `recommended_disposition: conservative_hold`.
- Treat `semantic_progress: false` with `same_family_micro_hardening_count >= 3` as a hard stop for another same-family micro-hardening task.
- Treat `semantic_progress: true` as a reset for the same-family streak, but keep no-overclaim flags and downstream validation requirements intact.
- Treat `effective_allowed_dispositions` as the intersection of all active constraining gates plus safety valves `terminal_blocked` and `user_escalation`. Downstream derivation must choose a disposition inside this field when it is present.
- Treat `consolidation_streak >= consolidation_streak_cap` as blocking another consolidation disposition; consolidation is workflow progress and does not reduce goal distance by itself.
- Treat `validator_disagreement` findings as a hard stop: when strict runner validation says `semantic_progress=true` but output-delta says `false`, use `authoritative_semantic_progress=false` and do not count runner pass as goal-productive evidence.
- Treat `coverage_quality_delta_reconciliation_gate.status=block` as an R-GCOV hard stop: when output-delta G-COV and loopback G-COV disagree, or expose conflicting values for the same metric key, use the conservative block verdict and do not promote measurement or rung progress from the favorable G-COV alone.
- Treat `validator_integrity_gate.status=block` as a hard stop for validator-derived progress. A top-level validator pass must equal the AND of embedded sub-results, and declared population coverage must match inspected count.
- Treat `pass_with_coupled_verifier=true` as F1: a gate whose verifier source was changed in the same change set did not effectively pass. Do not use that pass for close, semantic progress, high-water movement, or `goal_productive`; preserve a follow-up for verifier-source-independent revalidation or independent evidence recalculation.
- Treat `evidence_provenance_gate.attested_only_movement=true` as F2: producer-attested movement does not move high-water and does not reset stall counters. It is trace evidence only unless the adapter independently recalculates the same metric from domain source data.
- Treat `coverage_quality_delta_gate.quality_delta_pass=true` as the only G-COV path for measurement work to support `goal_productive`. The gate compares adapter-supplied quality/coverage axes against the previous high-water mark; legacy fallback axes may include counts or ratios such as named-event/entity, relation, or source-window coverage.
- Treat `substance_delta_gate.substance_delta_pass=false` or `status=missing` as G-SUBSTANCE fail-closed evidence. A validator, oracle, measurement check, or capability-ladder rung cannot be promoted from tool existence alone; require adapter-supplied substance delta or strict changed-and-semantic primary-output evidence.
- Treat `vacuous_corrective_gate.surface_corrective_noop=true` as G-VACUOUS evidence: attempted corrective/backfill lanes with `resolved=0` must be excluded from produced/semantic delta claims.
- Treat `facet_root_map_applied=true` as G-FACET evidence that adapter facet labels were collapsed before root-family caps. Treat `facet_root_map_missing=true` as a warning, not a hard stop: the packet must expose `terminal_outcome_key`, `terminal_outcome_family_key`, and `terminal_outcome_family_fallback_applied`, and repeated cycles with the same terminal outcome must remain in the same family even when proximate blockers mutate.
- Treat `adapter_mandate_required=true` as G-ADAPTER: when adapter contract gaps repeat with no quality/substance high-water improvement for the configured cap, derive must select adapter registration/strengthening before another domain micro-repair can count as `goal_productive`.
- Treat `adapter_wiring_defect=true` as C1: when an adapter is registered but not loaded, emit `recommended_disposition=self_inflicted_gate_defect`, `local=true`, `in_scope=true`, and `actionable=true`; downstream derive must select `adapter_wiring_fix`/`adapter_load_fix` or terminal/user escalation. Do not report this state as `adapter_mandate_required`.
- Treat `cumulative_goal_distance_stalled=true` as G-CHAIN: when the same adapter-collapsed root family, or `artifact_family` without an adapter, has no quality/substance high-water improvement for the configured cap, restrict the next disposition to `terminal_blocked` or `user_escalation` unless G-ADAPTER is the active preceding mandate. When the stall streak reaches the forced-retarget threshold and lateral churn continues, first emit `forced_selected_task_options` from self-inflicted gate fixes and the adapter `capability_ladder`; allow `goal_productive` only for those task kinds. If no actionable option exists, keep terminal/user escalation.
- Treat `untried_veto_overridden_by_chain_stall=true` as the only allowed override for the usual untried-root-cause terminal veto. Keep `untried_actionable_root_cause_exists=true` for traceability, but do not promote another distinct repair merely because its label is new.
- Treat `acceptance_unreachable_under_frozen_config=true` as G-REACH: derive must choose a constraint-relaxation task or `user_escalation`; envelope-internal micro-repair cannot be goal-productive while the abstract acceptance minimum exceeds the frozen envelope.
- Treat `acceptance_reachability_gate.envelope_thaw_item_required=true` as the H5 G-REACH extension: when acceptance is unreachable under a frozen envelope, reserve `envelope_thaw_item` with a thaw condition/schedule or route to constraint relaxation/user escalation. If the same state repeats for the configured cap, emit a blocking G-REACH finding; do not continue envelope-internal micro-repair as `goal_productive`.
- Treat `unverifiable_acceptance_contract=true` as the E2 revision: a measurable target requires a live verifier, but that verifier was not evaluated. `not_evaluated` is not a pass. Downstream derive must preserve the verifier-hook follow-up, explicit descope with residual scope, terminal blocker, or user escalation; it must not consume the original target.
- Treat missing required hooks for acceptance-referenced gates as the same E2 condition. A gate may fail quiet only when no measurable acceptance/caller contract says it is required.
- Treat `pass_with_unobserved_axes=true` as G3: a review pass did not observe at least one active measurable goal through an adapter-owned axis. Do not let derive or validation consume that review as pass for the affected goal.
- Treat residual cost fields as G4: when `cycle_fixed_cost` or `marginal_value_per_cycle_cost` is supplied, downstream derive must compare residual repair by value per cycle cost. Missing cost fields preserve legacy F3 with denominator `1`.
- Treat `oracle_metric_validity_gate.metric_goal_productive_excluded=true` as G-OENV: exclude tautological oracle/metric passes from goal-productive evidence and require metric correction or independent changed-and-semantic output-delta evidence. If `metric_validity_self_check` is absent, warn only.
- Treat `advice_freshness_gate.advice_metrics_stale=true` as a warn-level G-ADVICE-FRESH finding. Refresh, defer, or reject stale advice before using its headline metrics for next-task direction.
- Treat `observed_producer_claim` as non-authoritative. If a producer claim says `goal_productive`, `advanced`, or equivalent while adapter/output-delta evidence is missing or negative, emit `split_brain_progress_claim=true` and exclude the claim from semantic progress, completion, and high-water movement.
- Treat `structure_metrics_gate.structure_consolidation_recommended=true` as an S-STRUCT warning that Class C consolidation or module-boundary work may be a valid next-task direction when it reduces an overgrown entrypoint or command surface.
- Preserve `structure_metrics_gate.structure_high_water_moved`, `structure_high_water_key_scope`, `structure_global_invariant_metrics`, `improved_structure_axes`, `refactor_effect_required`, and semantic structure metrics such as shard count, coupling signal count, duplicate count, depth, fan-out, reuse ratio, and max LOC when the adapter supplies them. When `structure_high_water_key_scope=global_invariant`, local-scope reductions do not count as high-water movement unless the global invariant moved. Downstream validation uses these fields to prevent behavior-preserving refactor tasks from closing on module creation, file-count growth, relocated helpers, token-avoidance rewrites, or green tests when the original objective required structural reduction.
- Include `allowed_task_kinds` in `disposition_intersection_basis` when a gate allows `goal_productive` only for specific correction classes. This prevents downstream consumers from satisfying a constrained `goal_productive` label with an unrelated lateral task.
- Treat `measurement_progress=true` with `measurement_progress_allowed=false` as governance-only instrumentation. `measurement_progress_allowed=true` is valid only when the root-key and root-family measurement streaks are within cap and both G-COV and G-SUBSTANCE passed. Do not reinclude `goal_productive` for measurement-only work without quality/coverage and substance delta.
- Treat `provider_scale_dispatch_gate.dispatch_required=true` as a derive hard gate: if authority permits bounded extraction or scale execution, the next task must attempt it; otherwise it must terminal/user-escalate with the exact missing authority/input.
- Treat `blocker_mutation_kind=forward_mutation` as changed blocker-state progress only when `terminal_outcome_changed=true` from observed output-delta evidence. If the ladder rung changes but the terminal outcome does not, emit `forward_mutation_vacuous=true`, keep/raise the hard stop, and route to untried root-cause repair or terminal/user escalation.
- Treat `blocker_mutation_kind=facet_rename` as lateral churn, not forward mutation. Facet names, suffixes, dates, run directories, and version labels do not reset the root-family cap.
- Treat distinct-root-cause and stall keys as adapter-collapsed root family plus adapter-owned dominant parameter when available. Use `facet_root_map` for the root and `min_envelope_for(...).deficit_axis` or another adapter-supplied dominant parameter for the second component. Proximate labels alone must not create fresh untried roots when the collapsed root and dominant parameter are unchanged. If the hook is absent, fail quiet and keep the existing key.
- Treat `failure_surface_stage_gate` as H2: the effective count key extends to `(root, dominant parameter, failure surface stage)` and must be emitted as `effective_count_key`/`failure_surface_count_key` when available. If a terminal classification's mapped stage contradicts the observed `failure_surface_stage`, emit `terminal_classification_stage_contradiction=true`, `terminal_classification_invalid_for_counting=true`, and hard-stop counting/close until classification-stage or input-contract repair occurs.
- Treat `same_input_contract_gate.same_input_contract_violation=true` as H2 fail-closed evidence: same-condition comparisons across mismatched input sets are invalid for counting and cannot close or reset a family.
- Treat `diagnostics_unavailable_gate.instrumentation_supply_required=true` as H3: after repeated `diagnostics_unavailable` for the same failure surface, derive's forced option set and loopback's `forced_selected_task_options` must include instrumentation supply. A hypothesis repair that skips instrumentation must record why success/failure is already observable without new instrumentation.
- Treat `verification_source_separation_gate.independent_source_separation_status=missing|overlap|blocked` as H4: downgrade affected `independently_verified_fields` to attested. A zero-disagreement or clean verification result only counts as independently verified when `verification_input_paths` are disjoint from the verified artifacts or the adapter marks the axis `self_grounded`.
- Treat `requires_correction_or_terminal=true` as G-BALANCE: detection-only work has repeated for the same root blocker family while semantic progress remains false. Downstream derivation must choose correction/implementation work, `terminal_blocked`, or `user_escalation`; another validator, metric, gate, dashboard, lineage, or report is not goal-productive.
- Treat `untried_actionable_root_cause_exists=true` as a terminal-blocker veto only while `hypothesis_exhausted=false` and `untried_veto_overridden_by_chain_stall=false`. Downstream derivation must promote the verified untried hypothesis as the next goal-productive repair task instead of sealing the family unless G-CHAIN proves cumulative goal-distance stall.
- Treat root-cause actionability as provenance-hardened when `repo_owned_source_roots_status=provided`: repository-owned source provenance derives `local=true`, `in_scope=true`, and `actionable=true`, and conflicting producer self-report fields are ignored. The packet may emit `repo_owned_source_self_report_rejected` as a warning. When the hook is absent, do not infer repository ownership from project-specific path names in this skill.
- Treat `root_cause_unverified_hypotheses` as excluded from untried promotion. A self-asserted `actionable` flag without structural fields or provenance must not override terminal/quiescence.
- Treat `root_cause_duplicate_hypotheses` as excluded from untried promotion. Version suffixes, renamed slugs, and same `(root cause, target surface, observed delta class)` equivalents do not create fresh untried hypotheses.
- Treat `hypothesis_exhausted=true` as a hard stop equivalent to quiescence: after the same family spends the `untried_promotion_budget` on vacuous repairs with `terminal_outcome_changed=false`, route to `terminal_blocked` or `user_escalation` unless a supplied input delta changes the family.
- Treat `orphan_advice_not_intaken` findings as warn-only coherence findings: root steering docs such as `task_advice.md`, `skill_advice.md`, or `task_doctor_steering.md` need `$manage-external-advice intake` before derive can reliably consume them as active non-GT advice.
- Treat `primary_metric_gate.primary_metric_stalled=true` as the C4 trigger key when the adapter supplies `primary_metric`: if the primary metric high-water has not moved for the configured cap, label churn cannot reset forced retargeting. If C4 enumerates no actionable forced task options, emit exactly one `user_escalation` backstop with the missing input/authority/evidence kind; do not automatically retry, relax gates, or grant authority. If the adapter also supplies `evidence_provenance`, a primary metric movement must be `independently_verified` before it can move the high-water.
- Treat every gate packet's `evaluation_status` as three-state: `pass`, `fail`, or `not_evaluated`. A fail-quiet or missing required hook is `not_evaluated`, not `pass`. Consumers may fail quiet only when no acceptance/verifier contract says that gate is required.
- Never use `produced_domain_delta`, `progress=advanced`, non-empty row counts, lineage, gap reports, task-state records, or renamed command families as truth by themselves.

## Registry Rules

The producer owns `.task/anti_loop/family_progress_registry.jsonl` and the additive root-cause ledger `.task/anti_loop/root_cause_ledger.jsonl`.

- Key rows by suffix-normalized generation-independent `family_key`; do not include input fingerprints, run directories, timestamps, sampled work ids, task-pack names, advice IDs, cycle IDs, run IDs, date/hash suffixes, or version suffixes in the effective key.
- When the adapter supplies a collapsed root and dominant parameter, use that pair for root-cause distinctness and stall equivalence before falling back to proximate labels. Do not let version suffixes, renamed slugs, or blocker-label changes create a fresh untried hypothesis for the same pair.
- When the adapter supplies global structure invariants, use them as the structure high-water key before per-cycle selected-scope metrics. Do not let a new bounded refactor scope reset structure progress while the global invariant remains flat.
- Append or compact only this registry. Do not edit candidate outputs, task packs, issues, schema records, advice files, or implementation code.
- Append root-cause ledger rows idempotently by `(cycle_id, family_key, root_key, hypothesized_root_cause)`. The ledger is non-GT workflow evidence and records only whether a domain-owned hypothesis was attempted, whether the terminal outcome changed, actionability provenance, and compact distinctness fields.
- Compact root-cause ledger rows by family and equivalent `(root cause, target_surface, observed_delta_class)` while preserving `attempt_count` and `vacuous_attempt_count`; do not let version suffixes or renamed slugs grow the ledger indefinitely.
- When `hypothesis_exhausted=true`, feed the exhausted family into `.task/sealed_blocker_families.json` as workflow state so later cycles cannot silently regenerate untried repair tasks for the same family without new input.
- Re-running the same `cycle_id` for the same `family_key` must be idempotent.
- On idempotent replay, preserve recorded measurement, blocker-mutation, disposition, consolidation, and finding fields from the existing registry row; do not let the replay treat its own check IDs or frontiers as already-known evidence and erase A1/A2 progress fields.
- Missing or malformed artifacts must not increment counters or update high-water marks.

## Reviewer Prompt

When a reviewer is needed, give it only the raw artifact paths, the registry path, and the producer packet. Ask it to determine whether the output contains real semantic movement or only placeholder events, surface entities, lateral work churn, or artifact jitter. Do not pass intended fixes or prior conclusions.
