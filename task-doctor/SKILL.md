---
name: task-doctor
description: Review, retarget, replace, or task-pack a repository's active `task.md` only when the user gives explicit task-doctor direction. Use when Codex must externally adjust task scope or work direction before `$orchestrate-task-cycle`, optionally incorporate named `.agent_advice` non-GT documents, create/update `.task/task_pack` JSON+Markdown proposals that may include the current task, check `.agent_goal` conventions and repository rules, preserve task lifecycle IDs and `past_task` traceability, refresh schema/index/issue state, and invoke `$repo-change-commit`. Do not use for normal task implementation or ordinary next-task derivation.
---

# Task Doctor

## Overview

Use this skill as a pre-cycle intervention for task direction. It may replace or rewrite `task.md` from an explicit user instruction after checking goal truth, conventions, repository rules, and task-state traceability. It may also create or update a `.task/task_pack/` proposal when the user explicitly asks for a sequence of tasks or asks to include the current task in a task-pack plan.

This skill adjusts the workflow artifact that `$orchestrate-task-cycle` will later consume. It does not implement the task, run the full orchestrated cycle, or patch behavior-changing repository code.

When the user provides or names an external advice Markdown document, use `$manage-external-advice` to intake or render its active packet. Treat `.agent_advice/active/*.md` as non-GT direction evidence only: list it as `used_advice`, never as `.agent_goal` goal truth.

When creating or updating task packs, use the task-pack contract from `$orchestrate-task-cycle` [task-pack-workflow.md](../orchestrate-task-cycle/references/task-pack-workflow.md). The JSON queue under `.task/task_pack/` is canonical; the adjacent Markdown file is a user-language render. Keep one active `task.md`; task packs are planning state, not goal truth or completion evidence.

## Authority Boundary

The user's doctoring direction is a direction source, not blanket downstream permission. Use `authority.operations.json` and the shared [authority v2 contract](../manage-agent-authority/references/authority-v2-contract.md). Read-only diagnosis is authority-neutral. Before `mutate_task_scope` or `normalize_initial_selection`, freeze the exact prospective task/pack bytes, operation/version, subject revision/digest, effect and risk classification, then require a matching `allowed` decision and reservation. A grant for one task or pack cannot authorize another digest, a later rebuilt plan, implementation work, goal-truth changes, risk acceptance, external input, Git publication, or a destructive operation.

Perform feasibility and dry-run checks before reservation. Reverify the decision, reservation, scoped authority fingerprint, manifest, selected grant state/version, policy snapshot, and exact subject immediately before the first lifecycle write. Consume only after the owning publication transaction commits. Release only when execution did not start or no effect is verified; quarantine when an effect may have occurred. Multiple covering grants are usable only through a separately approved exact composition receipt.

Keep approval, goal ratification, risk/cost acceptance, external-input availability, and bounded design selection as separate typed decisions. If the exact request is awaiting approval or input, retain its identity and return one stable wait. On unchanged state, replay the wait without rewording the request, issuing another task/pack plan, consuming a use, or prompting again. Re-enter only from a declared relevant authority/input/subject change. Legacy receipts are historical diagnostics and never authorize a new mutation.

## Domain Adapter Contract

Task doctoring normally consumes adapter-derived fields through task, pack, acceptance, loopback, or validation packets. When direct adapter access is available, it may consume:

- `proxy_population(proxy_id, **context) -> dict`: optional Part O/O4' helper returning opaque proxy-population fields such as `measures_new_behavior`, `new_behavior_sample_count_field`, `min_sample_k`, and replacement/proxy-population status. The adapter owns proxy identity, new-behavior population, and threshold semantics. If absent or malformed, fail quiet and preserve existing task-shaping rules.

Do not hardcode proxy names, domain populations, or sample thresholds. O4' is not a replacement for G-OENV, N1', or B-series scope-fidelity checks, and must not be double-counted with them unless packets report distinct facts.

## Activation Gate

Proceed only when the user clearly asks to use `$task-doctor`, asks to doctor/replace/retarget/reassign `task.md`, asks to create/update a task pack from current task direction, or provides a direct instruction that the active task direction must be externally changed before continuing.

If the user only reports that a task failed, asks to execute the current task, or asks for the normal cycle, use `$orchestrate-task-cycle`, `$task-md-agent-governance`, or `$derive-improvement-task` instead.

Require at least one explicit direction source before writing:

- A new objective, work direction, constraint, or priority from the user.
- A named candidate, issue, task miss, goal file, or prior task that should become the new active task.
- A named `.agent_advice/active/*.md` document or newly provided advice Markdown that the user explicitly wants incorporated into the doctored task.
- A task-pack proposal, ordered task list, or instruction to include the current `task.md` plus proposed changes in `.task/task_pack/`.
- A clear instruction to narrow, expand, defer, or replace the active task.

If the direction source is missing or ambiguous, perform only read-only diagnosis and ask for the missing instruction. Do not infer a replacement task from repository state alone.

Active advice existing on disk is not enough by itself to trigger task doctoring. Use it in this skill only when the user asks for `$task-doctor`, names the advice, or explicitly asks to fold that advice into `task.md`.

An active task pack existing on disk is not enough by itself to trigger task doctoring. Use or modify it only when the user explicitly asks to doctor task direction, names the pack, or asks to turn the current task and changes into a pack proposal.

## Scope

Allowed writes:

