# Task Pack Workflow

This reference defines optional long-range task packs for `$orchestrate-task-cycle`. Task packs are workflow planning state, not `.agent_goal` goal truth.

## Contents

- [Core Invariant](#core-invariant)
- [Artifacts](#artifacts)
- [JSON Shape](#json-shape)
- [Scope Fidelity](#scope-fidelity)
- [Pack Transactions](#pack-transactions)
- [Promotion](#promotion)
- [Loop Breaker Fields](#loop-breaker-fields)
- [Part G Workflow Gates](#part-g-workflow-gates)
- [Part H Workflow Gates](#part-h-workflow-gates)

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
        "existing_diagnostics_sufficient": false
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

## Scope Fidelity

When a pack item derives from an external advice, steering document, issue, or user directive with a measurable target, record the directive-to-item mapping in `scope_fidelity`. This is provenance for later completion validation; it is not goal truth and does not grant authority.

Each record should include:

- `directive_id`: stable advice/user/issue directive ID or path fragment.
- `original_target`: the measurable target exactly enough for validation to compare actual achievement. Keep project-specific metric definitions in the repository adapter or project-owned contract, not in this generic workflow.
- `item_acceptance`: the acceptance criteria copied from or traceable to `original_target`.
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

If `target_met=false`, completion is valid only with `explicit_descope_decision=true` plus a still-open `residual_item_id`. If `acceptance_diluted=true`, do not mark the item `consumed`; validation must report `partial` and preserve the residual target.

If the item has a required verifier and `evaluation_status=not_evaluated`, do not mark the item `consumed`. Validation must report `partial` unless an explicit descope decision preserves residual verifier scope, or the pack transitions to terminal/user escalation.

If the item has an acceptance-required gate hook and `gate_hook_status` is `not_supplied`, `absent`, `fail_quiet`, or `not_evaluated`, do not mark the item `consumed`. Validation must report `partial` with `unverifiable_acceptance_contract`, preserve the missing hook as a concrete follow-up, and avoid treating fail-quiet as pass for that measurable target.

If the item result or loopback evidence has `pass_with_coupled_verifier=true`, do not mark the item `consumed` from that verifier pass. Require later non-coupled revalidation, independent evidence recalculation, explicit residual descope, or terminal/user escalation.

If the item result or qualitative review has `pass_with_unobserved_axes=true`, do not mark the item `consumed` from that review pass. Insert or promote an axis-supply item, residual descope, terminal blocker, or escalation item before consuming the measurable target.

If the item result or loopback evidence has `terminal_classification_stage_contradiction=true`, `terminal_classification_invalid_for_counting=true`, or `same_input_contract_violation=true`, do not mark the item `consumed` from terminal classification or same-condition comparison evidence. Insert classification-stage repair, same-input/input-contract repair, instrumentation supply, terminal blocker, or escalation before counting the family as closed or reset.

If the item result or loopback evidence has `instrumentation_supply_required=true`, do not mark the item `consumed` unless the item supplied instrumentation for the affected failure surface or records a concrete `existing_diagnostics_sufficient` / `diagnostics_observable_without_new_instrumentation` rationale. A generic hypothesis repair does not satisfy this gate.

If the item result has `independently_verified_fields`, require `verification_input_paths` to be disjoint from `verified_artifact_paths` unless the adapter marks the affected axis `self_grounded`. If `independent_source_separation_status` is `missing`, `overlap`, or `blocked`, or `independently_verified_downgraded_fields` is non-empty, consume the evidence as attested only or preserve residual verification-source repair.

If the item result or acceptance evidence has `envelope_thaw_item_required=true`, do not mark the item `consumed` without `envelope_thaw_item`, thaw condition/schedule, explicit residual descope, terminal blocker, or user escalation.

## Pack Transactions

`$derive-improvement-task` owns the decision. `scripts/task_pack_queue.py` owns deterministic queue mutation when available. Prefer:

```text
scripts/task_pack_queue.py --root . apply-mutation --plan <derive-pack-plan.json> --render --language <user-language>
```

Allowed `pack_disposition` values:

- `create_pack`: create a bounded 2-5 item pack when a known sequence prevents repeated myopic derivation.
- `promote_next_item`: promote one safe item into `task.md`; no other item becomes executable.
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
