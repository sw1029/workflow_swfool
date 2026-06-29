# Task Pack Workflow

This reference defines optional long-range task packs for `$orchestrate-task-cycle`. Task packs are workflow planning state, not `.agent_goal` goal truth.

## Contents

- [Core Invariant](#core-invariant)
- [Artifacts](#artifacts)
- [JSON Shape](#json-shape)
- [Pack Transactions](#pack-transactions)
- [Promotion](#promotion)
- [Loop Breaker Fields](#loop-breaker-fields)

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
      "positive_input_delta_required": false,
      "required_new_input_kinds": [],
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
- Markdown `render_path` after applying the mutation

The mutation reason must cite one of: new blocker evidence, repeated blocker/semantic/root-axis evidence, missing supplied positive input delta, provider-neutral retarget evidence, task-state/schema/validation/issue dependency repair, user-supplied direction, or terminal blocker evidence. Do not mutate a pack merely to prefer a newer idea, rename a version, or avoid executing the next item.

## Promotion

When an active pack exists, `$derive-improvement-task` should consider the next `planned` item before creating unrelated one-off candidates. Promote the item into `task.md` only after:

- the item still aligns with `.agent_goal` GT, authority policy, active advice disposition, schema contracts, and current blocker evidence;
- dependencies are satisfied or explicitly represented in the new `task.md`;
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