- `task.md`
- `.task/` task-state artifacts through `$manage-task-state-index`
- `.task/task_pack/*.json` and `.task/task_pack/*.md` task-pack proposals when the explicit doctoring instruction requests a task pack
- `.agent_log/` `past_task` and task-doctor handoff logs through `$record-agent-work-log`
- `.schema/` and `.contract/` records through `$manage-schema-contracts`
- `.issue/` tracking through `$manage-implementation-issues` when the replacement creates, resolves, or defers an implementation issue
- `.agent_advice/` lifecycle artifacts only through `$manage-external-advice` when the explicit doctoring instruction intakes, applies, rejects, or defers advice
- Git commits through `$repo-change-commit`

Forbidden writes:

- Source code, tests, notebooks, scripts, runtime/build/CI configuration, or generated implementation outputs.
- Goal truth files such as `.agent_goal/final_goal.md` or `.agent_goal/conventions.md` unless the user explicitly asked to edit the goal itself with the owning goal skill.
- Validation evidence that was not actually produced.

If the task direction change reveals a required code change, write it into the new `task.md` and leave implementation to `$orchestrate-task-cycle` and `$task-md-agent-governance`.

## Workflow

When reviewing a terminal or escalation request, require the existing loopback residual classification first. Any `self_resolvable_local`, `offline_recompute`, or `existing_authority` item keeps the goal nonterminal and should be retargeted into a bounded task. `unverified` yields `offline_scope_unverified`, not an assertion that external authority is required. Keep task-pack exhaustion separate from goal terminal.

1. Establish the workspace and explicit instruction.
   - Locate the repository or workspace root.
   - Restate the user's explicit task-doctor instruction in one or two sentences.
   - Confirm whether the operation is `initial_task`, `replace_task`, `retarget_task`, `candidate_promotion`, `task_pack_proposal`, `task_pack_update`, or `task_pack_promotion`.
   - Stop before writing if the user instruction is not concrete enough to determine the new active task.

2. Read task and rule context.
   - Read `task.md` when present.
   - Read `.agent_goal/final_goal.md`, `.agent_goal/conventions.md`, `.agent_goal/goal_architecture.md`, `.agent_goal/goal_theory.md`, and `.agent_goal/goal_schema_contract.md` when present.
   - Read or render `.agent_advice/active/*.md` only when the user names advice or the doctoring instruction depends on advice; use `$manage-external-advice render-packet` for a compact packet.
   - Treat the rendered advice packet as non-GT direction evidence, never as an executable task/pack plan. Require `execution_plan_eligible=false`. If `normalized_packet_use=warning_only_raw_review`, `fidelity_status=needs_review|degenerate`, `normalization_complete!=true`, or `raw_direct_reference_required=true`, inspect the named raw source and repair/re-intake the clause normalization or explicitly defer the affected clause before prepublication planning. Do not copy an incomplete normalized directive list into `task.md`, a task pack, ordering mutations, or authority subjects as though it were complete.
   - Check repository-local rule files when present, such as `AGENTS.md`, `CONVENTIONS.md`, `CONVENTION.md`, `RULES.md`, `README.md`, `.codex/`, `.task/`, `.issue/`, `.schema/`, and `.contract/`.
   - Read `.task/index.md`, `.task/candidate_task/`, `.task/task_pack/`, `.task/task_miss/`, `.issue/`, and recent `.agent_log/` summaries when they are relevant to the requested direction.
   - When `.task/task_pack/` is relevant, run or request `$orchestrate-task-cycle` with `python3 -m orchestrate_task_cycle task-pack --root . status --format json` and `validate` for the active or named pack.
   - When the requested doctoring changes provider, API credential, `.env`, terminal-blocker, or seal constraints, run `$orchestrate-task-cycle` with `python3 -m orchestrate_task_cycle gt-conflict --root .` on the current task and account for any conflict before writing the replacement.
   - When the requested doctoring cites workflow loop/dedup advice, run or request `$orchestrate-task-cycle` with `python3 -m orchestrate_task_cycle progress-loop --root .` and account for `feature_symbol_gate` without treating the advice itself as goal truth.
   - When the requested retarget touches a quiesced, sealed, or root-cause-exhausted family, run or request `$orchestrate-task-cycle` with `python3 -m orchestrate_task_cycle progress-loop --root .` and read the latest `anti_loop_progress_gate` if available. Account for `terminal_quiescence_gate`, `quiescence_untried_reconcile`, `hypothesis_exhausted`, and `.task/anti_loop/root_cause_ledger.jsonl` before writing the replacement.
   - When the requested retarget touches repeated terminal/recheck evidence, account for `terminal_escalation_gate`, `terminal_recheck_streak`, and `.task/sealed_blocker_families.json`. Do not doctor the task into another same-family recheck unless the user supplies a new input, authority change, external-state change, or verified unexhausted root-cause repair.
   - Keep inspection at workflow and convention level. Do not inspect implementation source to solve the task.

3. Refresh traceability before replacement.
   - Use `$manage-task-state-index` `scan --check` (or `scan --dry-run`) when any task-state artifact exists. This preflight is read-only: it must not create or rewrite `.task/index.jsonl` or `.task/index.md` merely to inspect readiness.
   - Use `$manage-task-state-index` `audit` before replacing `task.md` when `.task/index.jsonl` exists.
   - Treat high-severity active-task, missing-file, duplicate-ID, or broken-link findings as blockers unless the replacement is explicitly meant to repair that condition.

