# Repo-Local Skill Adapters

This reference defines how `$orchestrate-task-cycle` discovers, consumes, schedules, and validates repository-scoped skills under `.codex/skills/`. These adapters are workflow capability evidence for the current repository only; they are not workspace goal truth.

## Contents

- [Core Rule](#core-rule)
- [Adapter Scan](#adapter-scan)
- [Manifest v3 closure](#manifest-v3-closure)
- [Adapter Consumption](#adapter-consumption)
- [Creation Or Update Routing](#creation-or-update-routing)
- [Adapter Validation](#adapter-validation)
- [Adapter Architecture Audit](#adapter-architecture-audit)
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
- define a new canonical workflow mode or phase, self-activate a privileged mode profile, or widen a tracked mode profile's capture, consumption, reaction, or repair capability.

## Adapter Scan

During `repo_skill_adapter_scan`, inspect only compact metadata and contract bindings:

- `.codex/skills/<skill-name>/SKILL.md` frontmatter;
- optional `.codex/skills/<skill-name>/adapter.manifest.json`;
- existence of optional `scripts/render_adapter_packet.py`;
- manifest-v3 component/runtime-closure, hook-contract, and code-convention bindings;
- basic active/inactive/invalid status.

Use the deterministic scanner when callable adapters are registered:

```bash
python3 -m orchestrate_task_cycle repo-adapter scan \
  --root . --cycle-id <cycle-id> --output <cycle-packet-path>
```

Do not load adapter body text, examples, long references, fixtures, or domain maps during the initial scan. Load them only when a phase packet says the detail is relevant.

Record the scan as `repo_skill_adapter_packet`. Require and hash the callable wrapper for a callable registration. Preserve and hash a legacy delegate or deterministic renderer only when the repository declares one; neither migration compatibility nor a renderer is a universal adapter requirement. Validate every phase-consumer and phase-hook value as a unique string list whose members exist in the corresponding closed registry. Bind the present components plus both phase maps as one `adapter_revision_sha256`. Do not record source bodies, credentials, prompts, or corpus metadata.

## Manifest v3 closure

Prefer manifest format v3 for a callable adapter. Version 3 closes the complete adapter
revision and executable local dependency surface rather than hashing only a façade:

- `components` is a closed registry. Every row owns a unique component ID and safe regular
  path, kind, semantic role, required/revision/runtime/audit booleans, and declared
  dependency IDs. Unknown dependencies, duplicate IDs/paths, unsafe files, or a component
  dependency cycle block static validation.
- `runtime_closure` names entry component IDs, separately declared dynamic dependency
  IDs, and `unresolved_local_import_policy: block`. The scanner recursively follows
  declared dependencies and statically resolvable local Python imports. A local import
  not listed as a component is still auto-bound by path/digest as discovered transitive
  closure; it is never silently omitted from the adapter revision.
- The closure records component and discovered-transitive digests, local import edges,
  external distribution versions, dynamic-import call count, and interpreter ABI-bound
  revision material. Runtime-marked components must be reachable. A dynamic import call
  without declared dynamic dependencies or an unsafe/unreadable resolved local import
  fails closed; the manifest must explicitly declare its unresolved-local policy.
- `hook_contract_path` binds a closed typed registry. Each hook names input/output schema
  IDs, phases, consumers, side-effect class, owner component/symbol, fail policy, and
  optional test components. The hook registry must exactly agree with manifest phase
  maps and all owner/test component IDs must resolve.
- `code_convention_contract_path` binds repository-owned module roles, dependency DAG,
  size limits, forbidden effects or names, reuse/pattern guidance, and staged rollout
  policy when supplied by that contract.

The scanner derives `component_registry_sha256`, `runtime_closure_sha256`, and one
`adapter_revision_sha256` over the manifest, all revision-included component bytes,
closure, hook/convention contracts, phase maps, algorithm revision, and interpreter ABI.
The handoff reopens the manifest, every component, discovered transitive closure, and
both contracts and recompiles the row; any drift returns `registered_unavailable` with
bounded stale-component fields. Do not substitute the façade digest for this revision.

Manifest v2 remains readable as explicit `legacy_partial`. It has no closed component or
runtime-closure proof and must not be described as v3-complete. Compatibility is a
migration state, not a scanner pass upgraded by inference.

## Adapter Consumption

Prefer deterministic phase packets:

```bash
python3 .codex/skills/<skill-name>/scripts/render_adapter_packet.py --phase <phase>
```

Use a rendered packet only for the phase it names. If no renderer exists, assemble a compact manual packet from metadata and safe summaries.

An adapter may declare typed hook signatures, phase-scoped consumer probes, or a requested tracked mode-profile ID. For manifest v3, consume only a fresh handoff carrying the exact component registry, recursive runtime closure, hook/convention bindings, and adapter revision from the scan. The coordinator resolves a mode-profile request through the global registry and independent activation provenance. An ignored repo-local override may only disable capture, lower consumption/reaction authority, remove repairs, or add probes; adapter observations and packets are never activation sources.

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

- `quality_delta_policy(**context)`: return `{"keys": [<canonical metric ids>], "aliases": {<canonical id>: [<accepted source-field ids>]}}`. Only listed keys participate in G-COV/high-water updates. Missing or malformed policy leaves G-COV `not_evaluated`; it never activates repository-independent metric defaults.
- `gt_constraint_policy(**context)`: optionally return `action_specs` plus a `generalization` object. The generalization object owns scope regexes, single-unit regexes, behavior field paths for selected/target counts, unit IDs, flags and streaks, and an optional reason/action ID. Pass the normalized result to `python3 -m orchestrate_task_cycle gt-conflict --policy-json`; missing policy disables domain-unit/generalization inference while generic provider/credential conflicts remain available.
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

Resolve the registered adapter for each consumer before invocation:

```bash
python3 -m orchestrate_task_cycle repo-adapter handoff \
  --root . --scan-json <scan-packet> \
  --phase loopback_audit --consumer-id audit-cycle-loopback
```

Pass the scan packet to loopback with `--adapter-scan-json`; loopback must load the returned explicit wrapper path. Pass the corresponding derive adapter decision context to derive. Never rediscover `.task/domain_adapter.py` implicitly after a tracked wrapper was registered.

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

Adapter registration, repository-root import, or a passing adapter unit test does not prove wiring. Keep static validation, load preflight, and post-use decision receipts separate. Propagate the ready scan's phase consumer set and available-hook registry without rediscovery; availability alone is not decision demand. Bind load preflight to the adapter and consumer revisions plus the complete active required-hook set, defined by decision use or an independent `acceptance_required` declaration. Count a hook as consumed only after the consumer validates its return contract, accepts the semantic result, and records actual decision use. Optional uninvoked or `fail_quiet`/`not_evaluated` hooks do not create a global wiring defect; acceptance-required failures block the dependent decision. Bind post-use receipts to cycle, task, attempt, artifact, body, lane, input-state, adapter revision, and consumed hook-result hashes.

Preserve legacy single-hook receipts only when no explicit manifest/consumer/decision required set exists. Otherwise the external consumer receipt must echo the current `task_id`, exact adapter and consumer revisions, registered validator signature, expected `hook_id`, `required_hook_ids`, and `required_gate_ids`; it also carries closed per-invocation rows for hook ID, ordered invocation index, input/output digests, callable-signature digest, execution status, return-contract validity, semantic status, and decision-use status. Only completed, contract-valid, semantically accepted, decision-used required hook I/O may enter `consumed_hook_ids`, and consumed hooks must equal the required hook set, while disjoint `consumed_gate_ids` and `excluded_gate_ids` exactly cover the required gate set. Version, validator, hook-I/O rows, all five arrays, and `result_contract_status` belong to the canonical receipt hash basis. An excluded required gate, including an artifact-incompatible gate, is `not_evaluated` and cannot disappear from the required set to manufacture pass. A stale task/revision replay, rehashed boolean-only row, missing or extra member, duplicate ID, overlap, contract conflict, or coverage change without a new digest also remains `not_evaluated`.

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

## Adapter Architecture Audit

For a manifest-v3 adapter, audit architecture through three explicitly separated layers:

1. **Deterministic facts.** Compile a content-bound, raw-source-free fact packet from all
   audit-scoped components plus discovered transitive Python modules. Record module LOC
   and import-time effect kinds; symbols/signatures; import graph, SCCs, cycles, and
   condensation layers; call graph and dynamic calls; normalized-AST clone groups;
   inheritance bases, protocol/abstract markers, and overrides; hook owner/test mapping;
   repository dependency-DAG violations; and changed-path structural pressures.
2. **Semantic receipt.** When judgment is required, let a bounded semantic owner distill
   component responsibilities, recursively nested meaning-based module boundaries,
   cohesion/leakage observations, compatibility risks, and design observations. Every
   finding must cite existing deterministic fact IDs. Optional design-pattern assessment
   must state the problem force, benefit, risk, and simpler alternative. The receipt may
   not contain raw source, prompts, status/severity fields, authority, or completion
   claims.
3. **Deterministic adjudication.** Reopen the exact fact, convention, and semantic
   bindings and derive separate `adapter_consumability_status` and
   `adapter_architecture_status`. Unsafe/unreadable sources, unresolved hook owners, or
   forbidden import-time effects block consumability. Structural pressure alone is not
   a semantic defect; under strict repo policy it becomes `refactor_required` only when
   an actionable deterministic fact is corroborated by the semantic receipt. Missing
   convention or semantic receipt produces conservative `not_evaluated` architecture,
   not a fabricated pass and not a consumability block absent deterministic blockers.

Inheritance and design-pattern review are conditional: audit existing inheritance when
present and assess a pattern only against a demonstrated problem force. Absence of
inheritance or a named pattern is never a defect. Nested modules are allowed when their
distilled responsibilities, dependency direction, and compatibility constraints justify
them; depth or file count alone is not modularity.

Apply repo-owned rollout policy. A common migration mode enforces changed code while
grandfathering unchanged legacy pressure only below an exact per-axis high-water mark.
Do not reset high-water debt, convert unchanged debt to pass, or let a semantic receipt
set final severity.

Cache only by an exact fingerprint over before/after adapter revision material,
component registry, runtime closure, hook/convention contracts, analyzer/adjudicator and
semantic schema revisions, policy revision, and parser/runtime versions. A cached
semantic receipt must reopen and validate against the current fact IDs. Any mismatch is
a cache miss, never reusable judgment.

Emit integrity-bound native envelopes for `repo_skill_adapter_validate` and
`code_structure_audit`. Stage normalization may remove an envelope only after checking
its closed fields, cycle scope, internal digest, and field origins. Preserve raw fact and
semantic artifacts by ref/digest; do not flatten semantic judgments into deterministic
origins or persist source bodies.

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

If adapter scan fails, record the invalid adapter path/status and continue without consuming it unless the active task requires adapter work. For manifest v3, component, transitive-import, hook/convention, or revision drift is a wiring defect; never fall back to the stale façade or implicit legacy adapter.

If adapter validation fails, preserve the adapter files and logs, mark the adapter as not consumable for future routing, and derive a correction task or blocker.

If adapter packet rendering fails, fall back to metadata-only manual packets when safe. Otherwise mark the adapter phase packet as blocked and keep downstream decisions conservative.

If an adapter conflicts with `.agent_goal`, authority, active advice lifecycle, validation-set source-class rules, task-pack rules, or result-contract gates, ignore or reject the adapter packet for that phase and record the reason.
