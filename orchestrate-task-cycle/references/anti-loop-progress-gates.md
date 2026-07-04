# Anti-Loop Progress Gates

Use this reference when recent task-cycle evidence shows safe but stationary work: repeated no-live contracts, metadata-only output, unchanged primary artifacts, provider avoidance, or repeated command-surface hardening. These gates are workflow controls, not goal truth, authority, issue closure evidence, or permission grants.

## Contents

- [Ownership](#ownership)
- [Domain-Adapter Contract](#domain-adapter-contract)
- [Part D In-Place Revision Contract](#part-d-in-place-revision-contract)
- [Part E In-Place Revision Contract](#part-e-in-place-revision-contract)
- [Part F In-Place Revision Contract](#part-f-in-place-revision-contract)
- [Part G In-Place Revision Contract](#part-g-in-place-revision-contract)
- [Part H In-Place Revision Contract](#part-h-in-place-revision-contract)
- [Part I In-Place Revision Contract](#part-i-in-place-revision-contract)
- [Part J In-Place Revision Contract](#part-j-in-place-revision-contract)
- [Part K In-Place Revision Contract](#part-k-in-place-revision-contract)
- [Part L In-Place Revision Contract](#part-l-in-place-revision-contract)
- [G1 Disposition Intersection Gate](#g1-disposition-intersection-gate)
- [G0 Pre-Cycle Regression Guard](#g0-pre-cycle-regression-guard)
- [G0-SAT Gate Satisfiability Precheck](#g0-sat-gate-satisfiability-precheck)
- [G2 Qualitative Review Clamp](#g2-qualitative-review-clamp)
- [G3 Strict Output Delta](#g3-strict-output-delta)
- [R-GCOV Coverage Gate Reconciliation](#r-gcov-coverage-gate-reconciliation)
- [G-INTEGRITY Validator Integrity And Coverage](#g-integrity-validator-integrity-and-coverage)
- [G-COV Coverage/Quality Delta Gate](#g-cov-coveragequality-delta-gate)
- [G-SUBSTANCE Output Substance Gate](#g-substance-output-substance-gate)
- [G-VACUOUS Vacuous Corrective Gate](#g-vacuous-vacuous-corrective-gate)
- [G-MEAS-CAP Measurement Exception Cap](#g-meas-cap-measurement-exception-cap)
- [G-FACET Root-Family Measurement Cap](#g-facet-root-family-measurement-cap)
- [G-ADAPTER Adapter-Mandate Gate](#g-adapter-adapter-mandate-gate)
- [G-CHAIN Cumulative Goal-Distance Gate](#g-chain-cumulative-goal-distance-gate)
- [G-REACH Acceptance Reachability Gate](#g-reach-acceptance-reachability-gate)
- [G-OENV Oracle/Metric Validity Gate](#g-oenv-oraclemetric-validity-gate)
- [G-ADVICE-FRESH Advice Freshness Gate](#g-advice-fresh-advice-freshness-gate)
- [G-BALANCE Detection/Correction Balance](#g-balance-detectioncorrection-balance)
- [G-DISPATCH Provider/Scale Duty Gate](#g-dispatch-providerscale-duty-gate)
- [G4 Behavior-Based GT Conflict Detection](#g4-behavior-based-gt-conflict-detection)
- [G5 Command-Surface Hard Stop](#g5-command-surface-hard-stop)
- [S-STRUCT Structure Signal](#s-struct-structure-signal)
- [G5b Consolidation Streak Cap](#g5b-consolidation-streak-cap)
- [G6 Same-Family Micro-Hardening Limit](#g6-same-family-micro-hardening-limit)
- [G7 Loopback Progress Packet](#g7-loopback-progress-packet)
- [A1 Measurement Progress Exemption](#a1-measurement-progress-exemption)
- [A2 Blocker Forward-Mutation Ledger](#a2-blocker-forward-mutation-ledger)
- [A2b Root-Cause Hypothesis Ledger](#a2b-root-cause-hypothesis-ledger)
- [A3 Terminal-Blocked Exit Guard](#a3-terminal-blocked-exit-guard)
- [A3b Terminal Quiescence Gate](#a3b-terminal-quiescence-gate)
- [A3c Terminal Escalation Gate](#a3c-terminal-escalation-gate)
- [A4 Advice-Intake Coherence Gate](#a4-advice-intake-coherence-gate)
- [A5 Command-Surface Carve-Out](#a5-command-surface-carve-out)
- [Capability Ladder Router](#capability-ladder-router)
- [No-Overclaim Boundaries](#no-overclaim-boundaries)

## Ownership

- `orchestrate-task-cycle` owns packet assembly, script execution, stage ordering, and hard-gate enforcement before derive.
- `review-cycle-output-quality` owns direct qualitative inspection and progress caps from inspected output quality.
- `derive-improvement-task` owns final next-task selection, candidate retention, task-pack mutation, and terminal-blocker state.
- Repository-specific scripts may produce packets, but they do not replace the skill-owned decision gates.

## Domain-Adapter Contract

Gate logic must stay domain-agnostic. A repository may supply a domain adapter to `$audit-cycle-loopback` with `--domain-adapter <path.py>`, `TASK_CYCLE_DOMAIN_ADAPTER_PATH`, or the conventional `.task/domain_adapter.py` path when present. The adapter owns domain-specific paths, metric names, lexicons, thresholds, and artifact interpretation. The workflow consumes only these interfaces:

- `quality_vector(...)`: coverage/quality vector for G-COV.
- `substance_metrics(...)`: primary-output substance vector for G-SUBSTANCE.
- `corrective_resolution(...)`: corrective/backfill lanes with `attempted/resolved` counts for G-VACUOUS.
- `facet_root_map(...)`: facet labels mapped to root families for G-FACET.
- `min_envelope_for(target, **context)`: optional D1 helper returning adapter-owned `envelope_floor` and `deficit_axis` for measurable acceptance targets.
- `residual_gap_policy(target, **context)`: optional F3 helper returning adapter-owned residual gap threshold, comparison basis, and marginal-repair policy for measurable acceptance targets. The workflow consumes only abstract fields such as residual gap ratio and threshold status; metric definitions and threshold values stay adapter-owned.
- `output_fingerprint(...)`: current primary-output fingerprint for G-ADVICE-FRESH.
- `previous_accepted_fp(...)`: previous accepted primary-output fingerprint, optionally with previous quality/high-water vector, for R-GCOV baseline selection.
- `structure_metrics(...)`: optional structure metrics for S-STRUCT, such as entrypoint LOC, command count, active/legacy ratio, mechanical shard count, version-suffix file count, global-rebinding/coupling signal count, duplicate definition count, tree depth, directory fan-out, reuse ratio, max file LOC, consolidation recommendation, `structure_high_water_moved`, `improved_structure_axes`, and `refactor_effect_required`. It may expose `global_invariants`, `global_*` numeric fields, `global_structure_high_water_moved`, and `structure_high_water_key_scope=global_invariant` when structure progress must be keyed by fixed global invariants rather than a selected local scope.
- `producer_progress_claim_fields(...)`: optional D2 helper listing producer-owned progress/completion fields that must be stored only as `observed_producer_claim`.
- `adapter_load_status(...)` or packet fields `adapter_loaded`/`adapter_path`: optional registered-adapter load status. A registered adapter that is not loaded is `adapter_wiring_defect`, not adapter absence.
- `capability_ladder(...)`: optional next-rung options for G-CHAIN forced retargeting, including abstract `selected_task_kind`, actionability, authority, local-data, and provider-bound prerequisites.
- `primary_metric(...)`: optional D4 helper exposing one adapter-owned north-star progress value and high-water comparison semantics for G-CHAIN/C4 trigger keying.
- `verifier_source_paths(...)`: optional F1 helper exposing abstract gate IDs mapped to verifier source paths or globs. If the current change set touches a mapped verifier source, that gate's pass becomes `pass_with_coupled_verifier` and is not an effective pass for close or progress. Missing hooks fail quiet.
- `evidence_provenance(...)`: optional F2 helper exposing metric-field provenance as `independently_verified` or `producer_attested`. When present, untagged movement is treated as `producer_attested`; only independently verified metric movement can update high-water, reset stall counters, or support `goal_productive`. Missing hooks fail quiet.
- `root_cause_hypotheses(...)`: optional root-cause hypothesis rows with domain-owned slugs and actionability booleans for the generic root-cause ledger.
- `repo_owned_source_roots(...)`: optional repository-owned source glob roots for provenance-based root-cause actionability. When a blocker hypothesis points to a repo-owned source under these roots, `$audit-cycle-loopback` derives `local=true`, `in_scope=true`, and `actionable=true` from provenance and rejects conflicting producer self-report fields. If absent, fail quiet and keep legacy actionability rules.
- `gate_selfcheck(...)`: optional pre-execution gate artifact self-check consumed by `$run-task-code-and-log` failure autopsy. It may report `blocked_pre_exec`, `contradicting_evidence`, `trusted_evidence_source`, `prior_pass_observed`, and `repo_owned_pre_exec_blocker`.
- `partial_progress_axes(...)`: optional warn-only axes for all-or-nothing gate flatlining. Use it to recommend gate decomposition; never let this hook alone promote or block progress.
- `acceptance_reachability(...)`: optional abstract G-REACH input with `acceptance_min_output`, `frozen_envelope`, and optional `reachability_verdict`.
- `metric_validity_self_check(...)`: optional G-OENV input that reports tautological, constant, or self-fulfilling metrics/oracles.
- `target_required_verifier(target, **context)`: optional target-to-verifier mapping for measurable acceptance, returning abstract `required_verifier`, `verifier_required`, and current `evaluation_status: pass|fail|not_evaluated` when available.
- `goal_axis_map(targets, quality_vector, **context)`: optional mapping from active measurable goals to adapter-owned quality/vector axes that observe each goal. The workflow checks only whether each active measurable goal has at least one mapped axis; axis definitions, formulas, thresholds, and source artifacts stay adapter-owned.
- `execution_stage_ladder(**context)`: optional H1/H2 ordered execution stages, optionally with `terminal_classification_stage_map`. Loopback combines this with `last_successful_stage` from failure autopsy to derive `failure_surface_stage`.
- `terminal_classification_stage_map(**context)`: optional mapping of terminal classifications to allowed failure stages. A contradiction makes the terminal classification invalid for counting or close.
- `instrumentation_trigger_threshold(**context)`: optional H3 threshold for repeated `diagnostics_unavailable` on the same failure surface. Missing hook defaults to `2`.
- `hook_demand_threshold(**context)`: optional G-ADAPTER demand threshold for `adapter_hook_demand` `decision_relevant_skip_count`. Missing hook defaults to `2` and remains fail-quiet.
- Verification source metadata in `evidence_provenance(...)` or a dedicated hook: `verification_input_paths`, `verified_artifact_paths`, and `self_grounded` axes for H4 independent-source separation.
- `instrumentation_field_map(...)`: optional I1 map of supplied diagnostic/instrumentation fields and domain-owned non-empty criteria. Missing hooks fail quiet unless the task-pack item or caller packet explicitly marks the work as instrumentation supply.
- `run_disposition(safety_violations, quality_vector, **context)`: optional I4 disposition classifier returning `failed_closed`, `candidate_degraded`, or `candidate_written`. Safety contracts and quality axes remain adapter-owned.
- `runtime_config_echo(**context)`: optional I5 safe scalar/enum effective runtime configuration plus each field's `config_origin` and derived `config_overrides`.
- `acceptance_scenarios(...)`: optional J1 helper returning scenario records with abstract `scenario_id`, scalar `premise_predicate`, and `expected_terminal_state`. Missing hooks fail quiet unless normalized acceptance already supplied scenarios.
- `argv_redaction_policy(...)`: optional J2 helper that classifies argv values for redaction. Argument names must remain visible; secret, body, or hash-like values may be masked.
- `outcome_variance(target, **context)`: optional J4 helper returning recent stochastic output dispersion and comparable slack fields. It may be folded into `min_envelope_for(...)` as `slack`; metric definitions and thresholds remain adapter-owned.
- `designated_baseline(**context)`: optional K1 helper returning the current designated output surface id/path/version and supersede status for output-derived scalar expectations.
- `comparison_parity_axes(**context)`: optional K2 helper returning adapter-owned parity axes and per-axis status `controlled`, `measured`, or `unknown` for comparison/adoption tasks.
- `required_output_classes(**context)`: optional K3 helper returning required output classes or scalar predicates used to classify adoption axes as `gating`; axis definitions and thresholds stay adapter-owned.
- `resolution_downgrade_fields(**context)`: optional K4 helper mapping report fields that declare lower-resolution surrogate evidence for a higher-resolution contract. Missing hooks fail quiet and only caller-supplied downgrade fields are preserved.
- `production_lane_identity(artifact_paths, **context)`: optional L1 helper returning an opaque lane identity for validated artifacts, such as producer/contract/config lineage keys. Component definitions stay adapter-owned.
- `current_decision_lane(**context)`: optional L1 helper returning the opaque lane identity currently under adoption, capability, baseline, or next-rung decision.
- `gating_axis_producer_map(**context)`: optional L3 helper mapping gating axis IDs to producer source paths or globs that should supply that axis. Missing hooks fail quiet.
- `portfolio_quota(**context)`: optional L4 helper returning the recent-window size, verifier/report/metadata versus producer/envelope/long-run classification, and threshold ratio. Missing hooks are warn-only with default `N=6` and `3:1`.
- `throughput_evidence(**context)`: optional L5 helper returning observed cycle throughput, unit, run id, and confidence interval for scale reachability.
- `acceptance_scale(target, **context)`: optional L5 helper returning required acceptance scale and unit for the target.
- `metric_basis_inputs(metric_id, **context)`: optional L6 helper returning claimed basis class, consumed input classes, and whether the claim is derivable from those inputs.
- `surface_field_classes(artifact_family, **context)`: optional L7 helper returning producer-written surface string field classes and locator interpretation rules for qualitative review.

If the adapter is absent or omits a required vector, promotion must fail closed for the affected gate while packet production continues. If the adapter is registered by path or declaration but `adapter_loaded!=true`, set `adapter_wiring_defect=true`, route as `self_inflicted_gate_defect`, and select wiring/load correction instead of creating a new adapter. Do not hardcode project module paths, metric names, lexicon paths, or artifact filenames in the generic workflow skill body.

## Part D In-Place Revision Contract

These rules revise existing decision points. They do not create new detector phases, do not grant new authority, and do not weaken existing no-overclaim gates.

- D1 acceptance-envelope binding: `$normalize-acceptance-and-demo` treats a measurable acceptance target as the target plus adapter-owned `min_envelope_for(target)`. A selected slice below `envelope_floor` is acceptance-incomplete. Downstream derive may expand the envelope, preserve explicit descope with residual scope, or user-escalate; it must not lower the target to fit the smaller slice.
- D2 producer verdict seal: `$run-task-code-and-log` and downstream packets must downgrade producer progress labels to `observed_producer_claim`. Authoritative progress comes only from adapter recomputation, loopback/output-delta, or completion validation. A conflict is `split_brain_progress_claim` warning evidence, not a second truth source.
- D3 root-cause rekeying: distinct-root-cause vetoes and stall streaks use adapter-collapsed root family plus an adapter-owned dominant parameter such as `min_envelope_for(...).deficit_axis` when present. Proximate label churn cannot create a fresh untried root for the same pair. Missing hooks fail quiet to legacy keys.
- D4 C4 trigger rekeying: when `primary_metric(...)` is present, C4 forced-retargeting is triggered by zero high-water movement on that adapter-owned primary metric, not by mutable blocker labels. If C4 finds no actionable forced option, emit exactly one `user_escalation` backstop with the missing input, authority, or evidence kind.

## Part E In-Place Revision Contract

These rules revise existing decision meanings and keys. They do not add a new report, new derive phase, new detector family, authority grant, retry, or gate bypass.

- E1 gate result three-state: existing gate packets use `evaluation_status: pass|fail|not_evaluated`. A fail-quiet missing hook is `not_evaluated`, not `pass`. Consumers may ignore a missing optional hook only when no measurable acceptance or caller contract says that verifier is required.
- E2 acceptance completeness: measurable acceptance means measurable and verifiable. When `target_required_verifier(...)` or an acceptance packet marks a verifier as required and the gate is `not_evaluated`, normalize `unverifiable_acceptance_contract=true`. B1 acceptance provenance consumes that as incomplete acceptance, normally `partial`, and preserves a verifier-hook follow-up or explicit descope with residual scope.
- E3 structure high-water rekeying: when `structure_metrics(...)` exposes fixed global invariants, key S-STRUCT high-water by those invariants instead of the per-cycle selected scope. Local reductions are useful but cannot reset structural progress when `structure_high_water_key_scope=global_invariant` and the global invariant is flat.

If the required mapping or global invariant hook is absent, fail quiet to the existing D1-D4 behavior. Do not invent project-specific verifier names, invariant names, thresholds, paths, models, or capacities in this generic reference.

## Part F In-Place Revision Contract

These rules revise existing decision meanings, evidence definitions, and task-selection keys. They do not add a new phase, new report, new detector family, authority grant, automatic retry, or gate bypass.

- F1 verifier-source coupling: a gate result counts as effective `pass` only when the current change set did not modify that gate's verifier source according to adapter `verifier_source_paths(...)`. A passing gate whose verifier source changed in the same cycle is `pass_with_coupled_verifier`, which consumers must read as not-pass for close, high-water movement, and `goal_productive`. Route through B1 as `partial` with residual work for non-coupled revalidation or F2 independent evidence recalculation. Legitimate verifier fixes are allowed; they require a separate verification cycle or independent recalculation before the pass is consumed.
- F2 evidence provenance: primary-metric high-water movement, G-COV/G-SUBSTANCE movement, measurement promotion, and `goal_productive` evidence may count only fields whose adapter provenance is `independently_verified`. Producer-recorded scalar movement is `producer_attested` trace evidence; it cannot move high-water, reset stall counters, or silence C4/D4 forced retargeting. When the hook is provided, missing per-field provenance is interpreted as `producer_attested`. When absent, fail quiet to legacy accounting.
- F3 residual gap marginal value: derive selects residual acceptance-gap repair by comparing marginal gap value against explicit descope-with-residual plus the next capability-ladder rung, not by gap existence alone. Use the existing target-envelope distance from `min_envelope_for(...)` and adapter `residual_gap_policy` when supplied. Gaps below policy threshold default to B1 partial/descope with residual scope plus the next rung; repeated marginal repair is keyed like D3 dominant-parameter retry. Missing hooks fail quiet to existing selection.

Keep verifier source mappings, independent-source definitions, residual thresholds, metric names, paths, and domain source-data policy in the repository adapter or project-owned contracts.

## Part G In-Place Revision Contract

These rules revise the basis on which existing gates stand. They do not add a new phase, detector family, report surface, authority grant, retry, or gate bypass.

- G1 count-key hygiene: same-family counters, root-cause distinctness, family seals, and stall keys are valid only when the effective count key is generation-independent. Plan/advice/task-pack IDs, cycle IDs, run IDs, timestamps, hash-only suffixes, and version/date suffixes are trace material, not count-key material. If a generated key contains those components, preserve it only as a legacy/trace key and count with the adapter-collapsed root plus dominant parameter, or with the existing terminal-outcome family fallback when the adapter map is absent. Unmapped facets must merge conservatively by `terminal_outcome_key` rather than minting a new family.
- G2 required gate hooks: when a measurable acceptance contract depends on a gate named in a SKILL.md contract and that gate's required adapter hook is absent or `not_evaluated`, treat it as E2 `unverifiable_acceptance_contract`. Fail-quiet remains valid only for optional gates that no acceptance, task, advice, issue, or caller packet requires.
- G3 goal-axis completeness: a qualitative review `pass` is consumable only if every active measurable goal has at least one adapter-supplied quality/vector axis observing it. If a goal has zero mapped axes, the review result is `pass_with_unobserved_axes`, not pass, and consumers must preserve B1 partial/residual scope plus an adapter follow-up to supply axes. Missing `goal_axis_map` fails quiet to legacy review semantics.
- G4 cycle-cost denominator: F3 residual-gap selection compares `marginal_gap_value / cycle_fixed_cost` against the alternative's expected value per cycle cost. Reuse `$profile-cycle-efficiency` or equivalent cycle-efficiency evidence; when the denominator is absent, use `1` and preserve legacy F3. Below-policy ratios default to explicit descope-with-residual plus the next capability rung unless adapter evidence records a higher value case.

Keep generation-key rules, required-hook lists, goal-axis maps, residual value thresholds, and cycle-cost measurement details in repository adapters, caller packets, or existing workflow profile evidence. Generic skills consume abstract fields only.

## Part H In-Place Revision Contract

These rules revise existing failure autopsy, loopback counting, evidence provenance, reachability, and ledger-cost decisions. They do not add a new detector, phase, report, retry authority, or gate bypass.

- H1 failure autopsy stage/diagnostics: failed runs should carry `execution_stage_ladder`, `last_successful_stage`, and derived `failure_surface_stage` when the adapter or caller supplies a stage ladder. Store only safe scalar/enum post-failure diagnostics; if none are available, emit `diagnostics_unavailable=true`. Redaction/no-body policy still permits scalar stage names, status codes, counts, and enum labels.
- H2 failure-surface count key: same-family counting extends from collapsed root plus dominant parameter to `(root, dominant parameter, failure_surface_stage)`. A terminal classification whose allowed stage map contradicts the observed `failure_surface_stage` is invalid for counting/close. A same-condition input-set mismatch also invalidates comparison.
- H3 instrumentation supply trigger: when `diagnostics_unavailable=true` repeats for the same failure surface for the configured threshold, loopback emits `instrumentation_supply_required=true`. Derive must include/select instrumentation supply unless a hypothesis repair records why success/failure is already observable without new instrumentation.
- H4 independent source separation: `independently_verified` requires `verification_input_paths` disjoint from verified artifacts unless the adapter marks the axis `self_grounded=true`. Missing or overlapping inputs downgrade affected fields to attested, and zero-disagreement is clean only when separation holds.
- H5 frozen-envelope thaw: when G-REACH says acceptance is unreachable under a frozen envelope, consumers must reserve `envelope_thaw_item` with thaw condition/schedule or route to constraint relaxation, explicit descope, terminal blocker, or user escalation. Repeated thaw omission becomes a blocking reachability finding.
- H6 unchanged packet reference: ledger packets identical to a previous event by path and hash should use `unchanged_ref(path+hash)` rather than reserializing identical content. Profile uses `unchanged_ref_count` in the conservative fixed-cost denominator.

Keep stage names, classification maps, diagnostics thresholds, verification-source definitions, self-grounded axes, envelope thaw policy, and any project-specific artifact paths in repository adapters or caller packets. Generic skills consume abstract fields only.

## Part I In-Place Revision Contract

These rules revise evidence lifecycle seams: production, preservation, exercise, and consumption. They do not add a new phase, detector, report, authority grant, automatic retry, or gate bypass.

- I1 instrumentation exercise: when a task-pack item supplies instrumentation, diagnostics, or observation fields, consuming the supply item must create or preserve a follow-up `instrumentation_exercise` item requiring at least one fresh run id after the supply item with non-empty scalar evidence for the supplied fields. Existing artifact reinterpretation (`derived_from_existing_artifacts`) does not satisfy exercise. Measurement, comparison, adoption, or close items that depend on the supplied fields cannot become current until exercise is consumed or a concrete observability rationale proves success/failure is already measurable.
- I2 acceptance encoding preservation: derive and normalization must copy measurable quantifiers and relation predicates from the original directive into `acceptance.quantifiers`, and tag each acceptance clause with `evidence_kind: live_run|derived_artifact|code_contract|report_only`. If the original criterion requires execution, only `live_run` with a new run id after item creation can satisfy it. Substituting derived artifacts or reports for a live-run criterion is `acceptance_diluted` and must remain `partial` with residual scope.
- I3 guard-stacking family collapse: when the change set consists only of verifier, guard, or report-generator sources mapped by `verifier_source_paths(...)`, no new run id is cited, and the target artifact path set matches the previous cycle, count the cycle under `verifier_surface_hardening` plus the target artifact key regardless of verifier or guard names. At the detection-only cap, remove guard/verifier/report addition from effective dispositions and allow only execution work, explicit descope with residual scope, terminal blocking, or user escalation.
- I4 execution disposition split: distinguish unsafe output from quality-miss output. Safety-contract violations are `failed_closed` and artifacts are discarded. Quality misses are `candidate_degraded`: persist safe scalar artifacts with row/axis verification flags and degradation reasons, but do not promote them as canonical baseline until independently verified axes permit consumption. Successful output remains `candidate_written`.
- I5 runtime config echo: failed-run autopsy may include scalar/enum `runtime_config_echo`, `config_origin: cli|config_file|code_default|backend_default`, and derived `config_overrides`. A `code_default` override that plausibly caused the blocker is a Part A `self_inflicted_gate_defect` routing candidate. No raw bodies, prompts, credentials, secrets, or provider payloads may be stored.
- I6 execution starvation ranking: `$profile-cycle-efficiency` may expose `execution_starvation=true` when a pack or family has no fresh run id for the configured recent-cycle window. Derive must rank execution-output candidates above another guard, contract, verifier, lineage, or report candidate while preserving safety, authority, and explicit terminal/user-escalation constraints.

Keep instrumentation field names, non-empty criteria, quality axes, safety contracts, runtime setting names/defaults, and starvation window overrides in adapters or caller packets. Generic skills consume only abstract fields and safe scalars.

## Part J In-Place Revision Contract

These rules revise decision-contract symmetry and reproducibility. They do not add a new phase, detector, report, authority grant, automatic retry, or gate bypass.

- J1 scenario injection: when acceptance states premise class -> expected terminal state, validation assets must inject at least one input satisfying the premise and assert the expected state. `scenario_uncovered=true` returns to validation-set planning. `acceptance_inversion=true` means the changed tests or implementation assert the opposite state, so validation remains `partial` and derive routes code/contract repair even if the suite is green.
- J2 command provenance: every live execution run records full body-free `command_argv` once. Redaction may mask secret/body/hash-like values, but argument names and scalar nonsecret values must remain. `command_provenance_missing=true` disqualifies the run from baseline, A/B, comparison, and reproduction use while preserving other scalar evidence.
- J3 actionable blocker: blocker reason codes carry the violated abstract relation, observed scalar values, expected relation, and when possible the minimum input delta. A state-name-only blocker is `blocker_opacity=true`; two observations for the same gate feed a blocker-contract repair candidate rather than an immediate hard block.
- J4 stochastic feasibility: when `outcome_variance(...)` or equivalent caller evidence shows dispersion, exact achievement equality is `predetermined_unreachable`, and floor/envelope slack smaller than observed variance is `floor_edge_envelope`. Derive routes contract revision, interval/ratio/intersection criteria, envelope expansion, residual descope, terminal blocker, or user escalation instead of retry.
- J5 first-fire credit: the first fresh run that emits non-empty supplied instrumentation fields records `instrumentation_first_fire=true`, even when its run disposition is failed or degraded. This is one positive evidence delta only; it cannot also consume the instrumentation supply item or prove goal progress.

Keep scenario predicates, terminal states, argv redaction values, blocker relation details, stochastic variance calculations, and first-fire field criteria in adapters, caller packets, or project-owned contracts. Generic skills consume abstract fields only.

## Part K In-Place Revision Contract

These rules revise existing promotion, comparison, adoption, loopback, and result-contract decisions. They do not add a new phase, detector, report, authority grant, automatic retry, or gate bypass.

- K1 expectation lineage: when acceptance includes an output-derived scalar expectation, task promotion binds it to `expectation_anchor`. If `designated_baseline(...)` or caller evidence shows the anchor is superseded, set `expectation_lineage_stale`; derive must rebaseline against the current designated surface or fail closed before live execution. Missing anchors are warning-level `expectation_anchor_missing`, not lineage-verified evidence.
- K2 comparison parity: comparison/adoption tasks preserve `parity_axes` and each axis status `controlled`, `measured`, or `unknown`. `unknown` axes force `parity_unverified`; derive must route axis resolution, provisional comparison, explicit residual scope, terminal blocker, or user escalation before final adoption.
- K3 adoption axis semantics: multiaxis adoption decisions classify each axis as `gating` or `tradable` before measurement, using adapter-owned `required_output_classes(...)` when available. Failed gating axes block adoption regardless of tradable-axis wins. The measured artifact remains `measured_but_disqualified` rather than discarded.
- K4 resolution downgrade consumption: when a report declares that a higher-resolution contract was satisfied by a lower-resolution surrogate, loopback records `resolution_downgrade` and `surrogate_resolution_basis`. First occurrence is warning/provisional evidence; repeated same-contract downgrade feeds resolution restoration or contract revision to derive. Do not add a new detector; consume existing declaration fields.
- K5 report key integrity: when one report contains duplicate terminal keys with divergent values, preserve `report_key_divergence`. Result-contract and validation consumers block pass/close/adoption/baseline/comparison use of the report until it is repaired or a single source with matching values is declared. Matching duplicate terminal keys are warn-only schema debt.

Keep baseline discovery, parity axes, required output classes, evidence-resolution schemas, and duplicate-key policy in adapters, caller packets, or project-owned contracts. Generic skills consume abstract fields only.

## Part L In-Place Revision Contract

These rules revise existing validation consumption, decision refresh, derive selection, reachability, metric provenance, and qualitative-review procedure. They do not add a new phase, detector, report, authority grant, automatic retry, or repo-specific rule.

- L1 current-lane validation binding: when a capability or quality verifier pass is consumed as task, pack, capability, adoption, or next-rung evidence, bind the verified artifact to `production_lane_identity(...)` and compare it with `current_decision_lane(...)`. If they differ, set `pass_on_stale_lane=true`. The pass can prove that the historical artifact or introduced contract worked, but it cannot prove the current lane's capability, support adoption, or unlock the next rung until current-lane rerun/residual evidence exists. Missing lane hooks fail quiet and emit `lane_identity_missing` only.
- L2 fresh measurement for decision updates: when adoption, disqualification, baseline, or comparison decisions are updated after upstream production contracts changed, require a fresh measurement run for the current lane. If the task only relabels or reclassifies stale artifacts, set `decision_metadata_revision=true`; count it as metadata/governance, not measurement progress or pack consumption. Existing `required_new_run_id` and K parity/baseline fields carry the run requirement; no new run phase is created.
- L3 gating-axis producer starvation: when a gating axis remains zero or unmet, use `gating_axis_producer_map(...)` to classify whether the producer path that should create that axis is absent or unexercised. Set `axis_starved_by_missing_producer=true` when source/execution evidence is missing. Derive must prefer producer-supply work above another verifier/guard/report for that axis, and verifier/guard/report additions over the same starved axis collapse under verifier-surface hardening until producer supply fires.
- L4 verifier:producer portfolio quota: when recent consumed work exceeds the adapter-owned verifier/guard/report/metadata to producer/envelope/long-run ratio, set `portfolio_quota_exceeded=true`. If the adapter explicitly supplies a quota, restrict next selection to producer, envelope, long-run, descope-with-residual, terminal blocker, or user escalation until the ratio recovers. Without the hook, record warn-only default quota evidence and do not restrict selection.
- L5 cycle-scale reachability: when `acceptance_scale(...)` and `throughput_evidence(...)` prove the target scale cannot be reached within the cycle cap, set `unreachable_within_cycle=true` instead of `indeterminate`. Derive may select only long-run launch with monitor/harvest plan, throughput improvement with measured C increase, explicit descope-with-residual, terminal blocker, or user escalation. A small smoke repeat is not goal-productive in this state.
- L6 metric basis derivability: when a metric claims a basis/provenance class, compare the claim with `metric_basis_inputs(...)`. If the claim is not derivable from consumed inputs, set `basis_overclaim=true`, downgrade the metric to the actual input class, and exclude it from high-water/progress consumption under F2. The metric value may remain trace evidence; honest downgrade is not a regression.
- L7 surface-field review coverage: when a reviewed artifact family has source locators and `surface_field_classes(...)`, qualitative review samples the adapter-owned record count and compares every producer-written surface string field class, not only summaries. Record only scalar field-class by defect-class counts unless authority allows excerpts. Nonzero counts feed loopback root-family classification and producer-supply derivation; missing hooks fail quiet with `field_class_map_missing`.

Keep lane key components, upstream contract versioning, gating-axis definitions, producer path maps, quota thresholds, scale units, metric basis classes, surface field classes, locators, and excerpt policy in repository adapters or authority/project contracts. Generic skills compare opaque keys, enums, booleans, counts, and safe scalar fields only.

## G1 Disposition Intersection Gate

When multiple active gates provide `allowed_dispositions`, combine them by intersection, not union. The packet must expose:

- `effective_allowed_dispositions`: the intersection of all gates where `hard_stop_required`, `hard_gate`, `requires_goal_productive_next`, `requires_goal_productive_or_user_escalation`, `status=block`, or `constrains_disposition=true`.
- `disposition_intersection_basis`: each contributing gate's allowed set, optional `allowed_task_kinds`, and whether it constrained the result.

Always preserve `terminal_blocked` and `user_escalation` as safety valves. `$derive-improvement-task` must select only from `effective_allowed_dispositions` when the field is present. A disposition allowed by only one gate, such as command-surface `consolidation` when root-axis requires `goal_productive`, is invalid unless it remains in the effective intersection. If a constraining gate allows `goal_productive` only for named task kinds, a task with another `selected_task_kind` is `governance_only` or blocked even when its disposition label says `goal_productive`.

## G0 Pre-Cycle Regression Guard

Before deriving the next task, compare at least the most recent 3 to 5 cycle records when available:

- current artifact family, target command surface, root key, semantic signature, and observed output class
- `provider_request_count`, `env_file_read`, local-model/provider attempt booleans, and terminal/provider status
- primary output fingerprints, semantic counts, and qualitative review caps
- command-surface budget state and same-family micro-hardening streak

If the same artifact family repeats with `provider_request_count=0` and stagnant semantic output for at least 3 recent cycles, block another no-provider micro-hardening task as `goal_productive`. The next selection must be one of:

- a bounded provider or semantic-output transition authorized by authority and GT
- a valid consolidation/refactor task for the over-budget surface
- a supplied-input/domain-delta task that can change the semantic artifact
- `terminal_blocked` or user escalation with the missing input/authority named

## G0-SAT Gate Satisfiability Precheck

Every fail-closed gate must prove that its evidence source can produce the required evidence shape in the current environment before the gate evaluates pass/fail. The run skill or repository adapter may expose:

```text
gate_satisfiability(gate_id, env, **context) -> {
  satisfiable: bool,
  reason: str,
  alternative_evidence_source?: str
}
```

If `satisfiable=true`, evaluate the gate normally. If `satisfiable=false` and `alternative_evidence_source` is present, evaluate the unchanged gate against the alternative source and record the fallback. If `satisfiable=false` and no alternative exists, classify the blocker as `self_inflicted_gate_defect` and route the next task to gate-contract/code correction or user escalation. Do not reclassify this state as an environment/runtime blocker, and do not select another same-gate recheck as progress.

For pre-execution gate artifacts, the run skill may also call:

```text
gate_selfcheck(gate_artifact, gate_id, **context) -> {
  blocked_pre_exec: bool,
  contradicting_evidence: list,
  trusted_evidence_source?: str,
  prior_pass_observed?: bool,
  repo_owned_pre_exec_blocker?: bool
}
```

Classify `self_inflicted_gate_defect` only when repository-owned blocker provenance is confirmed and the same gate artifact contains contradiction evidence, a trusted alternative evidence source, or prior pass evidence. Without repository-owned confirmation, emit warn-only self-check evidence and keep the original failure class.

Keep domain facts, hardware names, command names, thresholds, and evidence-source details in the adapter or task packet. The generic workflow stores only the adapter interface, scalar outcome, classification, and routing rule.

## G2 Qualitative Review Clamp

The qualitative review packet should carry these structured fields when reviewable artifacts exist:

- `semantic_ready`: `true`, `false`, or `unknown`
- `placeholder_event_found`: boolean
- `surface_entity_suspected`: boolean
- `relation_semantics_ready`: `true`, `false`, or `unknown`
- `quality_blocker_codes`: stable short strings
- `progress_cap`: `goal_productive`, `governance_only`, or `terminal_blocked`
- `cap_reason`: concise evidence-backed explanation

If `semantic_ready=false`, `placeholder_event_found=true`, or `surface_entity_suspected=true` affects the primary output, cap `effective_progress_kind` at `governance_only` unless an independent strict output-delta packet proves changed and semantic primary-output progress. A quality cap is direction evidence, not human approval and not final validation.

## G3 Strict Output Delta

Do not treat non-empty rows, scalar counts, lineage records, gap reports, or workflow metadata as domain progress by themselves. `produced_domain_delta=true` requires both:

- `changed_vs_previous=true`: stable fingerprints for repository-declared primary output paths differ from the accepted previous baseline.
- `semantic_progress=true`: the changed content includes meaningful domain semantics, such as named events, named characters/entities, causal/temporal/story-order evidence, supported relation candidates, or reviewed source-backed assertions.

Metadata-only outputs remain `effective_progress_kind: governance_only` unless the active task's acceptance criteria are explicitly metadata/governance work and the same family is not already repeating. Output-delta packets should include `previous_output_fingerprint`, `current_output_fingerprint`, `changed_vs_previous`, `semantic_progress`, `semantic_delta_summary`, `metadata_only`, and evidence paths.

If strict runner validation and output-delta disagree on the same evidence class, prefer the conservative output-delta value. A runner `semantic_progress=true` with output-delta `semantic_progress=false` must produce a block-level `validator_disagreement` finding, set `authoritative_semantic_progress=false`, and prevent runner pass from being used as completion or goal-productive evidence.

Producer progress labels captured from artifacts or run logs are not output-delta truth. Store them as `observed_producer_claim` and compare them only as warning evidence; if they conflict with adapter or strict output-delta evidence, emit `split_brain_progress_claim` and use the conservative recomputed value.

## R-GCOV Coverage Gate Reconciliation

When both output-delta and loopback emit `coverage_quality_delta_gate`, compare them as one logical G-COV. The packet should expose `coverage_quality_delta_reconciliation_gate` with compact local/external gates, `validator_disagreement`, `gcov_metric_name_collision`, metric value conflicts, and `status`.

If the two G-COV values disagree, or the same metric key has conflicting values, treat `status=block` as a conservative hard stop. Do not promote measurement, oracle, or capability-ladder progress from whichever G-COV is favorable. The next task must resolve the disagreement, produce strict changed-and-semantic primary-output evidence, or terminal/user-escalate with the missing evidence.

## G-INTEGRITY Validator Integrity And Coverage

Validator/oracle packets must fail closed when their own structure is contradictory or incomplete:

- A top-level validator success must equal the AND of embedded checks, sub-results, assertions, validator rows, or equivalent child results.
- A validator that declares a target population must inspect the full declared population. If `inspected_count`, `checked_count`, `validated_count`, or equivalent is below `population_count`, `target_count`, `expected_count`, or equivalent, surface `validator_coverage: under_detection`.

Packets should expose `validator_integrity_gate` with `validator_integrity`, `validator_coverage`, `status`, `hard_stop_required`, `allowed_dispositions`, and compact findings. If this gate blocks, do not cite the validator pass as goal-productive evidence. Derive may still choose correction/implementation work that fixes the primary output or the validator, but another validator-only task is not progress.

## G-COV Coverage/Quality Delta Gate

When output-delta or loopback evidence includes a high-water mark, require at least one real adapter-supplied coverage or quality axis to improve before measurement work can be promoted. Example axes include:

- `event_named_ratio`
- `proper_noun_character_ratio`
- `coreference_resolved_ratio`
- `causal_edge_count` or `causal_or_temporal_edge_count`
- `windows_covered` or an equivalent source-window count

The packet must expose `coverage_quality_delta_gate` with previous/current vectors, `improved_fields`, `quality_delta_pass`, and `status`. If `quality_delta_pass=false`, new validators, oracles, ladder checks, metrics, dashboards, lineage, gap reports, or scalar contracts remain `governance_only` unless independent strict output-delta evidence proves changed semantic primary output. Do not add new domain-specific metric names to this generic skill; put them behind the adapter.

## G-SUBSTANCE Output Substance Gate

Before a measurement/oracle transition or capability-ladder rung movement can support `goal_productive`, require adapter-supplied substance metrics to improve on at least one axis. The packet must expose `substance_delta_gate` with previous/current substance vectors, `improved_axes`, `substance_delta_pass`, `status`, and fail-closed metadata.

If `substance_delta_pass=false` or `status=missing`, validator/oracle existence, metric availability, or non-empty report rows cannot open the next rung by themselves. The next task must create real primary-output substance, choose correction/implementation work, or terminal/user-escalate with the missing adapter/output evidence. Independent strict output-delta evidence with `changed_vs_previous=true` and `semantic_progress=true` may still prove progress.

## G-VACUOUS Vacuous Corrective Gate

Corrective, repair, backfill, or reconciliation lanes must be counted by resolved items, not attempted rows. The packet must expose `vacuous_corrective_gate` with lane `attempted/resolved` counts, `surface_corrective_noop`, `excluded_delta_lanes`, and `status`.

If any lane has `attempted>0` and `resolved==0`, set `surface_corrective_noop=true`. Exclude those lanes from produced/semantic delta claims and do not let the task count as `goal_productive` unless independent strict changed-and-semantic primary-output evidence exists.

## G-MEAS-CAP Measurement Exception Cap

Measurement progress is capped to one transition per suffix-normalized `root_key`, and only when G-COV and G-SUBSTANCE pass. The packet must expose `measurement_progress`, `measurement_progress_allowed`, `measurement_progress_streak_for_root_key`, `measurement_streak_cap`, `measurement_check_ids`, `measurement_frontiers_observed`, and `measurement_progress_basis`.

Do not re-add `goal_productive` to `effective_allowed_dispositions` merely because a new check ID, oracle, metric, or capability-ladder observation appeared. Treat measurement as a `goal_productive` basis only when `measurement_progress_allowed=true`, `coverage_quality_delta_gate.quality_delta_pass=true`, and `substance_delta_gate.substance_delta_pass=true`. Otherwise set `measurement_goal_productive_allowed=false` and choose real implementation/output progress, `terminal_blocked`, or `user_escalation`.

## G-FACET Root-Family Measurement Cap

Normalize blocker and measurement families by removing version/date/run-directory suffixes and facet labels. When the domain adapter supplies `facet_root_map`, collapse facet labels through that map before applying family-level caps. Use `root_family_key` or `blocker_root_family`; do not let equivalent facet renames reset the measurement exception counter.

When `facet_root_map` is absent, empty, or fails, do not fall back to raw proximate blocker text as the family key. Emit `facet_root_map_missing=true` and group by a stable terminal-outcome family such as `artifact_family + terminal_outcome_key`; use that value as `family_key` and `root_family_key`, and preserve the previous artifact/signature key as `legacy_family_key`. If the raw key contains generation-dependent components, mark that raw key trace-only and keep counting on the terminal-outcome family. The packet should expose `terminal_outcome_key`, `terminal_outcome_family_key`, `terminal_outcome_family_fallback_applied`, and `terminal_outcome_family_previous_count`. This fallback is intentionally conservative: if the terminal outcome is unchanged, blocker-label mutation or generation churn cannot reset the same-family cap.

Packets should expose `measurement_progress_streak_for_root_family` alongside `measurement_progress_streak_for_root_key`. `measurement_progress_allowed=true` is valid only when both the root-key and root-family streaks are within cap and G-COV/G-SUBSTANCE passed.

Treat `blocker_mutation_kind=facet_rename` as lateral churn. Treat `blocker_mutation_kind=forward_mutation` only when the normalized root family actually changes or a recorded capability ladder transition is not merely a facet rename. If the terminal outcome remains unchanged, set `forward_mutation_vacuous=true` and keep the hard stop.

## G-ADAPTER Adapter-Mandate Gate

When `facet_root_map_missing=true`, `substance_delta_gate.status=missing`, or `quality_vector` is missing for the same `artifact_family` across the configured adapter cap, default `3`, and quality/substance high-water has not improved during that span, emit:

- `adapter_mandate_required: true`
- `adapter_missing_streak`
- `adapter_contract_unmet`, using only abstract contract names such as `facet_root_map`, `substance_metrics`, and `quality_vector`
- `adapter_mandate_gate.allowed_dispositions: [goal_productive, terminal_blocked, user_escalation]`

The next goal-productive task must register or strengthen the repository domain adapter. Do not count another domain-specific micro-repair as goal-productive until the adapter supplies the missing collapse/substance/quality contract or the cycle terminal/user-escalates with the exact adapter blocker.

Separate from the existing Tier-0 mandate condition, G-ADAPTER also reads `adapter_hook_demand`. If any opaque hook id reaches `hook_demand_threshold` on `decision_relevant_skip_count`, emit `hook_supply_required=true` and `demanded_hooks`. If `demanded_hooks` has two or more entries, the recommended task kind is `adapter_hook_batch_supply`; supplying hooks one cycle at a time preserves the fail-quiet blind spot and wastes cycles on separate adapter edits. This is an input expansion of the single G-ADAPTER gate, not a second gate or second truth source. If both `adapter_mandate_required` and `hook_supply_required` are active, the mandate precedes hook supply routing.

Define `tier0_hook_set` only by reference as the hook set already mandated by G-ADAPTER plus adapter load status. Do not enumerate new hook names here. Tier-1+ hooks are every other hook and may be supplied only through `adapter_hook_demand`; hooks defined before demand are more likely to be misdefined for the real blocker.

If the repository has registered an adapter but the loopback packet reports `adapter_loaded!=true`, emit `adapter_wiring_defect=true` and `recommended_disposition=self_inflicted_gate_defect`. That state is local, in-scope, and actionable because the workflow failed to inject or load its own registered adapter. The next goal-productive task kind is `adapter_wiring_fix` or `adapter_load_fix`; do not misroute it as `adapter_mandate_required` or a new-adapter task.

If G-ADAPTER fires, it precedes G-CHAIN. This prevents adapter absence from being mistaken for a domain terminal state when the real missing prerequisite is the workflow's own adapter contract.

## G-CHAIN Cumulative Goal-Distance Gate

Track cumulative high-water movement by `root_family_key` after adapter facet collapse. If the adapter is absent, track by `artifact_family` instead of proximate blocker label or terminal outcome. This gate is independent of `blocker_signature`, terminal-outcome wording, version suffixes, and renamed hypotheses.

When the same scope has no G-COV or G-SUBSTANCE high-water improvement for the configured chain cap, default `3`, emit:

- `cumulative_goal_distance_stalled: true`
- `cumulative_goal_distance_stall_streak`
- `cumulative_goal_distance_scope_key`
- `high_water_vector`
- `high_water_last_improved_cycle`

If untried hypotheses remain in the same stalled scope, also emit `cumulative_untried_chain_without_quality_delta=true` and `untried_veto_overridden_by_chain_stall=true`. `$derive-improvement-task` must then ignore the usual untried-root-cause terminal veto. When the stall streak reaches the forced-retarget threshold and lateral churn continues, the packet must enumerate `forced_selected_task_options` before terminal/user escalation:

- self-inflicted gate defects such as `adapter_wiring_fix`;
- the first actionable adapter `capability_ladder` rung whose authority, local-data, and provider-bound prerequisites are satisfied.

If an option exists, expose it as `forced_selected_task` and allow `goal_productive` only for its `selected_task_kind`. If no option exists or the adapter omits the ladder hook, keep `terminal_blocked` or `user_escalation` under the existing fail-quiet rule.

Use this gate for the "distinct but non-converging hypothesis chain" case: each repair can be locally valid and still fail to reduce goal distance. Do not delete or weaken A2b; G-CHAIN adds a separate cumulative no-progress axis.

When the adapter exposes `primary_metric(...)`, key the C4 forced-retarget trigger to primary-metric high-water movement. If the primary metric has zero independently verified high-water movement for the configured cap, renamed labels, facets, version suffixes, or producer-attested scalar movement cannot reset the trigger. If no forced option is actionable, emit one user-escalation backstop with the missing input, authority, or evidence kind; do not schedule another same-family retry solely to recheck the condition.

## G-REACH Acceptance Reachability Gate

Before derive promotes another repair inside a frozen envelope, compare the task acceptance lower bound with the frozen execution/resource/input envelope when the adapter or caller exposes abstract comparable values. The packet should carry:

- `acceptance_min_output`
- `frozen_envelope`
- `reachability_verdict: reachable|unreachable|indeterminate`
- `acceptance_unreachable_under_frozen_config`
- `envelope_thaw_item_required`
- `envelope_thaw_item`
- `relaxation_or_escalation_required`

If `reachability_verdict=unreachable`, another envelope-internal micro-repair is not goal-productive. Derive must choose a constraint-relaxation task when authority permits it, reserve an `envelope_thaw_item` with thaw condition/schedule, explicitly descope with residual scope, or choose `user_escalation` when relaxation/thaw needs user approval. If the values are absent or not comparable, use `indeterminate` and do not block solely from G-REACH.

When an `acceptance_envelope_contract` exists, treat `envelope_below_floor=true` as the same acceptance-incomplete condition before derive selects a task slice. This is not a new gate; it is the normalized acceptance contract saying the selected envelope cannot satisfy the target.

When an `acceptance_verifier_contract` or adapter mapping marks a live verifier required, the same gate must expose `evaluation_status`. `not_evaluated` means the gate did not run and cannot be read as pass. If the target is measurable and the verifier remains `not_evaluated`, set `unverifiable_acceptance_contract=true` and preserve residual verifier work rather than consuming the target.

## G-OENV Oracle/Metric Validity Gate

When the adapter exposes `metric_validity_self_check(...)`, check whether a metric/oracle can pass tautologically, by constant output, or by echoing an input/order it is supposed to evaluate. The packet should expose `oracle_metric_validity_gate` with `metric_validity`, `metric_validity_states`, `metric_validity_self_check_provided`, and `metric_goal_productive_excluded`.

If `metric_goal_productive_excluded=true`, do not use that oracle/metric pass to justify measurement progress, capability-ladder promotion, or completion. The next task must correct the metric/oracle definition or provide independent strict changed-and-semantic output-delta evidence. If the adapter omits the self-check, warn only.

If a metric validity self-check is required by the acceptance verifier contract but is `not_evaluated`, treat the metric as unavailable for goal-productive support. Do not treat the missing check as a passing validity check.

## G-ADVICE-FRESH Advice Freshness Gate

Advice is non-GT steering evidence. When active/root advice declares headline output fingerprints or metric snapshots, compare those claims to the current adapter/output fingerprint. The packet should expose `advice_freshness_gate` with `current_output_fingerprint`, declared fingerprint claims, stale advice paths, and `advice_metrics_stale`.

If `advice_metrics_stale=true`, warn and require refresh, defer, or reject rationale before relying on the advice's headline metrics for derive. This does not change phase order and does not promote advice to goal truth.

Gate-result regression is absorbed here rather than added as a separate hard gate. When a supplied gate packet shows `passed -> blocked` under a stable environment fingerprint, expose `gate_result_regression_stale=true` and warn. Route the next task through current evidence review, `gate_selfcheck`, or provenance-hardened root-cause repair before relying on stale headline gate state.

## G-BALANCE Detection/Correction Balance

Classify each cycle task as:

- `detection`: validator, oracle, metric, gate, contract, dashboard, lineage, gap report, coverage report, or other instrumentation added without primary-output semantic progress.
- `correction`: producer, prompt, transform, resolver, extraction, generation, provider dispatch, or other implementation work that can change primary output.
- `mixed`: both detection and correction are present.

If `detection_only` repeats for the same `blocker_root_family` at or above the cap, default `2`, and primary-output semantic progress remains false, expose `detection_balance_gate` or `requires_correction_or_terminal=true`. The next task must be correction/implementation work, `terminal_blocked`, or `user_escalation`. Another detection-only task cannot satisfy a goal-productive hard gate.

## G-DISPATCH Provider/Scale Duty Gate

When `ever_provider_dispatch=false`, provider request count is zero, and the coverage/quality high-water vector remains all-zero, do not select another surface-only, runner-surface, contract, preflight, locator, or accounting task as `goal_productive`. The packet should expose `provider_scale_dispatch_gate` with `dispatch_required`, `provider_request_count`, `high_water_all_zero`, `allowed_dispositions`, and `status`.

If current authority permits bounded dispatch or provider-free scale execution, derive must select real extraction/scale work such as full-window, multi-window, or multi-work execution. If authority, source input, or provider state blocks that work, derive must write `terminal_blocked` or user escalation naming the missing condition. A self-imposed missing runner surface is not a valid terminal blocker when an in-place Class B implementation can create the surface.

## G4 Behavior-Based GT Conflict Detection

Detect task-vs-GT conflict from behavior booleans, not only task text. Include scalar booleans and counts such as:

- `provider_request_count`
- `env_file_read`
- `local_model_loaded`
- `package_install_attempted`
- `raw_body_persisted`
- `bounded_retry_evidence`
- `legitimate_terminal`

If GT or authority allows or requires a provider/env path but the task/run avoids it with `provider_request_count=0`, `env_file_read=false`, and no legitimate terminal or authority blocker, derive must resolve the contradiction, select an authorized bounded attempt, or terminal/user-escalate. A wording change that still forbids required behavior does not satisfy the gate.

If goal truth or the active task requires corpus/generalization progress and behavior evidence shows `single_work_id:true`, `selected_work_count=1`, or a single-work-only streak for at least the local threshold, report `status:block` with reason `single_work_id_invariant_blocks_generalization`. The next task must implement bounded multi-work execution with `single_work_id` separation or terminal/user-escalate on the exact missing source/authority/provider condition.

## G5 Command-Surface Hard Stop

When `command_surface_budget.budget_exceeded=true` and `hard_gate=true`, do not allow another task on the same over-budget surface merely because it is labeled `goal_productive`. Classify the proposed command-surface change:

- Class A, blocked while over budget: new `cmd_*`, versioned `vNNN` wrapper, preflight, gate, locator, handoff, family rename, or alternate runner route.
- Class B, allowed and preferred when it directly creates primary-output progress: in-place modification of the single canonical extraction entrypoint with non-increasing command count.
- Class C, allowed consolidation: command count reduction, family retirement/freezing, or module extraction that reduces the over-budget surface.

Allowed dispositions before intersection are:

- consolidation/refactor candidate selected or registered
- `terminal_blocked`
- user escalation

Allow a goal-productive disposition only for strict changed-and-semantic primary-output evidence or a Class B in-place task that directly creates the missing primary-output transition and records why pure consolidation would not reduce the blocker. The derive result must cite the evidence path.

## S-STRUCT Structure Signal

When the domain adapter supplies `structure_metrics(...)`, expose `structure_metrics_gate` with numeric structure metrics, `structure_consolidation_recommended`, optional `structure_high_water_moved`, `improved_structure_axes`, and `refactor_effect_required`. Semantic structure metrics may include mechanical shard count, version-suffix file count, global-rebinding or hidden-coupling signal count, duplicate public definition count, tree depth, directory fan-out, reuse ratio, and max file LOC. Treat the adapter hook as the single truth source for structure progress; producer-local structure reports are advisory until absorbed into this hook. Treat the signal as warn-level unless another gate makes command-surface pressure hard. Use it to justify Class C consolidation, `semantic_consolidation`, `reuse_extraction`, `coupling_reduction`, or module-boundary work when that work reduces the reported structure burden.

When the adapter supplies `global_invariants` or `global_*` metrics, expose `structure_high_water_key_scope=global_invariant` and `structure_global_invariant_metrics`. For structural objectives, high-water movement must come from those fixed invariants before a task can claim global structure progress. A cycle-local reduction inside a newly selected scope is not enough if global invariants are flat.

For behavior-preserving refactor tasks whose objective is structural reduction, downstream validation must require real structure high-water movement. New modules, relocated helpers, additional files, token/pattern avoidance, or green tests are not enough when the adapter reports `refactor_effect_required=true` and `structure_high_water_moved=false`. Define coupling axes by durable dependency/reference counts or equivalent movement-resistant metrics, not only by absence of forbidden token strings. If `structure_high_water_key_scope=global_invariant`, validation must not close the refactor as global progress from selected-scope improvement alone.

If the adapter omits structure metrics, do nothing beyond warn-only generic code-structure audit findings. Do not hardcode project-specific module paths, metric names, kernel/reuse roots, dependency DAGs, or thresholds into this generic workflow reference.

## G5b Consolidation Streak Cap

Consolidation is governance-only unless it independently produces accepted primary-output progress. Track `consolidation_streak` over recent progress items. When `consolidation_streak >= consolidation_streak_cap` (default 2), remove `consolidation` from `effective_allowed_dispositions` and require `goal_productive`, `terminal_blocked`, or `user_escalation`.

## G6 Same-Family Micro-Hardening Limit

If the last 3 selected tasks in the same artifact family are micro-hardening changes such as `add_field`, `lineage`, `gap_report`, `relation_label_tweak`, `contract_scalar`, `preflight_scalar`, or renamed command variants, block the next same-family micro-hardening task as `goal_productive`.

The next task must be one of:

- provider or semantic-output transition
- valid consolidation/refactor of the repeated surface
- supplied-input or source-backed domain-delta task
- terminal/user escalation with evidence that no authorized productive alternative remains

## G7 Loopback Progress Packet

Run `$audit-cycle-loopback` after qualitative review and before derivation whenever raw run artifacts, output-delta evidence, or repeated-family loop evidence exists. The packet is workflow evidence only and must not be treated as goal truth, validation proof, human review, issue-closure evidence, or readiness/gold promotion evidence.

The producer must compute `anti_loop_progress_gate` from raw artifact content and the append-only family progress registry, not from self-declared `progress=advanced`, non-empty counts, renamed command families, or `produced_domain_delta` alone. Required packet fields include:

- `family_key`, `artifact_family`, and `semantic_signature`
- `changed_vs_previous` and `semantic_progress`
- `same_family_micro_hardening_count`
- `provider_request_count` and other safe provider/env behavior scalars when available
- `quality_vector`, including confidence and domain-context fields when the adapter supplies them
- `previous_accepted_baseline`, `coverage_quality_delta_reconciliation_gate`, `substance_delta_gate`, `vacuous_corrective_gate`, `facet_root_map_applied`, `advice_freshness_gate`, and `structure_metrics_gate`
- `repo_owned_source_roots_status`, `partial_progress_axes_gate`, and provenance-hardened root-cause actionability fields when supplied by the adapter
- `terminal_outcome_changed`, `observed_delta_class`, `forward_mutation_vacuous`, `root_cause_ledger_path`, `root_cause_unverified_hypotheses`, `root_cause_duplicate_hypotheses`, `untried_actionable_root_cause_exists`, `untried_root_cause_hypotheses`, `untried_promotion_budget`, `vacuous_untried_streak`, and `hypothesis_exhausted` when applicable
- `adapter_mandate_required`, `adapter_missing_streak`, `adapter_contract_unmet`, `adapter_hook_demand`, `hook_supply_required`, `demanded_hooks`, `hook_demand_threshold`, `adapter_loaded`, `adapter_wiring_defect`, `cumulative_goal_distance_stalled`, `cumulative_goal_distance_stall_streak`, `forced_selected_task_options`, `untried_veto_overridden_by_chain_stall`, `acceptance_unreachable_under_frozen_config`, `relaxation_or_escalation_required`, and `oracle_metric_validity_gate` when applicable
- `evidence_provenance_gate`, `independently_verified_fields`, `producer_attested_fields`, `attested_only_movement`, `primary_metric_gate`, `primary_metric_stalled`, `primary_metric_zero_movement_streak`, `c4_user_escalation_backstop_required`, `coupled_verifier_gate`, `pass_with_coupled_verifier`, and `changed_verifier_source_paths` when applicable
- `evaluation_status` on required gate packets, `acceptance_verifier_not_evaluated`, `unverifiable_acceptance_contract`, `metric_verifier_not_evaluated`, `structure_high_water_key_scope`, and `structure_global_invariant_metrics` when applicable
- count-key hygiene fields when available, such as `legacy_family_key`, `raw_root_family_key`, `terminal_outcome_family_key`, `terminal_outcome_family_fallback_applied`, and any adapter-supplied dominant parameter that makes counting generation-independent
- goal-axis completeness fields when supplied by review/caller packets, such as `goal_axis_map`, `unobserved_goal_axes`, and `pass_with_unobserved_axes`
- residual-gap cost-ratio fields when supplied by normalize/derive/profile packets, such as `cycle_fixed_cost`, `alternative_cycle_cost`, `marginal_value_per_cycle_cost`, and `residual_gap_cost_policy`
- Part I evidence-lifecycle fields when supplied, such as `instrumentation_exercise_required`, `instrumentation_exercised`, `instrumentation_field_map`, `derived_from_existing_artifacts`, `acceptance.quantifiers`, `evidence_kind`, `verifier_surface_hardening`, `target_artifact_paths`, `change_set_kind`, `run_disposition`, `candidate_degraded`, `runtime_config_echo`, `config_overrides`, and `execution_starvation`
- Part J decision-contract fields when supplied, such as `acceptance_scenario_gate`, `scenario_uncovered`, `acceptance_inversion`, `command_provenance_missing`, `blocker_opacity`, `outcome_variance`, `predetermined_unreachable`, `floor_edge_envelope`, `instrumentation_first_fire`, and `first_fire_consumed_item_id`
- Part K lineage/comparison fields when supplied, such as `expectation_anchor`, `designated_baseline`, `expectation_anchor_missing`, `expectation_lineage_stale`, `parity_axes`, `parity_axis_status`, `parity_unverified`, `adoption_axis_classification`, `required_output_classes`, `majority_vote_adoption`, `provisional_adoption`, `measured_but_disqualified`, `required_evidence_resolution`, `observed_evidence_resolution`, `resolution_downgrade`, `surrogate_resolution_basis`, `report_key_divergence`, and duplicate report-key path/value evidence
- `recommended_disposition`, `hard_stop_required`, `evidence_class`, and evidence paths

The repository adapter or shared module must fail closed on noisy quality inputs. If confidence is low, artifacts are missing/malformed, adapter output is missing, or domain interpretation is uncertain, emit `evidence_class: insufficient_evidence`, `recommended_disposition: conservative_hold`, and `hard_stop_required: true`. Legacy repository quality modules may remain as compatibility fallbacks, but new domain-specific metrics, paths, lexicons, and thresholds belong behind the adapter interface.

Use the packet as a derive gate:

- `semantic_progress=true` may reset the same-family streak, subject to ordinary validation and no-overclaim constraints.
- `semantic_progress=false` with `same_family_micro_hardening_count >= 3` blocks another same-family micro-hardening task as `goal_productive`.
- `evidence_class=insufficient_evidence` blocks `goal_productive` unless the next task supplies the missing raw artifacts, runs a bounded provider/semantic transition, or records terminal/user escalation with evidence.
- `effective_allowed_dispositions` bounds the next selected disposition. Do not choose a disposition by taking a union of individual gates.
- `disposition_intersection_basis.allowed_task_kinds` binds `goal_productive` to those task kinds. A label-only `goal_productive` task with another kind is not valid progress.
- `pass_with_coupled_verifier=true` means a modified verifier source produced the pass in the same change set. Consumers must not count that pass for close, high-water movement, or `goal_productive`; choose verifier-source-independent revalidation, independent evidence recalculation, residual descope, terminal blocker, or user escalation.
- `attested_only_movement=true` means producer-attested scalar movement was observed but excluded from high-water. It does not reset stall counters and cannot satisfy a hard `goal_productive` requirement without independent recalculation.
- `primary_metric_gate.primary_metric_stalled=true` applies C4 forced retargeting on the adapter-owned primary metric. If `c4_user_escalation_backstop_required=true`, derive must emit `user_escalation` with the missing input/authority/evidence rather than another same-family retry.
- `substance_delta_gate.substance_delta_pass=false` blocks measurement promotion unless strict changed-and-semantic primary-output evidence exists.
- `blocker_mutation_kind=forward_mutation` blocks rung promotion unless `terminal_outcome_changed=true`; set `forward_mutation_vacuous=true` when the ladder moved but observed domain output did not.
- `adapter_mandate_required=true` forces adapter registration/strengthening before another domain repair can count as `goal_productive`.
- `hook_supply_required=true` means `adapter_hook_demand` reached `hook_demand_threshold` for `decision_relevant_skip_count`. Derive must supply the `demanded_hooks`, record why the target is observable without those hooks, descope/terminal-block, or user-escalate. This warning/selection signal is not a hard-stop and does not change G-ADAPTER mandate priority.
- `adapter_wiring_defect=true` forces adapter wiring/load correction as `self_inflicted_gate_defect`; it is not adapter absence.
- `cumulative_goal_distance_stalled=true` restricts the next disposition to `terminal_blocked` or `user_escalation` unless G-ADAPTER is active or `chain_stall_forced_retarget_gate` exposes an actionable forced task kind.
- `untried_actionable_root_cause_exists=true` invalidates terminal blocking and forces derive to select the untried root-cause repair only when `hypothesis_exhausted=false`, `untried_veto_overridden_by_chain_stall=false`, and the hypothesis is actionability-verified.
- `repo_owned_source_roots_status=provided` means repository-owned provenance can override conflicting producer self-report fields for root-cause `local`, `in_scope`, and `actionable`. Do not trust self-reported `local=false`, `in_scope=false`, or `actionable=false` for that hypothesis.
- `acceptance_unreachable_under_frozen_config=true` forces constraint relaxation or `user_escalation`.
- `unverifiable_acceptance_contract=true` blocks full target consumption and forces verifier-hook implementation, explicit descope with residual scope, terminal blocker, or user escalation.
- `pass_with_unobserved_axes=true` blocks review pass consumption for the affected measurable goals and forces adapter axis supply, explicit descope with residual scope, terminal blocker, or user escalation.
- generation-dependent `legacy_family_key` or unmapped facet fallback evidence must not support a claim that a blocker family is new. Count, seal, and stall on the effective root family/dominant-parameter key or terminal-outcome family.
- below-policy `marginal_value_per_cycle_cost` must not support another same-gap `goal_productive` repair unless the derive result records a higher value case; preserve descope-with-residual and the next capability rung.
- `oracle_metric_validity_gate.metric_goal_productive_excluded=true` blocks tautological metric/oracle passes from supporting progress.
- `root_cause_unverified_hypotheses` and `root_cause_duplicate_hypotheses` never override terminal/quiescence. Self-asserted actionability without structural fields or provenance is not enough, and rename/version suffix equivalents are not fresh hypotheses.
- `hypothesis_exhausted=true` means the same family has spent the untried repair budget on vacuous attempts; derive must terminal-block or user-escalate unless a supplied input delta changes the family.
- `vacuous_corrective_gate.surface_corrective_noop=true` blocks counting unresolved corrective rows as output delta.
- `partial_progress_axes_gate.status=warn` is advisory only: it recommends decomposing all-or-nothing gates when partial axes exist but high-water remains flat. It must not add a new blocker.
- `structure_metrics_gate.refactor_effect_required=true` with `structure_high_water_moved=false` means a refactor may be useful but cannot be completed as structural goal progress without residual work or explicit descope. File-count growth, mechanical splitting, token avoidance, or producer self-reports must not be treated as an improved structure axis.
- `structure_high_water_key_scope=global_invariant` means per-scope local improvement cannot reset global structure stall or satisfy global structure acceptance unless `global_structure_high_water_moved=true` or equivalent global invariant movement is present.
- `instrumentation_exercise_required=true` means supplied instrumentation has not yet been exercised by a fresh run with non-empty scalar fields. Derive must insert/select the exercise item before dependent measurement/adoption work unless an observability rationale proves the fields are unnecessary.
- `acceptance_encoding_gate.acceptance_diluted=true` means measurable quantifiers or `evidence_kind=live_run` did not survive task encoding. Consumers must return `partial`, preserve the original criterion, and keep residual scope open.
- `verifier_surface_hardening=true` means this cycle is guard/verifier/report-only hardening over the same target artifact without a fresh run id. Count it under the collapsed hardening family and stop adding more guard surfaces once the detection-only cap is reached.
- `run_disposition=candidate_degraded` is preserved quality-miss evidence, not canonical success. It may feed later comparison only for axes that satisfy provenance and source-separation requirements.
- `runtime_config_echo.config_overrides` from `code_default` is self-inflicted-gate evidence when it explains a local execution cap or incompatible default.
- `execution_starvation=true` is a ranking input: prefer execution-producing work over another guard/report/contract task unless safety, authority, or terminal conditions block execution.
- `scenario_uncovered=true` forces validation-set planning or fixture/live-run supply before close.
- `acceptance_inversion=true` forces code/contract repair and keeps the cycle partial even when current tests pass.
- `command_provenance_missing=true` blocks baseline/comparison/reproduction claims from the run.
- repeated `blocker_opacity=true` for the same gate feeds a blocker-contract repair candidate.
- `predetermined_unreachable=true` or `floor_edge_envelope=true` means stochastic contract revision outranks retry.
- `instrumentation_first_fire=true` contributes one evidence credit but must not be double-counted as goal progress or instrumentation-supply consumption.
- `expectation_lineage_stale=true` forces expectation rebaseline or fail-closed task selection before dependent live execution.
- `parity_unverified=true` or unknown parity axes prevent final adoption/baseline/comparison-winner consumption until axis resolution, provisional residual scope, terminal blocker, or user escalation is recorded.
- failed `gating` adoption axes or `measured_but_disqualified=true` prevent adoption of that candidate while preserving it as measured evidence.
- `resolution_downgrade=true` means surrogate evidence cannot satisfy the original high-resolution contract without restoration, contract revision, or residual high-resolution scope; repeated same-contract downgrade should feed derive repair.
- `report_key_divergence=true` blocks pass/close/adoption/baseline/comparison/high-water consumption of the divergent report. Matching duplicate terminal keys do not block consumption but should remain warn-only schema debt.

## A1 Measurement Progress Exemption

When a cycle introduces a new validator, oracle, metric, or first-observed capability frontier, `anti_loop_progress_gate.measurement_progress=true` records workflow instrumentation only. It does not by itself count as goal-productive progress.

The packet must expose `measurement_progress_allowed`, `measurement_streak`, `measurement_progress_streak_for_root_key`, `measurement_streak_cap`, `measurement_check_ids`, `measurement_frontiers_observed`, and `measurement_progress_basis`. If `measurement_progress_allowed=true`, derive may treat a bounded measurement-linked transition as progress only because G-COV and G-SUBSTANCE also passed. If the root-key/root-family streak exceeds the cap, or if G-COV/G-SUBSTANCE fails, the next task must be real implementation/output progress, terminal-blocked, or user-escalated.

Known oracle/check reruns are not new measurement progress. Do not use this exemption for repeated accounting, dashboard, or metadata-only cycles that do not introduce a new check ID or first-observed frontier.

## A2 Blocker Forward-Mutation Ledger

Use `blocker_signature` and `blocker_ladder_rung` to distinguish same-family repetition from capability-ladder movement. `blocker_mutation_kind` values are:

- `repeat`: same blocker signature and no forward rung movement; preserve hard-stop behavior.
- `facet_rename` or `lateral`: changed label/facet without normalized root-family movement; require independent output/input evidence before counting progress.
- `forward_mutation`: normalized root family changed or a recorded capability ladder transition is not merely a facet rename. Treat it as changed blocker-state progress only when strict observed output-delta evidence sets `terminal_outcome_changed=true`; otherwise set `forward_mutation_vacuous=true` and do not reset the family loop counter.

Track `forward_mutation_budget_remaining`. When it reaches zero, set `force_implementation_cycle=true`: the next task must implement the next rung in place, terminal-block with a concrete authority/data blocker, or user-escalate. Do not keep climbing the ladder through governance or measurement-only cycles.

## A2b Root-Cause Hypothesis Ledger

`$audit-cycle-loopback` may append `.task/anti_loop/root_cause_ledger.jsonl` rows keyed by `family_key`, `root_key`, and `hypothesized_root_cause`. The hypothesis slug is domain-owned; the generic workflow evaluates whether it was attempted, whether terminal outcome changed, whether it is actionability-verified, and whether it is distinct from attempted hypotheses by normalized `(hypothesized_root_cause, target_surface, observed_delta_class)`.

When the adapter supplies a collapsed root plus `root_dominant_parameter_key`, distinctness is evaluated on that pair before proximate labels. Renaming prompt/schema/event-edge labels, version suffixes, or target-surface wording does not create a fresh untried hypothesis for the same collapsed root and dominant parameter.

Before terminal blocking or sealing, `$derive-improvement-task` must check the loopback packet or ledger summary. If `untried_actionable_root_cause_exists=true`, `hypothesis_exhausted=false`, and `untried_veto_overridden_by_chain_stall=false`, terminal blocking is invalid. Promote that hypothesis as the next `goal_productive` repair task unless authority, safety, or external state makes it non-actionable and records that rationale. If `hypothesis_exhausted=true` or `untried_veto_overridden_by_chain_stall=true`, do not promote another same-family untried repair without supplied input delta; terminal-block or user-escalate.

## A3 Terminal-Blocked Exit Guard

Before derive writes `terminal_blocked`, check the next unsatisfied capability-ladder rung against authority and local evidence:

- If the next rung uses only local data, needs no new permission, uses provider dependency `none` or `bounded`, stays inside `.agent_goal` scope, and can be implemented through an allowed command-surface class, terminal blocking is not allowed.
- Promote that rung as a `goal_productive` task-pack item or standalone implementation task instead.
- Allow terminal blocking only when no authorized local/bounded rung remains, required input or authority is missing, or safety/GT forbids the implementation path.

## A3b Terminal Quiescence Gate

When loop detection reports `terminal_quiescence_gate.quiescence_required=true`, the orchestrator must not automatically start another domain cycle for the same `root_key`. Record one user-handoff note and skip closeout/dashboard/report/recheck reproduction with `commit_skipped_reason: terminal_quiescence`.

This gate applies only when `has_supplied_input_delta=false` and the same root has reached terminal state at least `terminal_quiescence_threshold` consecutive times, default `2`. Count `untried_root_cause_repair_required` records with no terminal outcome change as same-root no-progress records for the streak. Use `quiescence_untried_reconcile` as the single source of truth for priority: a verified, unexhausted untried hypothesis may override quiescence; exhausted or unverified hypotheses may not.

## A3c Terminal Escalation Gate

When loop detection reports `terminal_escalation_gate.escalation_required=true`, the workflow must promote repeated terminal recheck into `user_escalation`. This gate applies when the same root family has `terminal_blocked`, terminal handoff, or recheck records for at least `terminal_escalation_threshold` consecutive cycles, default `2`, and `has_supplied_input_delta=false`.

The packet must expose `terminal_recheck_streak`, `root_family`, `forced_disposition: user_escalation`, `seal_required: true`, `seal_family_path`, and exactly one `missing_input` object. The missing input kind must be one of `new_input_kind`, `authority_change`, `external_state_change`, or `gate_contract_fix_approval`.

`terminal_blocked` recheck is not progress for this gate. `$derive-improvement-task` must seal the family and emit `selected_task_source: user_escalation` unless a verified unexhausted root-cause repair, supplied input delta, authority change, or external-state change reopens the family.

## A4 Advice-Intake Coherence Gate

At context and loopback stages, check root steering docs such as `task_advice.md`, `skill_advice.md`, and `task_doctor_steering.md`. If a root steering doc is not represented in `.agent_advice/active`, emit a warn-level `orphan_advice_not_intaken` finding and recommend `$manage-external-advice intake`.

This warning does not change the canonical phase order and does not make advice goal truth. It prevents derive from silently ignoring a direction document that has not entered the active non-GT advice channel.

## A5 Command-Surface Carve-Out

When `force_implementation_cycle=true`, command-surface budget pressure must still allow:

- Class B: in-place extension of the canonical entrypoint with non-increasing command count.
- Class C: surface reduction, retirement, or consolidation.

Class A remains blocked while over budget: new `cmd_*`, new versioned wrappers, alternate runners, handoff commands, locators, or family renames. Reinclude `goal_productive` only for Class B implementation work that directly advances the missing primary-output transition, or for Class C when it is the required consolidation path.

## Capability Ladder Router

When `goal_productive` is required and no concrete candidate exists, derive the next task from the next unsatisfied capability in the quality vector:

1. `M0_single_work_full_window`: one work has full-window coverage with source-backed primary output.
2. `M1_same_work_reconstruction_measured`: the same work has measured event reconstruction quality.
3. `M2_three_work`: three distinct works run with `single_work_id` separation preserved and no collapsed cross-work graph.
4. `M3_unseen_10`: ten unseen works run or are terminal-blocked with precise source/authority/provider evidence.
5. `M4_unseen_15`: fifteen unseen works run or are terminal-blocked with precise source/authority/provider evidence.

Promote the first unsatisfied rung as a goal-productive task-pack item only when it can be implemented through an allowed command-surface class and current authority permits the needed provider/runtime behavior. A rung passes by G-COV quality/coverage delta or strict changed-and-semantic output-delta evidence, not by oracle existence alone.

When G-CHAIN reaches the forced-retarget threshold, this ladder is not optional planning context. The loopback packet must expose the first actionable rung as `forced_selected_task` when authority, local data, and bounded/provider prerequisites allow it. `$derive-improvement-task` may terminal/user-escalate only after recording that no ladder rung or self-inflicted gate correction is actionable.

## No-Overclaim Boundaries

These gates must not close implementation issues, promote gold/readiness/rights/ZKP claims, or infer user/human review. They only decide whether the cycle can count as goal-productive progress and which next-task family is allowed.