4. Decide the task update shape.
   - Preserve all applicable user requirements and repo conventions.
   - Normalize noncanonical progress labels without extending the task-pack enums. Keep `progress_target` in `advanced|safety_only|no_progress|regressed` and `progress_kind_expected` in `goal_productive|governance_only`. Put an open bounded subtype such as `workflow_capability`, `artifact_truth_only`, `artifact_truth_reconciliation`, or `artifact_truth_verification` in `item_kind`; `item_kind` routes the work but is not progress evidence.
   - When the direction says `workflow_capability`, preserve that source label in directive provenance or `scope_fidelity` and use `item_kind: workflow_capability`. When it says `artifact_truth_only`, preserve the exact source target in `scope_fidelity`, use `item_kind: artifact_truth_only`, and retain the required verifier/evaluation status in acceptance. Select the canonical progress fields from expected observable outcomes; do not create `effective_progress_kind_expected`, `artifact_truth_only` as a progress enum, or a new verdict-axis vocabulary.
   - Preserve the previous `## Execution Environment` section only when it remains applicable to the new task.
   - If no environment is applicable, set `Status: not_applicable`.
   - If a Python or runnable environment is needed but unknown, use `$find-local-python-envs` or mark `Status: unresolved` with the blocker. Do not install dependencies from this skill.
   - Keep the result narrow enough for one `$orchestrate-task-cycle` pass.
   - If the user requested a task pack, keep `task.md` as the single active executable task and use `.task/task_pack/` only for the ordered proposal. Bind an included current first task through the helper's bootstrap/authorized initial-selection transaction; do not hand-author an unproven promoted item.
   - When an existing pack's first selection predates that contract, do not replay promotion or patch JSON directly. Require an explicit normalization direction, immutable creation/task snapshots, and a validated `$manage-agent-authority` receipt; then use the helper's `normalize_initial_selection_provenance` transaction. Current ratification authorizes continuation only and must preserve partial historical authority.
   - Use a task pack only when the explicit direction contains an ordered sequence or when a single doctored task would lose important sequencing context. Otherwise write only `task.md`.
   - Do not create multiple active task packs. Update the named active pack in place when appropriate; when replacing it with a successor, use the helper-owned `replace_pack` transaction so predecessor supersession and successor publication share one journal/receipt. Never supersede first and create separately.
   - If active advice was used, decide whether it is incorporated into the new task, deferred for later implementation, or rejected because it conflicts with user instruction, GT, authority, or repository facts.
   - Do not write a replacement task that forbids a `.agent_goal` allowed or required provider/credential action unless the new task explicitly resolves the conflict or cites a newer explicit user instruction that supersedes the GT with a verifiable source. A bare phrase such as "latest user instruction" is not enough. When caller authority permits quoting, supply the exact bounded user quote separately and bind it to the validated privacy-safe [$audit-session-governance](../audit-session-governance/SKILL.md) packet's event/hash/timestamp reference; require an explicit `integrity_status` and preserve its limitations. The packet itself contains no quote or message body, and a raw transcript path or transcript-only observation is insufficient. The quote supports provenance only and cannot by itself expand authority. Otherwise keep the prior supersession/authority state and ask the user for confirmation.
   - Do not write a replacement task whose progress case depends only on self-declared `produced_domain_delta=true`; require observed output evidence, legitimate provider-terminal evidence, consolidation, or explicit terminal/user escalation.
   - Do not write a replacement task whose progress case depends on `observed_producer_claim` or any producer self-reported `goal_productive`, `advanced`, or `effective_progress_kind` label. Preserve such labels only as trace evidence and require adapter/output-delta/validation truth.
   - Do not write a replacement task whose progress case depends on `producer_attested_fields` or `attested_only_movement`. Preserve those fields as trace evidence and require `independently_verified` adapter/output-delta/validation truth.
   - Do not write a replacement task that treats a new oracle, validator, metric, ladder record, dashboard, lineage, or gap report as `goal_productive` unless `coverage_quality_delta_gate.quality_delta_pass=true` or strict changed-and-semantic output-delta evidence exists.
   - Do not preserve a fail-closed gate as an environment blocker when recent run evidence classifies it as `self_inflicted_gate_defect`. The replacement task must correct the gate contract/code, use a recorded alternative evidence source, or ask the user for `gate_contract_fix_approval`.
   - Do not rewrite `adapter_wiring_defect=true` into generic adapter absence or adapter creation. The replacement task must correct adapter wiring/load, use a recorded alternative evidence source, or terminal/user-escalate with the registered adapter path.
   - Do not rewrite a gate-constrained `goal_productive` recommendation by keeping only the label. If `disposition_intersection_basis.allowed_task_kinds` or `forced_selected_task` exists, preserve the allowed `selected_task_kind` in the new task or record why the task is terminal/user escalation instead.
   - Do not weaken a measurable user/advice/issue directive into a smaller `pilot`, `plan`, or `slice` acceptance criterion without recording explicit descope. If a measurable directive is narrowed, the new task or pack item must preserve the original target in acceptance or create an open residual follow-up with the reason.
   - If a measurable directive uses a proxy and Part O/O4' evidence reports `trivially_satisfiable_proxy=true`, do not preserve that proxy as sufficient completion by itself. Add the adapter-owned new-behavior sample precondition, replace the proxy with one measuring new behavior, or write explicit residual/descope, terminal blocker, or user escalation. If `proxy_population` is absent, fail quiet and keep existing proxy handling.
   - If a measurable target has an `acceptance_envelope_contract`, preserve the target plus adapter-owned minimum envelope in the doctored task or pack item. If the requested slice is below the envelope floor, record envelope expansion, explicit descope with residual scope, terminal blocker, or user escalation; do not silently lower the target.
   - If a measurable target has an `acceptance_verifier_contract` or loopback reports `unverifiable_acceptance_contract=true`, preserve the required verifier and its `evaluation_status`. If the required verifier is `not_evaluated`, the replacement task must implement/correct the verifier, explicitly descope with residual scope, terminal-block, or user-escalate; do not rewrite the missing verifier as a passed gate.
   - If a measurable target depends on a gate's required adapter hook, preserve the required hook and its status. If the hook is absent, fail-quiet, or `not_evaluated`, route it through `unverifiable_acceptance_contract` and write hook-supply, explicit descope with residual scope, terminal-block, or user escalation into the replacement; do not rewrite the missing hook as a passed gate.
   - If loopback reports `pass_with_coupled_verifier=true`, preserve it as not-pass. The replacement task must request verifier-source-independent revalidation, independent evidence recalculation, explicit residual descope, terminal-block, or user escalation; do not rewrite the coupled pass as accepted completion.
   - If review or loopback evidence reports `pass_with_unobserved_axes=true`, `goal_axis_completeness_gate.evaluation_status=fail`, or nonempty `unobserved_goal_axes`, do not write the review as accepted pass evidence for that measurable target. Preserve an adapter axis-supply task, explicit residual scope, terminal blocker, or user escalation.
   - If adapter `residual_gap_policy` fields show a below-threshold residual gap, do not retarget the task into another same-gap repair by default. Preserve descope-with-residual plus the next capability-ladder rung, or record explicit evidence that marginal repair value is higher. If cycle-cost fields are supplied, require the replacement to justify value per cycle cost rather than gap existence alone.
   - If loopback evidence reports generation-dependent count-key material, do not write a task or pack item that treats label/task/advice/pack/cycle/run/date/hash/version churn as a new family. Preserve the effective root-family/dominant-parameter key or terminal-outcome family in the task background.
   - If loopback evidence reports `terminal_classification_stage_contradiction=true`, `terminal_classification_invalid_for_counting=true`, or `same_input_contract_violation=true`, do not doctor the task into a close/count/seal path. Preserve classification-stage repair, input-contract repair, instrumentation supply, terminal blocker, or user escalation.
   - If loopback evidence reports `instrumentation_supply_required=true`, do not rewrite the blocker as an ordinary opaque repair. Preserve instrumentation supply or an explicit observability rationale proving success/failure is already measurable without new instrumentation.
   - If task-pack, loopback, or validation evidence reports `instrumentation_exercise_required=true`, do not retarget into dependent measurement, adoption, baseline, or close work. Preserve or create an `instrumentation_exercise` item requiring a fresh run id with non-empty scalar fields, or record an explicit observability rationale.
   - If measurable acceptance carries `acceptance.quantifiers`, `evidence_kind`, `item_created_at`, or `required_new_run_id`, preserve those fields in the replacement task or pack. A `live_run` criterion cannot be rewritten as derived-artifact, code-contract, or report-only evidence without explicit descope and residual scope.
   - If measurable acceptance carries `acceptance_scenarios`, preserve each premise-class -> expected-terminal-state pair in the replacement task or pack. Do not rewrite it into a generic green-test criterion; require a premise-satisfying fixture/live run or residual scenario item.
   - If loopback evidence reports `verifier_surface_hardening=true` with `guard_stacking_cap_reached=true`, do not doctor the task into another same-target guard, verifier, consistency check, or report as `goal_productive`; write execution-producing work, explicit descope with residual scope, terminal blocker, or user escalation.
   - If run evidence reports `run_disposition=candidate_degraded`, preserve it as quality-miss evidence and do not write a replacement that promotes it as canonical baseline unless independent verification evidence permits the consumed axes.
   - If run evidence reports `command_provenance_missing=true`, do not write a replacement that consumes that run as baseline, A/B, comparison, or reproduction evidence. Preserve a full-argv rerun/provenance repair, or explicitly exclude the run from those claims.
   - If gate evidence reports repeated `blocker_opacity=true`, do not write a replacement that treats the opaque blocker as actionable. Preserve blocker-contract repair requiring violated relation, observed values, expected relation, or minimum input delta.
   - If loopback evidence reports `predetermined_unreachable=true` or `floor_edge_envelope=true`, do not rewrite the task into another retry. Preserve stochastic contract revision, envelope expansion, explicit residual descope, terminal blocker, or user escalation.
   - If run or loopback evidence reports `instrumentation_first_fire=true`, preserve it as one evidence credit only and do not let the doctored task count it as both goal progress and instrumentation supply consumption.
   - If a task or pack item has an output-derived scalar expectation, preserve `expectation_anchor` with the source surface identifier. Before promotion, compare it with adapter/caller `designated_baseline`; if the anchor is superseded, rebaseline the expectation against the current designated surface or write a fail-closed `expectation_lineage_stale` blocker instead of scheduling live execution.
   - If `expectation_anchor` is missing but the expectation is clearly output-derived, set `expectation_anchor_missing` and keep the existing behavior fail-quiet, but do not claim the expectation is lineage-verified. When the current designated surface is available, add a rebaseline follow-up or task-pack item.
   - If a task compares producer/settings outputs to adopt, reject, or rank a candidate, preserve `parity_axes` and each axis status as `controlled`, `measured`, or `unknown`. Unknown axes keep adoption `parity_unverified`; do not write a final adoption task or pack item until axis-resolution, explicit residual scope, terminal blocker, or user escalation is recorded.
   - If a comparison has multiple measured axes, preserve `adoption_axis_classification` as `gating` or `tradable` before measurement. A failed gating axis blocks adoption regardless of tradable-axis wins; preserve the measured candidate as `measured_but_disqualified` instead of deleting or promoting it.
   - If evidence resolution was downgraded from the contract's required unit to a count, ratio, ordinal, or other surrogate, preserve `resolution_downgrade` and `surrogate_resolution_basis`. Do not doctor the result into a completed high-resolution comparison; route resolution restoration, residual scope, or provisional decision status.
   - If a consumed report has duplicate terminal keys with divergent values, preserve `report_key_divergence` as a blocking contract defect. Do not use either copy as pass/close evidence until the report has a single source or matching values.
   - If evidence reports `pass_on_stale_lane=true`, do not write a replacement task that consumes that pass as current-lane capability, adoption, comparison-winner, or next-rung evidence. Preserve current-lane rerun/revalidation, explicit residual descope, terminal blocker, or user escalation.
   - If decision evidence reports `decision_metadata_revision=true` or `stale_measurement_artifact=true`, do not rewrite it as fresh measurement progress. Preserve a fresh current-lane run requirement, no-impact proof requirement, residual scope, terminal blocker, or user escalation.
   - If loopback reports `axis_starved_by_missing_producer=true`, do not doctor the task into another verifier, guard, consistency check, or report as `goal_productive` for that axis. Preserve producer-supply work or descope/terminal/escalation.
   - If portfolio evidence reports restrictive `portfolio_quota_exceeded=true`, do not doctor the next task into another verifier-like item unless the task records a valid exception. Preserve producer, envelope, long-run, descope, terminal, or escalation work.
   - If acceptance or loopback reports `unreachable_within_cycle=true`, do not doctor the task into another small smoke rerun as progress. Preserve long-run launch/monitor/harvest, throughput improvement, explicit descope, terminal blocker, or user escalation.
   - If metric evidence reports `basis_overclaim=true`, do not preserve the metric as independently verified progress. Preserve basis-compatible measurement, basis repair, downgrade-aware residual scope, or terminal/user escalation.
   - If qualitative review reports nonzero `surface_field_defect_matrix`, preserve producer/field repair or residual scope before consuming the review pass for affected field classes.
   - If failure autopsy reports `runtime_config_echo.config_overrides` from `code_default`, preserve the self-inflicted default/cap repair option rather than rewriting it as a generic runtime blocker.
   - If profile evidence reports `execution_starvation=true`, do not doctor the task into another no-run guard/report/contract cycle unless safety, authority, GT, or terminal evidence blocks execution.
   - If loopback or validation evidence reports non-disjoint independent verification (`independent_source_separation_status=missing|overlap|blocked` or `independently_verified_downgraded_fields`), do not preserve those fields as high-water or goal-productive proof. Treat them as attested or write a verification-source repair.
   - If loopback or acceptance evidence reports `envelope_thaw_item_required=true`, do not retarget into another frozen-envelope-internal repair as progress. Preserve `envelope_thaw_item`, constraint relaxation, explicit residual descope, terminal blocker, or user escalation.
   - If loopback evidence contains `root_dominant_parameter_key`, do not treat proximate label changes as a new root-cause family for retargeting. If `primary_metric_stalled=true` or `c4_user_escalation_backstop_required=true`, preserve the forced option or user-escalation requirement instead of rewriting it into another same-family recheck.
   - If loopback evidence contains `structure_high_water_key_scope=global_invariant`, do not retarget structure work around a new local scope as full progress unless the global invariant movement or residual global scope is recorded.
   - Do not retarget a quiesced or `hypothesis_exhausted=true` family silently. A user-directed retarget is allowed, but the new `task.md` or task-pack mutation must record `quiescence_override` with the user instruction, supplied input delta, authority change, external-state change, or verified unexhausted root-cause evidence.
   - Do not retarget a G2-escalated terminal family into another `terminal_blocked` recheck. A user-directed override must record `terminal_escalation_override` with one of: supplied input delta, authority change, external-state change, gate-contract fix approval, or verified unexhausted root-cause evidence.
   - When an explicit `gt_constraint_policy.generalization` reports a repeated single-unit invariant against a multi-unit/generalization goal, require the adapter-indicated bounded multi-unit path or terminal-block on the exact missing source/authority/provider condition. Do not infer domain units or generalization fields without that policy.
   - Put `## Execution Environment` immediately after `# Task`.

