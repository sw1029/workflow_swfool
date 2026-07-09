# Repo-Local Skill Adapters

This reference defines how `$orchestrate-task-cycle` discovers, consumes, schedules, and validates repository-scoped skills under `.codex/skills/`. These adapters are workflow capability evidence for the current repository only; they are not workspace goal truth.

## Contents

- [Core Rule](#core-rule)
- [Adapter Scan](#adapter-scan)
- [Adapter Consumption](#adapter-consumption)
- [Creation Or Update Routing](#creation-or-update-routing)
- [Adapter Validation](#adapter-validation)
- [Gap Analysis And Derive Handoff](#gap-analysis-and-derive-handoff)
- [Failure Handling](#failure-handling)

## Core Rule

Treat repository-scoped domain skills under `.codex/skills/` as optional adapters for domain vocabulary, artifact taxonomy, validation-set planning hints, command profiles, qualitative-review criteria, output-delta interpretation, code convention contracts, structure metrics, verifier-source/provenance contracts, count-key collapse, required gate-hook supply, goal-axis mapping, residual-gap policy/cost comparison, and derive candidate selection.

Adapters must not:

- become `.agent_goal` goal truth;
- grant authority, external/API permission, or human approval;
- bypass `$manage-agent-authority`, `.agent_advice` lifecycle rules, validation-set source-class rules, task-pack rules, result-contract gates, or anti-loop gates;
- prove task completion by themselves;
- patch repository implementation code outside `$task-md-agent-governance`.

## Adapter Scan

During `repo_skill_adapter_scan`, inspect only compact metadata:

- `.codex/skills/<skill-name>/SKILL.md` frontmatter;
- optional `.codex/skills/<skill-name>/adapter.manifest.json`;
- existence of optional `scripts/render_adapter_packet.py`;
- basic active/inactive/invalid status.

Do not load adapter body text, examples, long references, fixtures, or domain maps during the initial scan. Load them only when a phase packet says the detail is relevant.

Record the scan as `repo_skill_adapter_packet` with adapter ID/path/status, metadata summary, renderer availability, non-GT warning, and validation status when known.

## Adapter Consumption

Prefer deterministic phase packets:

```bash
python3 .codex/skills/<skill-name>/scripts/render_adapter_packet.py --phase <phase>
```

Use a rendered packet only for the phase it names. If no renderer exists, assemble a compact manual packet from metadata and safe summaries.

Adapters may inform these phases when applicable:

- `validation_set_plan`
- `governance`
- `run`
- `qualitative_review`
- `loopback_audit`
- `validation_set_build`
- `schema_pre_derive`
- `derive`
- `schema_post_derive`
- `validate`

Adapters may expose `code_convention_contract` as compact data. Keep project-specific naming rules, max LOC/depth/fan-out values, kernel/reuse roots, dependency DAGs, forbidden patterns, and semantic module placement rules inside the repo-owned adapter or `.agent_goal/conventions.md`; generic workflow skills consume only the contract shape and status.

Loopback and validation adapters may expose Part F hooks as compact data:

- `verifier_source_paths(gate, **context)`: map an abstract gate/verifier key to repository-owned verifier source paths. If the current change set touches a mapped verifier source, the affected pass is `pass_with_coupled_verifier` and is not consumable as a pass until a later non-coupled run or independent recalculation.
- `evidence_provenance(metric, **context)`: label each metric or improved field as `independently_verified` or `producer_attested`. Missing per-field provenance is producer-attested when the hook is present; if the hook is absent, keep legacy accounting.
- `residual_gap_policy(target, **context)`: provide abstract residual-gap comparison inputs such as ratio, threshold, and basis. Keep thresholds and metric definitions inside the adapter; generic workflow skills only consume `marginal_repair`, explicit descope, and next-rung hints.
- `primary_metric(**context)`: optionally provide the adapter-owned high-water metric used by C4/D4 chain-stall routing. If its movement is producer-attested only, it cannot reset stalls.

Loopback, review, normalization, and validation adapters may expose Part G fields as compact data:

- `facet_root_map(...)` plus dominant-parameter evidence: collapse labels, target surfaces, or generated names to generation-independent root families. Raw task/advice/pack/cycle/run/date/hash/version strings stay trace-only; unmapped facets should merge by terminal outcome rather than mint a new family.
- Required gate-hook status: expose whether SKILL.md-required adapter hooks for an acceptance-referenced gate are supplied and evaluated. Missing, unloaded, fail-quiet, or `not_evaluated` hooks become `unverifiable_acceptance_contract` for that target.
- `goal_axis_map(targets, quality_vector, **context)`: map active measurable goals to adapter-owned quality/vector axes. The generic workflow checks only whether each active goal has at least one mapped axis; axis definitions and calculations remain adapter-owned.
- Residual cost comparison fields: expose `cycle_fixed_cost`, `marginal_gap_value`, `marginal_value_per_cycle_cost`, alternative value/cost fields, and below-policy status when available. If the adapter/profile does not provide cost evidence, downstream consumers use denominator `1`.

Loopback, run, normalization, and validation adapters may expose Part H fields as compact data:

- `execution_stage_ladder(**context)` and optional `terminal_classification_stage_map`: ordered execution stages and allowed failure stages for terminal classifications. The generic workflow derives `failure_surface_stage` from `last_successful_stage`; stage naming and mapping remain adapter-owned.
- `instrumentation_trigger_threshold(**context)`: threshold for repeated `diagnostics_unavailable` before instrumentation supply is forced. If absent, downstream consumers use default `2`.
- Verification source separation metadata: `verification_input_paths`, `verified_artifact_paths`, and `self_grounded` axes for `independently_verified` fields. Missing or overlapping source paths downgrade the field to attested.
- Frozen-envelope thaw metadata: `frozen_envelope`, `deficit_axis`, `envelope_thaw_item`, thaw condition/schedule, or a declaration that `envelope_thaw_item_required=true`.

Loopback, run, normalization, validation, and profile adapters may expose Part I fields as compact data:

- `instrumentation_field_map(...)`: abstract supplied instrumentation fields plus each field's non-empty/minimum-record condition. Domain field names and thresholds remain adapter-owned. If absent, instrumentation exercise rules fail quiet unless `item_kind=instrumentation_supply` or caller evidence explicitly requires them.
- Acceptance encoding metadata: `acceptance.quantifiers`, `evidence_kind: live_run|derived_artifact|code_contract|report_only`, `item_created_at`, and `required_new_run_id` when a directive requires post-item live execution. If extraction is uncertain, preserve the original measurable clause as a quoted packet field rather than paraphrasing it.
- Guard-stacking metadata: `verifier_source_paths(...)` plus changed-file classification, `target_artifact_paths`, and `change_set_kind` sufficient to identify verifier/guard/report-only hardening over the same artifact target. Missing hooks fail quiet to existing family counting.
- `run_disposition(safety_violations, quality_vector, **context) -> failed_closed|candidate_degraded|candidate_written`: separate safety violations from quality misses. Safety contracts and quality axes remain adapter-owned; missing classification scalars should emit `disposition_unclassified` as warning evidence when the hook exists.
- `runtime_config_echo(**context) -> dict`: safe scalar/enum effective runtime settings, each with `config_origin: cli|config_file|code_default|backend_default` and derived `config_overrides`. Do not include raw prompts, bodies, credentials, secrets, or provider payloads.
- `execution_starvation` evidence: pack/recent-cycle run-id counts such as `recent_cycle_run_id_count` and `execution_starvation_window`. The default window is workflow-owned; project-specific adjustment belongs in adapter/config.

Loopback, run, normalization, validation, and report-profile adapters may expose Part K fields as compact data:

- `designated_baseline(**context) -> dict`: current designated output surface id/path/version and whether a supplied `expectation_anchor` is superseded. The adapter owns the output-surface taxonomy; global workflow skills only preserve ids and stale/missing status.
- `comparison_parity_axes(**context) -> list|dict`: required parity axes for baseline, comparison, ranking, or adoption work, with each status limited to `controlled`, `measured`, or `unknown`. Axis definitions, thresholds, and domain-specific measurements stay adapter-owned.
- `required_output_classes(**context) -> list|dict`: adoption classes or axes that are gating rather than tradable. Missing classification makes majority/aggregate adoption provisional rather than final.
- `resolution_downgrade_fields(**context) -> list|dict`: required versus observed evidence-resolution classes and any `surrogate_resolution_basis`. The adapter may identify id/set/intersection/row-level requirements, but the generic workflow only consumes abstract resolution labels.
- `report_key_integrity_fields(**context) -> list|dict`: duplicate terminal report-key paths and scalar values when a single report contains divergent duplicates. Matching duplicate keys are schema debt; divergent values block pass/close/adoption/baseline/comparison consumption.

Loopback, run, normalization, validation, review, derive, and profile adapters may expose Part L fields as compact data:

- `production_lane_identity(artifact_paths, **context) -> dict`: opaque lane identity for artifacts being validated or reviewed. The adapter owns the lane key components; generic workflow skills compare only opaque key equality.
- `current_decision_lane(**context) -> dict`: opaque lane identity for the artifact/output lane currently under capability, adoption, baseline, comparison, or next-rung decision.
- Decision freshness metadata: `upstream_contract_changed_since_measurement`, `measurement_run_id`, `measurement_artifact_created_at`, `required_new_run_id`, and `decision_metadata_revision` when decision/adoption/reclassification work may otherwise reuse stale artifacts.
- `gating_axis_producer_map(**context) -> dict`: gating axis id to producer source paths or globs. The workflow consumes only path-presence/execution status and `axis_starved_by_missing_producer`; axis meaning stays adapter-owned.
- `portfolio_quota(**context) -> dict`: recent-window size, verifier/guard/report/metadata versus producer/envelope/long-run classification, threshold ratio, and whether the quota is restrict or warn-only. Missing hooks use default warn-only evidence.
- `throughput_evidence(**context) -> dict`: observed cycle throughput, unit, run id, and confidence interval. `acceptance_scale(target, **context) -> dict`: required target scale and matching unit. Together they support `unreachable_within_cycle`.
- `metric_basis_inputs(metric_id, **context) -> dict`: claimed basis class, consumed input classes, derivability, and downgraded actual basis class for metric provenance overclaim checks.
- `surface_field_classes(artifact_family, **context) -> dict`: producer-written surface string field classes and locator interpretation rules for qualitative review. Review results should report scalar field-class by defect-class counts and avoid excerpts unless authority permits them.

These hooks are optional and fail quiet when absent unless a measurable acceptance or caller contract explicitly requires them. When present, they revise existing pass/progress/repair/counting semantics; they do not authorize new phases, reports, automatic retries, or repo-specific rules in global workflow skills.

If a repository also registers a loopback domain adapter, pass its declared path/status to `$audit-cycle-loopback`. A registered adapter that does not load is an `adapter_wiring_defect` or adapter load correction task, not evidence that no adapter exists. Keep this distinction in `repo_skill_gap_packet` so `$derive-improvement-task` does not schedule duplicate adapter creation.

Keep adapter-loaded references one level deep inside the adapter skill. Detailed domain maps, validation policies, command profiles, and examples belong in `references/`. Deterministic packet renderers, lint checks, or fixture-safe checks belong in `scripts/`.

## Creation Or Update Routing

Create or update repo-local adapters only through a separate active `task.md` selected by `$derive-improvement-task`. The next task must route implementation through `$task-md-agent-governance`, invoke `$skill-creator`, and place files under `.codex/skills/<skill-name>/` unless the user explicitly requests a global skill location.

Do not opportunistically edit `.codex/skills/` during a normal cycle. A derive result may only schedule adapter work by writing the next `task.md`, retained candidate, or task-pack item.

Use `$skill-creator` rules for adapter tasks:

- keep `SKILL.md` concise;
- split detailed reusable knowledge into first-level `references/`;
- add `scripts/` only for deterministic repeated or fragile operations;
- use `assets/` only for files used in produced outputs;
- avoid README, changelog, quick-reference, installation-guide, or process-history files;
- refresh `agents/openai.yaml` when UI discovery matters;
- validate with `quick_validate.py` when available;
- run adapter-local lint or a minimal forward-test when the adapter can affect future routing.

## Adapter Validation

Adapter registration, repository-root import, or a passing adapter unit test does not prove wiring. The project contract lists only opaque `required_consumer_ids`; each actual consumer loader must probe from its own working directory, module-loading mechanism, and environment and return a row with `consumer_context_id`, `adapter_loaded`, `required_hook_callable`, `hook_signature_compatible`, `return_contract_valid`, and `probe_evidence_id`. Store these rows in the existing consumer packet as `consumer_context_conformance`.

`consumer_context_ready` is not an adapter self-hook. Hook-name strings, metric labels, filenames, and packet claims are not probe evidence. If an acceptance-required consumer row is missing or fails, that consumer's dependent hook is `not_evaluated`, not pass.

When `.codex/skills/` changed in the current task, run `repo_skill_adapter_validate` before treating the adapter as consumable in later cycles.

Validation must check:

- folder/name alignment and lowercase hyphenated skill name;
- `SKILL.md` frontmatter has only `name` and `description`;
- concise `SKILL.md` body and progressive-disclosure links;
- no extraneous auxiliary documentation files;
- one-level `references/` organization;
- deterministic script executability or representative script execution when scripts were added;
- `agents/openai.yaml` consistency when present;
- `$skill-creator` `quick_validate.py` result when available;
- forward-test evidence or a recorded reason it was unsafe, unavailable, or unnecessary.

Treat validation failures as validation/derive blockers. The orchestrator must not patch the adapter directly; route correction through a selected task and `$task-md-agent-governance`.

## Gap Analysis And Derive Handoff

Build `repo_skill_gap_packet` before derivation when current-cycle evidence shows reusable friction:

- repeated domain lookup;
- repeated command/profile discovery;
- repeated validation/oracle/source-class ambiguity;
- repeated progress-classification uncertainty;
- repeated measurable acceptance with no live verifier mapping or required verifier stuck at `not_evaluated`;
- repeated coupled-verifier passes where the task changed a mapped verifier source and then consumed its pass;
- repeated producer-attested metric movement with no independently verified high-water movement;
- repeated below-threshold residual-gap repair where explicit descope plus a next capability rung was not considered;
- repeated count-key churn where task/advice/pack/cycle/run/date/hash/version labels reset same-family counters or seals;
- repeated acceptance-required gate hooks that remain absent, fail-quiet, or `not_evaluated`;
- repeated qualitative-review pass with zero mapped axes for active measurable goals;
- repeated below-policy residual value per cycle cost where cycle-efficiency evidence exists but derive keeps selecting same-gap repair;
- repeated failure autopsies that lack stage ladder, `last_successful_stage`, `failure_surface_stage`, or scalar diagnostics while failures remain opaque;
- repeated terminal-classification/failure-stage contradictions or same-input contract mismatches that prevent counting/close;
- repeated `diagnostics_unavailable` on the same failure surface where no instrumentation supply task has been scheduled;
- repeated independent-verification claims without disjoint verification input paths or adapter `self_grounded` axes;
- repeated frozen-envelope unreachable acceptance without a reserved `envelope_thaw_item` or thaw schedule;
- missing or stale `code_convention_contract` when governance, code-structure audit, loopback, derive, or validation repeatedly needs repo-specific naming, reuse, dependency, depth, fan-out, or structure high-water rules;
- repeated mechanical shard, duplicate-helper, global-rebinding, dependency-direction, or reuse-layer ambiguity that generic workflow checks can only report warn-only;
- repeated local-scope structure improvement that does not move adapter-owned global invariants;
- repeated verifier pass, adoption, comparison, or next-rung claim where the validated artifact lane does not match the current decision lane;
- repeated decision-update work that reclassifies stale artifacts after an upstream production contract changed instead of producing a fresh measurement run;
- repeated zero or failed gating axis where the producer path that should populate that axis is missing or unexercised;
- repeated over-quota verifier/guard/report/metadata work compared with producer/envelope/long-run work;
- repeated cycle-unreachable scale targets where long-run launch/monitor/harvest routing, throughput improvement, explicit descope, terminal blocker, or escalation is not selected;
- repeated metric basis overclaim where the claimed evidence class is not derivable from consumed inputs;
- repeated qualitative review pass that checks only a subset of producer-written surface string field classes while locator-backed field classes are available;
- adapter validation failure;
- task_miss caused by missing repo-specific procedure;
- a known 2-5 task sequence that would otherwise reload long domain context.

The packet should include recommended adapter name, scope, target path, expected resources (`references`, `scripts`, `assets`), future consuming phases, and whether derive should create, update, defer, or reject adapter work.

For convention, Part F, Part G, Part H, Part I, Part K, and Part L adapter gaps, include the missing contract fields abstractly, such as `reuse_roots`, `semantic_naming_rules`, `dependency_layers`, `max_tree_depth`, `max_dir_fan_out`, `max_file_loc`, `forbidden_name_patterns`, `structure_metrics`, `global_invariants`, `target_required_verifier`, `high_water_axes`, `verifier_source_paths`, `evidence_provenance`, `verification_input_paths`, `self_grounded`, `primary_metric`, `residual_gap_policy`, `facet_root_map`, `root_dominant_parameter_key`, `execution_stage_ladder`, `terminal_classification_stage_map`, `instrumentation_trigger_threshold`, `instrumentation_field_map`, `run_disposition`, `runtime_config_echo`, `envelope_thaw_item`, required gate-hook status, `goal_axis_map`, `quality_vector` axes, `cycle_fixed_cost`, `marginal_value_per_cycle_cost`, `execution_starvation` ranking fields, `designated_baseline`, `comparison_parity_axes`, `required_output_classes`, `resolution_downgrade_fields`, `report_key_integrity_fields`, `production_lane_identity`, `current_decision_lane`, `gating_axis_producer_map`, `portfolio_quota`, `throughput_evidence`, `acceptance_scale`, `metric_basis_inputs`, and `surface_field_classes`. Do not put project-specific values into the generic orchestrator skill.

Promote an adapter task only when reusable value is concrete. For one-off instructions, use `.agent_advice`, task acceptance criteria, or normal schema/contract notes instead.

Adapter work is usually `governance_only`. Treat it as goal-productive only when it directly unlocks a blocked validation/run/review/derive state or creates a validated deterministic packet/check tied to a current blocker.

If `$derive-improvement-task` selects adapter work, the selected task must name:

- adapter purpose and scope;
- proposed skill name;
- target path `.codex/skills/<skill-name>/`;
- expected resources;
- validation commands;
- future phases that will consume compact packets.

## Failure Handling

If adapter scan fails, record the invalid adapter path/status and continue without consuming it unless the active task requires adapter work.

If adapter validation fails, preserve the adapter files and logs, mark the adapter as not consumable for future routing, and derive a correction task or blocker.

If adapter packet rendering fails, fall back to metadata-only manual packets when safe. Otherwise mark the adapter phase packet as blocked and keep downstream decisions conservative.

If an adapter conflicts with `.agent_goal`, authority, active advice lifecycle, validation-set source-class rules, task-pack rules, or result-contract gates, ignore or reject the adapter packet for that phase and record the reason.
