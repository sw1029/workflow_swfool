# Task And Candidate Templates

## Contents

- [`task.md` template](#taskmd-template)
- [Derive analysis envelope](#derive-analysis-envelope)
- [Candidate task template](#candidate-task-template)
- [Task pack JSON template](#task-pack-json-template)
- [Candidate application rule](#candidate-application-rule)

## `task.md` Template

Use this shape for the final selected task:

```markdown
# Task

## Execution Environment

- Status: selected | unresolved | not_applicable
- Source: previous_task | find-local-python-envs | repository_manifest | manual_inference
- Type: conda | venv | local | non_python | unknown
- Name:
- Python:
- Run Prefix:
- Dependency Notes:
- Progress Target: advanced | safety_only | no_progress | regressed
- Progress Kind: goal_productive | governance_only
- Validation Profile: current_only | affected_chain | full_chain
- Authority Policy: `$manage-agent-authority` result (`.agent_goal/agent_authority.md` | default_current_agent_permissions)
- External Advice: <adv-id/path | none>
- Task Pack: <pack-id/path | none>
- Task Pack Item: <item-id | none>
- Pack Position: <order/total | none>
- Pack Source: planned | inserted | reordered | none
- Prerequisite Manifest: <path/status/hash summary, or none>

## Objective

<One concrete improvement objective.>

## Background

- Goal alignment:
- Issue link:
- Architecture/theory link:
- Authority policy link:
- External advice link:
- Schema contract link:
- Task miss or candidate source:

## Requirements

- <Specific requirement>

## Acceptance Criteria

- <Observable completion condition>

## Validation

- <Test, command, metric, review, or evidence required>

## Constraints

- <Relevant convention, forbidden action, compatibility or safety rule>

## Out Of Scope

- <What this task should not attempt>

## Open Questions

- <Unknowns that must be resolved before or during implementation>
```

Environment section rules:

- Put `## Execution Environment` immediately after `# Task`.
- Prefer the previous `task.md` environment section when it is explicit and still applicable.
- If it is absent for a Python task, use `$find-local-python-envs` and choose in this priority order: conda, venv, local/system Python.
- `Run Prefix` must be directly usable, such as `conda run -n ENV`, `/path/to/.venv/bin/python`, or `python3`.
- Use `Status: unresolved` when no usable environment is found; include the blocker in `Dependency Notes`.
- Use `Status: not_applicable` only when the task requires no Python/code execution.
- Include `Progress Target` for every task. Use `advanced` only when the task is expected to unlock a new execution/readiness/goal state or materially reduce a blocker.
- Include `Progress Kind` for every task. Use `goal_productive` only when the task is expected to produce goal-relevant output, quality evidence, source-backed validation, or another non-sidecar artifact that reduces goal distance.
- Include `Validation Profile` for every executable or verifiable task. Use `full_chain` only for live dispatch, readiness promotion, issue closure, shared validator/runtime changes, or explicit user request.
- Include `Authority Policy` for every task from `$manage-agent-authority`. Use `.agent_goal/agent_authority.md` when present; otherwise use `default_current_agent_permissions` and do not infer API/network/destructive authority.
- Include `External Advice` as `none` unless an `.agent_advice/active` document influenced selection, requirements, constraints, or validation. When used, list the `adv-*` ID or path and keep it separate from goal truth.
- Include task-pack fields as `none` for standalone tasks. When a pack item is promoted, list the pack ID/path, item ID, item position, and whether it was planned, inserted, or reordered.
- When a measurable target has a required verifier, include the abstract verifier contract in acceptance or validation. Do not mark `evaluation_status: not_evaluated` as a passing condition.
- When a measurable target depends on an acceptance-referenced gate with required adapter hooks, include required hook status in acceptance or validation. Missing, fail-quiet, or `not_evaluated` hook status means `unverifiable_acceptance_contract`, not pass.
- When a verifier pass came from a verifier source modified in the same change set, include `pass_with_coupled_verifier` evidence and require later non-coupled revalidation or independent recalculation; do not consume it as `pass`.
- When review evidence reports `pass_with_unobserved_axes` or non-empty `unobserved_goal_axes`, include adapter axis-supply, explicit residual scope, terminal blocker, or user escalation in the task; do not consume that review as pass.
- When loopback reports generation-dependent count-key material, include the effective adapter-collapsed count key or terminal-outcome family fallback. Do not use task/advice/pack/cycle/run/date/hash/version labels as family novelty or stall reset.
- When loopback reports failure-surface or same-input Part H blockers, include `failure_surface_stage`, `terminal_classification_stage_contradiction`, and/or `same_input_contract_violation` evidence and select classification/input-contract repair, instrumentation supply, terminal blocker, or user escalation rather than ordinary repair.
- When loopback reports `instrumentation_supply_required`, include instrumentation supply acceptance or a concrete observability rationale proving success/failure is already measurable without new instrumentation.
- When the caller supplies `bounded_prerequisite_chain.applicability: applicable`, copy the opaque stable root, owner, relation, reduction/high-water tristates, budget, position/cap, comparable before/after values, and closed reduction-observation receipt. Record `selected_successor_kind`. A raw decreasing scalar is not strict-reduction evidence; a reasonless `not_applicable` is not a bypass. Do not reset the chain from renamed tasks or fixtures; a non-reducing or exhausted chain cannot select another prerequisite, and exhaustion must select a concrete task kind that implements the declared mandatory direct successor.
- When loopback reports `hook_supply_required`, use `selected_task_kind: adapter_hook_batch_supply` when `demanded_hooks` has two or more entries. Supply all `demanded_hooks` in one task item, and consume the item only after a fresh packet shows each supplied hook fired at least once with a non-empty scalar or adapter-owned non-empty value; code existence alone is not acceptance.
- When independently verified evidence lacks disjoint `verification_input_paths`, include source-separation repair or treat the fields as attested; do not claim high-water or `goal_productive` from them.
- When frozen-envelope reachability reports `envelope_thaw_item_required`, include `envelope_thaw_item` with thaw condition/schedule, constraint relaxation, explicit residual descope, terminal blocker, or user escalation.
- When metric movement is producer-attested, include `evidence_provenance_gate`, `producer_attested_fields`, and `attested_only_movement` evidence and require independent verification before claiming high-water movement or `goal_productive`.
- When a residual measurable gap is below adapter policy, include `residual_gap_ratio`, `residual_gap_policy`, `marginal_repair`, cycle-cost fields when supplied, and either explicit descope-with-residual plus the next capability rung or higher marginal-value-per-cycle-cost evidence.
- When a verifier/review/metric pass is on a stale lane, include `production_lane_identity`, `current_decision_lane`, `pass_on_stale_lane`, and current-lane rerun/residual requirements; do not consume it as current-lane progress.
- When a decision/adoption/reclassification update reused stale artifacts after upstream production-contract changes, include `decision_metadata_revision`, `stale_measurement_artifact`, and a fresh run or no-impact proof requirement.
- When a gating axis is starved by missing producer supply, include `axis_starved_by_missing_producer`, the abstract gating axis id, and producer-supply requirement before another verifier/report item.
- When `execution_starvation_status=present`, carry the exact execution scope and required-input binding IDs without source metadata. The selected kind must be execution-producing, producer/input/receipt reconciliation, or explicit residual descope; otherwise publish only a separately valid terminal/user-escalation outcome. A stale-input or malformed producer receipt does not clear the state. When a selected task excludes a producer required by an active goal/product axis, carry reason-bound `execution_scope_applicability: excluded_by_task` with `execution_scope_status: excluded_by_task` and keep starvation `present`; never relabel it `not_applicable`, `absent`, or terminal. Use reason-bound `not_applicable` only when the task class intrinsically has no producer semantics.
- When portfolio quota evidence restricts verifier-like work, include `portfolio_quota_exceeded`, quota mode, and the allowed producer/envelope/long-run/descope/terminal/escalation path.
- When a target is unreachable within the cycle, include `acceptance_scale`, `throughput_evidence`, `unreachable_within_cycle`, and long-run launch/monitor/harvest, throughput improvement, descope, terminal, or escalation acceptance.
- When a metric basis is overclaimed, include `basis_overclaim`, `actual_basis_class`, and basis-compatible measurement or downgrade-aware residual requirements.
- When qualitative review found surface field defects, include `surface_field_defect_matrix`, affected field classes, and producer/field repair or residual handling.

## Derive Analysis Envelope

Publish this contract with every derive decision. Use opaque IDs, relative refs, and digests; do not copy source-title or person metadata into the envelope.

```json
{
  "derive_contract_version": 2,
  "selection_outcome": "selected | terminal_wait | terminal_blocked | user_escalation",
  "selected_candidate_id": "candidate-id-or-empty",
  "pack_disposition": "canonical value from derive-selection-contract.json",
  "improvement_analysis_manifest": {
    "schema_version": 1,
    "shared_evidence_manifest": {
      "cycle_id": "opaque-cycle-id",
      "task_id": "opaque-task-id",
      "attempt_id": "opaque-attempt-id",
      "artifact_id": "opaque-artifact-id",
      "artifact_sha256": "sha256",
      "body_projection_fingerprint": "sha256",
      "production_lane_identity": "opaque-lane-id",
      "input_state_fingerprint": "sha256",
      "issue_fit": {
        "status": "available | not_applicable | unavailable",
        "evidence_ids": ["opaque-evidence-id"],
        "unavailable_reason": "required only when unavailable"
      },
      "active_advice_clause_set": {
        "contract_version": 1,
        "applicability": "applicable | not_applicable",
        "advice_packet_digest": "sha256 or null only when not_applicable",
        "actionable_clause_ids": ["exact sorted opaque clause IDs"],
        "clause_source_digests": {"opaque-clause-id": "sha256"},
        "not_applicable_reason_id": "required only when not_applicable",
        "evidence_ids": ["required only when not_applicable"],
        "clause_set_sha256": "canonical body sha256"
      },
      "adapter_applicability": "required | not_applicable",
      "adapter_decision_context": {
        "packet_ref": "relative-ref",
        "packet_sha256": "sha256",
        "packet": {
          "phase": "derive",
          "required_consumer_ids": ["derive-improvement-task"],
          "static_validation": {"status": "pass"},
          "load_preflight": {"status": "pass"},
          "candidate_projection": {"status": "eligible", "eligible": true},
          "adapter_revision": {"adapter_revision_sha256": "sha256"},
          "hook_results_sha256": "sha256",
          "decision_identity": {
            "cycle_id": "opaque-cycle-id",
            "task_id": "opaque-task-id",
            "attempt_id": "opaque-attempt-id",
            "artifact_id": "opaque-artifact-id",
            "artifact_sha256": "sha256",
            "body_projection_fingerprint": "sha256",
            "production_lane_identity": "opaque-lane-id",
            "input_state_fingerprint": "sha256"
          },
          "post_use_decision_receipt": {"status": "pass", "receipt_sha256": "seal sha256"}
        }
      },
      "adapter_post_use_seal": {
        "schema_version": 1,
        "consumer_id": "derive-improvement-task",
        "cycle_id": "opaque-cycle-id",
        "task_id": "opaque-task-id",
        "attempt_id": "opaque-attempt-id",
        "artifact_id": "opaque-artifact-id",
        "artifact_sha256": "sha256",
        "body_projection_fingerprint": "sha256",
        "production_lane_identity": "opaque-lane-id",
        "input_state_fingerprint": "sha256",
        "adapter_revision_sha256": "sha256",
        "hook_results_sha256": "sha256",
        "value_consumed_by_decision": true,
        "decision_id": "opaque-decision-id",
        "receipt_sha256": "canonical body sha256"
      },
      "evidence_refs": [
        {"evidence_id": "opaque-id", "ref": "relative-ref", "sha256": "sha256"}
      ]
    },
    "shared_evidence_manifest_sha256": "canonical body sha256",
    "lens_results": [
      {
        "role_id": "goal_value | architecture_contract | miss_validation",
        "agent_id": "unique-opaque-agent-id",
        "agent_receipt_id": "unique-opaque-id",
        "read_only": true,
        "status": "complete",
        "input_evidence_manifest_sha256": "identical shared digest",
        "output_ref": "relative-ref",
        "output_sha256": "canonical output sha256",
        "output": {
          "candidates": [
            {
              "candidate_id": "unique-opaque-id",
              "exact_subject_fingerprint": "opaque-fingerprint",
              "first_failing_invariant": "opaque-invariant-id",
              "canonical_owner": "opaque-owner-id",
              "task_kind": "opaque-task-kind",
              "expected_blocker_transition": "opaque-transition-id",
              "actionability": "actionable | blocked_external | blocked_authority | unverified",
              "pack_disposition": "canonical value",
              "issue_derived": false,
              "evidence_ids": ["opaque-id"],
              "validation_ids": ["opaque-id"]
            }
          ],
          "rejection_inventory": [
            {"option_id": "opaque-id", "reason_code": "opaque-code", "evidence_ids": ["opaque-id"]}
          ],
          "advice_clause_set_sha256": "exact shared clause-set digest",
          "advice_clause_assessments": [
            {
              "contract_version": 1,
              "clause_id": "exact actionable clause ID",
              "lens_agent_id": "this lens agent ID",
              "lens_receipt_id": "this lens receipt ID",
              "disposition": "incorporated | deferred | tested | rejected",
              "evidence_ids": ["opaque-id"],
              "candidate_ids": ["candidate IDs from this lens only"],
              "assessment_sha256": "canonical body sha256"
            }
          ]
        }
      }
    ],
    "synthesis": {
      "synthesis_agent_id": "opaque-agent-id distinct from all lens agents",
      "synthesis_receipt_id": "opaque-id",
      "input_evidence_manifest_sha256": "identical shared digest",
      "consumed_agent_receipt_ids": ["exactly three receipt IDs"],
      "candidate_union_ids": ["exact validated union"],
      "candidate_union_sha256": "canonical sorted-union sha256",
      "advice_clause_set_sha256": "exact shared clause-set digest",
      "advice_clause_reconciliation": [
        {
          "contract_version": 1,
          "clause_id": "exact actionable clause ID",
          "final_disposition": "incorporated | deferred | tested | rejected",
          "consumed_lens_assessment_sha256s": ["exact three sorted assessment digests"],
          "evidence_ids": ["opaque-id"],
          "selected_candidate_ids": ["selected union candidate IDs"],
          "reconciliation_sha256": "canonical body sha256"
        }
      ],
      "advice_reconciliation_sha256": "canonical sorted reconciliation sha256",
      "synthesis_output_ref": "relative ref to actual synthesis output",
      "synthesis_output_sha256": "canonical synthesis projection sha256",
      "selected_candidate_id": "union member or empty",
      "selection_outcome": "selected | terminal_wait | terminal_blocked | user_escalation",
      "pack_disposition": "canonical value"
    }
  },
  "terminal_wait": {
    "selection_epoch": "opaque-id",
    "analysis_evidence_manifest_sha256": "shared evidence digest",
    "observed_input_manifest_sha256": "selection-tick watched-input digest",
    "selection_tick_baseline": {
      "format_version": 2,
      "artifact_kind": "selection_tick",
      "packet_id": "content-derived selection-tick ID",
      "status": "baseline_recorded | no_op",
      "selection_required": false,
      "agent_fanout_allowed": false,
      "full_cycle_allowed": false,
      "mutation_performed": false,
      "not_goal_truth": true,
      "not_authority": true,
      "wake_predicates": ["opaque-predicate-id"],
      "wake_evaluation_rule": "explicit-premise-or-bound-class-change-v1",
      "wake_predicate_ids_are_policy_labels": true,
      "watched_evidence_classes": ["supported-opaque-class-id"],
      "minimum_material_delta": "opaque-delta-id",
      "premise_input_contract": "validated_exact_subject_premise_receipt_v2 | raw_exact_file_v1",
      "watch_entries": ["content-bound body-free read-only entries"],
      "carried_forward_watch_ids": ["sticky exact-premise or authority watch IDs"],
      "baseline_rebased": false,
      "selection_acknowledgement_status": "not_requested",
      "selection_acknowledgement_binding": null
    },
    "selection_tick_baseline_sha256": "canonical baseline packet digest",
    "wake_predicates": ["opaque-predicate-id"],
    "watched_evidence_classes": ["opaque-class-id"],
    "minimum_material_delta": "opaque-delta-id",
    "last_selection_receipt": "validated selection-decision receipt ID"
  }
}
```

Use [derive-selection-contract.json](../../orchestrate-task-cycle/references/derive-selection-contract.json) as the enum source. Omit `terminal_wait` unless that outcome is selected. Require three distinct opaque lens `agent_id` values in addition to three unique receipt IDs; the synthesis agent ID must be different from all three. A lens may return zero candidates only with a non-empty rejection inventory. The synthesis output must consume all three unique receipts and may select only an actionable union member. Advice coverage is exact-set: every lens assesses every actionable clause and synthesis consumes exactly three assessment digests per clause. Persist three closed lens receipt projections containing their exact outputs plus the canonical synthesis-output projection under `.task/cycle/<cycle-id>/agent_receipts/` as four distinct compact canonical JSON regular non-symlink files; only their reopened `durable_runtime_artifact_bound` projection may generate `wired` receipts. Empty advice still uses the closed `not_applicable` clause-set object and empty assessment/reconciliation lists. `verified` additionally requires current-input-bound happy/negative producer outputs and complete outer receipts persisted in the same store, distinct verifier/invariant-owner identities with disjoint input/invariant IDs, and a negative state that differs from happy. This content binding does not cryptographically attest process identity. For terminal wait, keep the analysis digest distinct from the `selection-tick` watched-input digest and carry the exact read-only baseline packet needed by the next tick; substituting the shared analysis digest would reopen immediately instead of proving unchanged inputs.

For a return to wait opened by `selection_required`, treat the activated predecessor packet as `A`, the selection-required trigger as `B`, and the acknowledgement/rebased safe packet as `C`. The durable chain is the four runtime artifacts above, then `derive_selection_synthesis`, then `preliminary_selection_decision` bound to `B`, then `selection_decision_receipt` bound to persisted `B` and the preliminary decision, then `C`, then a direct full final derive result. Each stage must persist as a workspace-relative regular non-symlink file and the next stage must reopen its exact raw bytes. The preliminary decision and selection-decision receipt are intermediate evidence; neither may be used as the terminal owner's `source_derive`.

The terminal owner must reopen `A` from `expected_current_snapshot_sha256`, prove that `B.previous_input_manifest_sha256` equals `A.observed_input_manifest_sha256`, and recompute `B`'s change set. It must then prove that `C.previous_input_manifest_sha256` and `C.observed_input_manifest_sha256` both equal `B.observed_input_manifest_sha256`, that `C` keeps the same watch entries and wake contract, and that `C` has no changed entries/classes. The direct final derive result must pass block-mode derive validation, embed `C`, bind its canonical packet digest and receipt ID, and carry the exact receipt-reopened analysis manifest. A `{ "result": ... }` wrapper or partial/preliminary artifact is invalid.

The wake predicate and minimum-delta values are policy labels, not caller-defined executable expressions. The only executable rule is `explicit-premise-or-bound-class-change-v1`: the authenticated manifest must change and contain either an added/content-changed exact-premise row or a changed row in a baseline-bound evidence class. Exact-premise and effective-authority rows are sticky across caller omission. An identical receipt/replay identity stays `no_op` even when accompanied only by nonmaterial drift; an unchanged effective-authority fingerprint also stays `no_op`.

For an initial wait baseline, use `baseline_rebased: false`, `selection_acknowledgement_status: not_requested`, and no acknowledgement binding. If this terminal-wait result follows a `selection_required` tick, replace those three example values with:

```json
{
  "baseline_rebased": true,
  "selection_acknowledgement_status": "accepted",
  "acknowledged_selection_tick_id": "exact selection-required trigger packet ID",
  "selection_acknowledgement_binding": {
    "trigger_tick_id": "same exact trigger packet ID",
    "trigger_tick_sha256": "canonical trigger packet digest",
    "selection_receipt_id": "validated selection-decision receipt ID",
    "selection_receipt_ref": "workspace-relative durable receipt ref",
    "selection_receipt_sha256": "raw SHA-256 of exact persisted receipt bytes",
    "selection_receipt_integrity_sha256": "receipt-internal canonical integrity digest",
    "selection_outcome": "terminal_wait",
    "selected_task_id": null
  }
}
```

In that branch, the acknowledgement owner must require exactly those eight binding fields. It reopens the workspace-relative regular non-symlink selection-decision receipt, matches its exact bytes to the raw digest, recomputes the declared receipt ID and internal integrity digest, reopens persisted `B`, the preliminary decision, durable selection synthesis, and all four runtime artifacts, and then requires `last_selection_receipt` to equal `selection_acknowledgement_binding.selection_receipt_id`. A caller-authored ID plus an arbitrary 64-hex digest is invalid. Input drift during acknowledgement is another `selection_required` result, not `C`. After the direct full final derive result is durable, materialize the authority subject from that result, `C`, the terminal task, and the exact predecessor snapshot; publish through the authority-settled terminal-wait baseline owner. Its current pointer is a downstream lifecycle artifact and must not be fabricated inside this derive envelope.

For autonomous premise-triggered re-entry, require `validated_exact_subject_premise_receipt_v2`. Its consumed artifact-verified receipt binds the current terminal task or selection baseline, a freshness subject/revision/digest, one canonical writable owner and authority scope, the first failing invariant, producer/verifier/replay or source-separated-current-body evidence, and the reopened raw digest of each referenced workspace-local regular non-symlink artifact. Persist neither source path nor source body. A structural v1 receipt or raw exact-file row is compatibility evidence only and must not be described as semantic freshness, artifact identity, or owner proof.

When no adapter is registered, replace both adapter objects with `adapter_registry_status: no_registered_adapter`, `adapter_not_applicable_reason`, and non-empty `adapter_registry_evidence_ids`. Do not use this branch for a registered-but-unloaded adapter. Normalize equivalent candidates by `(exact subject, first-failing invariant, canonical owner, task kind, blocker transition, actionability, disposition, issue-derived)` so repeated lens proposals share one candidate ID rather than becoming votes.

## Candidate Task Template

Store unapplied candidates under `.task/candidate_task/YYYYMMDD-HHMMSS-<slug>.md`.

```markdown
# Candidate Task

- Status: candidate | blocked | deferred
- Source: goal_alignment | task_miss | prior_candidate | synthesis
- Candidate Class: state_transition | batchable_micro_contract | safety_only | goal_progress
- Expected Progress: advanced | safety_only | no_progress | regressed
- Progress Kind: goal_productive | governance_only
- Semantic Signature:
- Effective Count Key:
- Count-Key Hygiene: generation-dependent raw keys trace-only | not_applicable
- Supplied Input Delta Needed: yes | no
- Validation Profile: current_only | affected_chain | full_chain
- Authority Policy: `$manage-agent-authority` result (`.agent_goal/agent_authority.md` | default_current_agent_permissions)
- External Advice: <adv-id/path | none>
- Created:
- Supersedes:
- Exact Subject Fingerprint:
- First Failing Invariant:
- Canonical Owner:
- Expected Blocker Transition:
- Actionability: actionable | blocked_external | blocked_authority | unverified
- Issue Derived: yes | no
- Pack Disposition: <canonical value>

## Candidate Objective

<Concrete improvement candidate.>

## Why Not Applied Now

- <Reason this was not selected as the current task.md>

## Evidence

- <Goal, issue, authority, external advice, architecture, theory, task_miss, or repo evidence>

## Potential Requirements

- <Requirement if promoted later>

## Validation Idea

- <How to verify if later applied>

## Blocking Questions

- <Unknowns or dependencies>

## Part G Gates

- Required Gate Hooks:
- Goal Axis Completeness:
- Residual Value Per Cycle Cost:

## Part H Gates

- Failure Surface Stage:
- Same Input Contract:
- Instrumentation Supply:
- Verification Source Separation:
- Envelope Thaw:

## Part L Gates

- Lane Identity:
- Decision Freshness:
- Gating-Axis Producer:
- Portfolio Quota:
- Cycle Reachability:
- Metric Basis:
- Surface Field Review:
```

`adapter_hook_batch_supply` candidate variant:

Use this candidate variant when G-ADAPTER emits `hook_supply_required=true` and `demanded_hooks` contains two or more opaque hook ids.

```markdown
# Candidate Task

- Status: candidate | blocked | deferred
- Source: anti_loop_progress_gate
- Candidate Class: state_transition
- Expected Progress: advanced | safety_only
- Progress Kind: goal_productive | governance_only
- Selected Task Kind: adapter_hook_batch_supply
- Demanded Hooks: [<opaque-hook-id>, <opaque-hook-id>]
- Hook Demand Threshold: <hook_demand_threshold>
- Evidence: <loopback packet path or registry row reference>

## Candidate Objective

Supply all demanded adapter hooks in one batch without adding repo-specific hook semantics to the generic skill body.

## Potential Requirements

- Implement the demanded opaque hooks in the repository-owned adapter or repair adapter loading if the hooks are registered but unreachable.
- Keep hook meanings, paths, thresholds, and metric semantics adapter-owned.

## Acceptance Criteria

- A fresh loopback packet records each demanded hook firing at least once with a non-empty scalar or adapter-owned non-empty value.
- The fresh packet no longer emits `hook_supply_required=true` for those demanded hooks, or records an explicit observability-without-hook rationale.
- Code presence alone does not consume the candidate; this follows the I1 instrumentation exercise principle.

## Validation Idea

- Run the loopback provider on the relevant artifact family and cite the fresh packet fields `adapter_hook_demand`, `hook_supply_required`, and `demanded_hooks`.
```

## Task Pack JSON Template

Store task packs under `.task/task_pack/pack-YYYYMMDD-HHMMSS-<slug>.json`. The JSON queue is canonical; render a same-name `.md` file in the user's requested language after every JSON change.

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
      "lane_identity_contract": {
        "production_lane_identity": null,
        "current_decision_lane": null,
        "pass_on_stale_lane": false
      },
      "decision_freshness_contract": {
        "required_new_run_id": false,
        "stale_measurement_artifact": false,
        "decision_metadata_revision": false
      },
      "gating_axis_producer_contract": {
        "axis_starved_by_missing_producer": false,
        "producer_supply_required": false
      },
      "cycle_reachability_contract": {
        "unreachable_within_cycle": false,
        "long_run_launch_required": false,
        "harvest_validation_required": false
      },
      "metric_basis_contract": {
        "basis_overclaim": false,
        "actual_basis_class": null
      },
      "surface_field_review_contract": {
        "surface_field_defect_matrix": {},
        "field_class_map_missing": false
      },
      "positive_input_delta_required": false,
      "required_new_input_kinds": [],
      "scope_fidelity": [
        {
          "directive_id": "adv-...#directive-id",
          "original_target": {"metric": "abstract_metric", "comparator": ">=", "target": "original target"},
          "item_acceptance": ["Acceptance copied from or traceable to the original directive target."],
          "acceptance_envelope_contract": {"envelope_floor": "adapter-owned abstract floor", "deficit_axis": "adapter-owned axis", "status": "provided|not_provided|indeterminate"},
          "acceptance_verifier_contract": {
            "required_verifier": "adapter-owned abstract verifier",
            "verifier_required": true,
            "required_gate_hooks": [],
            "gate_hook_status": "pass|fail|not_supplied|absent|fail_quiet|not_evaluated",
            "evaluation_status": "pass|fail|not_evaluated"
          },
          "residual_gap_ratio": null,
          "residual_gap_policy": null,
          "envelope_thaw_item_required": false,
          "envelope_thaw_item": null,
          "cycle_fixed_cost": null,
          "marginal_gap_value": null,
          "marginal_value_per_cycle_cost": null,
          "marginal_repair": false,
          "narrowed": false,
          "narrow_reason": null,
          "residual_item_id": null
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

Pack rules:

- Keep at most one active task pack unless a caller explicitly authorizes multiple packs.
- Prefer 2-5 items. Use a standalone task when only one item is known.
- Promote only one item into the active `task.md` per derivation.
- Preserve measurable directive scope with `scope_fidelity`. If a pack item narrows an original target, set `narrowed=true`, record `narrow_reason`, and create an open residual item rather than consuming the target under a weaker acceptance criterion.
- Preserve adapter-owned `acceptance_envelope_contract` when it exists. If the planned item envelope is below the floor, keep the original target open and represent the item as envelope expansion, explicit descope with residual scope, terminal blocker, or user escalation rather than a weakened acceptance target.
- Preserve adapter-owned `acceptance_verifier_contract` when it exists. If the required verifier is `not_evaluated`, keep verifier work or residual target scope open; do not consume the target under an unverified acceptance criterion.
- Preserve acceptance-required gate-hook status when it exists. If a required hook is absent, fail-quiet, or `not_evaluated`, keep hook-supply work or residual target scope open; do not consume the target under fail-quiet.
- Preserve `adapter_hook_demand`, `hook_supply_required`, and `demanded_hooks` when supplied. If two or more hooks are demanded, batch them as one `adapter_hook_batch_supply` item rather than serializing one hook per cycle.
- Preserve goal-axis completeness fields when supplied. If `pass_with_unobserved_axes=true`, keep adapter axis-supply work, residual target scope, terminal blocker, or user escalation open.
- Preserve count-key hygiene fields when supplied. Generation-dependent raw keys are trace-only; use `effective_count_key_expected` or terminal-outcome fallback for repeated-family decisions.
- Preserve Part F fields when present. `pass_with_coupled_verifier` is not a passing verifier, `attested_only_movement` is not high-water progress, and `marginal_repair` for a below-threshold residual gap should stay behind explicit descope plus the next capability rung unless higher marginal value is recorded.
- Preserve Part G residual cost fields when present. If cycle-cost evidence is supplied, same-gap repair must justify marginal value per cycle cost; otherwise keep denominator `1` legacy behavior.
- Preserve Part H fields when present. Terminal-classification/stage contradictions and same-input mismatches cannot close or count work; repeated diagnostics unavailable must force instrumentation or explicit observability; independently verified fields need disjoint verification inputs or become attested; frozen-envelope unreachable acceptance needs `envelope_thaw_item`, residual/descope, terminal blocker, or user escalation.
- Preserve Part L fields when present. Stale-lane passes cannot consume current-lane work; stale decision measurements need fresh runs or no-impact proof; producer-starved gating axes need producer supply before more verifier-like work; restrictive portfolio quota changes task ordering; cycle-unreachable targets need long-run/throughput/descope/terminal/escalation; basis-overclaimed metrics are downgraded; surface-field defect matrices preserve producer/field repair or residual scope.
- Use `terminal_blocked` when no viable item remains and no supplied input delta, authority change, or external-state change exists. Include `semantic_signature`, `root_cause_attempted_for_family`, authorized-alternative-path status, provider re-attempt status, and dual-track attempt evidence when a hard loop gate applies, so later derivation can seal the family rather than only the current target surface.
- Refresh the Markdown render with `python3 -m orchestrate_task_cycle task-pack --root . render --language <language>` after any JSON edit.

## Candidate Application Rule

When a candidate becomes the real `task.md`:

1. Log the old `task.md` as `past_task`.
2. Write the candidate-derived final `task.md`.
3. Delete the applied candidate file from `.task/candidate_task/`.
4. Mention the deleted candidate path in the final response and `past_task` log note.

If no previous `task.md` exists, treat the write as `initial_init`: skip `past_task` logging, write the initial `task.md`, index it when possible, and only delete an applied candidate after the new task is written and the candidate transition is recorded.