5. Pass the prepublication feasibility gate.
   - Run this gate before creating a `past_task` archive, overwriting canonical `task.md`, superseding or creating a pack, appending task-state events, rendering a durable view, Git staging, or committing. The only permitted preparation writes are a bounded noncanonical prospective-task file and, after its exact subject is known, a one-shot subject-bound authority receipt; neither is lifecycle progress or proof that selection occurred.
   - Inspect `python3 -m orchestrate_task_cycle task-pack --root . capabilities` and verify that the requested operation, canonical progress enums, open `item_kind`, first-selection mode, replacement recovery, active-pack cardinality, and transaction scope are supported. A requested source label that is representable through canonical fields plus `item_kind` is not grounds for enum expansion.
   - Materialize the exact prospective `task.md`, exact successor pack body, exact create/replace mutation plan, and authority subject inputs in memory or a disposable noncanonical staging area. Set deterministic successor `created_at` and `updated_at` in that body instead of allowing apply-time defaults, bind the plan to the named predecessor's exact ref, file/canonical hashes, IDs, order, and current item, and retain the exact bytes/digests that passed preflight. Keep the plan body-safe: replace raw prompts, transcripts, credentials, corpus metadata, and source instruction bodies with opaque IDs, bounded workspace refs, and hashes before the helper content-addresses it.
   - When replacement also performs initial selection, use two bounded feasibility phases whether canonical `task.md` is absent or still contains the old active task. First dry-run the exact successor/carry/retirement body without `initial_selection` to obtain deterministic creation-snapshot identities. Write the exact prospective task bytes only to a bounded noncanonical workspace path, compute the deterministic task-snapshot identity, resolve authority, and issue the exact one-shot receipt. Then add `initial_selection.prospective_task_ref` and `prospective_task_sha256` and run the complete final plan in dry-run mode. The helper records canonical `task_path: task.md` while sourcing bytes from staging for dry-run even when old canonical bytes exist. After that full plan passes, publish byte-identical `task.md` and apply the same plan; apply requires canonical bytes to equal the staged digest.
   - Run the exact helper dry-run and require `status: dry_run`, `findings: []`, and no helper-owned pack/snapshot/journal/receipt or lifecycle residue. The explicitly permitted prospective-task staging file and unused subject-bound authority receipt are preparation evidence, not a dry-run mutation. Keep staging byte-identical through apply; remove it only after the committed replacement receipt validates, or on pre-prepare abort, and report its cleanup. Keep a replacement successor in memory or noncanonical staging: its final `.task/task_pack/<pack_id>.json` path must remain absent for apply. Use `validate --pack <path> --strict-findings` only to audit an already-existing pack artifact; it is debt/input, not a publishable replacement at that same ref. Evaluate the prospective successor through replacement dry-run independently from unrelated historical pack debt; global debt may remain reported, but it neither invalidates a clean exact candidate nor permits publishing a candidate with findings.
   - For a new sequence, require two to five newly derived items. For `replace_pack`, allow more than five total items only when the successor introduces at most five new items and every additional item is exact carry-forward under `replacement_contract`, including unchanged planning content and preserved predecessor-relative order. Existing predecessor IDs cannot be relabeled as new. Account for every nonterminal predecessor item as exact carry-forward or as an explicit `retired_items` disposition with a bounded reason and hash-bound direction/authority evidence outside `.task/task_pack/`; omission is a failed preflight. Reject a carried dependency on a removed predecessor unless that dependency is already consumed with preserved completion evidence; otherwise rederive the dependent item under a new ID and count it as new.
   - Confirm before publication that exactly one active predecessor exists when replacing, no active pack exists when creating, the prospective task snapshot is deterministic, the exact authority subject is constructible when initial selection is requested, the task-state store is appendable, and all outer lifecycle writes are authorized. Apply must reuse the byte-identical preflight task and pack plan; if any digest or deterministic timestamp differs, rerun preflight and reissue any subject-bound authority rather than silently rebuilding the candidate.
   - If any check fails, stop fail-closed. Do not archive, replace canonical `task.md`, mutate either pack, append task state, render a durable view, Git-stage, commit, or run orchestration. Remove disposable prospective-task staging. If the exact one-shot authority receipt was already issued for the full preflight, retain and report it as unused subject-bound preparation; it proves no selection or lifecycle mutation and cannot be reused for a different plan/subject. Report a stable blocker signature, the first exact finding, the missing material delta, and all retained non-lifecycle evidence.

