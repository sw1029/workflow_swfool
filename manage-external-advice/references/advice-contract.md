# External Advice Contract

This contract defines `.agent_advice/` artifacts. Advice is direction evidence, not `.agent_goal` goal truth.

## Directory Layout

```text
.agent_advice/
├── raw/
├── active/
├── deferred/
├── applied/
├── rejected/
├── index.jsonl
└── index.md
```

## Normalized Advice Template

```markdown
# External Advice

- advice_id: adv-YYYYMMDD-HHMMSS-slug
- status: active | applied | rejected | deferred
- not_goal_truth: true
- raw_source_path: .agent_advice/raw/YYYYMMDD-HHMMSS-slug.md
- received_at: <ISO-8601>
- normalized_at: <ISO-8601>
- scope: task | design | schema | validation | goal_context | mixed
- priority: low | normal | high
- source_label: <human label>

## Summary

<Short summary of the advice.>

## Extracted Claims

- <Claim with confidence or evidence note.>

## Actionable Directives

- <Directive that can influence task/design/workflow behavior.>

## Measurable Targets

- directive_id: <stable directive id>
  metric: <abstract metric name or adapter-owned target label>
  comparator: <>, <=, >=, ==, contains, exists, or equivalent>
  target: <target value or condition>
  acceptance_text: <acceptance wording to copy into task.md or scope_fidelity>
  residual_policy: <how to preserve remaining scope if narrowed>

## Normalization Fidelity

- fidelity_status: ok | needs_review | degenerate
- fidelity_reason: <why the extraction is trustworthy or not>
- raw_direct_reference_required: true | false
- candidate_line_count: <deterministic extraction count when available>

## Advice Freshness

- advice_metrics_stale: true | false | unknown
- declared_output_fingerprints: []
- current_output_fingerprint: <fingerprint or unknown>
- re_advised_dead_hypothesis: true | false | unknown
- dead_hypothesis_claims: []
- freshness_reason: <why the advice is current, stale, or unknown>

## Conflicts

- <Conflict with user instruction, GT, authority, repo facts, or none.>

## Task Integration

- <How task.md, candidate_task, task-doctor, or derive should use this.>

## Workflow Contract Revisions

- in_place_revisions: []
- additive_new_surfaces: []
- exclusions: []
- count_key_hygiene: <generation-independent count-key rule, or none>
- required_gate_hooks: <acceptance-required gate hooks treated as verifier completeness, or none>
- goal_axis_completeness: <goal-axis mapping/pass completeness rule, or none>
- residual_gap_cost_policy: <value-per-cycle-cost comparison rule, or none>
- failure_autopsy_contract: <last_successful_stage plus scalar diagnostics or diagnostics_unavailable rule, or none>
- failure_surface_count_key: <root + dominant parameter + failure surface stage count-key rule, or none>
- instrumentation_supply_rule: <diagnostics_unavailable streak rule and observability-rationale exception, or none>
- verification_source_separation: <verification_input_paths disjointness/self_grounded rule, or none>
- frozen_envelope_thaw: <envelope_thaw_item requirement and thaw-condition/schedule rule, or none>
- ledger_unchanged_ref_policy: <unchanged_ref path+hash recording rule, or none>
- acceptance_scenario_contract: <scenario premise -> expected state injection rule, or none>
- command_provenance_policy: <full argv recording and redaction rule, or none>
- blocker_actionability_contract: <violated relation, observed values, expected relation/minimum delta requirement, or none>
- stochastic_acceptance_policy: <variance-aware exact-match/floor-edge rule, or none>
- instrumentation_first_fire_credit: <first-fire evidence credit and no-double-counting rule, or none>
- expectation_lineage_contract: <output-derived expectation anchor, designated baseline check, stale-anchor rebaseline/fail-close rule, or none>
- comparison_parity_contract: <parity axes and controlled/measured/unknown classification rule, or none>
- adoption_axis_contract: <gating/tradable axis classification and measured-but-disqualified rule, or none>
- resolution_downgrade_contract: <required versus observed evidence resolution and surrogate downgrade routing rule, or none>
- report_key_integrity_contract: <duplicate terminal key divergence and single-source report rule, or none>
- lane_identity_contract: <production lane/current decision lane binding and stale-lane pass downgrade rule, or none>
- decision_freshness_contract: <fresh current-lane measurement requirement after upstream contract changes, or none>
- gating_axis_producer_contract: <gating-axis starvation and producer-supply-first routing rule, or none>
- portfolio_quota_contract: <verifier-like to producer-like recent-work quota and restriction/warn mode, or none>
- cycle_reachability_contract: <acceptance scale, throughput evidence, unreachable-within-cycle, and long-run routing rule, or none>
- metric_basis_contract: <claimed metric basis versus consumed-input derivability and downgrade rule, or none>
- surface_field_review_contract: <surface field class coverage and scalar defect matrix review rule, or none>

## Design Integration

- <How architecture/schema/theory/governance should use this.>

## Application Gates

- <Evidence required before using the advice in work.>

## Evidence To Mark Applied

- <Task/schema/log/validation/issue evidence that can retire this advice.>

## Exclusions

- <What this advice must not cause.>
```

