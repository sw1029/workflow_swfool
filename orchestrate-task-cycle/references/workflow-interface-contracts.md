# Workflow Interface Contracts

This reference indexes the contact surfaces between `$orchestrate-task-cycle`, its helper scripts, and the owning skills it calls. It is skill-internal operating guidance, not workspace goal truth.

## Contents

- [Ownership Model](#ownership-model)
- [Cross-Skill Handoffs](#cross-skill-handoffs)
- [Core Packet Contracts](#core-packet-contracts)
- [Scoped Progress and Retained Change](#scoped-progress-and-retained-change)
- [Helper Script Surfaces](#helper-script-surfaces)
- [Fail-Closed Consumer Rules](#fail-closed-consumer-rules)

## Ownership Model

Run/review own observed claims only. Loopback owns recurrence observations and prepared state mutations but performs no current-state write. Completion validation owns the identity-bound final candidate and preserves or downgrades the existing six verdict axes. The orchestrator's cycle-ledger finalizer alone assigns the attempt revision, publishes the immutable snapshot, atomically advances the current pointer, and issues the content-bound finalization receipt. Derive, result-contract, dashboard, index, report, and later packets consume only a re-verified current receipt and may never upgrade an authoritative false or hard stop. A terminal-outcome change is progress only with independent evidence, no conflict, and all acceptance-required integrity axes evaluated.

If finalization compare-and-swap finds a different current revision, it does not overwrite that authoritative pointer and does not discard an otherwise valid attempt. The ledger writes a content-addressed `cycle_finalization_pending_conflict` record containing only validated candidate material, expected/actual revision bindings, and the attempt-memory digest, then raises a conflict with `state_commit_status: recovery_required` and `attempt_memory_disposition: pending_conflict`. `load_pending_finalization_conflicts` is the recovery input. Derive may select only bounded finalization reconciliation while any such record remains active. A byte-equivalent attempt finalized against the refreshed pointer automatically writes an immutable `merged` resolution; an owning reconciliation may explicitly write `retired` with an opaque evidence ID. Pending memory is anti-loop evidence, not committed progress or authoritative registry state.

Use `python3 -m orchestrate_task_cycle ledger --root . pending-finalizations --cycle-id <id>` to inspect unresolved records. Use `resolve-pending-finalization` only after the owning reconciliation can supply the exact pending ID, `merged|retired` disposition, and opaque resolution evidence ID; a normal task-selection decision is not retirement evidence.

Actual-artifact recomputation outranks verifier, current-transform, producer, carried-forward, and workflow claims. `report_key_divergence` and `report_body_divergence` are distinct blocking facts. Source-separated ids/fingerprints and external consumer-context probe rows travel in existing packets; no additional workflow phase is introduced.

The orchestrator coordinates packets and ordering. It also owns metadata-only repo adapter scan/gap packets, but it does not own implementation edits, acceptance normalization, validation-scope judgment, final validation, issue lifecycle decisions, schema authority, Git staging, or subskill-internal verdicts.

Use these ownership rules:

- `$task-md-agent-governance` owns implementation changes and post-implementation governance evidence.
- `$run-task-code-and-log` owns execution, durable run logging, running-state metadata, failure autopsy, and `gate_satisfiability` run records.
- `$review-cycle-output-quality` owns direct qualitative output review with exactly one read-only reviewer agent.
- `$audit-cycle-loopback` owns write-free `anti_loop_progress_gate` production and prepared family/root/seal mutations; it does not publish current workflow state.
- `$build-validation-set-with-agents` owns reusable validation-set plan/build/refresh/consume evidence under `.validation/` and `.task/validation_set/`.
- `$normalize-acceptance-and-demo` owns task-bound acceptance normalization and source task ID/path/fingerprint provenance.
- `$plan-validation-scope` owns the pre-change `validation_scope_plan` and post-change `validation_scope_finalize` packets.
- `$profile-cycle-efficiency` owns the pre-validation cycle-cost and execution-starvation profile.
- `$audit-session-governance` owns optional privacy-safe session-observation projection and advisory relation claims; it owns no canonical workflow verdict, comparator truth, or semantic repair.
- `$manage-schema-contracts` owns `.schema/` and `.contract/` refresh/reconciliation.
- `$validate-task-completion` owns the current-task final candidate and downgrade-only verdict reconciliation before derive or promotion.
- `$orchestrate-task-cycle` owns finalization through the existing cycle-ledger helper: same-attempt revision, immutable snapshot, atomic current pointer, and content-bound receipt.
- `$manage-implementation-issues` owns current-task issue lifecycle updates and validation provenance before derive or promotion.
- `$derive-improvement-task` owns archiving the validated `task.md`, writing the next `task.md`, task-pack mutation decisions, terminal blocker derivation, and next-task selection.
- `$manage-task-state-index` owns both the pre-validation traceability snapshot and post-derive final index, link repair, and ID lifecycle consistency.
- `$repo-change-commit` owns Git classification, staging, commit readiness, and commit creation.

## Cross-Skill Handoffs

| Surface | Producer | Consumers | Required handoff |
| --- | --- | --- | --- |
| Model/effort routing evidence | Every agent-bearing owning skill | Result contract, ledger, validation, report | `policy_id`, `profile_id`, `routing_tier`, requested model/effort, reason codes/signals, Tier 5 signal evidence, routing violations even when empty, `routing_enforcement: enforced|prompt_only|inherited_unverified`, optional actual model/effort, and limitation or max prior-pass evidence when applicable. |
| Authority decision packet | `$manage-agent-authority` plus orchestrator closed projection | Governance, run dispatch, derive, validation, report | Reopened immutable decision ref/hash, exact request/operation/subject, selected and lineage grant digests/state versions and policy snapshots, deterministic approval projection, explicit composition receipt when needed, independent authority/local/external/risk/GT axes, scoped effective fingerprints, and exact reservation plus immutable `pre_dispatch` verification for mutation. Consumption requires an explicit workspace root and rejects path escape, symlink, byte drift, forged echoes, and stale current CAS state. See [authority-boundary-contract.md](authority-boundary-contract.md). |
| Active advice packet | `$manage-external-advice` or orchestrator context | Governance, validation-set, review, derive, validation, report, commit | Advice ID/path, summary, declared and canonical actionable clause ID sets, source/clause digests, content-bound packet digest/basis, application gates, raw-direct-reference requirement, disposition or explicit non-use rationale. |
| Session-audit sidecar projection | `$audit-session-governance` trusted collector | Context, loopback, validation, issue, derive, report | A validated, privacy-safe, deterministic source projection with explicit capture/validation status. Raw/slim transcript text is inert and must not cross this interface. Direct packets, result-owned projected collections, and packet-owned relation claims remain advisory. Only a separate comparator contract may establish a mismatch that lowers/blocks. Findings may propose work, never upgrade verdicts, establish authority, or perform semantic repair. Missing/incomplete capture is advisory/`not_evaluated` unless independently required by acceptance/caller. |
| Repo adapter scan packet | Orchestrator metadata scan | Acceptance, validation-set, governance, run, review, loopback, schema, derive, validation | `cycle_id`, scan status, adapter count including zero, adapter ID/path/status, renderer availability, optional `code_convention_contract` locator, explicit blockers/evidence paths, and non-GT/authority limits. The scan precedes acceptance and does not load long adapter bodies. |
| Acceptance packet | `$normalize-acceptance-and-demo` | Governance, validation-scope, run planning, validation-set, loopback, derive, validation | `acceptance_id`, `task_id`, status, `acceptance_provenance.source_task_id|source_task_path|source_task_fingerprint`, criteria, non-goals, demo surfaces, validation commands, forbidden shortcuts, preserved `acceptance.quantifiers`, `evidence_kind`, `item_created_at`, and `required_new_run_id` for measurable criteria, scenario contracts (`acceptance_scenarios` with opaque scenario/predicate IDs, expected terminal states, and optional applicability), optional `acceptance_envelope_contract` from adapter `min_envelope_for`, optional `acceptance_verifier_contract` from adapter target-to-verifier mapping, required gate-hook completeness for gates named by measurable acceptance, frozen-envelope reachability and `envelope_thaw_item`/`envelope_thaw_item_required` when supplied, residual-gap value/cycle-cost comparison inputs when supplied, Part K fields for output-derived expectations, comparison parity axes, adoption-axis classification, evidence resolution requirements, and provisional/disqualified adoption state when applicable, Part L scale/freshness fields such as `acceptance_scale`, `throughput_evidence`, `unreachable_within_cycle`, `required_new_run_id`, and `decision_metadata_revision` when supplied, and Part M launch/contract fields such as `harvest_contract_preflight`, `harvest_gate_unaudited`, `harvest_risk_accepted`, `validation_predicate_contract`, `producer_directives`, `mutually_unsatisfiable_contract`, and `closed_world_collection_consumption` when supplied. Missing or mismatched source-task provenance blocks governance. |
| Validation-scope plan | `$plan-validation-scope` | Governance, scope finalization, result contract | `step: validation_scope_plan`, `mode: plan`, task/profile floor, planned changed files/surfaces, commands/prerequisites, `finalized: false`, findings/evidence. Actual changed files remain explicit but empty until finalization. |
| Repo adapter validation packet | Orchestrator applying `$skill-creator` validation rules | Ledger, run, repo skill gap, validation | Task ID, validation status, changed-adapter and validated-adapter counts including zero, explicit blockers, evidence paths. Invalid changed adapters cannot become routing evidence. |
| Validation-set packet | `$build-validation-set-with-agents` | Governance, schema, derive, index, validation, report | Need/status, quality tier, `not_gold`, item/label/oracle counts, source-class distribution, oracle/split/leakage/root paths, candidate scenario-supply fields (`acceptance_scenario_id`, premise status, expected/observed terminal state, hashed evidence), and blocked/candidate-only reasons. These rows plan or identify invocation supply; they are not completion receipts until the actual invocation owner emits the full structured `premise_receipts` row. |
| Governance result | `$task-md-agent-governance` | Result contract, ledger, code audit, run, schema, validation | Task ID, changed files, task_miss, used GT/advice, implementation summary, validation profile, blockers. |
| Code-structure audit packet | `python3 -m orchestrate_task_cycle code-structure` | Run, derive, validation, issue, report | Scanned changed files, oversize files, responsibility clusters, semantic structure metrics/findings, convention conformance, moduleization requirement, split plan, semantic-refactor plan, exemptions, evidence paths. |
| Run result | `$run-task-code-and-log` | Review, loopback, validation-set, schema, derive, index, validation, issue, report | Status, command, full body-free `command_argv` or `command_provenance_missing`, exit code, output/artifact paths, running metadata, log path, shortcomings, structured `premise_receipts` for actually invoked acceptance scenarios, `failure_autopsy` including stage ladder, `last_successful_stage`, `failure_surface_stage`, scalar diagnostics or `diagnostics_unavailable`, `runtime_config_echo` and `config_overrides` when available, `run_disposition` (`failed_closed`, `candidate_degraded`, `candidate_written`), `gate_satisfiability`, scalar `gate_selfcheck`, actionable blocker fields when a gate returns a reason code, Part K report/comparison fields declared by artifacts, Part L lane/freshness/basis fields declared by artifacts or adapters (`production_lane_identity`, `current_decision_lane`, `measurement_run_id`, `upstream_contract_changed_since_measurement`, `metric_basis_inputs`, `basis_overclaim`), Part M terminal disposition and collection fields (`execution_cost_scalar`, `high_cost_artifact`, `destructive_disposition_requested`, `destructive_disposition_blocked`, `quarantine_required`, `failure_check_provenance`, `reharvest_path`, `reharvest_before_rerun_required`, `collection_truncated`, `sample_as_universe_misuse`) when supplied, and any producer progress labels only as `observed_producer_claim`. For `long_run_branch=true`, preserve `event_kind`, `long_run_role`, `run_id`, `owner_task_id`, `launch_cycle_id`, `workdir`, `output_dir`, `log_path`, heartbeat, monitor/stop commands, expected completion signal/artifacts, remaining validation, residual/harvest task linkage, and Part M harvest preflight/risk-acceptance anchors when supplied. A cycle-unreachable run additionally preserves the full content-bound reachability gate, open residual, harvest plan, and later receipt/recomputed gate; the plan binds the same run, gate digest, scale, throughput evidence, residual, and validation predicates. |
| Qualitative review packet | `$review-cycle-output-quality` | Loopback, validation-set, schema, derive, validation, report | `review_agent_count`, reviewed artifacts, quality verdict, findings, progress cap, output-delta fields, goal-axis completeness fields, instrumentation-exercise/acceptance-encoding/report-only hardening observations when relevant, Part L surface-field review fields (`surface_field_classes`, `surface_field_defect_matrix`, `field_class_map_missing`, `surface_field_review_status`) when locator-backed surface classes are available, no-overclaim flags, evidence paths. |
| Anti-loop progress gate | `$audit-cycle-loopback` | Validation and finalizer candidate assembly | Family/root keys, semantic signature, exact decision artifact ref, compatibility-filtered gate IDs, consumer invocation evidence, axis-scoped verification provenance, optional `progress_scope_contract`/`work_intent`/task-root-global observations and actual retained-change evidence, terminal outcome fields, effective dispositions, hard-stop state, and bounded prepared registry/root/seal mutations. The packet is immutable candidate evidence and carries no `authoritative_final` claim. |
| Loop-breaker packet | `python3 -m orchestrate_task_cycle progress-loop` plus orchestrator synthesis | Derive, task-pack, validation, report | Blocker/root/semantic signatures, root-axis counts, terminal quiescence/escalation gates, supplied-input delta, provider retry, command surface, sealed family, zero-candidate state. |
| Task-pack packet | `python3 -m orchestrate_task_cycle task-pack` and `$derive-improvement-task` | Derive, index, validation, report, commit | Pack ID/path/status, current item, canonical before/after coherence receipt, mutation plan, promotion origin, Markdown render, terminal blocker state, and selected disposition. Preserve task acceptance, artifact truth/semantics, pack transition, historical index, and goal readiness as separate verdict axes. |
| Repo skill gap packet | Orchestrator | Efficiency profile, validation, derive, report | Task ID, status, gap count including zero, gap packet with select/defer/reject recommendation, blockers, evidence paths. Adapter work remains derive-owned. |
| Cycle-efficiency profile | `$profile-cycle-efficiency` | Validation-scope finalize, validation, derive, report | Task ID, profile status, cycle fixed cost/basis, recommendation, execution-starvation or consolidation constraints, blockers, evidence paths. It is produced before validation/derive so it can constrain selection. |
| Validation-scope final packet | `$plan-validation-scope` | Pre-validation index, validation, issue, derive, report | `step: validation_scope_finalize`, `mode: finalize`, task/profile floor, planned and actual changed files/surfaces, non-empty required commands, prerequisites, `finalized: true`, findings/evidence. This packet, not the plan, authorizes completion validation. |
| Pre-validation index snapshot | `$manage-task-state-index` | Validation, issue, schema, derive, report | Current task ID, index status, stable snapshot ID, traceability blockers, evidence paths. It snapshots current-cycle state and does not mutate the next task. |
| Validation result | `$validate-task-completion` | Cycle-ledger finalizer | Current `task_id`, `final_candidate: true`, stable attempt identity, legacy validation/progress summaries, six evidence-bound verdict axes, exact decision artifact identity, compatible gate set, required consumer invocation receipts, axis-scoped verification provenance, optional recomputed scoped-progress/retained-change/closeout projection, blockers, and evidence paths. A pack/index transition failure or unavailable reviewer must not erase deterministic bounded task acceptance; task-local or root-only completion must not become global progress. This result is not durable current truth by itself. |
| Cycle finalization receipt | Orchestrator cycle-ledger finalizer inside `validate` | Issue, schema, derive, post-derive index, commit, dashboard, report, next cycle | `kind: cycle_finalization_receipt`, schema version, cycle/attempt ID, attempt revision, optional superseded revision, expected previous revision, `state_commit_status: committed`, closed `authoritative_final: success|failure|blocked|partial|not_evaluated`, final-candidate and six-axis digests, authoritative projection ID/digest, snapshot ref/hash, finalization token, and receipt hash. Consumers must re-verify it against the current pointer and immutable snapshot; a stale, mismatched, missing, or merely prepared receipt is non-consumable. |
| Issue packet | `$manage-implementation-issues` | Schema, derive, post-derive index, commit, dashboard, report | `issue_packet_id`, current `task_id`, lifecycle status, explicit `issue_ids` including `[]` for a reasoned no-op, `issue_provenance.source_task_id` plus validation ID/report path, blocker links, resolution evidence, skipped reason. Mutation status requires a durable issue ID/path/URL. |
| Exact-subject premise validation receipt | Deterministic `validate_exact_subject_premise` contract | Selection tick, derive re-entry | Deterministic `consumed|rejected` outcome, replay identity, current terminal-task or selection-baseline binding, freshness baseline, opaque subject/revision plus content digest, canonical writable owner/surface/authority scope, first-failing invariant evidence, and either producer/verifier/replay or source-separated-current-body evidence. Exact replay must reproduce the same receipt. The receipt persists neither source path nor source body, is not GT or authority, and only `consumed` may become a verified exact-subject watch row. |
| Derive packet | `$derive-improvement-task` | Schema reconciliation, final index, commit, dashboard, report | Re-verified predecessor receipt/projection; one hash-frozen exact-subject evidence manifest including adapter decision context and post-use seal; exactly three unique lens receipts with identical input digest and structured 0–5 candidates; zero-candidate rejection inventories; one synthesis receipt consuming all three and selecting only the exact candidate union; canonical pack disposition; disjoint `selected|terminal_wait|terminal_blocked|user_escalation`; finalized scoped-progress cap and completed-local/successor state when supplied; task-pack receipt, blockers, and evidence refs. A terminal-wait outcome additionally binds a safe authenticated selection-tick packet, watched-input digest distinct from the analysis digest, fixed executable wake-rule ID, policy-label predicate/delta IDs, watched classes, locked premise-input contract, and `last_selection_receipt`. If selection was opened by `selection_required`, persist and reopen the three lens projections plus canonical synthesis-output projection, seal `derive_selection_synthesis`, bind it to exact trigger `B` in a preliminary decision, bind persisted `B` plus that decision in a selection-decision receipt, and acknowledge `B` into input-stable `C`. Require `B` to descend from activated predecessor `A`, `C` to descend unchanged from `B`, and the closed eight-field acknowledgement receipt ID to equal `last_selection_receipt`. The final terminal result is a direct full derive object embedding `C` and the receipt-reopened analysis, never a wrapper or preliminary artifact. Exact-premise and effective-authority observations remain body-free and sticky; identical premise replay plus only nonmaterial drift is `no_op`. Prospective `goal_productive` intent never upgrades the retrospective cap. Issue-fit unavailability degrades only issue-derived candidates. Initial/bootstrap or standalone repair may reason about predecessor non-applicability but does not bypass the three-lens publication contract. |
| Terminal-wait baseline current binding | Authority-settled terminal-wait baseline owner | Selection tick, derive re-entry, audit/report | Exact non-executable terminal-task binding, direct full final source-derive result, optional transition evidence, safe selection packet, predecessor snapshot, immutable prepare/snapshot/completion/activation refs and digests, settled authority-use receipt, and expected-current CAS pointer. A rebased publication revalidates `A -> B -> C`, the selection-decision chain, exact final derive/C/receipt/analysis equality, and `expected_current_snapshot_sha256` before authority prepare. Prepare/completion is non-current. Only a verified activation exposes `.task/terminal_wait_baseline/current.json`; normal selection ticks may auto-discover it and must fail closed on task, lineage, settlement, or pointer drift. Resolve/audit outputs are body-free. |
| Commit packet | `$repo-change-commit` | Dashboard, report, closeout | `commit_role`, created/skipped/blocked status, commit hash/subject when created, skipped reason when not. |
| Dashboard result | `$render-cycle-dashboard` | Report, closeout | Current task ID, `dashboard_status`, ledger `event_count`, explicit `current_stage_event_count`, finalization receipt/token and authoritative projection digest, snapshot status, finalized validation/progress verdicts and axes, issue/commit summaries, blockers, malformed/noncanonical event visibility, dashboard path, and evidence paths. It references the verified projection and never recomputes a completion verdict. |

## Core Packet Contracts

### Scoped Progress and Retained Change

Use the existing loopback, completion, and derive result packets to keep prospective work intent separate from retrospective progress. This is an optional nested/adjacent contract on those packets, not a new phase, registry, report, or source of authority. Once any scoped-progress surface is supplied, all consumers recompute its cap conservatively and may only preserve or downgrade it.

`progress_scope_contract` binds the comparison identity:

```yaml
progress_scope_contract:
  task_family_id: <opaque_id>
  root_family_id: <opaque_id>
  global_scope_applicability: applicable|not_applicable
  global_goal_axis_id: <adapter_axis_id_or_null>
  task_terminal_predicate_id: <opaque_id>
  root_terminal_predicate_id: <opaque_id>
  global_terminal_predicate_id: <opaque_id_or_null>
  identity_basis_id: <opaque_id>
```

When global scope is `not_applicable`, both global identifiers are null and consumers evaluate only task and root scope. When it is `applicable`, both identifiers are required. `global_goal_axis_id` identifies one adapter-owned observation, not a synthetic single axis that replaces the active goal-axis set.

`work_intent` records what selection expected to attempt. It never proves what the completed attempt changed:

```yaml
work_intent:
  selected_transition_kind: <opaque_enum>
  expected_scope: task|root|global
  expected_progress_cap: semantic|root_reduction|task_local|safety|governance|none
```

`progress_observations` records actual outcomes separately:

```yaml
progress_observations:
  task_scope:
    terminal_outcome_changed: true|false|not_evaluated
    progress_class: semantic|root_reduction|task_local|safety|governance|none
  root_scope:
    comparison_status: comparable|incomparable|basis_changed|not_evaluated
    movement_status: improved|flat|regressed|incomparable|not_evaluated
    residual_relation_status: reduced|resolved|unchanged|expanded|unknown
    independent_verification_status: independently_verified|explicit_self_grounded|coupled|unverified
    observation_binding_status: exact_bound|exact_current|not_evaluated
    observation_subject_id: <stable_root_id>
    independent_observation_receipt: <closed source-and-invariant-separated before/after receipt or null>
    self_grounded_owner_id: <opaque_id_or_null>
    self_grounded_contract_id: <opaque_id_or_null>
    premise_replay_receipt_sha256: <full_sha256_or_null>
    calculation_receipt_sha256: <full_sha256_or_null>
    progress_class: semantic|root_reduction|safety|governance|none
  global_scope:
    movement_status: improved|flat|regressed|incomparable|not_evaluated
    high_water_moved: true|false
    independent_verification_status: independently_verified|coupled|unverified
    observation_binding_status: exact_bound|exact_current|not_evaluated
    axis_observations: [<adapter-owned per-axis rows>]
    progress_class: semantic|safety|governance|none
```

A root reset requires a comparable same-basis exact-bound observation, `movement_status: improved`, residual `reduced|resolved`, and `independently_verified|explicit_self_grounded` evidence. A bare `verified` alias is invalid. Independent evidence requires a closed receipt that binds the stable-root subject, distinct before/after revisions and digests, comparison basis/input digest, disjoint producer/verifier input IDs, different producer/verifier owners and invariants, the observed residual relation, and its canonical receipt hash. Explicit self-grounding instead requires `self_grounded_contract_status: verified|pass`, `premise_replay_status: verified|pass|replayed`, opaque owner/contract IDs, and complete closed contract/replay/calculation bodies with matching receipt digests; it is valid only for an owner-declared deterministic invariant whose premise and calculation are replayable. A basis migration, task/facet/report/pack rename, changed predicate value without residual reduction, or task-local pass cannot reset root stall.

An applicable global reset requires exact-bound current high-water movement, independently verified provenance, global readiness, and complete non-conflicting observation of every active measurable axis. The supplied `goal_axis_completeness_gate` must be `pass`, carry a non-empty duplicate-free `active_measurable_goals` list, an exact non-empty adapter-owned `goal_axis_map` entry for every active goal, opaque map owner/revision IDs, a recomputed map digest, a content-bound actual-consumer hook receipt, and no unobserved goals. Flattened mapped axis IDs must equal the `global_scope.axis_observations` IDs exactly; every row needs a positive premise population, exact binding, and its own closed independent-observation receipt with disjoint source IDs and invariant owners. A provenance label, scalar `axis_completeness_status`, owner label, or subset of rows is never sufficient by itself. An improved axis does not dominate an unobserved, failed, regressed, or conflicted gating axis. Root-only reduction, tests, schemas, verifiers, lifecycle state, reports, and governance changes cannot reset global stall. `terminal_outcome_changed` may support a terminal disposition but cannot turn failed/none task evidence into task-local progress. When no global scope applies, do not create synthetic global state.

Classify retained changes from the preserved change evidence rather than a task title, commit message, work-intent label, or caller-supplied boolean:

```yaml
retained_change_evidence:
  actual_changed_files: [<bounded path ids>]
  file_changes:
    - path: <workspace_relative_path>
      change_kind: added|modified|deleted
      subject_id: <opaque_id>
      before_sha256: <full_sha256_or_null_for_added>
      after_sha256: <full_sha256_or_null_for_deleted>
      receipt_sha256: <digest_of_exact_row>
  producer_body:
    subject_id: <opaque_id>
    before_sha256: <full_sha256>
    after_sha256: <full_sha256>
    receipt_sha256: <digest_bound_to_role_and_exact_row>
  producer_source:
    subject_id: <opaque_id>
    before_sha256: <full_sha256>
    after_sha256: <full_sha256>
    receipt_sha256: <digest_bound_to_role_and_exact_row>
  semantic_logic:
    subject_id: <opaque_id>
    before_sha256: <full_sha256>
    after_sha256: <full_sha256>
    receipt_sha256: <digest_bound_to_role_and_exact_row>

retained_change_classification:
  producer_body_changed: true|false
  producer_source_changed: true|false
  semantic_logic_changed: true|false
  tests_only_changed: true|false
  schema_or_verifier_only_changed: true|false
  lifecycle_only_changed: true|false
  effective_progress_class: semantic|root_reduction|task_local|safety|governance|none
```

`actual_changed_files` is only a transport echo and must equal the paths derived from content-bound `file_changes`; the list by itself is not evidence. Every row uses a safe relative path, explicit change kind, opaque subject, valid added/modified/deleted before/after relation, and a digest recomputed from that exact row. Role-level producer/body/semantic pairs also carry a digest bound to the role so rows cannot be relabeled. Missing, mismatched, duplicated, or malformed receipts are `not_evaluated`. Generic path classification recognizes test/fixture, schema/verifier, workflow-lifecycle state, documentation/governance, and implementation-source surfaces. It does not infer a domain-specific semantic axis. Tests or mixed bounded test/schema/lifecycle changes cap at `task_local`; verifier-only changes cap at `safety`; schema/lifecycle/documentation-only changes cap at `governance`; implementation-source changes cap at `root_reduction` until root evidence proves reduction; semantic/global eligibility additionally requires an actual producer-body or semantic-logic digest delta and the independent scope observations above. Mixed or unknown evidence uses the most conservative supported cap.

The existing run boundary produces these rows from actual bytes. Before execution, run `python3 -m orchestrate_task_cycle.retained_change_evidence capture --root .` and preserve the exact body-free baseline in the cycle packet. After execution, run the same module's `compare --root . --baseline-json <baseline.json>` command. A Git workspace uses the bound full object ID only to discover paths; each dirty file is hashed at capture, so an already-dirty user change is not attributed to the task. Newly dirty tracked files are compared with the bound revision and untracked files with absence. A non-Git run supplies repeated `--path` values for its bounded planned surface. Missing baseline, tampering, symlink traversal, oversized files, or an unbounded inventory fails closed to `not_evaluated`. This helper does not infer semantic logic, producer-body meaning, task success, or progress.

Closeout keeps local completion separate from review and global readiness:

```yaml
closeout_projection:
  task_acceptance: pass|fail|partial|not_evaluated
  review_axis: pass|fail|unavailable|not_applicable
  global_readiness: ready|blocked|not_evaluated
  task_lifecycle: active|completed_local|replaced
  successor_state: derived|terminal_wait|blocked_on_material_input|not_evaluated
```

`task_acceptance: pass`, `review_axis: unavailable`, and `global_readiness: blocked` are compatible. Close the bounded task as immutable `completed_local`; reviewer unavailability limits only review-backed claims. If no fresh successor evidence exists, use `successor_state: terminal_wait` (or the owning workflow's valid empty/terminal-wait pointer) and never reactivate that completed task as executable. A completed-local closeout must still classify its successor as derived, terminal wait, or blocked on a named material input.

Loopback may prepare these observations but cannot finalize them. Completion recomputes retained-change and scoped-progress claims, rejects root/global reset overclaims, and may emit global `advanced` only for the exact-bound axis-complete semantic case. Derive may keep a future `progress_kind: goal_productive` intent, but a retrospective `effective_progress_kind` cannot exceed finalized evidence. A subsequent same-root task requires finalized root residual reduction, strict prerequisite-graph reduction, fresh material input, an opened direct-producer transition, or an exact terminal/wait outcome; prospective intent alone is insufficient.

### Bootstrap Transaction Boundary

When no `task.md` exists, `initial_init` is a separate bootstrap transaction with order `context -> authority -> schema_pre_derive -> derive -> schema_post_derive -> index`. Use the explicit `bootstrap` workflow mode and `bootstrap_complete` transition. It may resolve authority, refresh relevant schema contracts, derive exactly one initial task, record its execution environment, reconcile contracts, and index the bootstrap result. Its derive contract requires the real `next_task_id` but not a fabricated `completed_task_id`. It must not emit task-bound acceptance, governance, run, completion-validation, issue, or promotion packets. The first normal cycle starts afterward from a fresh context and `repo_skill_adapter_scan`, then binds acceptance to the newly created task ID/path/fingerprint.

### Model And Effort Routing Evidence

Use [model-effort-routing.md](model-effort-routing.md), [model-effort-profiles.json](model-effort-profiles.json), and `python3 -m orchestrate_task_cycle model-effort` for delegated LLM work. Request packets carry `policy_id`, `profile_id`, `routing_tier`, requested model/effort, reason codes, signals, and routing violations. Result packets carry the same selection plus `routing_enforcement`; include actual model/effort only when the runtime exposes them.

`prompt_only` means the routing was written into the prompt but the delegation API did not enforce it. `inherited_unverified` means the child inherited an unverified runtime selection. Neither value proves configured-model execution. A result that claims `enforced` with reference-only configuration or without runtime-selectable model/effort evidence is a routing-contract defect. Deterministic scripts and direct shell commands do not need routing evidence.

Do not use delegated `ultra`. Tier 5 direction-profile routing is valid only for a target/profile allowlisted final-direction role with explicit final-direction ownership and structured evidence for every active Tier 5 signal. A direction-profile `max` result requires one bounded `exceptional_arbitration` agent, `prior_tier5_unresolved=true`, a structured `prior_tier5_evidence` object bound to the earlier `derive_synthesis` direction-profile/xhigh pass and unresolved finding, and `max_escalation_reason` describing that ambiguity.

### Gate Satisfiability

Fail-closed gates named by `task.md`, caller packets, or command harnesses must be checked before the gate is evaluated. The repository or environment adapter may expose:

```python
gate_satisfiability(gate_id, env, **context) -> {
    "satisfiable": bool,
    "reason": str,
    "alternative_evidence_source": optional[str],
}
```

`$run-task-code-and-log` records one `gate_satisfiability` entry per prechecked gate: `gate_id`, `satisfiable`, `reason`, `evidence_source`, `alternative_evidence_source`, and `classification`.

If `satisfiable=false` and no alternative source exists, classify the run as `self_inflicted_gate_defect`. Consumers must route a gate-contract/code correction task or `user_escalation`; they must not schedule another same-gate environment recheck.

For pre-execution gate artifacts, `$run-task-code-and-log` may also include `gate_selfcheck` entries with `gate_id`, `blocked_pre_exec`, `repo_owned_pre_exec_blocker`, `contradicting_evidence`, `trusted_evidence_source`, `prior_pass_observed`, `status`, `classification`, and `alternative_evidence_source`. Treat `classification: self_inflicted_gate_defect` as valid only when repository-owned provenance is confirmed. Treat `status: warn_missing_repo_owned_confirmation` as advisory until `$audit-cycle-loopback` or the adapter confirms repository-owned blocker provenance.

### Failure Autopsy

When execution fails with a nonzero exit, traceback, runtime exception, or provider/HTTP-style error, `$run-task-code-and-log` should include scalar-safe diagnostics only:

- `error_type`
- `exception_class`
- `traceback_last_frame`
- `http_status`
- `missing_env_key_names`
- `provider_request_count`
- `provider_status`
- `failure_class`
- `provider_response_empty`
- `provider_response_parse_failed`
- `mitigations_attempted`
- `mitigations_unavailable`
- `classification`
- `alternative_evidence_source`
- `gate_selfcheck`
- `execution_stage_ladder_status`
- `execution_stage_ladder`
- `last_successful_stage`
- `failure_surface_stage`
- `post_failure_scalar_diagnostics`
- `diagnostics_unavailable`
- `diagnostics_unavailable_reason`
- `runtime_config_echo`
- `config_origin`
- `config_overrides`

Do not persist raw prompts, provider bodies, generated bodies, stdout/stderr bodies, source bodies, credentials, tokens, or secrets in the autopsy packet.

When an execution stage ladder is available, `last_successful_stage` and `failure_surface_stage` are required for downstream H2 counting. If safe post-failure scalar/enum diagnostics cannot be collected, the packet must say `diagnostics_unavailable=true`; no-body and redaction policy still allows scalar diagnostics such as stage, enum status, count, HTTP code, and exception class.

When runtime config echo is available, keep only scalar/enum effective settings, each field's `config_origin`, and derived `config_overrides`. A `code_default` override is routing evidence for self-inflicted gate/default repair when it explains the blocker; it is not completion evidence.

### Qualitative Review

The qualitative review packet must report exactly one read-only reviewer agent when delegation is available. It must include `review_agent_count: 1`, reviewer routing, reviewed artifacts, direct read scope, qualitative findings, direction recommendations, blocker taxonomy delta, no-overclaim flags, evidence paths, and active advice usage or disposition.

When output-delta evidence exists, include explicit values for `output_delta_status`, `changed_vs_previous`, `semantic_progress`, `produced_domain_delta`, `metadata_only`, `effective_progress_kind`, and `progress_cap`. Omit neither false nor not-applicable values.

### Anti-Loop Progress Gate

The canonical schema for `anti_loop_progress_gate` is owned by `$audit-cycle-loopback` and documented in [packet-schema.md](../../audit-cycle-loopback/references/packet-schema.md) when that skill is available, plus [anti-loop-progress-gates.md](anti-loop-progress-gates.md) for orchestrator policy.

Consumers must preserve:

- family keys: `family_key`, `root_key`, `root_family_key`, `blocker_root_family`
- progress fields: `changed_vs_previous`, `semantic_progress`, `authoritative_semantic_progress`, `terminal_outcome_changed`
- terminal outcome fields: `terminal_outcome_key`, `terminal_outcome_family_key`
- constraint fields: `effective_allowed_dispositions`, `disposition_intersection_basis` including optional `allowed_task_kinds`, `hard_stop_required`, `evidence_class`
- root-cause fields: `repo_owned_source_roots_status`, `root_cause_unverified_hypotheses`, `root_cause_duplicate_hypotheses`, `untried_actionable_root_cause_exists`, `untried_root_cause_hypotheses`, `hypothesis_exhausted`, and provenance-hardened ledger entries
- adapter/chain fields: `adapter_mandate_required`, `adapter_contract_unmet`, `adapter_missing_streak`, `adapter_loaded`, `adapter_registered`, `adapter_wiring_defect`, `adapter_wiring_gate`, `cumulative_goal_distance_stalled`, `cumulative_goal_distance_stall_streak`, `chain_stall_forced_retarget_gate`, `forced_selected_task`, `forced_selected_task_options`, `untried_veto_overridden_by_chain_stall`
- reachability/metric fields: `acceptance_envelope_contract`, `envelope_below_floor`, `acceptance_unreachable_under_frozen_config`, `relaxation_or_escalation_required`, `oracle_metric_validity_gate`, `primary_metric_gate`, `primary_metric_stalled`, `primary_metric_zero_movement_streak`, and `c4_user_escalation_backstop_required`
- gate completeness fields: per-gate `evaluation_status: pass|fail|not_evaluated`, `acceptance_verifier_not_evaluated`, `unverifiable_acceptance_contract`, and `metric_verifier_not_evaluated`
- verifier/provenance fields: `coupled_verifier_gate`, `pass_with_coupled_verifier`, `changed_verifier_source_paths`, `evidence_provenance_gate`, `independently_verified_fields`, `producer_attested_fields`, and `attested_only_movement`
- count-key hygiene fields: `legacy_family_key`, `raw_root_family_key`, `terminal_outcome_key`, `terminal_outcome_family_key`, `terminal_outcome_family_fallback_applied`, `root_dominant_parameter_key`, and any `generation_dependent_count_key`/trace-only finding supplied by loopback
- failure-surface fields: `execution_stage_ladder_status`, `execution_stage_ladder`, `last_successful_stage`, `failure_surface_stage`, `failure_surface_count_key`, `failure_surface_stage_gate`, `terminal_classification_stage_contradiction`, `terminal_classification_invalid_for_counting`, `same_input_contract_gate`, and `same_input_contract_violation`
- diagnostics/instrumentation fields: `diagnostics_unavailable`, `diagnostics_unavailable_streak`, `diagnostics_unavailable_gate`, and `instrumentation_supply_required`
- evidence lifecycle fields: `instrumentation_exercise_required`, `instrumentation_exercised`, `instrumentation_field_map`, `derived_from_existing_artifacts`, `acceptance.quantifiers`, `evidence_kind`, `acceptance_diluted`, `verifier_surface_hardening`, `guard_stacking_cap_reached`, `target_artifact_paths`, `run_disposition`, `candidate_degraded`, `runtime_config_echo`, `config_overrides`, `execution_scope_applicability`, exact `required_input_binding`, content-bound `producer_run_receipt`, and `execution_starvation_status`
- Part J fields: `acceptance_scenarios`, structured `premise_receipts` (or structured `scenario_coverage` alias), recomputed `scenario_uncovered`, recomputed `acceptance_inversion`, `command_argv` or `command_provenance_missing`, `blocker_actionability_gate`, repeated `blocker_opacity`, `instrumentation_first_fire`, `first_fire_consumed_item_id`, `outcome_variance`, `predetermined_unreachable`, and `floor_edge_envelope`
- Part K fields: `expectation_anchor`, `designated_baseline`, `expectation_anchor_missing`, `expectation_lineage_stale`, `parity_axes`, `parity_axis_status`, `parity_unverified`, `adoption_axis_classification`, `required_output_classes`, `majority_vote_adoption`, `provisional_adoption`, `measured_but_disqualified`, `required_evidence_resolution`, `observed_evidence_resolution`, `resolution_downgrade`, `surrogate_resolution_basis`, `report_key_divergence`, and duplicate report-key path/value evidence
- Part L fields: `production_lane_identity`, `current_decision_lane`, `lane_identity_missing`, `pass_on_stale_lane`, `decision_metadata_revision`, `stale_measurement_artifact`, `axis_starved_by_missing_producer`, `producer_supply_required`, `portfolio_quota_exceeded`, `unreachable_within_cycle`, `long_run_launch_required`, `basis_overclaim`, `actual_basis_class`, `field_class_map_missing`, and `surface_field_defect_matrix`
- Part M fields: `harvest_gate_inventory`, `harvest_contract_preflight`, `harvest_gate_unaudited`, `harvest_risk_accepted`, `lane_incompatible`, `scale_incompatible`, `contract_conflict`, `execution_cost_scalar`, `high_cost_artifact`, `destructive_disposition_requested`, `destructive_disposition_blocked`, `quarantine_required`, `failure_check_provenance`, `reharvest_path`, `reharvest_available`, `reharvest_before_rerun_required`, `rerun_before_reharvest`, `validation_predicate_contract`, `producer_directives`, `mutually_unsatisfiable_contract`, `closed_world_collection_consumption`, `collection_truncated`, `sample_as_universe_misuse`, `full_collection_required`, and `sample_consistency_only`
- verification source fields: `verification_source_separation_gate`, `verification_input_paths`, `verified_artifact_paths`, `independent_source_separation_status`, and `independently_verified_downgraded_fields`
- envelope thaw fields: `envelope_thaw_item_required`, `envelope_thaw_item`, `thaw_condition`, `thaw_schedule`, and `envelope_thaw_streak`
- goal-axis completeness fields: `goal_axis_map`, `unobserved_goal_axes`, `pass_with_unobserved_axes`, and `goal_axis_completeness_gate` when review or the adapter supplies them
- residual-gap cost fields: `cycle_fixed_cost`, `alternative_cycle_cost`, `marginal_gap_value`, `marginal_value_per_cycle_cost`, `alternative_value_per_cycle_cost`, and `residual_gap_cost_policy` when profile/normalize/derive supplies them
- truth-source fields: `producer_progress_claim_fields`, `observed_producer_claim`, and `split_brain_progress_claim`
- warn-only fields: `partial_progress_axes_gate` and `advice_freshness_gate.gate_result_regression_stale`
- mutation fields: `blocker_mutation_kind`, `root_dominant_parameter_key`, `forward_mutation_vacuous`, `forward_mutation_budget_remaining`, `force_implementation_cycle`
- evidence: findings and `evidence_paths`

### Acceptance Provenance

When task direction originates in advice, issue, task pack, or user steering with a measurable target, `$task-doctor` and `$derive-improvement-task` must preserve a directive-to-item mapping through `scope_fidelity`. `$validate-task-completion` owns the close-time comparison against the original target.

Generic fields:

- `scope_fidelity.directive_id`: stable source directive identifier.
- `scope_fidelity.original_target`: abstract measurable target. Project-specific metric definitions and thresholds belong in the advice packet, task pack, repository adapter, or project-owned contracts.
- `scope_fidelity.item_acceptance`: acceptance copied from or traceable to the original target.
- `scope_fidelity.acceptance.quantifiers`: original counts, rates, run counts, row counts, disjointness predicates, or other measurable relation predicates copied without reinterpretation.
- `scope_fidelity.acceptance.evidence_kind`: `live_run`, `derived_artifact`, `code_contract`, or `report_only`; a live-run requirement needs a satisfying run id after item creation.
- `scope_fidelity.narrowed`, `narrow_reason`, and `residual_item_id`: explicit descope record and open residual scope.
- `acceptance_provenance_gate.target_met`: validation result comparing actual achievement to the original target.
- `acceptance_provenance_gate.acceptance_diluted`: true when the item was closed against a weaker target.
- `acceptance_provenance_gate.explicit_descope_decision`: true only when a reason and residual item/link exist.

Consumers must not mark a measurable item consumed, applied, or complete when `acceptance_diluted=true`. A narrowed item may be useful progress, but it remains `partial` unless the original target is met or the residual target stays open under an explicit descope decision.

Consumers must not satisfy `evidence_kind=live_run` with a derived artifact, code contract, or report-only matrix. If a live-run criterion cannot be executed, preserve residual scope, explicit descope, terminal blocker, or user escalation.

### Advice Clause Consumption Receipts

Advice-container lifecycle is not clause consumption. The canonical actual consumer is the existing derive boundary: freeze the exact sorted actionable clause set, packet digest, clause-source digests, and clause-set digest in the shared manifest; require all three lens output hashes to cover that exact set with agent/receipt-bound dispositions and evidence; then require synthesis to consume the exact three assessment digests per clause and bind its reconciliation set and agent/receipt IDs. Persist each closed lens receipt projection containing identity/status/input/ref/digest fields plus the exact output, and the canonical synthesis projection, as four distinct compact canonical JSON files under `.task/cycle/<cycle-id>/agent_receipts/`. A `wired` row is valid only when validation receives the trusted workspace root, reopens those exact regular non-symlink files without path escape, matches their bytes/digests, and cross-binds the resulting `durable_runtime_artifact_bound` projection to the exact decision identity. Result-authored roots, caller-authored refs, booleans, missing files, symlinks, or recomputed hashes do not create wiring, and non-derive legacy rows remain pending.

`verified` additionally requires a `skill_forward_test` row with distinct happy and negative producer-agent artifacts bound to the current clause-set and synthesis-output digests. Persist each exact producer output and complete outer forward receipt as separate canonical JSON files in the same cycle-local store; validation reopens them before accepting the path. Each outer receipt embeds the verifier receipt; all two producer, two verifier, and two invariant-owner IDs are distinct, as are all four producer/verifier receipt IDs. Verifier input IDs are disjoint from producer preconditions/evidence, and invariant IDs are disjoint from producer preconditions. Both paths must echo the exact decision identity, scenario/preconditions, expected/observed decisions, and evidence IDs, and the negative expected/observed state must differ from happy state. Reused IDs, coupled inputs/invariants, a no-op fault, stale hashes, deferred verification, self-hashed booleans, nonexistent/arbitrary refs, path escape, or symlinks cannot advance `wired` to `verified`.

This store proves exact durable content and distinct declared receipt/agent IDs. It does not cryptographically prove that IDs came from different child processes. The derive workflow must still perform the specified delegation; when the runtime cannot supply those agents or persist their exact outputs, retain `pending`/`wired` instead of synthesizing missing identities.

When the orchestrator context supplies an applicable active advice packet with `canonical_actionable_clause_ids`, every advice-consuming result must cover that set exactly once and echo both `advice_packet_digest` and its clause-assigned source digest. Zero, missing, duplicate, external, or digest-mismatched rows are blocking at validation/report and whenever a result claims positive advice/successor consumption; otherwise preserve them as pending debt. No packet or `applicability: not_applicable` retains fail-quiet behavior.

The optional `finalized_advice_clause_states` recurrence audit runs only when finalized rows explicitly supply `recurrence_id`, `clause_id`, `finalized_clause_state`, and `recurrence_observed`. Missing finalized state fails quiet. A recurring non-verified clause emits warning-level `unconsumed_advice_regression` debt and cannot manufacture GT, authority, pass, or semantic progress.

When adapter `residual_gap_policy` is available, consumers should preserve residual-gap fields supplied by normalize/derive such as `residual_gap_ratio`, `residual_gap_policy`, `marginal_repair`, and `descope_with_residual`. A residual gap below the adapter threshold should default to explicit descope with residual scope plus the next capability-ladder rung rather than another same-gap repair.

### Acceptance Scenario Coverage

When normalized acceptance contains a scenario contract of the form premise class -> expected terminal state, the validation-set plan must require at least one fixture or live run whose scalar inputs satisfy the premise. The run owner emits the actual-invocation receipt. Completion validation recomputes coverage and inversion from its structure; it never accepts a caller boolean as a substitute.

Generic fields:

- `acceptance_scenarios`: list of `{scenario_id, premise_predicate_id, expected_terminal_state, applicability?}`. The bounded safe `premise_predicate` alias remains accepted. A declaration with `applicability: not_applicable` is excluded from receipt coverage without failing unrelated validation.
- `premise_receipts`: list of actual invocation rows. The existing `scenario_coverage` name remains a compatibility alias only when each row carries the same full structure.
- Each receipt contains `scenario_id`, `premise_predicate_id`, closed `premise_evaluation_status: pass|fail|not_evaluated|not_applicable`, non-negative integer `premise_satisfying_item_count`, closed `invocation_kind: cli|api|ui|notebook|remote|other`, opaque `invocation_descriptor_id`, non-empty opaque `input_revision_ids`, full `result_digest`, expected/observed terminal states, `run_id`, and an opaque evidence reference.
- Invocation evidence always includes ordered non-empty typed `invocation_component_ids` and a recomputed `canonical_invocation_digest` over contract version, exact scenario/predicate, invocation kind/descriptor, ordered components, and input revisions. CLI components begin with `cmd:<opaque-id>` and preserve logical order through bounded `subcommand:`, `flag:`, `mode:`, and opaque `ref:` tokens. If a CLI argv echo is retained, it must exactly equal those typed components. API/UI/notebook/remote components use bounded action/parameter/ref IDs in their transaction order. Raw paths, source locators/entities, credentials, bodies, `--key=value`, ellipses, and untyped values are invalid; use opaque references. A well-shaped but arbitrary 64-hex string is not evidence because validation recomputes the digest.
- `premise_evaluation_status: pass` must agree with `premise_satisfying_item_count > 0`; every other status must agree with count `0`. A legacy `premise_satisfied` field, when present, must be a consistent boolean but never establishes coverage by itself.
- `scenario_uncovered` and `acceptance_inversion` are derived summaries. Completion validation recomputes them from exact scenario/predicate binding and matching expected/observed terminal state. A conflicting caller summary blocks a positive close rather than overriding the receipt.

Green tests, renamed tests, assertion text, high test count, or verifier pass rate do not override this gate. Missing/malformed/wrong-premise receipts route back to invocation or validation-set supply as `not_evaluated`; a valid opposite terminal observation sets `acceptance_inversion`, fixes the verdict at `partial`, and routes implementation/code contract repair. Receipt findings expose only opaque IDs, row indices, and invalid field names.

### Command Provenance And Blocker Actionability

Live execution packets must preserve the full argv once in body-free form. Redaction may mask values, but it must not remove argument names. If only a summarized command, `...`, or missing flags are recorded, set `command_provenance_missing=true`; the run may still be evidence for other facts but cannot be a baseline, A/B, comparison, or reproduction source.

Gate and validator blockers should be actionable. A blocker reason code should carry the violated abstract relation, observed scalar values, expected relation, and, when possible, a minimum input delta. If only a state name is returned, set `blocker_opacity=true`. Repeated opacity for the same gate is a derive candidate for blocker-contract repair; it is warn-only until the repeated condition exists.

### Long-Running Execution Branch

Use `step: run` for every long-running event. Set `event_kind` to `long_run_launch`, `long_run_monitor`, `long_run_harvest`, or `long_run_finalize`, and set `long_run_role` to `launch`, `monitor`, `harvest`, or `finalize`. Do not add a new canonical phase.

Required fields for `long_run_branch=true` are `run_id`, `owner_task_id`, `launch_cycle_id`, `command_argv`, `workdir`, `output_dir`, `log_path`, `startup_or_heartbeat_evidence`, `monitor_command`, `stop_command`, `remaining_validation`, `expected_completion_signal`, and `expected_completion_artifacts`.

`long_run_launch` can satisfy only the workflow handoff objective. If the original task required live-run/domain evidence, preserve it through `scope_fidelity`, `residual_item_id`, or `harvest_task_id`; do not mark the original target consumed from launch/startup evidence. `completed_pending_validation` means terminal artifacts appear to exist, but harvest validation still owns completion, output-delta, review, loopback, and issue/commit decisions.

### Stochastic Feasibility And First-Fire Credit

When adapter or caller evidence reports `outcome_variance` for a stochastic producer, exact equality contracts and envelope/floor slack smaller than observed variance are contract feasibility problems. Use `predetermined_unreachable` for exact-match contracts and `floor_edge_envelope` for too-small slack. Derive should route to interval/ratio/intersection criteria, envelope expansion, explicit residual descope, terminal blocker, or user escalation rather than another retry.

When a run first produces non-empty scalar evidence for supplied instrumentation, record `instrumentation_first_fire=true`. This credit is a positive evidence delta even when the run is failed or degraded, but it may consume only one workflow item and cannot also satisfy goal progress or the original instrumentation-supply item.

### Expectation And Comparison Lineage

Output-derived scalar expectations must carry `expectation_anchor` and, when supplied, current `designated_baseline`. If the anchor surface is superseded, set `expectation_lineage_stale`; derive must rebaseline or fail closed before live execution. Missing anchors are warning-level through `expectation_anchor_missing`, but consumers must not describe the expectation as lineage verified.

Comparison or adoption tasks must carry `parity_axes` with each axis classified as `controlled`, `measured`, or `unknown`. `unknown` axes force `parity_unverified` and make final adoption/baseline promotion invalid until resolved, explicitly provisional, terminal-blocked, or escalated. Axis definitions and echo/equality checks are adapter-owned.

Adoption axes must be classified before measurement as `gating` or `tradable`, using adapter/caller `required_output_classes` or equivalent goal-contract evidence. A failed gating axis makes the candidate `measured_but_disqualified` and blocks final adoption regardless of tradable-axis wins. Missing classification makes majority-vote adoption only provisional.

When a contract requires id, row, element-set, or intersection evidence but the implementation reports a count, ratio, ordinal, or other lower-resolution surrogate, preserve `resolution_downgrade` and `surrogate_resolution_basis`. First occurrence is provisional/warn evidence; repeated same-contract downgrade should route resolution restoration or contract revision.

When one report contains the same terminal key at multiple JSON paths with divergent values, set `report_key_divergence=true`. Result contracts and validation must block pass/close/adoption/baseline/comparison consumption of that report until the report is repaired or a single source with matching values is declared. Matching duplicate terminal keys are warn-only schema debt.

### Lane Lineage And Premise Supply

Capability, validation, comparison, adoption, and qualitative-review decisions must preserve what artifact lane and premise supply they actually consumed.

Generic fields:

- `production_lane_identity`: opaque key for the artifact or output lane validated by a verifier, review, or metric.
- `current_decision_lane`: opaque key for the lane currently under capability, adoption, baseline, comparison, or next-rung decision.
- `lane_identity_missing`: true when either lane hook is absent; this is warning evidence unless the task explicitly requires lane binding.
- `pass_on_stale_lane`: true when a verifier/review pass applies to a different lane than the current decision target.
- `decision_metadata_revision`: true when a decision update only relabels stale artifacts after relevant upstream production contract changes.
- `axis_starved_by_missing_producer`: true when a gating axis is zero/unmet because the producer path that should populate it is absent or unexercised.
- `portfolio_quota_exceeded`: true when recent verifier/guard/report/metadata work exceeds the adapter-owned verifier:producer quota.
- `unreachable_within_cycle`: true when required target scale exceeds observed cycle throughput times the cycle cap.
- `basis_overclaim`: true when a metric's claimed basis class is not derivable from consumed input classes.
- `surface_field_defect_matrix`: scalar counts by producer-written field class and defect class from locator-backed qualitative review.

Consumers must not use `pass_on_stale_lane` as current-lane capability, adoption, comparison-winner, or next-rung evidence. They may record the pass as historical or contract evidence and keep current-lane rerun/residual work open.

Consumers must treat `decision_metadata_revision` as governance or metadata progress only. It cannot consume a measurement/adoption pack item, reset high-water movement, or satisfy `goal_productive` unless a fresh current-lane run id exists or the packet proves the upstream change cannot affect the measured axis.

When `axis_starved_by_missing_producer=true`, derive should choose producer-supply work before adding another verifier, guard, consistency check, or report for the same axis. Those verifier-like items collapse under verifier-surface hardening until producer supply fires.

When `portfolio_quota_exceeded=true` and the adapter explicitly supplies `portfolio_quota_mode=restrict`, derive is limited to producer, envelope, long-run, descope-with-residual, terminal blocker, or user escalation. Default quota evidence without an adapter hook is warn-only.

When `unreachable_within_cycle=true`, derive must route to long-run launch with monitor/harvest plan, throughput improvement, explicit descope-with-residual, terminal blocker, or user escalation. `$monitor-running-execution` and later harvest validation own completion evidence; launch/startup evidence does not consume the original domain acceptance.

When `basis_overclaim=true`, downgrade affected metric fields to the actual consumed-input class and treat them as producer-attested or otherwise non-authoritative under F2. Honest downgrade of the basis label is not a regression.

When `surface_field_defect_matrix` has nonzero counts, loopback and derive should feed those counts into root-family and producer-supply routing. The review packet must not store raw excerpts unless authority explicitly allows them; absent `surface_field_classes` fails quiet.

### Execution Context Reaudit

Use [execution-context-contracts.md](execution-context-contracts.md) whenever Part M launch, terminal disposition, predicate/directive, or collection-consumption fields appear in a packet. These are in-place revisions of existing long-run, validation, derive, schema, and result-contract decisions; do not create a new canonical phase.

Generic fields:

- `harvest_contract_preflight`: prelaunch harvest-gate compatibility packet for cycle-unreachable long runs.
- `harvest_gate_unaudited`: true when an adapter inventory was absent; warn/fail-quiet unless acceptance declares the preflight required.
- `harvest_risk_accepted`: explicit acceptance of a known harvest risk when launch proceeds before repair.
- `lane_incompatible`, `scale_incompatible`, `contract_conflict`: non-degradable harvest preflight findings.
- `high_cost_artifact`, `destructive_disposition_blocked`, `quarantine_required`, `failure_check_provenance`, and `reharvest_path`: terminal disposition and reharvest routing fields.
- `validation_predicate_contract`, `producer_directives`, and `mutually_unsatisfiable_contract`: predicate/directive compatibility fields.
- `closed_world_collection_consumption`, `collection_truncated`, `sample_as_universe_misuse`, and `full_collection_required`: closed-world collection-consumption fields.

Consumers must route non-degradable harvest incompatibility to repair/mitigation or explicit `harvest_risk_accepted=true` before long-run launch. High-cost non-safety artifacts must be quarantined rather than destructively overwritten, and available reharvest should precede a new full rerun after verifier/governance failures. `mutually_unsatisfiable_contract=true` blocks consuming either predicate or directive as valid until reconciliation, residual descope, terminal blocker, or user escalation. `sample_as_universe_misuse=true` blocks pass/close consumption until a full collection is supplied or the contract is revised to sample-only consistency.

### Acceptance Envelope And Verifier

When normalized acceptance has a measurable target and a domain adapter exposes `min_envelope_for(target)`, the acceptance packet should carry `acceptance_envelope_contract` with abstract `envelope_floor`, `deficit_axis`, comparison status, and evidence paths. Project-specific metrics, capacities, model limits, paths, and thresholds remain in the adapter or project-owned contracts.

If `envelope_below_floor=true`, consumers must treat the selected or executed slice as acceptance-incomplete. They may select envelope expansion, explicit descope with residual scope, or user escalation; they must not lower the target silently or reclassify the planned failure as a new prompt/tool/schema blocker. If the adapter hook is absent, fail quiet and keep existing acceptance rules.

If reachability evidence says the target is unreachable under a frozen envelope, consumers must preserve `acceptance_unreachable_under_frozen_config`, `frozen_envelope`, `deficit_axis`, and either `envelope_thaw_item` with thaw condition/schedule or `envelope_thaw_item_required=true`. Derive and validation must not consume another envelope-internal micro-repair as `goal_productive` until thaw, constraint relaxation, residual descope, terminal blocker, or user escalation is recorded.

When normalized acceptance has a measurable target and a domain adapter or caller packet exposes a required live verifier, the acceptance packet should carry `acceptance_verifier_contract` with abstract `required_verifier`, `verifier_required`, `evaluation_status`, and evidence paths. A required verifier without an explicit passing evaluation is `not_evaluated`, not pass. If the required verifier is `not_evaluated`, consumers must treat the target as `unverifiable_acceptance_contract=true`: useful work may remain partial, but the original target cannot be consumed or marked applied without verifier implementation, explicit descope with residual scope, terminal blocker, or user escalation. If the target-to-verifier mapping hook is absent, fail quiet and keep existing acceptance rules.

If measurable acceptance names or depends on a gate whose SKILL.md contract lists required adapter hooks, those hooks are verifier completeness for that target. When a required hook is absent, failed to load, or returns `evaluation_status: not_evaluated`, normalize the target as `unverifiable_acceptance_contract=true` through the same E2 path. Do not count a gate's fail-quiet behavior as pass once acceptance declares that gate required.

### Goal-Axis Completeness

When a qualitative review is used as pass evidence for a measurable goal, the review or caller packet may carry `goal_axis_map` from the repository adapter. Consumers check only the formal condition that every active measurable goal maps to at least one `quality_vector` axis. If any goal maps to zero axes, the review packet must set `pass_with_unobserved_axes=true` and list `unobserved_goal_axes`; derive and validation must treat the review as not-pass for those goals. Preserve adapter axis-supply work, explicit descope with residual scope, terminal blocker, or user escalation. If `goal_axis_map` is absent, fail quiet to legacy review semantics without inventing domain axes.

G-COV producers and consumers use `quality_delta_policy` as the sole metric-key/alias contract. The normalized shape is `keys: [string]`, `aliases: {string: [string]}`, and `supplied: bool`. `python3 -m orchestrate_task_cycle output-delta` accepts it from the repository contract or provider payload; loopback accepts it from the domain adapter hook; progress-loop detection accepts it from the packet. Without it, all three emit or preserve `not_evaluated` rather than inventing metric axes.

### Residual Gap Cost Ratio

When `residual_gap_policy` is available and a cycle-efficiency profile supplies cost evidence, consumers should compare residual-gap repair by value per cycle cost. Generic fields are `marginal_gap_value`, `cycle_fixed_cost`, `marginal_value_per_cycle_cost`, `alternative_expected_value`, `alternative_cycle_cost`, and `alternative_value_per_cycle_cost`. If cost evidence is absent, use denominator `1` and preserve legacy F3. A below-policy cost ratio defaults to explicit descope-with-residual plus the next capability rung unless the adapter records a higher value case.

### Progress Truth-Source Seal

Producer artifacts and run logs may contain progress fields such as `progress_kind`, `effective_progress_kind`, `progress_verdict`, `goal_productive`, or `produced_domain_delta`. `$run-task-code-and-log` must store these under `observed_producer_claim` using adapter `producer_progress_claim_fields()` when available. Downstream loopback, derive, and validation must not read those claims as authoritative progress.

Authoritative progress must come from adapter-recomputed quality/substance/structure evidence, strict output-delta fields, or validation gates. If producer self-report conflicts with recomputed evidence, set `split_brain_progress_claim` and use the conservative recomputed verdict.

When `evidence_provenance_gate` is present, authoritative high-water and `goal_productive` evidence are limited to `independently_verified_fields`. `producer_attested_fields` and `attested_only_movement` are trace evidence only and must not reset stalls or satisfy progress requirements.

`independently_verified_fields` are authoritative only when H4 source and invariant separation both hold. Verification inputs must be disjoint from producer inputs/artifacts, and the axis receipt must name different bounded `producer_invariant_owner_id` and `verifier_invariant_owner_id` values with `invariant_separation_status=independent`. Different files or function names alone do not establish independence. Missing, overlapping, shared-owner, or unknown separation moves the affected fields to attested evidence through `independently_verified_downgraded_fields`, even when a zero-disagreement result is reported. `self_grounded` is valid only for an explicit `axis_scope=root_local` structural check and never supplies global semantic evidence.

### Refactor And Behavior-Change Evidence

When a behavior-preserving refactor or consolidation claims structural reduction, `$audit-cycle-loopback` may pass adapter-supplied `structure_metrics_gate.structure_high_water_moved`, `structure_high_water_key_scope`, `structure_global_invariant_metrics`, `improved_structure_axes`, `refactor_effect_required`, and semantic metrics such as shard count, coupling signal count, duplicate definition count, depth, fan-out, reuse ratio, and max LOC. `$validate-task-completion` must not complete a structural-reduction task from module creation, file-count growth, relocated helpers, token/pattern avoidance, producer self-reports, or green tests alone when that gate says high-water did not move. If `structure_high_water_key_scope=global_invariant`, selected-scope improvement cannot satisfy global structure progress while global invariants are flat.

When `disposition_intersection_basis` includes `allowed_task_kinds`, `$derive-improvement-task` must emit `selected_task_kind` and choose one of those kinds for `goal_productive`. Label-only `goal_productive` is a contract failure. When `forced_selected_task` is present, the selected task kind must match it unless the result is terminal/user escalation with evidence that the forced option became unactionable.

When a task changes runtime gate, routing, validator, dispatch, or judgment behavior, `$validate-task-completion` must require fresh live before/after evidence, or record an explicit defer gate that leaves follow-up work open. Unit/static evidence alone does not complete behavior-change work whose purpose is to change live outcomes.

### Loop Breaker And Terminal Gates

`python3 -m orchestrate_task_cycle progress-loop` produces or contributes loop-breaker evidence. The derive packet must carry normalized `blocker_signature`, additive `semantic_signature`, suffix-normalized `root_key`, root-axis counts, compared cycle IDs, positive input delta status, provider reattempt/mitigation gate status, command-surface budget, sealed-family matches, and zero-candidate state.

When `terminal_escalation_gate.escalation_required=true`, the derive result must emit `selected_task_source: user_escalation`, `forced_disposition: user_escalation`, `terminal_recheck_streak`, `required_missing_input_count: 1`, exactly one `required_missing_input.kind`, and `.task/sealed_blocker_families.json` update or mutation-plan evidence.

When terminal blocking is selected, use the `terminal_blocker` shape in [task-pack-workflow.md](task-pack-workflow.md). Do not write another non-terminal recheck in a sealed family without a supplied input delta, authority change, external-state change, or verified unexhausted root-cause repair.

Terminal eligibility is not one residual label. For each terminal-relevant item, preserve independent `authority_status`, `local_resolution_status`, `external_dependency`, and `risk_or_cost_confirmation` axes plus opaque evidence IDs and explicit `classification_valid=true`. Every non-unverified governance assertion and both values of a verified local-capability assertion require non-empty bound evidence; consumers must not default an omitted validation flag or evidence list to valid. Local diagnostic, deterministic repair, bounded producer work, or current-envelope mutation routes an in-scope engineering task and prohibits goal-terminal classification. An already-authorized external `waiting_state` routes the existing monitor/harvest owner without asking for new input. Verified new authority or risk/cost confirmation routes a bounded user escalation. Missing rows, malformed evidence, or any `unverified` axis route classification repair; current-task close and task-pack exhaustion are not substitutes.

### Decision Revision Freshness

When a domain artifact has revision lineage, preserve `decision_freshness_lineage` with the exact decision subject, latest implementation revision, latest compatible deliverable revision, and latest semantically reviewed deliverable revision. Revision IDs from implementation and deliverable/review stores are not comparable strings. Bind implementation→deliverable compatibility and deliverable→semantic-review coverage with exact-subject, endpoint-bound, content-hashed relation receipts. `all_current` means both relations reach the declared current endpoints; it does not mean all revision IDs are equal. `implementation_ahead_of_artifact` means the compatibility receipt still points from an older implementation revision. `artifact_ahead_of_review` means the review receipt covers an older deliverable revision. The former makes report/fixture/metadata movement non-semantic and routes bounded producer or consumer refresh; the latter preserves artifact production while withholding only review-backed readiness. `no_domain_artifact` is valid for non-domain work but cannot support semantic artifact claims.

If the exact decision identity declares body, production-lane, or producer-run dimensions applicable, current evidence is content-bound. A producer-run dimension requires a measurement receipt with the same subject and implementation revision, a fresh run ID, output fingerprint, and receipt digest. Body/lane-only applicability may use a no-impact receipt only when it binds the same subject/revision, named predicate, evidence digest, and receipt digest. Scalar or truthy no-impact flags never satisfy freshness.

Legacy decision identities remain readable for diagnostics and initial/bootstrap routing but are revisionless by themselves. Before contract v0 or a flat v1 identity controls semantic progress, completion, pack consumption, hard stop, or terminal state, supply `legacy_revision_bridge_receipt` with exactly these fields: `bridge_contract_version`, `bridge_status`, `artifact_id`, `artifact_class`, `artifact_sha256`, `revision_id`, `subject_digest`, `lineage_id`, `freshness_status`, `evidence_ref`, `evidence_sha256`, and `receipt_sha256`. Require version `1`, status `revision_bound`, freshness `current`, exact id/class/hash equality with a scope-verified non-advisory legacy reference, `subject_digest == artifact_sha256`, and a canonical SHA-256 over every receipt field except `receipt_sha256`. Missing or extra fields, stale freshness, identity drift, malformed evidence bindings, or digest tampering block positive consumption. Do not require this bridge for non-positive legacy diagnostics or reasoned initial/bootstrap routing, and prefer explicit applicability-aware identities for new producers.

### Repo Adapter And Gap Packets

Repo adapter packet details are owned by [repo-local-skill-adapters.md](repo-local-skill-adapters.md). The orchestrator passes adapter packets as non-GT capability evidence only.

`repo_skill_gap_packet` should include repeated domain lookup, repeated command/profile discovery, validation/oracle/source-class ambiguity, progress-classification uncertainty, missing or stale `code_convention_contract`, adapter validation failures, task_miss caused by missing repo-specific procedure, recommended adapter name/scope/resources, and defer/reject rationale when not selected.

## Module Command Surfaces

Module commands provide decision-support evidence. They do not replace owning skill judgment.

| Module command | Inputs | Output or write surface | Consumers |
| --- | --- | --- | --- |
| `python3 -m orchestrate_task_cycle context` | `--root`, optional Git/file limits | Compact JSON for `task.md`, `.agent_goal`, `.agent_advice`, `.task`, `.issue`, `.agent_log`, `.schema`, `.contract`, validation, Git | Context, packets, report |
| `python3 -m orchestrate_task_cycle mode-profile` | `validate|resolve`, tracked profile registry, optional reducing override, explicit activation source | Closed non-GT mode resolution with capture/consume/reaction effects and exact derived-index repair scope | Coordinator before optional session observation behavior |
| `python3 -m orchestrate_task_cycle ledger` | `init`, `append`, `render`, `current`; stage JSON or explicit `--step` | `initialization.json` storage bootstrap; `stage.jsonl` beginning with canonical `context`; `current_stage.json`, packets, dashboard support | Dashboard, report, transition checks |
| `python3 -m orchestrate_task_cycle packet` | `--target <phase>`, context/stage evidence | Markdown or JSON packet with routing, required inputs/outputs, GT/advice separation | Every owning subskill |
| `python3 -m orchestrate_task_cycle transition` | `--transition <name>`, accumulated `--stage`, separate current `--routing-json`, optional `--workflow-mode bootstrap` | Transition `pass|warn|block` findings without reading a prior stage's route as the current target route | Orchestrator before major phases |
| `python3 -m orchestrate_task_cycle result-contract` | `--target <target>`, `--mode warn|block`, result JSON, optional long-run `--context`; stable facade over the `result_contract` rule registry | Contract findings, ledger-envelope readiness, closed `authority` packet/axis/reservation/pre-dispatch checks, pending-long-run pass/advanced and ordinary-derive blocks, plus target gate findings | Orchestrator before advancing stages; focused consumers may instantiate a target rule through `RuleContext`/`RuleRegistry` |
| `python3 -m orchestrate_task_cycle authority-packet` | `--root`, exact decision binding, mutation-only reservation and verification bindings, optional evidence-backed local-available override | Artifact-reopened, closed and verified authority-phase packet; no grant or policy mutation | Existing authority phase before result-contract validation and dispatch |
| `$plan-validation-scope` helpers | Planned files/surfaces before governance; actual changed files afterward | `validation_scope_plan` followed by authoritative `validation_scope_finalize` | Governance, pre-validation index, validation, derive, report |
| `python3 -m orchestrate_task_cycle code-structure` | `--root`, changed-file list or input JSON, optional `--convention-json` | Scalar audit packet with size, responsibility, semantic structure, and convention-conformance fields; no source bodies; no patches | Run, derive, validation, report |
| `python3 -m orchestrate_task_cycle gt-conflict` | `--root`, task/GT/behavior evidence | GT/task conflict packet | Derive |
| `python3 -m orchestrate_task_cycle progress-loop` | `--root`, optional explicit policy/finalized-cycle inputs; legacy write flag is prepare-only | Loop-breaker packet plus receipt-gated typed mutation candidate; never direct current registry/ledger/seal writes | Finalizer, then receipt-verifying derive/task-pack/validation/report consumers |
| `python3 -m orchestrate_task_cycle output-delta` | `--root`, output paths/contracts when present | Output-delta packet or not-applicable reason | Review, loopback, derive, validation |
| `python3 -m orchestrate_task_cycle task-pack` | `status`, `validate`, `render`, `next`, `apply-mutation`, `mark-consumed` | `.task/task_pack/*.json` canonical queue and Markdown render when mutating through derive-approved plan; validates `scope_fidelity` and measurable acceptance provenance when present | Derive, index, validation, report |
| `python3 -m orchestrate_task_cycle visible-increment` | Completed evidence, cycle ID, task ID | Formal `visible_increment` envelope; optional `.task/delta/<cycle-id>-visible-delta.{md,json}` with `not_validation_evidence: true` | Report only; not validation |
| `python3 -m orchestrate_task_cycle dashboard` | Cycle ledger evidence | Korean `dashboard.md` snapshot | Report, closeout |
| `python3 -m orchestrate_task_cycle efficiency` | Task ID and cycle ledger evidence through repo skill gap analysis | Formal `cycle_efficiency_profile` envelope with cycle-cost and `execution_starvation` fields when applicable | Scope finalization, validation, derive, report |
| `python3 -m orchestrate_task_cycle monitor` | Running process/log metadata, optional tmux session and completion artifact paths | Running-state verification without success promotion; optional `step: run` ledger append with `event_kind: long_run_monitor` | Validation, report |
| `python3 -m orchestrate_task_cycle report` | Context, validation, progress, commit JSON | Korean report draft/check in required field order | Final report |

## Fail-Closed Consumer Rules

- Validate `authority` in `block` mode with an explicit workspace root before every allowed mutation. Reopen exact non-symlink owner artifacts and reject unknown manifested operations, implicit grant union, missing/stale selected or lineage grants and policy snapshots, forged decision/approval echoes, missing reservation/use budget, non-reserved state, stale grant version, or non-matching immutable `pre_dispatch` verification. Treat legacy authority material as unverified diagnostics only.
- Keep permission, local resolvability, external-input availability, risk/cost consent, and GT alignment independent. Missing external input is not missing permission; a self-resolvable engineering gap is not an authority escalation; task/improvement authority is not action or policy authority.
- Treat missing or malformed packet evidence as `conservative_hold`, `not_applicable`, `partial`, or `blocked`; never silently upgrade it to success.
- For the optional session sidecar, reject raw transcript input, unvalidated/privacy-unsafe packets, and result-owned collection projections claiming collector trust. Treat absence, transcript-only claims, incomplete capture, quarantine, and packet-owned canonical relations as advisory/`not_evaluated` unless acceptance or the caller independently marked audit completeness required. Only a separate deterministic comparator contract may lower or block an owning verdict for a semantic mismatch.
- Treat missing/mismatched acceptance source task ID/path/fingerprint as blocking before governance. Acceptance from a prior task fingerprint is not reusable task-bound evidence.
- Treat a validation-scope plan as non-authoritative after implementation. Completion validation requires a `mode: finalize`, `finalized: true` packet with actual changed files explicitly present and at least one required command.
- Treat missing issue source-task/validation provenance as blocking before schema/derive. Created, updated, opened, resolved, or closed issue state without a durable issue ID/path/URL is invalid; an explicit `issue_ids: []` is allowed only for a reasoned skipped/not-applicable no-op.
- Treat acceptance scenarios as uncovered unless a structured actual-invocation receipt binds the exact scenario/predicate, proves a positive satisfying-item count, preserves invocation/revision/result/run evidence, and observes the expected terminal state. Green tests and caller booleans that never prove this structure are not scenario coverage.
- Treat `acceptance_inversion=true` as a code/contract repair condition and keep completion `partial` even when the current test suite is green.
- Treat `command_provenance_missing=true` as disqualifying for baseline, A/B, comparison, and reproduction evidence, while preserving the run for other scalar facts.
- Treat `blocker_opacity=true` as warn-only until repeated for the same gate; repeated opacity is a repair candidate for the gate/blocker contract.
- Treat `predetermined_unreachable` and `floor_edge_envelope` as contract-revision findings, not retry findings.
- Treat `instrumentation_first_fire=true` as one evidence credit only. Do not double-count it as goal progress and instrumentation-supply consumption.
- Treat `expectation_lineage_stale=true` as blocking live-execution promotion that depends on the stale scalar until rebaseline, explicit residual descope, terminal blocker, or user escalation.
- Treat `parity_unverified=true` and unknown parity axes as incompatible with final adoption, baseline promotion, or comparison-winner claims.
- Treat failed `gating` adoption axes and `measured_but_disqualified=true` as blocking adoption of that candidate while preserving the artifact as measured evidence.
- Treat `resolution_downgrade=true` as lower-resolution evidence only; do not consume it as high-resolution proof without contract revision or residual high-resolution scope.
- Treat `report_key_divergence=true` as a blocking report-integrity defect for pass/close/adoption/baseline/comparison/high-water claims.
- Treat `decision_freshness_lineage` subject/revision mismatch as blocking. Do not let a truthy no-impact flag bypass an applicable producer-run receipt, and do not collapse `artifact_ahead_of_review` into loss of the artifact-production fact.
- Treat terminal authority, local resolution, external waiting, and risk/cost confirmation as independent axes. Preserve `external_input: missing_unsupplyable` even when its typed decision routes alternative/descope through `blocked_by_goal_truth`; do not relabel the external fact as GT. Route exact unchanged waits to replay, local work to in-scope repair, the owner-bound approval projection to typed escalation, and unverified axes to classification repair.
- Enforce `effective_allowed_dispositions` as an intersection already computed by gates. Do not union individual gate dispositions.
- Enforce gate-constrained `allowed_task_kinds` inside `disposition_intersection_basis`; do not accept unrelated tasks merely because their disposition label is `goal_productive`.
- Treat `adapter_wiring_defect=true` as a self-inflicted workflow wiring/load bug. Do not downgrade it to adapter absence, adapter mandate, environment failure, or terminal blocker without a wiring/load correction attempt or user escalation.
- Treat self-reported `produced_domain_delta`, non-empty rows, lineage, gap reports, renamed commands, or metric existence as insufficient for goal-productive progress without strict changed-and-semantic output evidence or independent validated positive evidence.
- Treat `acceptance_diluted=true` as incompatible with final completion. Preserve residual measurable scope instead of consuming the original directive.
- Treat `unverifiable_acceptance_contract=true` as incompatible with final completion for the measurable target. Preserve required verifier work or explicit descope/residual scope.
- Treat behavior-preserving refactor completion claims as partial when adapter-supplied structure high-water is flat and the original objective was structural reduction. Additional files, numbered shards, version-suffix modules, relocated helpers, token/pattern avoidance, or producer-local reports are not structural progress by themselves.
- Treat `evaluation_status: not_evaluated` as not-pass when a gate is required by acceptance, task, advice, issue, or caller packet.
- Treat absent required adapter hooks for acceptance-referenced gates as `not_evaluated`, not pass.
- Treat `pass_with_coupled_verifier=true` as not-pass for completion, high-water movement, and `goal_productive`; require non-coupled revalidation, independent evidence recalculation, explicit residual descope, terminal blocker, or user escalation.
- Treat `pass_with_unobserved_axes=true` as not-pass for review-backed measurable goals; require adapter axis supply, explicit residual descope, terminal blocker, or user escalation.
- Treat generation-dependent count keys as trace-only. Do not let task/advice/pack/cycle/run IDs, dates, hashes, or version suffixes prove a blocker family is new.
- Treat terminal-classification/failure-surface contradictions as invalid for counting or close. Do not close or seal a family from a terminal classification whose allowed stage map excludes the observed `failure_surface_stage`.
- Treat same-condition input-set mismatch as invalid for same-family comparison. Do not reset stalls or close a family across mismatched windows/input sets.
- Treat repeated `diagnostics_unavailable` as an instrumentation-supply trigger. Do not advance another hypothesis repair unless instrumentation lands or a concrete observability rationale proves success/failure is already measurable.
- Treat supplied-but-unexercised instrumentation as unresolved. Do not advance dependent measurement, adoption, baseline, or close work unless a fresh run id exercised the supplied fields or a concrete observability rationale removes the dependency.
- Treat `evidence_kind=live_run` as requiring a run id after item creation. Derived artifacts, code contracts, and reports are not substitutes without explicit descope and residual scope.
- Treat same-target verifier/guard/report-only changes past the hardening cap as no-progress for `goal_productive`; require fresh execution-output evidence, explicit descope, terminal blocker, or user escalation.
- Treat `candidate_degraded` as preserved quality-miss evidence, not canonical success or baseline replacement. Only independently verified axes may be consumed later.
- Treat `runtime_config_echo` as failure/root-cause routing evidence only, and route plausible `code_default` overrides to self-inflicted default repair rather than opaque retry.
- Treat `execution_starvation_status=present` as a derive routing constraint. A fresh run clears it only when a canonical producer-run receipt binds the exact required input revision and content digest; replayed, stale-input, malformed, or unbound runs do not count. Permit only execution-producing work, producer/input/receipt reconciliation, explicit residual descope, or a separately valid terminal/user-escalation outcome, while preserving safety and authority. If an active goal/product axis requires producer output but the selected task excludes it, preserve reason-bound `execution_scope_applicability=excluded_by_task`, matching scope status, and present starvation; cap the result below goal-product movement. Reserve reason-bound `not_applicable` for task classes whose producer semantics are intrinsically absent, and never coerce either disposition to absence or terminal.
- Treat pending long-running statuses (`launching`, `running`, `completed_pending_validation`, `stale`, `not_running`) as eligible only for partial handoff validation. They are incompatible with final-output-dependent review, loopback, ordinary derivation or task-pack promotion, issue closure, `validation_verdict: passed`, `progress_verdict: advanced`, and `complete_verified`. Select monitor, harvest, finalize, terminal blocker, or user escalation for the same `run_id`.
- Treat Part M harvest-gate incompatibility, destructive high-cost disposition, rerun-before-reharvest, mutually unsatisfiable predicate/directive contracts, and sample-as-universe misuse as incompatible with pass/close/progress consumption until their matching repair, explicit residual/descope, terminal blocker, or user escalation is recorded.
- Treat non-disjoint/missing verification inputs or coupled/unknown invariant owners as an automatic downgrade from `independently_verified` to attested. Treat `self_grounded` as a separate root-local structural provenance, not an exception for semantic evidence.
- Treat frozen-envelope unreachable acceptance as requiring `envelope_thaw_item`, constraint relaxation, explicit residual/descope, terminal blocker, or user escalation before ordinary repair can count.
- Treat below-policy residual-gap value per cycle cost as marginal repair; do not select or validate another same-gap repair as `goal_productive` without a higher value case.
- Treat `attested_only_movement=true` as no high-water movement. It cannot reset G-CHAIN/C4 stall counters or satisfy `goal_productive`.
- Treat runtime behavior-change completion claims as partial when fresh live before/after evidence is required but absent.
- Keep `available_goal_truth` separate from `used_goal_truth`; final `기준 GT` may list only actually used GT.
- Keep `.agent_advice` out of GT and authority. Active advice in scope requires `used_advice` or an explicit defer/reject/not-applicable rationale.
- Keep repo-local adapters out of GT, authority, human approval, and completion evidence.
- Preserve raw subskill statuses in result packets, but write lifecycle statuses such as `complete`, `partial`, `skipped`, `not_applicable`, `blocked`, or `failed` to the ledger.
- Do not let validation-set assets, visible-increment artifacts, dashboard snapshots, or closeout commits replace completion validation.