6. Archive the old task before overwriting.
   - If `task.md` exists, use `$record-agent-work-log` to create a `past_task` entry before changing it.
   - Include the old task content or a safe summary, the user-provided doctor instruction, and why the old task was superseded.
   - Run `$manage-task-state-index` `scan` after logging so the old task is indexed as `past-*` or `log-*` when possible.
   - If `task.md` is absent, treat the operation as `initial_task` and skip `past_task` archival.
   - For `initial_task`, apply the non-blocking `tier0_hook_set` acceptance pointer in `$orchestrate-task-cycle` [workflow-routing.md](../orchestrate-task-cycle/references/workflow-routing.md); Tier-1+ hooks remain demand-ledger work through `adapter_hook_demand`.

7. Write the new `task.md`.
   - Use this structure:

     ```markdown
     # Task

     ## Execution Environment

     - Status: selected | unresolved | not_applicable
     - Source: previous_task | find-local-python-envs | repository_manifest | user_instruction | manual_inference
     - Type: conda | venv | local | non_python | unknown
     - Name:
     - Python:
     - Run Prefix:
     - Dependency Notes:
     - Task Pack: <pack-id/path | none>
     - Task Pack Item: <item-id | none>
     - Pack Position: <order/total | none>
     - Pack Source: planned | inserted | reordered | none

     ## Objective

     <One concrete externally adjusted objective.>

     ## Background

     - Task doctor instruction:
     - Goal alignment:
     - Convention/rule alignment:
     - External advice source:
     - Issue/candidate/task_miss source:
     - Schema contract link:

     ## Requirements

     - <Specific requirement>

     ## Acceptance Criteria

     - <Observable completion condition>

     ## Validation

     - <Command, test, review, metric, or evidence required>

     ## Constraints

     - <Relevant convention, forbidden action, compatibility or safety rule>

     ## Out Of Scope

     - <What the next cycle must not attempt>

     ## Open Questions

     - <Unknowns, or `None`>
     ```

   - If the new task came from `.task/candidate_task/`, delete the applied candidate only after the new `task.md` is written and the transition is indexed. Keep unapplied candidates.
   - Do not delete task misses or issues from this skill unless their owning skill confirms the lifecycle transition.