## Lifecycle Statuses

- `active`: normalized advice that must be considered by supported workflows.
- `applied`: directive was incorporated or made obsolete by a recorded decision with durable evidence.
- `rejected`: advice conflicts with a higher-priority source or is unsafe/unsupported.
- `deferred`: advice is plausible but blocked by missing evidence, user decision, or prerequisite work.

## Index Fields

Record advice in `.agent_advice/index.jsonl` and `$manage-task-state-index`:

- artifact type: `external_advice`
- ID prefix: `adv-*`
- useful fields: `not_goal_truth`, `status`, `raw_source_path`, `scope`, `priority`, `source_label`
- fidelity fields: `fidelity_status`, `fidelity_reason`, `raw_direct_reference_required`
- freshness fields: `advice_metrics_stale`, `declared_output_fingerprints`, `current_output_fingerprint`, `freshness_reason`
- root-cause freshness fields: `re_advised_dead_hypothesis`, `dead_hypothesis_claims`, `root_cause_ledger_path`
- measurable target fields: `directive_id`, `metric`, `comparator`, `target`, `acceptance_text`, `residual_policy`
- workflow revision fields: `in_place_revisions`, `additive_new_surfaces`, `exclusions`, `count_key_hygiene`, `required_gate_hooks`, `goal_axis_completeness`, `residual_gap_cost_policy`, `failure_autopsy_contract`, `failure_surface_count_key`, `instrumentation_supply_rule`, `verification_source_separation`, `frozen_envelope_thaw`, `ledger_unchanged_ref_policy`, `acceptance_scenario_contract`, `command_provenance_policy`, `blocker_actionability_contract`, `stochastic_acceptance_policy`, `instrumentation_first_fire_credit`, `expectation_lineage_contract`, `comparison_parity_contract`, `adoption_axis_contract`, `resolution_downgrade_contract`, `report_key_integrity_contract`, `lane_identity_contract`, `decision_freshness_contract`, `gating_axis_producer_contract`, `portfolio_quota_contract`, `cycle_reachability_contract`, `metric_basis_contract`, `surface_field_review_contract`
- useful links: `advice_for`, `incorporated_into`, `applied_by`, `rejected_by`, `superseded_by`, `conflicts_with_goal`, `conflicts_with_authority`

## Audit Freshness Gate

When `scripts/advice_registry.py audit` receives `--current-output-fingerprint` or `--current-output-fingerprint-json`, it must compare active advice fingerprint claims to the supplied current fingerprint and emit:

