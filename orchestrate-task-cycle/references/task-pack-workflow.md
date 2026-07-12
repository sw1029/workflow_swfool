# Task Pack Workflow

This reference defines optional long-range task packs for `$orchestrate-task-cycle`. Task packs are workflow planning state, not `.agent_goal` goal truth.

## Contents

- [Core Invariant](#core-invariant)
- [Artifacts](#artifacts)
- [JSON Shape](#json-shape)
- [Progress Classification](#progress-classification)
- [Scope Fidelity](#scope-fidelity)
- [Pack Transactions](#pack-transactions)
- [Replacement Transaction](#replacement-transaction)
- [Promotion](#promotion)
- [Loop Breaker Fields](#loop-breaker-fields)
- [Part G Workflow Gates](#part-g-workflow-gates)
- [Part H Workflow Gates](#part-h-workflow-gates)
- [Part I Workflow Gates](#part-i-workflow-gates)
- [Part J Workflow Gates](#part-j-workflow-gates)
- [Part K Workflow Gates](#part-k-workflow-gates)
- [Part L Workflow Gates](#part-l-workflow-gates)

## Core Invariant

Keep one canonical active `task.md`. A task pack may contain a sequence of planned items, but each cycle consumes at most one item by promoting it into `task.md`.

Use a task pack only when a single next task is too myopic and a known ordered sequence is needed to avoid repeated narrowing, handoff, or blocker cycles.

## Artifacts

Canonical queue:

```text
.task/task_pack/pack-<timestamp>-<slug>.json
```

User-language render:

```text
.task/task_pack/pack-<timestamp>-<slug>.md
```

The JSON is authoritative. The Markdown render is for scanability and must use the user's requested reporting language when known.
`pack_id` is one path-safe token, the JSON filename must equal `<pack_id>.json`, and every CLI-supplied pack path must resolve under `.task/task_pack` without parent or symlink escape.

## JSON Shape

```json
{
  "schema_version": 1,
  "pack_id": "pack-YYYYMMDD-HHMMSS-slug",
  "status": "active",
  "language": "ko",
  "goal": "Long-range task goal.",
  "current_item_id": "item-001",
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601",
  "items": [
    {
      "item_id": "item-001",
      "order": 1,
      "status": "planned",
      "title": "Promotable task title",
      "objective": "One concrete task objective.",
      "acceptance": ["Observable condition"],
      "validation_profile": "current_only",
      "progress_target": "advanced",
      "dependencies": [],
      "source_evidence": [],
      "blocker_signature_expected": "taxonomy|issue|surface|missing_input",
      "semantic_signature_expected": "stable-goal-axis-family",
      "progress_kind_expected": "goal_productive",
      "item_kind": "implementation",
      "effective_count_key_expected": "adapter-root|dominant-parameter",
      "count_key_hygiene": {
        "generation_dependent_count_key": false,
        "trace_only_keys": []
      },
      "goal_axis_contract": {
        "goal_axis_map_status": "not_supplied",
        "active_goal_axes": [],
        "quality_vector_axes": [],
        "unobserved_goal_axes": [],
        "pass_with_unobserved_axes": false
      },
      "failure_surface_contract": {
        "effective_count_key_expected": "adapter-root|dominant-parameter|failure-surface-stage",
        "terminal_classification_invalid_for_counting": false,
        "same_input_contract_required": false
      },
      "diagnostics_contract": {
        "diagnostics_unavailable": false,
        "instrumentation_supply_required": false,
        "existing_diagnostics_sufficient": false,
        "instrumentation_exercise_required": false,
        "instrumentation_exercise_item_id": null,
        "instrumentation_exercised": false,
        "instrumentation_field_map": {},
        "derived_from_existing_artifacts": false
      },
      "acceptance_encoding": {
        "quantifiers": [],
        "evidence_kind": "live_run",
        "item_created_at": "ISO-8601",
        "required_new_run_id": true
      },
      "acceptance_scenarios": [],
      "command_provenance_contract": {
        "command_argv_required": false,
        "command_provenance_missing": false
      },
      "blocker_actionability_contract": {
        "blocker_opacity": false,
        "violated_relation_required": false
      },
      "stochastic_feasibility_contract": {
        "outcome_variance": null,
        "predetermined_unreachable": false,
        "floor_edge_envelope": false
      },
      "instrumentation_first_fire_contract": {
        "instrumentation_first_fire": false,
        "first_fire_consumed_item_id": null
      },
      "expectation_lineage_contract": {
        "expectation_anchor": null,
        "designated_baseline": null,
        "expectation_anchor_missing": false,
        "expectation_lineage_stale": false
      },
      "comparison_parity_contract": {
        "comparison_contract": false,
        "parity_axes": [],
        "parity_axis_status": {},
        "parity_unverified": false
      },
      "adoption_axis_contract": {
        "required_output_classes": [],
        "adoption_axis_classification": {},
        "majority_vote_adoption": false,
        "provisional_adoption": false,
        "measured_but_disqualified": false
      },
      "resolution_downgrade_contract": {
        "required_evidence_resolution": null,
        "observed_evidence_resolution": null,
        "resolution_downgrade": false,
        "surrogate_resolution_basis": null
      },
      "report_key_integrity_contract": {
        "report_key_divergence": false,
        "duplicate_key_paths": []
      },
      "lane_identity_contract": {
        "production_lane_identity": null,
        "current_decision_lane": null,
        "lane_identity_missing": false,
        "pass_on_stale_lane": false,
        "current_lane_residual_required": false
      },
      "decision_freshness_contract": {
        "upstream_contract_changed_since_measurement": false,
        "measurement_run_id": null,
        "required_new_run_id": false,
        "stale_measurement_artifact": false,
        "decision_metadata_revision": false
      },
      "gating_axis_producer_contract": {
        "axis_starved_by_missing_producer": false,
        "gating_axis_id": null,
        "producer_supply_required": false,
        "producer_path_status": "not_evaluated"
      },
      "portfolio_quota_contract": {
        "portfolio_quota_exceeded": false,
        "portfolio_quota_mode": "warn",
        "recent_verifier_like_count": null,
        "recent_producer_like_count": null
      },
      "cycle_reachability_contract": {
        "acceptance_scale": null,
        "throughput_evidence": null,
        "unreachable_within_cycle": false,
        "long_run_launch_required": false,
        "harvest_validation_required": false
      },
      "metric_basis_contract": {
        "basis_overclaim": false,
        "claimed_basis_class": null,
        "actual_basis_class": null,
        "basis_downgraded_fields": []
      },
      "surface_field_review_contract": {
        "surface_field_classes": [],
        "field_class_map_missing": false,
        "surface_field_defect_matrix": {},
        "surface_field_review_status": "not_evaluated"
      },
      "guard_stacking_contract": {
        "change_set_kind": "implementation",
        "target_artifact_paths": [],
        "verifier_surface_hardening": false
      },
      "run_disposition_contract": {
        "allowed_dispositions": ["failed_closed", "candidate_degraded", "candidate_written"],
        "run_disposition": null,
        "candidate_degraded": false,
        "canonical_promotion_allowed": null
      },
      "verification_source_contract": {
        "verification_input_paths": [],
        "verified_artifact_paths": [],
        "self_grounded_axes": [],
        "independent_source_separation_status": "not_evaluated"
      },
      "envelope_thaw_contract": {
        "envelope_thaw_item_required": false,
        "envelope_thaw_item": null,
        "thaw_condition": null,
        "thaw_schedule": null
      },
      "positive_input_delta_required": false,
      "required_new_input_kinds": [],
      "scope_fidelity": [
        {
          "directive_id": "adv-...#directive-r1",
          "original_target": {"metric": "abstract_metric", "comparator": "<=", "target": "original target"},
          "item_acceptance": ["Acceptance copied from or traceable to the original directive target."],
          "narrowed": false,
          "narrow_reason": null,
          "residual_item_id": null
        },
        {
          "directive_id": "adv-...#directive-r2",
          "original_target": {"metric": "abstract_metric", "comparator": ">=", "target": "original target"},
          "item_acceptance": ["Acceptance copied from or traceable to the original directive target."],
          "acceptance": {
            "quantifiers": ["original measurable quantities or relation predicates copied without reinterpretation"],
            "evidence_kind": "live_run",
            "required_new_run_id": true
          },
          "narrowed": false,
          "narrow_reason": null,
          "residual_item_id": null,
          "acceptance_verifier_contract": {
            "required_verifier": "abstract_verifier_id",
            "verifier_required": true,
            "required_gate_hooks": ["adapter_hook_id"],
            "gate_hook_status": "not_supplied",
            "evaluation_status": "not_evaluated"
          },
          "residual_gap_policy": {
            "threshold": "adapter-owned",
            "basis": "abstract_gap_ratio",
            "cycle_cost_basis": "profile-cycle-efficiency|implicit_legacy_1"
          },
          "residual_gap_ratio": null,
          "cycle_fixed_cost": null,
          "marginal_gap_value": null,
          "marginal_value_per_cycle_cost": null,
          "marginal_repair": false
        }
      ],
      "promotion": {
        "task_id": null,
        "task_path": null,
        "promoted_at": null
      },
      "result": {
        "validation_verdict": null,
        "progress_verdict": null,
        "progress_kind": null,
        "semantic_signature": null,
        "blocker_signature": null
      }
    }
  ],
  "mutation_log": [],
  "terminal_blocker": null
}
```

Allowed pack statuses:

- `active`: the pack can supply the next task.
- `completed`: every item was consumed or intentionally skipped with evidence.
- `blocked`: the pack is waiting on a resolvable prerequisite.
- `terminal_blocked`: no viable item remains and no new input delta is available.
- `superseded`: another pack replaced this plan.

Allowed item statuses:

- `planned`
- `promoted`
- `in_progress`
- `consumed`
- `inserted`
- `reordered`
- `skipped`
- `blocked`
- `terminal_blocked`
- `superseded`

At most one item may be `promoted` or `in_progress`. While one exists, `next`
returns `status: in_flight` and no executable `next_item`; the following queued
item remains visible only as planning state until the in-flight item is
consumed or otherwise closed.

## Progress Classification

Keep lifecycle outcome, evidence class, and work subtype orthogonal:

- `progress_target` is the expected lifecycle outcome and remains one of `advanced`, `safety_only`, `no_progress`, or `regressed`.
- `progress_kind_expected` is the expected goal-distance evidence class and remains `goal_productive` or `governance_only`.
- `item_kind` is an optional open, bounded, path-safe subtype such as `workflow_capability`, `artifact_truth_only`, `artifact_truth_reconciliation`, `artifact_truth_verification`, `implementation`, or `instrumentation_exercise`. It routes work but never upgrades either canonical progress field.

Do not add a new lifecycle enum merely because an instruction uses a domain or workflow label. For example, map `workflow_capability` to `item_kind: workflow_capability`, and map a source `artifact_truth_only` label to `item_kind: artifact_truth_only` plus its explicit verifier/acceptance contract. Choose the canonical `progress_target` and `progress_kind_expected` from the expected outcome and observable output evidence. Preserve the source wording and any narrower/original measurable target in `scope_fidelity`; do not invent `effective_*` shadow fields or a parallel verdict vocabulary.

`item_kind` is not authoritative progress evidence. In particular, `item_kind: artifact_truth_only` requires its declared verifier and bound artifact evidence before any artifact-truth claim; the label alone proves nothing. A workflow-capability or artifact-truth subtype normally remains `governance_only` unless independent output-delta or adapter evidence proves goal-product output movement, and a verifier-only result cannot by itself claim semantic, readiness, gold, canonical, or production promotion.

## Scope Fidelity

When a pack item derives from an external advice, steering document, issue, or user directive with a measurable target, record the directive-to-item mapping in `scope_fidelity`. This is provenance for later completion validation; it is not goal truth and does not grant authority.

Each record should include:

- `directive_id`: stable advice/user/issue directive ID or path fragment.
- `original_target`: the measurable target exactly enough for validation to compare actual achievement. Keep project-specific metric definitions in the repository adapter or project-owned contract, not in this generic workflow.
- `item_acceptance`: the acceptance criteria copied from or traceable to `original_target`.
- `acceptance.quantifiers`: original measurable counts, rates, run counts, row counts, disjointness predicates, or relation predicates copied without reinterpretation. If extraction is uncertain, preserve the original clause as a quoted string.
- `acceptance.evidence_kind`: `live_run`, `derived_artifact`, `code_contract`, or `report_only`. If the original criterion requires execution, use `live_run` only and require a new run id after `item_created_at`.
- `acceptance_scenarios`: optional scenario-shaped acceptance records with `scenario_id`, premise predicate summary, and expected terminal state. Scenario completion needs a premise-satisfying fixture/live run.
- `expectation_lineage_contract`: optional Part K K1 fields for output-derived scalar expectations. If `expectation_anchor` is known, preserve it; if the current baseline is known, preserve `designated_baseline`; if the anchor is superseded, set `expectation_lineage_stale` and do not promote live execution until rebaseline or fail-close is planned.
- `comparison_parity_contract`: optional Part K K2 fields for comparison/adoption items. Preserve `parity_axes` and per-axis status `controlled`, `measured`, or `unknown`; unknown axes set `parity_unverified`.
- `adoption_axis_contract`: optional Part K K3 fields for adoption decisions. Preserve `required_output_classes`, axis classification `gating` or `tradable`, `majority_vote_adoption`, `provisional_adoption`, and `measured_but_disqualified`.
- `resolution_downgrade_contract`: optional Part K K4 fields for required versus observed evidence resolution. Preserve `resolution_downgrade` and `surrogate_resolution_basis` when a high-resolution contract was satisfied only by surrogate evidence.
- `report_key_integrity_contract`: optional Part K K5 fields for duplicate terminal keys inside a report. Divergent duplicate values block consumption.
- `narrowed`: `true` only when the item intentionally covers less than the original target.
- `narrow_reason`: required when `narrowed=true`.
- `residual_item_id`: required when `narrowed=true`; it must point to another open pack item that preserves the remaining target.
- `acceptance_verifier_contract`: optional adapter-owned verifier contract for measurable targets, with abstract `required_verifier`, `verifier_required`, `evaluation_status`, and evidence paths. Keep project-specific verifier implementation details in the repository adapter or project-owned contract.
- `required_gate_hooks` and `gate_hook_status`: optional fields inside `acceptance_verifier_contract` for verifier contracts that require adapter hooks. If a measurable acceptance depends on a gate and the gate's SKILL.md-required hook is absent, unloaded, fail-quiet, or not evaluated, the item cannot close through that gate; route through `unverifiable_acceptance_contract` and preserve a hook-supply follow-up.
- `residual_gap_policy`, `residual_gap_ratio`, `cycle_fixed_cost`, `marginal_gap_value`, `marginal_value_per_cycle_cost`, and `marginal_repair`: optional adapter-owned F3/G4 fields. Keep thresholds, value functions, and metric definitions in the repository adapter or project-owned contract. When `cycle_fixed_cost` is available, compare residual repair by value per cycle cost. When it is absent, use denominator `1` for legacy F3 behavior. When `marginal_repair=true`, the pack should preserve explicit residual descope plus the next capability-ladder rung unless derive records evidence that the marginal value per cycle cost is higher.

Do not let labels such as `pilot`, `plan`, `slice`, or `phase 1` silently descope a measurable directive. Either copy the original measurable target into the item acceptance, or mark `narrowed=true` with a reason and an open residual item.

When a measurable item is marked `consumed`, its `result` must include an `acceptance_provenance_gate` such as:

```json
{
  "target_met": true,
  "acceptance_diluted": false,
  "explicit_descope_decision": false,
  "evidence_paths": []
}
```

Every consumed item, measurable or not, must also preserve two distinct
hash-bound transactions: `promotion` proves the preceding task authorized the
item and stores an immutable task snapshot under `.task/task_pack/task_snapshots/`;
`completion` proves the promoted task itself reached a terminal run, complete/pass
validation with no blockers, and same-task issue reconciliation. Use
`mark-consumed` with run/validation/issue packet paths and SHA-256 values,
`--validation-evidence-path`, and `--completion-evidence-path`; directly changing
an item from planned to consumed is invalid.

If `target_met=false`, completion is valid only with `explicit_descope_decision=true` plus a still-open `residual_item_id`. If `acceptance_diluted=true`, do not mark the item `consumed`; validation must report `partial` and preserve the residual target.

If the item has a required verifier and `evaluation_status=not_evaluated`, do not mark the item `consumed`. Validation must report `partial` unless an explicit descope decision preserves residual verifier scope, or the pack transitions to terminal/user escalation.

If the item has an acceptance-required gate hook and `gate_hook_status` is `not_supplied`, `absent`, `fail_quiet`, or `not_evaluated`, do not mark the item `consumed`. Validation must report `partial` with `unverifiable_acceptance_contract`, preserve the missing hook as a concrete follow-up, and avoid treating fail-quiet as pass for that measurable target.

If the item's `acceptance.evidence_kind=live_run`, do not mark the item consumed from `derived_artifact`, `code_contract`, or `report_only` evidence. A satisfying run must have a run id created after `item_created_at`. Derived substitution sets `acceptance_diluted=true`; validation must report `partial` and preserve the original live-run target.

If the item result or loopback evidence has `pass_with_coupled_verifier=true`, do not mark the item `consumed` from that verifier pass. Require later non-coupled revalidation, independent evidence recalculation, explicit residual descope, or terminal/user escalation.

If the item result or qualitative review has `pass_with_unobserved_axes=true`, do not mark the item `consumed` from that review pass. Insert or promote an axis-supply item, residual descope, terminal blocker, or escalation item before consuming the measurable target.

If the item result or loopback evidence has `terminal_classification_stage_contradiction=true`, `terminal_classification_invalid_for_counting=true`, or `same_input_contract_violation=true`, do not mark the item `consumed` from terminal classification or same-condition comparison evidence. Insert classification-stage repair, same-input/input-contract repair, instrumentation supply, terminal blocker, or escalation before counting the family as closed or reset.

If the item result or loopback evidence has `instrumentation_supply_required=true`, do not mark the item `consumed` unless the item supplied instrumentation for the affected failure surface or records a concrete `existing_diagnostics_sufficient` / `diagnostics_observable_without_new_instrumentation` rationale. A generic hypothesis repair does not satisfy this gate.

If `item_kind=instrumentation_supply` is consumed without fresh exercise evidence, append or preserve a follow-up `item_kind=instrumentation_exercise` item. The exercise item must require one new run id after the supply item and non-empty scalar fields according to `instrumentation_field_map`. `derived_from_existing_artifacts=true` cannot satisfy exercise.

If the item has `acceptance_scenarios`, do not mark it `consumed` until at least one evidence item satisfies each premise and observes the expected terminal state. If evidence observes the opposite state, set `acceptance_inversion=true` and keep the item open or route code/contract repair.

If the item result has `command_provenance_missing=true`, do not mark comparison, baseline, A/B, or reproduction work consumed from that run.

If the item result has repeated `blocker_opacity=true` for the same gate, do not mark blocker repair consumed until the blocker contract emits violated relation, observed values, expected relation, or minimum input delta.

If the item result has `predetermined_unreachable=true` or `floor_edge_envelope=true`, do not mark retry work consumed as progress. Route contract revision, envelope expansion, explicit residual descope, terminal blocker, or escalation.

If the item result has `instrumentation_first_fire=true`, assign the credit to one item only. Do not also consume the instrumentation supply item or goal-progress item with the same run.

If the item result or acceptance has `expectation_lineage_stale=true`, do not mark the item consumed and do not promote dependent live execution until the expectation is rebaselined against `designated_baseline`, explicitly descoped with residual scope, terminal-blocked, or user-escalated. `expectation_anchor_missing=true` is warning-level but cannot support a lineage-verified expectation claim.

If the item result has `parity_unverified=true`, missing `parity_axes`, or any parity axis status `unknown`, do not mark final adoption, baseline promotion, or comparison-winner work consumed. Preserve parity-axis resolution or provisional adoption before consumption.

If the item result has `majority_vote_adoption=true` without `adoption_axis_classification`, or any `gating` axis failed, do not mark adoption consumed. Preserve axis-classification repair, gating-axis repair/contract revision, or `measured_but_disqualified` evidence.

If the item result has `resolution_downgrade=true`, do not mark a high-resolution comparison/evidence contract consumed unless resolution is restored, the contract is explicitly revised, or residual high-resolution scope remains open.

If the item result has `report_key_divergence=true`, do not mark any pass/close/adoption/baseline/comparison item consumed from that report.

If the item result has `independently_verified_fields`, require `verification_input_paths` to be disjoint from `verified_artifact_paths` unless the adapter marks the affected axis `self_grounded`. If `independent_source_separation_status` is `missing`, `overlap`, or `blocked`, or `independently_verified_downgraded_fields` is non-empty, consume the evidence as attested only or preserve residual verification-source repair.

If the item result or acceptance evidence has `envelope_thaw_item_required=true`, do not mark the item `consumed` without `envelope_thaw_item`, thaw condition/schedule, explicit residual descope, terminal blocker, or user escalation.

If the item result has `pass_on_stale_lane=true`, do not mark current-lane capability, adoption, comparison-winner, or next-rung work consumed. Preserve current-lane rerun, explicit residual scope, terminal blocker, or user escalation.

If the item result has `decision_metadata_revision=true` or `stale_measurement_artifact=true`, consume it only as metadata/governance work. Measurement, adoption, or comparison items need a fresh current-lane run id unless the packet proves the upstream production-contract change cannot affect the measured axis.

If the item result has `axis_starved_by_missing_producer=true`, do not mark another verifier/guard/report item for that gating axis consumed as progress. Promote producer-supply work, descope, terminal blocker, or user escalation before verifier-like work resumes.

If the item result has restrictive `portfolio_quota_exceeded=true`, do not promote another verifier/guard/report/metadata item until the quota recovers or the pack records producer/envelope/long-run, descope, terminal blocker, or escalation.

If the item result has `unreachable_within_cycle=true`, do not mark a small smoke or cycle-bound rerun consumed as progress. Promote long-run launch with monitor/harvest plan, throughput improvement, explicit residual descope, terminal blocker, or user escalation.

If the item result has `basis_overclaim=true`, consume the affected metric only at the downgraded actual basis class. It cannot support independent high-water/progress until basis-compatible input evidence exists.

If the item result has nonzero `surface_field_defect_matrix` counts, preserve producer-supply or field-repair residual work unless authority, residual descope, terminal blocker, or user escalation says those fields are out of scope.

## Pack Transactions

`$derive-improvement-task` owns the decision. `scripts/task_pack_queue.py` owns deterministic queue mutation when available. Prefer:

```text
scripts/task_pack_queue.py --root . apply-mutation --plan <derive-pack-plan.json> --render --language <user-language>
```

Before publication, inspect the helper contract with `capabilities` and require `findings: []` from the create/replace dry-run for the exact in-memory candidate body. Use `validate --pack <workspace-relative-pack.json> --strict-findings` only to audit an already-existing pack artifact; create/replace requires the final successor JSON path to remain absent, so an existing canonical-path candidate is debt/input rather than a publishable successor at that ref. Historical findings in unrelated inactive packs are separate debt: they do not authorize publishing a candidate with findings, and global debt must not be misreported as a defect in a clean exact candidate.

Bind every current mutation plan to the canonical JSON body with `pack_coherence.schema_version: 1`: exact pack ref, canonical before SHA-256, before item IDs/order/current item, proposed after IDs/order, and mutation kind. Require the complete mutation receipt at result-contract consumption. The helper rejects stale hashes, unknown IDs, mismatched after state, and any material no-op. `pack_coherence.schema_version: 0` normalizes only an old mutation precondition; it never repairs initial-selection authority provenance.

For promotion, write the new `task.md` only after the prior task has an
authoritative validation result, then record the transition with the same
helper using `pack_disposition: promote_next_item`. The plan must include
`item_id`, the new `task_id` and `task_path`, `validated_task_id`,
`validation_verdict`, `run_report_path`/`run_report_sha256`,
`validation_report_path`/`validation_report_sha256`,
`validation_evidence_paths`, `issue_packet_path`/`issue_packet_sha256`,
`reason`, and `evidence_paths`. The referenced packets and every evidence path
must be existing workspace-relative files. The helper verifies their hashes,
task binding, terminal run state, complete/pass validation with no blockers,
and current-task issue reconciliation (including a reasoned no-op) before it
advances the queue. It refuses partial/failed validation, pending long runs,
paths outside `.task/task_pack` for pack storage, symlink escapes, and
promotion metadata recorded before the new task file exists.

Use `promotion_origin: predecessor_completion` for successor items. For the first item only, use `bootstrap_initial_selection` or `authorized_initial_selection` with an `initial_selection_receipt` bound to a helper-owned or immutable-VCS creation snapshot, first item/order, exact task snapshot, and a subject-bound authority receipt file plus SHA-256. A bare ref, advice, or later completion is not authority. Create stores a content-addressed planned snapshot and receipt. Never reuse an initial origin for a later item. When completing an in-flight item and promoting its successor together, place the predecessor completion packet under `consume_current_item` in the same `promote_next_item` plan so the helper performs one atomic pack write.

For a pre-contract pack whose first item is already selected, use `pack_disposition: normalize_initial_selection_provenance` only after `$manage-agent-authority` issues or validates a receipt for `task_pack.normalize_initial_selection`. The helper verifies the exact creation snapshot, task snapshot, authority subject and temporality, preserves every item status/order/result/completion and `current_item_id`, appends provenance plus one mutation record, and performs one locked atomic pack write. `current_ratification` permits continuation now while preserving `historical_selection_authority_status: unverifiable_before_ratification`, `historical_authority_verdict: partial`, and `retroactive_claim_allowed: false`. Literal replay of the same bound receipt is a validated no-op; a conflicting receipt blocks. Use [initial-selection-provenance.md](initial-selection-provenance.md) for complete plan shapes, snapshot construction, rollback, and replay rules.
For standalone `mark-consumed`, pass the same current coherence object with `--pack-coherence-json` and all six versioned lifecycle verdict axes with `--verdict-axes-json`; use explicit version `0` only for a genuinely legacy transaction.
The helper also refuses a second promotion while another item is in flight,
rejects blocking result-contract envelopes/findings, snapshots the exact new
task bytes, and writes Markdown renders atomically without following symlinks.

## Replacement Transaction

Use `pack_disposition: replace_pack` with helper action `replace_pack` when one active pack must be superseded by a clean successor. Do not emulate replacement by separately applying `supersede_pack` and `create_pack`, and do not hand-edit either pack. The plan must bind the exact unique active predecessor through current coherence and must provide a successor whose publication validation returns no findings.

Place the successor JSON under the plan's top-level `pack` key; `successor_pack` is not an alias. `pack_coherence` describes the predecessor-side supersession precondition, so its declared and proposed IDs/order repeat the predecessor's exact IDs/order and its exact `current_item_id`. The successor IDs/order belong only to `pack.items` and `replacement_contract`.

The successor must contain `replacement_contract.schema_version: 1` with:

- exact predecessor pack ref, file SHA-256, and canonical SHA-256;
- a complete, disjoint partition of successor items into `new_item_ids` and `carried_forward_item_ids`;
- a complete disposition for every nonterminal predecessor item: carry it unchanged, or list it under `retired_items` with a bounded reason and non-empty evidence entries containing exact workspace-relative `path` and `sha256` values. Retirement evidence must live outside the mutable `.task/task_pack/` transaction store and must still verify after publication;
- at most five newly derived items;
- exact carried-forward planning contracts and predecessor-relative order;
- dependency closure: a successor dependency that names a predecessor item must still resolve to a successor item, or that predecessor item must already be `consumed` with preserved completion evidence. Retiring an unfinished dependency target requires rederiving the dependent item with a new ID and counts against the new-item bound.

An ordinary new pack contains two to five newly derived items. A replacement may contain more than five total items only when the excess items are exact carry-forward items under this contract; lifecycle-only fields may be normalized by the helper, but changed objective, acceptance, validation, dependencies, scope, or other planning content makes the item newly derived. An existing predecessor ID cannot be relabeled as new, and omission is not retirement. Use `retired_items` only when exact direction/authority evidence permits removing that live predecessor item. Do not use carry-forward or retirement to evade the five-new-item bound.

Set deterministic successor `created_at` and `updated_at` values in the planned body before preflight. Keep the persisted plan body-safe: refer to source instructions and sensitive external metadata through opaque IDs, workspace evidence refs, and hashes rather than raw prompts, transcripts, credentials, or corpus metadata. Run that exact plan with `apply-mutation --dry-run` first and require `status: dry_run` and `findings: []`; then reuse the byte-identical plan and task inputs for apply. If any input digest or timestamp changes, rerun preflight and rebuild any precomputed creation-snapshot/authority binding instead of relying on apply-time defaults. The dry-run must leave no pack, render, snapshot, receipt, or transaction residue. On apply, the helper content-addresses the exact plan, locks the task-pack store, writes a prepare journal whose transaction identity binds the plan fingerprint and every target before/after hash, publishes the predecessor as `superseded` and the successor as the only active pack, verifies creation evidence and the postcondition, and writes a completion receipt. Optional first-item selection uses the same creation-snapshot, task-snapshot, and authority receipt contract described in [initial-selection-provenance.md](initial-selection-provenance.md). A downstream result must supply the complete validated receipt, including its durable ref and SHA-256; a transaction ID alone is not a receipt.

For replacement plus initial selection, use a two-phase preflight. First dry-run the successor/carry/retirement plan without selection to derive creation identities. Store prospective new-task bytes in a bounded noncanonical workspace staging file, hash them, construct the deterministic task-snapshot subject, and issue the one-shot authority receipt. Then add `prospective_task_ref` and `prospective_task_sha256` beside canonical `task_path` inside `initial_selection` and dry-run the complete final plan. Dry-run uses staging even when canonical `task.md` still contains the predecessor task; apply requires canonical `task.md` to equal those staged bytes. Keep staging until apply completes, then remove it. The staging file and unused subject-bound receipt are explicit preparation evidence; no pack, helper snapshot, journal, completion receipt, or lifecycle state may survive dry-run.

The helper's transaction scope is deliberately limited to the task-pack store and helper-owned evidence: predecessor/successor JSON, requested Markdown renders, creation/task snapshots, journal, and receipt. It does not atomically publish or roll back `task.md`, `past_task` archives, `.task/index.*`, issue/schema state, Git staging, or a commit. For optional initial selection, the exact `task.md` must exist by apply time; preflight may use the hash-bound prospective staging path above. The helper hash-verifies and snapshots task bytes but does not publish them. The caller must preflight those outer lifecycle surfaces before archive or replacement and reconcile them afterward without claiming they were part of the pack transaction. Retain old task/index anchors until commit: restore the old task only when failure occurs before durable prepare, but forward-recover the pack and then reconcile links once a valid prepare exists.

If a prepare journal exists without a valid completion receipt, every other pack mutation must fail closed. Run `recover-replacement` to forward-complete the exact journal only after its content-addressed plan, target binding, creation snapshot/receipt, and current before/after state all validate; do not truncate, delete, recreate, rehash, or apply a different replacement plan. Replaying a completed exact plan is a receipt-validated no-op, while a different plan, altered journal, missing helper-owned evidence, or stale predecessor binding remains blocked.

Allowed `pack_disposition` values:

- `create_pack`: create a bounded 2-5 newly derived item pack when a known sequence prevents repeated myopic derivation.
- `replace_pack`: supersede the unique active predecessor and publish one clean successor through the helper-owned replacement transaction; a successor over five total items requires exact carry-forward and may still add at most five new items.
- `promote_next_item`: promote one safe item into `task.md`; no other item becomes executable.
- `normalize_initial_selection_provenance`: append only verified first-selection provenance to an existing pack without changing lifecycle or semantic state.
- `insert_items`: insert prerequisite or retarget items before the current item.
- `reorder_items`: reorder existing items when the old order is unsafe, stale, or stationary.
- `skip_items`: exclude item(s) by setting `status: skipped`; do not delete them.
- `supersede_pack`: set the old pack and remaining planned items to `superseded`.
- `derive_standalone`: bypass the active pack only with a rationale showing why the pack is unsafe, stale, blocked, or not goal-fit.
- `terminal_blocked`: record terminal blocker state when no viable item or candidate remains.

Every non-promotion mutation must produce a `pack_mutation_plan` with:

- `action`
- `reason`
- `evidence_paths`
- `pack_path` when mutating an existing pack
- changed item IDs
- `before_order` and `after_order` when order changes
- `terminal_blocker` for `terminal_blocked`
- `scope_fidelity` records for new or changed measurable items
- required gate-hook, goal-axis, count-key hygiene, and residual value-per-cycle-cost records when the mutation changes a measurable item or loop-family decision
- Markdown `render_path` after applying the mutation

The mutation reason must cite one of: new blocker evidence, repeated blocker/semantic/root-axis evidence, missing supplied positive input delta, provider-neutral retarget evidence, task-state/schema/validation/issue dependency repair, user-supplied direction, or terminal blocker evidence. Do not mutate a pack merely to prefer a newer idea, rename a version, or avoid executing the next item.

## Promotion

When an active pack exists, `$derive-improvement-task` should consider the next `planned` item before creating unrelated one-off candidates. Promote the item into `task.md` only after:

- the item still aligns with `.agent_goal` GT, authority policy, active advice disposition, schema contracts, and current blocker evidence;
- dependencies are satisfied or explicitly represented in the new `task.md`;
- any `scope_fidelity` measurable target is copied into `task.md` acceptance or explicitly narrowed with residual scope;
- any `acceptance_verifier_contract` required verifier is copied into `task.md` acceptance/validation, or the new task explicitly implements that verifier before consuming the target;
- any acceptance-required gate hook is copied into `task.md` validation, supplied by an adapter/project-owned module, or converted into a hook-supply task before consuming the target;
- any `goal_axis_contract` with supplied `goal_axis_map` has at least one observable `quality_vector` axis for every active measurable goal axis; otherwise promote an axis-supply, residual, terminal, or escalation item first;
- any below-threshold `residual_gap_policy` marginal repair is either deferred behind descope-with-residual plus the next rung, or explicitly justified by higher marginal value per cycle cost;
- any `failure_surface_contract` contradiction, invalid terminal count key, or same-input mismatch is converted into classification/input-contract repair, instrumentation supply, terminal blocker, or escalation before ordinary repair;
- any `diagnostics_contract.instrumentation_supply_required=true` is promoted as instrumentation supply unless the task records why success/failure is already observable without new instrumentation;
- any `diagnostics_contract.instrumentation_exercise_required=true` is promoted as instrumentation exercise before measurement, comparison, or adoption work that depends on the supplied fields;
- any `acceptance_scenarios` are promoted as scenario fixture/live-run coverage before close when not covered, or as code/contract repair when inverted;
- any `acceptance_encoding.evidence_kind=live_run` preserves its quantifiers and requires a post-item run id before consumption;
- any `command_provenance_contract.command_provenance_missing=true` is converted into full-argv rerun/provenance repair before comparison, baseline, A/B, or reproduction work consumes that run;
- any repeated `blocker_actionability_contract.blocker_opacity=true` is converted into blocker-contract repair before another opaque recheck;
- any `stochastic_feasibility_contract.predetermined_unreachable=true` or `floor_edge_envelope=true` is converted into contract revision/envelope/descope/escalation before retry;
- any `instrumentation_first_fire_contract.instrumentation_first_fire=true` is assigned to exactly one evidence-credit path;
- any `expectation_lineage_contract.expectation_lineage_stale=true` is converted into expectation rebaseline or fail-closed terminal/user-escalation before live execution depends on it;
- any `comparison_parity_contract.parity_unverified=true`, missing parity axes, or unknown parity axis is converted into parity-axis resolution, provisional comparison, residual scope, terminal blocker, or escalation before final adoption;
- any `adoption_axis_contract.majority_vote_adoption=true` without axis classification, failed `gating` axis, or `measured_but_disqualified=true` is converted into axis-classification/gating repair, candidate rejection, or preserved measured-but-disqualified evidence before adoption;
- any `resolution_downgrade_contract.resolution_downgrade=true` is converted into resolution restoration, contract revision, or residual high-resolution scope before consumption;
- any `report_key_integrity_contract.report_key_divergence=true` is converted into report/schema/sync repair before consuming the report;
- any `lane_identity_contract.pass_on_stale_lane=true` is converted into current-lane rerun, explicit residual scope, terminal blocker, or escalation before consuming capability/adoption/comparison evidence;
- any `decision_freshness_contract.decision_metadata_revision=true` or `stale_measurement_artifact=true` is converted into fresh measurement or explicit no-impact proof before consuming measurement/adoption/comparison work;
- any `gating_axis_producer_contract.axis_starved_by_missing_producer=true` is converted into producer-supply work before another verifier/guard/report for the same axis;
- any restrictive `portfolio_quota_contract.portfolio_quota_exceeded=true` is converted into producer, envelope, long-run, descope, terminal, or escalation work before another verifier-like item;
- any `cycle_reachability_contract.unreachable_within_cycle=true` is converted into long-run launch with monitor/harvest, throughput improvement, descope, terminal, or escalation before another small cycle-bound run;
- any `metric_basis_contract.basis_overclaim=true` is converted into basis-compatible measurement, downgrade-aware residual scope, or contract revision before independent progress consumption;
- any nonzero `surface_field_review_contract.surface_field_defect_matrix` is converted into producer/field repair, residual scope, terminal blocker, or escalation before review pass consumption;
- any `guard_stacking_contract.verifier_surface_hardening=true` beyond the detection-only cap is converted into execution work, explicit descope with residual scope, terminal blocker, or escalation before another guard/report/verifier item;
- any `verification_source_contract` with missing/overlapping verification inputs is promoted as source-separation repair or consumed as attested only, not as independent high-water proof;
- any `envelope_thaw_contract.envelope_thaw_item_required=true` is promoted as thaw/relax/descope/terminal/escalation before another frozen-envelope-internal repair;
- loop-breaker checks do not require insertion, reordering, or terminal blocking first.

The promoted `task.md` must include these fields in `## Execution Environment`:

- `Task Pack: <pack-id/path | none>`
- `Task Pack Item: <item-id | none>`
- `Pack Position: <order/total | none>`
- `Pack Source: planned | inserted | reordered | none`

After promotion, record `promotion.task_id`, `promotion.task_path`, and `promotion.promoted_at` in the JSON queue and render the Markdown view.

## Insert, Reorder, Skip, Supersede

Late-cycle derivation may insert, reorder, skip, or supersede pack items only when new evidence makes the existing order unsafe, stale, or stationary. Valid reasons:

- a new blocker signature appeared;
- a repeated blocker signature would otherwise be selected again without new input;
- an evidence-family task lacks the required positive input delta;
- a provider/runtime/output blocker repeats while provider-neutral work can advance;
- a task-state, schema, validation-set, or issue-lifecycle dependency must be repaired before the next planned item.
- user-supplied direction explicitly excludes an item, in which case set the item to `skipped` or `superseded` and keep traceability.

Every insert, reorder, skip, supersede, or terminal-block mutation must append a `mutation_log` entry with:

- `timestamp`
- `action: insert | reorder | skip | supersede | terminal_block`
- `reason`
- `evidence_paths`
- `before_order`
- `after_order`
- `actor: $derive-improvement-task`

Do not reorder merely to prefer a newer idea or sequential version number. Do not delete skipped/excluded items during derivation; deletion is a separate cleanup action that requires ID audit evidence and an owning workflow decision.

## Loop Breaker Fields

Use `blocker_signature` to compare recent blockers. Normalize from:

- blocker taxonomy;
- issue or task_miss path;
- target surface;
- provider dependency;
- missing input kind;
- evidence family.

Also carry `semantic_signature` when available. It should remove volatile target-surface tokens such as timestamps, run directories, sequential `after-*` suffixes, and version suffixes, then reduce the blocker to a stable goal-axis family such as `hash_reconcile`, `evidence_anchor`, `provider_terminal`, `task_state_digest`, `validation_set`, `quality_review`, `kg_core`, or `claim_rights`. Use `semantic_signature` before raw `blocker_signature` for loop-family comparisons, while preserving `blocker_signature` for compatibility and traceability.

When an adapter supplies count-family fields, store raw plan IDs, task-pack IDs, advice IDs, run IDs, cycle IDs, dates, hashes, work IDs, sequential suffixes, and version suffixes only as trace material. The effective count key is the adapter-collapsed root plus dominant parameter. If a new facet is unmapped, fall back to the terminal outcome family rather than minting a new loop family from volatile generation material.

For evidence-family tasks, `positive_input_delta_required: true` means progress can only be claimed when at least one `required_new_input_kinds` value was newly introduced since the compared recent cycles and the result also records a supplied positive input delta: a non-empty artifact in `supplied_input_artifact_paths` or `produced_domain_delta=true` backed by `changed_vs_previous=true` and `semantic_progress=true`. New wording alone is not progress.

If no viable candidate or pack item remains and no supplied positive input delta is available, write `status: terminal_blocked` and include:

```json
"terminal_blocker": {
  "semantic_signature": "stable-goal-axis-family",
  "blocker_signature": "normalized-signature",
  "reason": "Concrete missing input, authority, or external-state change.",
  "required_handoff": "What the user or external system must provide.",
  "root_cause_attempted_for_family": true,
  "root_cause_ledger_path": ".task/anti_loop/root_cause_ledger.jsonl",
  "untried_actionable_root_cause_exists": false,
  "untried_root_cause_hypotheses": [],
  "hypothesis_exhausted": false,
  "vacuous_untried_streak": 0,
  "authorized_alternative_path": null,
  "authorized_alternative_path_exists": false,
  "authorized_alternative_path_attempted": false,
  "alternative_in_gt_allowed": false,
  "gt_allowed_alternative_attempted": false,
  "gt_allowed_alternative_evidence_paths": [],
  "authorized_alternative_source_gt_paths": [],
  "provider_mitigation_required": false,
  "missing_mitigations": [],
  "provider_reattempt_required": false,
  "dual_track_attempt_evidence": [],
  "terminal_quiescence": false,
  "terminal_escalation": false,
  "terminal_recheck_streak": 0,
  "forced_disposition": null,
  "required_missing_input": null,
  "required_missing_input_count": 0,
  "commit_skipped_reason": null,
  "recent_cycle_ids": [],
  "evidence_paths": []
}
```

`terminal_blocked` prevents narrowing -> blocker -> handoff -> narrowing loops. Treat its `semantic_signature` as a sealed family; do not create a new non-terminal narrowing task in that family until a materially supplied input delta, authority change, or external state change exists.

Do not write `terminal_blocked` as a provider-terminal seal when `provider_mitigation_required=true`, `provider_reattempt_required=true`, `untried_actionable_root_cause_exists=true` with `hypothesis_exhausted=false` and `untried_veto_overridden_by_chain_stall=false`, or when an authority-permitted productive alternative remains unattempted; retarget to bounded retry/probe, verified root-cause repair, record an authority/user-escalation blocker, or use the authorized provider-neutral/quality track first. If `hypothesis_exhausted=true` or `untried_veto_overridden_by_chain_stall=true`, record the exhausted/overridden state and do not create another same-family untried repair without supplied input delta.

When repeated terminal state reaches quiescence, set `terminal_quiescence: true` and `commit_skipped_reason: terminal_quiescence`; do not generate another narrowing, dashboard, report, recheck, or closeout-only pack item merely to reconfirm the same terminal family. Use `quiescence_untried_reconcile` when present: only verified, unexhausted untried repairs may override quiescence.

When repeated terminal state reaches G2 escalation, set `terminal_escalation: true`, `forced_disposition: user_escalation`, `terminal_recheck_streak`, `required_missing_input_count: 1`, and exactly one `required_missing_input` object. The input kind must be one of `new_input_kind`, `authority_change`, `external_state_change`, or `gate_contract_fix_approval`. Seal the family in `.task/sealed_blocker_families.json` through the derive/task-pack mutation. Do not add another `terminal_blocked` recheck, dashboard, report, or closeout item to the pack as a substitute for user escalation.

When `authorized_alternative_path_exists=true`, also record:

- `authorized_alternative_path`: the concrete productive alternative action, not a fabricated input class.
- `alternative_in_gt_allowed: true`: the alternative is derived from `.agent_goal/agent_authority.md`, `.agent_goal/conventions.md`, or another used GT file.
- `gt_allowed_alternative_attempted: true`: the GT-allowed alternative was actually attempted.
- `gt_allowed_alternative_evidence_paths`: non-empty safe evidence paths for that attempt.
- `authorized_alternative_source_gt_paths`: GT files that authorize or require the alternative.

## Part G Workflow Gates

Task packs must preserve the in-place Part G workflow revisions without adding project-specific logic to this generic contract:

- Count-key hygiene: pack item IDs, pack IDs, cycle IDs, run IDs, dates, hash suffixes, advice IDs, and version names are trace-only. Consume, skip, insert, reorder, or terminal-block decisions must use the effective adapter-collapsed family key or terminal-outcome fallback.
- Required gate hooks: if measurable acceptance requires a gate and that gate's required hook is absent, unloaded, fail-quiet, or not evaluated, the item cannot be marked consumed through that gate. Use `unverifiable_acceptance_contract` and preserve the hook-supply work.
- Goal-axis completeness: when `goal_axis_map` is supplied, each active measurable goal needs at least one mapped `quality_vector` axis before a qualitative review pass can support consumption. Zero mapped axes means `pass_with_unobserved_axes=true`.
- Residual repair denominator: compare residual repairs by marginal gap value per cycle cost when `$profile-cycle-efficiency` or equivalent cost evidence is available. If no denominator is available, use denominator `1` to preserve legacy F3 behavior.

## Part H Workflow Gates

Task packs must also preserve the Part H in-place workflow revisions as generic contracts:

- Failure autopsy and stage resolution: failure-derived pack items should carry `last_successful_stage`, `failure_surface_stage`, `failure_surface_count_key`, and `effective_count_key` when supplied. Contradictory terminal classification or same-input mismatch is trace evidence only until repaired; it cannot close, seal, or reset the family.
- Diagnostics supply: when loopback reports repeated `diagnostics_unavailable` for the same failure surface, insert or promote instrumentation supply unless the chosen repair records why the current evidence already observes success/failure.
- Verification source separation: `independently_verified` evidence is consumable only when verification inputs are disjoint from verified artifacts, except adapter-declared `self_grounded` axes. Missing or overlapping source paths downgrade the affected fields to attested evidence.
- Frozen-envelope thaw: when acceptance is unreachable under a frozen envelope, reserve `envelope_thaw_item` with thaw condition/schedule, or route to constraint relaxation, explicit residual descope, terminal blocker, or user escalation.
- Ledger fixed cost: when a pack mutation records repeated cycle artifacts, prefer `unchanged_ref(path+hash)` references for identical prior packets and keep full serialization for changed content only.

## Part I Workflow Gates

Task packs must preserve evidence lifecycle seams without adding project-specific logic to this generic contract:

- Instrumentation exercise: `item_kind=instrumentation_supply` may consume on code/contract landing, but if it lacks fresh exercise evidence it must set `instrumentation_exercise_required=true` and insert or preserve an `instrumentation_exercise` item before dependent measurement/comparison/adoption items become current. Existing artifact reinterpretation does not exercise the supplied fields.
- Acceptance encoding: measurable directive quantifiers and `evidence_kind` must survive pack encoding. Live-run criteria require a new run id after item creation; derived artifacts, code contracts, or report-only matrices cannot silently replace live-run evidence.
- Guard-stacking collapse: guard/verifier/report-only items over the same target artifact paths and no new run id share one `verifier_surface_hardening` family regardless of verifier names. After the detection-only cap, do not create another guard item as the next progress step.
- Run disposition: preserve `candidate_degraded` output as quality-miss evidence with verification flags and degradation reasons, but do not promote it as the canonical baseline unless independent verification permits the consumed axes. Discard only `failed_closed` unsafe output.
- Runtime config echo: failed-run pack evidence may carry scalar `runtime_config_echo` and `config_overrides`; `code_default` overrides route to self-inflicted gate/root-cause repair when they explain the blocker.
- Execution starvation: when profile evidence reports no fresh run id for the recent pack window, prioritize an execution-producing item over another guard/contract/report item unless safety, authority, or terminal state blocks execution.

## Part J Workflow Gates

Task packs must preserve decision-contract symmetry and reproducibility without adding project-specific logic to this generic contract:

- Scenario injection: scenario-shaped acceptance needs premise-satisfying fixture or live-run evidence plus expected terminal-state observation. Green tests without premise injection do not consume the item; opposite-state observation is `acceptance_inversion`.
- Command provenance: live-run items that will support baseline, A/B, comparison, reproduction, or run-specific acceptance require full body-free argv. `command_provenance_missing=true` blocks those consumption paths.
- Blocker actionability: repeated opaque blockers must become blocker-contract repair items requiring violated relation, observed values, expected relation, or minimum input delta.
- Stochastic feasibility: exact-match or floor-edge contracts with observed variance route to contract revision, envelope expansion, explicit residual descope, terminal blocker, or escalation before retry.
- First-fire credit: the first run that emits supplied instrumentation fields earns one evidence credit only. It cannot also consume instrumentation supply or goal progress for the same run.

## Part K Workflow Gates

Task packs must preserve expectation/comparison lineage without adding project-specific logic to this generic contract:

- Expectation lineage: output-derived scalar expectations require `expectation_anchor` when known and current `designated_baseline` comparison when supplied. A superseded anchor sets `expectation_lineage_stale` and blocks live-execution promotion until rebaseline, explicit residual descope, terminal blocker, or user escalation.
- Comparison parity: comparison/adoption items require `parity_axes` with per-axis `controlled`, `measured`, or `unknown`. Unknown axes set `parity_unverified` and keep adoption provisional.
- Adoption axis semantics: adoption axes are `gating` or `tradable` before measurement. Failed gating axes block adoption regardless of tradable wins; the candidate remains `measured_but_disqualified`.
- Resolution downgrade: high-resolution contracts such as id/set/intersection evidence cannot be consumed from lower-resolution count/ratio/ordinal surrogates unless the contract is revised or residual high-resolution scope remains open.
- Report key integrity: duplicate terminal keys with divergent values inside one report set `report_key_divergence` and block pass/close/adoption/baseline/comparison consumption until repaired. Matching duplicate terminal keys remain warn-only schema debt and do not consume or block the item by themselves.

## Part L Workflow Gates

Task packs must preserve lane lineage and premise-supply contracts without adding project-specific logic to this generic contract:

- Lane identity: verifier/review/metric passes must record the artifact lane they inspected when supplied. A pass on a lane different from `current_decision_lane` is `pass_on_stale_lane` and cannot consume current-lane capability, adoption, comparison-winner, or next-rung items.
- Decision freshness: decision-update items after upstream production-contract changes require a fresh measurement run id for the current lane. Relabeling stale artifacts is `decision_metadata_revision` and remains metadata/governance work.
- Gating-axis producer supply: if a gating axis is starved because the producer path is missing or unexercised, producer-supply work outranks another verifier/guard/report item. Verifier-like work over that axis collapses under verifier-surface hardening until producer supply fires.
- Portfolio quota: when an adapter-supplied quota restricts overrepresented verifier/guard/report/metadata work, the next item must be producer, envelope, long-run, descope-with-residual, terminal blocker, or user escalation until the ratio recovers. Missing quota hooks are warn-only.
- Cycle reachability: when required scale is unreachable within a cycle, use a long-run launch item with monitor/harvest validation, a throughput-improvement item with measured C increase, explicit descope, terminal blocker, or user escalation. Do not keep promoting small smoke reruns as progress.
- Metric basis: metrics whose claimed basis is not derivable from consumed inputs must carry `basis_overclaim` and downgraded actual basis fields. They cannot support independent high-water/progress consumption until basis-compatible evidence exists.
- Surface field review: locator-backed qualitative review should cover every adapter-supplied producer-written surface string field class and record scalar defect counts by field class and defect class. Missing `surface_field_classes` fails quiet; nonzero counts preserve producer/field repair or residual scope.