8. Write or update a task-pack proposal when requested.
   - Create `.task/task_pack/` only when the explicit doctor instruction asks for a pack, sequence, ordered proposal, or current-task-plus-followups plan.
   - Use canonical JSON under `.task/task_pack/pack-<timestamp>-<slug>.json` and render `.task/task_pack/pack-<timestamp>-<slug>.md` in the user's language.
   - Follow the schema from `$orchestrate-task-cycle` [task-pack-workflow.md](../orchestrate-task-cycle/references/task-pack-workflow.md): `schema_version`, `pack_id`, `status`, `language`, `goal`, `current_item_id`, `items`, `mutation_log`, and optional `terminal_blocker`.
   - For every item derived from a measurable directive, include `scope_fidelity` with `directive_id`, `original_target`, `item_acceptance`, `narrowed`, `narrow_reason`, and `residual_item_id`.
   - When a measurable item has an adapter-owned minimum envelope, include `acceptance_envelope_contract` with abstract `envelope_floor` and `deficit_axis` fields in the item or task background. Keep project-specific metric definitions and thresholds in the adapter or project-owned contracts.
   - When a measurable item has an adapter-owned required verifier, include `acceptance_verifier_contract` with abstract `required_verifier`, `verifier_required`, `evaluation_status`, and evidence fields in the item or task background. Keep project-specific verifier implementation details in the adapter or project-owned contracts.
   - When a measurable item has acceptance-required gate hooks, include abstract required-hook fields and `evaluation_status` in the item or task background. Keep hook implementation details in the adapter or project-owned contracts.
   - When a measurable item has goal-axis completeness fields, include abstract `goal_axis_map`, `unobserved_goal_axes`, or `pass_with_unobserved_axes` fields in the item or task background. Keep axis definitions and calculations in the adapter.
   - When a measurable item has Part O/O4' proxy-population fields, include abstract `trivially_satisfiable_proxy`, `new_behavior_sample_count_field`, and sample-precondition or proxy-replacement status in the item or task background. Keep proxy definitions and thresholds in adapter/caller packets.
   - When a measurable item has adapter-owned residual-gap policy fields, include abstract `residual_gap_ratio`, `residual_gap_policy`, `marginal_repair`, value-per-cycle-cost fields when supplied, and residual item references. Keep thresholds and metric definitions in the adapter or project-owned contracts.
   - When a measurable item has Part H evidence, include abstract `failure_surface_stage`, terminal-classification/same-input status, diagnostics/instrumentation requirement, verification source separation status, and `envelope_thaw_item` fields in the item or task background. Keep stage ladders, classification maps, source paths, self-grounded axes, and thaw schedules in adapter/caller packets.
   - When a measurable item has Part I evidence, include abstract `instrumentation_exercise_required`, `instrumentation_field_map`, `acceptance.quantifiers`, `evidence_kind`, `verifier_surface_hardening`, `run_disposition`, `runtime_config_echo`, and `execution_starvation` fields in the item or task background. Keep field criteria, safety/quality policy, runtime defaults, and starvation window overrides in adapter/caller packets.
   - When a measurable item has Part J evidence, include abstract `acceptance_scenarios`, `command_provenance_missing`, `blocker_opacity`, `outcome_variance`, `predetermined_unreachable`, `floor_edge_envelope`, and `instrumentation_first_fire` fields in the item or task background. Keep scenario predicates, argv redaction, blocker relation details, variance thresholds, and first-fire criteria in adapter/caller packets.
   - When a measurable item has Part K evidence, include abstract `expectation_anchor`, `designated_baseline`, `expectation_anchor_missing`, `expectation_lineage_stale`, `parity_axes`, `parity_axis_status`, `parity_unverified`, `adoption_axis_classification`, `required_output_classes`, `majority_vote_adoption`, `provisional_adoption`, `measured_but_disqualified`, `required_evidence_resolution`, `observed_evidence_resolution`, `resolution_downgrade`, `surrogate_resolution_basis`, and `report_key_divergence` fields in the item or task background. Keep concrete baseline discovery, axis definitions, report schemas, and thresholds in adapter/caller packets.
   - When a measurable item has Part L evidence, include abstract `production_lane_identity`, `current_decision_lane`, `lane_identity_missing`, `pass_on_stale_lane`, `decision_metadata_revision`, `stale_measurement_artifact`, `axis_starved_by_missing_producer`, `producer_supply_required`, `portfolio_quota_exceeded`, `unreachable_within_cycle`, `long_run_launch_required`, `basis_overclaim`, `actual_basis_class`, `field_class_map_missing`, and `surface_field_defect_matrix` fields in the item or task background. Keep lane-key components, producer paths, quota thresholds, scale units, basis taxonomies, field classes, and locator rules in adapter/caller packets.
   - If `narrowed=true`, create or preserve the residual item in the same pack and keep it open. Do not mark the source advice applied or the original target consumed until `$validate-task-completion` records `target_met=true` or an explicit descope decision plus residual scope.
   - If prior pack items closed a measurable directive under weaker acceptance, reopen the residual scope as `planned`, `inserted`, or `blocked` rather than deleting or silently superseding it.
   - If the current `task.md` remains active and is included in the pack, make it the first item and promote it with a creation-snapshot- and authority-bound initial origin; do not create a second active task.
   - If the doctor instruction replaces `task.md` and also creates a pack, create the planned pack then use the same initial-selection contract to promote the new first task; put follow-up tasks after it as `planned`.
   - Prefer `create_pack` with its optional subject-bound initial-selection input when available so creation snapshot, authority receipt, task snapshot, and first promotion share one locked transaction. If the helper exposes only two-step compatibility, do not continue unless its durable creation receipt is captured and verified before promotion.
   - When one active pack must be replaced, use one helper-owned `replace_pack` plan and receipt. Do not emulate it with separate `supersede_pack` and `create_pack` applies, and do not hand-edit predecessor or successor JSON. Require exact predecessor coherence, a finding-free successor, a complete new/carried/retired disposition, exact carry-forward planning hashes/order, hash-bound evidence for each retired live item, a content-addressed exact-plan snapshot, and a valid complete completion receipt. A transaction ID alone is not a receipt.
   - Treat replacement atomicity honestly. The helper transaction covers the task-pack store and helper-owned evidence only; `task.md`, `past_task` archive, `.task/index.*`, schema/issue records, Git staging, and commits remain outer doctor workflow steps. For initial selection, exact `task.md` must exist by apply time; complete dry-run may use the declared hash-bound prospective staging path. The helper only hash-verifies/snapshots task bytes; it does not publish or roll them back atomically. Preflight all outer surfaces before archive, then reconcile them after the pack receipt without claiming a cross-store atomic commit.
   - Preserve the exact old `task.md` bytes and pre-replacement index anchors until the pack receipt commits. If apply fails before a prepare journal exists, restore the old task bytes, leave the still-active predecessor pack unchanged, keep the truthful archive as history, and reconcile only append-only/index-view consequences. If a valid prepare journal exists, do not roll the task or pack backward; forward-recover that exact pack transaction, then reconcile task/index links. Report which boundary was crossed.
   - If a replacement prepare journal is pending, stop every other pack mutation and run `recover-replacement` only after its plan fingerprint, target-binding transaction ID, creation evidence, and exact before/after states validate. Do not delete/truncate/rehash the journal, recreate the pack, or submit a different plan. A completed exact-plan replay may be accepted only as a receipt-validated no-op.
   - If the instruction only asks for a pack proposal, do not overwrite `task.md` unless the user explicitly asks to retarget the active task.
   - Validate and render the pack with:

     ```bash
     PYTHONPATH="${CODEX_HOME:-$HOME/.codex}/skills/orchestrate-task-cycle/scripts" python3 -m orchestrate_task_cycle task-pack --root . validate --pack <candidate-path> --strict-findings
     PYTHONPATH="${CODEX_HOME:-$HOME/.codex}/skills/orchestrate-task-cycle/scripts" python3 -m orchestrate_task_cycle task-pack --root . render --language <language>
     ```

   - If validation reports a blocking pack-schema issue, fix the pack before continuing to index or commit.