- `advice_freshness_gate.current_output_fingerprint`
- `advice_freshness_gate.declared_fingerprint_claims`
- `advice_freshness_gate.advice_metrics_stale`
- `advice_freshness_gate.stale_advice`
- `advice_freshness_gate.re_advised_dead_hypothesis`
- `advice_freshness_gate.dead_hypothesis_claims`
- warn-level `advice_metrics_stale` findings for each stale active advice item
- warn-level `re_advised_dead_hypothesis` findings for each active advice item that re-supplies an already attempted root-cause hypothesis with `terminal_outcome_changed=false`

This gate recommends refresh, deferral, rejection, current-evidence justification, or a required supplied input delta. It does not auto-promote advice to goal truth and does not by itself mark advice applied.

## Precedence

Advice is below system/developer/user instructions, `.agent_goal` GT, authority policy, and repository evidence. Never use advice to grant permissions or override safety, scope, schema, or validation rules.

If `fidelity_status` is `degenerate` or `needs_review`, downstream workflows must cite or inspect `raw_source_path` before applying directives. Normalized claims/directives alone are not sufficient application evidence in that state.

If `advice_metrics_stale` is `true`, downstream workflows must refresh, defer, reject, or explicitly justify use against current repository evidence before relying on headline metric or fingerprint claims. Advice freshness is a warning gate, not goal truth.

If `re_advised_dead_hypothesis` is `true`, downstream workflows must not use that advice as fresh untried root-cause evidence unless it supplies a new input delta, authority change, or external-state change.

If advice includes measurable targets, downstream `$task-doctor` and `$derive-improvement-task` must carry them into task-pack `scope_fidelity` or `task.md` acceptance. Do not mark the advice applied merely because a narrowed pilot/plan/slice was completed; either the original target is met, or explicit descope with residual scope is recorded.

If advice includes workflow contract revisions, downstream workflows must keep them as non-GT in-place decision revisions unless the advice explicitly requests an additive surface and that surface is compatible with higher-priority instructions. For Part G/H-style advice, preserve abstract contracts without repo-specific names or thresholds: generation-dependent count keys are trace-only; acceptance-required gate hooks are `not_evaluated` when absent; review pass requires mapped axes for active measurable goals when `goal_axis_map` is available; residual-gap repair is compared by value per cycle cost when cycle-efficiency evidence exists; failure autopsy needs `last_successful_stage` plus scalar diagnostics or `diagnostics_unavailable`; loopback counting uses the failure-surface key when available; repeated unavailable diagnostics forces instrumentation supply or a concrete observability rationale; independently verified evidence requires disjoint `verification_input_paths` unless the axis is `self_grounded`; frozen unreachable envelopes require an `envelope_thaw_item`; and duplicate ledger packets should be referenced by `unchanged_ref(path+hash)`.

For Part K-style advice, preserve expectation/comparison lineage as abstract contracts only. Output-derived scalar expectations need `expectation_anchor` and current `designated_baseline` comparison before promotion; comparison/adoption tasks need `parity_axes` and `adoption_axis_classification`; `unknown` parity axes keep decisions `parity_unverified`; failed `gating` axes make candidates `measured_but_disqualified`; lower-resolution surrogate evidence is `resolution_downgrade`; and divergent duplicate report keys are `report_key_divergence`. Concrete surface discovery, axis definitions, thresholds, model/backend labels, report schemas, and metric names remain adapter or project-contract owned.

For Part L-style advice, preserve lane lineage and premise-supply contracts as abstract contracts only. Verifier/review/metric passes need lane binding before current-lane consumption; decision updates after upstream production-contract changes need fresh measurement or become `decision_metadata_revision`; starved gating axes route producer supply before verifier-like work; portfolio quota restrictions apply only when an adapter supplies the quota; cycle-unreachable scale targets route long-run launch/monitor/harvest, throughput improvement, descope, terminal blocker, or escalation; metric basis claims must be derivable from consumed inputs; and surface-field review covers adapter-supplied producer-written field classes with scalar defect matrices. Lane-key components, producer path maps, thresholds, units, basis taxonomies, field-class definitions, locators, and excerpt policies remain adapter, authority, or project-contract owned.
