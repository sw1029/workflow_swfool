# Execution Context Contract Reaudit

Use this reference when advice or caller packets expose Part M execution-context-transition evidence. These rules are in-place revisions of existing launch, monitor, validation, derivation, schema-contract, and result-contract decisions. Do not create a new canonical phase, detector, report, or repository-specific rule in a generic skill.

## Fields

Preserve these abstract fields when supplied by advice, adapter, run, acceptance, loopback, derive, validation, or result-contract packets:

- `harvest_gate_inventory`, `harvest_gate_unaudited`, `harvest_risk_accepted`, `harvest_contract_preflight`, `harvest_gate_check_id`, `anchor_kind`, `runtime_derived_anchor`, `code_constant_anchor`, `mutable_global_anchor`, `sample_cap_anchor`, `ratio_floor_anchor`, `degradable`, `consumed_reference_cap`, `target_run_scale`, `lane_incompatible`, `scale_incompatible`, `contract_conflict`, `harvest_gate_repair_required`, `harvest_gate_mitigation_required`.
- `execution_cost_scalar`, `execution_cost_threshold`, `high_cost_artifact`, `destructive_disposition_requested`, `destructive_disposition_blocked`, `quarantine_required`, `quarantine_path`, `disposal_proportionality_unchecked`, `failure_check_provenance`, `domain_quality`, `governance_metadata`, `verifier_defect`, `reharvest_path`, `reharvest_available`, `reharvest_command_id`, `reharvest_before_rerun_required`, `rerun_before_reharvest`, `reharvest_terminal_blocked`.
- `validation_predicate_contract`, `producer_directives`, `directive_id`, `directive_class`, `affected_fields`, `predicate_output_requirements`, `mutually_unsatisfiable_contract`, `predicate_revision_required`, `producer_directive_revision_required`, `same_task_contract_repair_required`.
- `closed_world_collection_consumption`, `collection_field`, `truncation_flag_field`, `sample_limit_field`, `partial_flag_field`, `sampled_flag_field`, `truncation_flag_aliases`, `collection_truncated`, `sample_as_universe_misuse`, `full_collection_required`, `sample_consistency_only`.

Keep domain-specific paths, metric names, thresholds, model/backend names, artifact classes, check names, and field aliases in repository adapters or project-owned contracts. Generic skills should only pass opaque ids, booleans, enums, scalar counts, and paths already supplied by the owning repository.

## M1: Harvest Gate Preflight

When `unreachable_within_cycle=true` routes work into a long-run launch, require the launch consume packet to include a preflight of harvest checks that will run at terminal harvest if the repository adapter exposes `harvest_gate_inventory(**ctx)`.

Evaluate only non-degradable checks:

- Anchor durability: expected values must be stable for the run lifetime. A mutable global, current task id, current lane, or monitor-switched context used as the terminal expectation is `lane_incompatible` unless it is launch-manifest-derived.
- Scale compatibility: reference samples, whitelists, and caps consumed as closed-world evidence must cover the target run scale. A cap below the target scale is `scale_incompatible`.
- Producer compatibility: validation floors and required-output predicates must be simultaneously satisfiable with producer directives. If a producer may honestly emit empty or transformed output while the predicate requires universal non-empty or copied output, set `contract_conflict`.

Missing inventory is fail-quiet: record `harvest_gate_unaudited=true` and keep legacy launch behavior. Violations do not permanently block launch, but derive/acceptance must insert repair or mitigation items before launch, or require explicit `harvest_risk_accepted=true` in the packet. Silent risky launch is invalid.

## M2: Cost-Proportional Disposition

At terminal validation or run-disposition time, if a repository adapter exposes `disposal_cost_policy(**ctx)`, compare existing safe cost scalars such as elapsed duration, request count, or cycle-cap multiples against the adapter threshold. If the artifact is high cost and the failure is not a safety-policy violation, destructive deletion or overwrite is invalid; quarantine is the allowed disposition.

Failure autopsy must classify each failed check as `domain_quality`, `governance_metadata`, or `verifier_defect` using the existing Part A provenance path. If `verifier_defect` plus `governance_metadata` form the dominant failure cause and a deterministic `reharvest_path(artifact_family, **ctx)` is available, derive must rank gate repair followed by reharvest of preserved artifacts before any new full rerun. A rerun before terminal-blocked reharvest evidence is `rerun_before_reharvest`.

Missing cost or reharvest hooks are fail-quiet: preserve legacy behavior and record `disposal_proportionality_unchecked` or `reharvest_path.available=false`. If no reharvest path exists, derive should prefer supplying that path before rerun when the preserved material and deterministic post-processing make reharvest plausible. Safety-policy violations keep existing fail-closed disposal.

## M3: Predicate-Directive Satisfiability

When a task creates or changes a validation predicate, floor, inclusion check, required output class, or schema validation rule, close requires pairwise satisfiability against producer directives if an adapter or project contract exposes `producer_directives(**ctx)`. The reverse is also true: when a task changes producer directives, close requires comparison against existing affected predicates.

If the predicate requires output the directive forbids, or the directive allows output that the predicate must fail, set `mutually_unsatisfiable_contract=true`. The same task must revise one side or keep the task partial/blocked with residual scope. Do not defer the contradiction to a later generation while allowing both contracts to coexist as consumable truth.

Missing producer-directive hooks are fail-quiet. The generic skill must not infer domain prompt text, lexical requirements, or thresholds.

## M4: Truncated Collection Consumption

Before any result contract, validator, report consumer, or derivation treats a collection field as a closed-world universe, it must inspect co-resident truncation, sample-limit, partial, or sampled flags. Generic field patterns include `*_truncated`, `*_sample_limit`, `*_partial`, and `*_sampled`; adapters may supply additional names with `truncation_flag_aliases(**ctx)`.

If a truncation/partial/sample flag is true, the collection can only prove consistency of included elements. Membership absence outside the sample cannot be counted as a violation. Closed-world use is `sample_as_universe_misuse` and must fail close for pass/close consumption. If closed-world evidence is required, derive must insert a full untruncated collection supply item before the consuming decision.

If no generic flag or alias exists, fail quiet and keep legacy semantics. Do not scan repository-specific schemas from the generic skill body.

## Consumer Map

- `$manage-external-advice`: preserve Part M fields as abstract in-place revisions during advice normalization.
- `$normalize-acceptance-and-demo`: attach harvest preflight requirements to long-run launch acceptance and preserve producer-directive/predicate satisfiability when acceptance changes validation contracts.
- `$monitor-running-execution`: keep launch, monitor, and harvest linkage explicit; do not let monitor task switching become an unobserved terminal expectation change.
- `$audit-cycle-loopback`: preserve Part M fields, route self-inflicted harvest-gate defects and reharvest-before-rerun ordering, and do not treat sample-as-universe failures as domain quality.
- `$derive-improvement-task`: select repair/mitigation, reharvest, predicate/directive reconciliation, or full-collection supply before rerun or pass consumption when Part M fields require it.
- `$plan-validation-scope`: choose affected-chain or full-chain validation when shared harvest gates, terminal disposition, producer directives, predicates, or closed-world collection consumers change.
- `$manage-schema-contracts`: record producer directives, validation predicates, collection truncation flags, and disposition semantics as compatibility surfaces when they are shared contracts.
- `$validate-subskill-result-contract`: block pass/close consumption of unaudited risky launch, destructive high-cost disposition, mutually unsatisfiable contracts, and sample-as-universe misuse when the source fields are present.
- `$validate-task-completion`: reject completion/progress claims that consume unresolved Part M findings; include dedicated gate rows when fields are present.