9. Reconcile state after replacement.
   - Use `$manage-schema-contracts` when `.agent_goal/goal_schema_contract.md`, `.schema/`, `.contract/`, or the new task names schema/module/script contract work.
   - Use `$manage-task-state-index` `scan` after writing `task.md` or `.task/task_pack/`.
   - Link relevant `adv-*` artifacts to the new task with `advice_for` or `incorporated_into` when `.agent_advice/` and `.task/index` exist.
   - Link task-pack artifacts to the new or current task with `pack_for_task` or `promoted_from_pack` when IDs are known.
   - Use `$manage-external-advice mark-applied` only when the advice directive is fully consumed or retired by the doctored task/design record. Otherwise keep it active and list it as a non-GT source for the later cycle.
   - Use `$manage-task-state-index` `audit`; write an audit report when the replacement touched candidates, task packs, task misses, issues, schema records, or prior task links.
   - Use `$manage-implementation-issues` when the new task intentionally defers, supersedes, creates, or tracks an implementation blocker.

10. Commit the task-direction change.
   - If `git rev-parse --is-inside-work-tree` returns `true`, invoke `$repo-change-commit` as the final mutating step.
   - Commit intent: task-doctor direction update only; include `Task: <new task id if known>`, old task/past log ID when known, and `Validation: not_run` unless a real validation command was run.
   - Let `$repo-change-commit` stage only coherent workflow artifacts and preserve unrelated local changes unstaged.
   - If the workspace is not a Git worktree, report that Git finalization was not applicable.

11. Hand off to orchestration.
   - Do not automatically run `$orchestrate-task-cycle` unless the user explicitly asked for both task doctoring and execution.
   - Report the prepublication feasibility result and exact candidate findings, the new active task summary, important convention checks, old-task archive path, task/index IDs, schema/issue updates, replacement transaction/receipt or aborted-residue state, commit hash or commit skip reason, and the recommended next invocation: `$orchestrate-task-cycle`.

## Compatibility Rules

- Preserve `$orchestrate-task-cycle` ordering by doing only pre-cycle task replacement and state reconciliation.
- Use `$derive-improvement-task` only when the user asks for agent-derived alternatives rather than direct task-doctor replacement. If used, keep its `past_task`, candidate deletion, and top execution-environment rules.
- Use `$manage-task-state-index` before and after task replacement whenever task-state artifacts exist.
- Use `$manage-task-state-index` before and after task-pack proposal changes whenever `.task/` exists.
- Keep `.agent_advice` separate from `.agent_goal`: advice can explain task direction but cannot override GT, grant authority, or satisfy `기준 GT`.
- Keep quiescence overrides explicit: when doctoring re-enters a terminal/quiesced/exhausted family, record the override reason and evidence instead of relying on renamed task wording.
- Link the new active task to the archived old task with `supersedes` or `archived_as` when IDs are known.
- Link task-pack proposals to the active/new task with `pack_for_task` or `promoted_from_pack` when IDs are known.
- Keep `task.md` formatted so `$task-md-agent-governance` can implement it without additional interpretation.
- Keep `.task/task_pack` formatted so `$derive-improvement-task` and `$orchestrate-task-cycle` can consume, insert, reorder, or terminal-block it without additional interpretation.
- Keep measurable directive provenance in `scope_fidelity`; `task.md` wording alone is not enough to prove that original acceptance survived task doctoring.
- Never claim the doctored task is complete. Completion belongs to `$validate-task-completion` after the later orchestrated cycle.

## Reporting

Report in Korean when the surrounding workflow is Korean or the repository uses `$orchestrate-task-cycle`. Preserve file paths, IDs, commands, and commit hashes exactly.

Use this concise order:

- `task doctor 지시:` explicit user direction used
- `규칙 확인:` goal/convention/rule files checked
- `선행 feasibility:` exact candidate dry-run/findings, helper capability, authority-subject constructibility, and appendability result
- `외부 조언:` used `.agent_advice` paths or `없음`
- `이전 task 처리:` archived path or `없음`
- `신규 task:` objective and path
- `task pack:` pack path/status/current item or `없음`
- `replacement transaction:` receipt/recovery state, or fail-closed blocker plus durable residue `none`
- `상태 갱신:` index/schema/issue actions and IDs when known
- `Git:` commit hash or skip reason
- `다음 단계:` `$orchestrate-task-cycle` or the specific blocker
