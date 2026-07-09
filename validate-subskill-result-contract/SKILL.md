---
name: validate-subskill-result-contract
description: "Validate result contracts from `$orchestrate-task-cycle` subskills. Use before advancing cycle stages to check required fields such as task IDs, verdicts, changed files, blockers, evidence paths, running-state details, issue status, commit status, and final-report fields; default to warn except final report or explicit block mode."
---

# Validate Subskill Result Contract

## Overview

Use this skill as a stage gate between orchestration phases. It checks whether the previous owning skill returned enough structured evidence for the coordinator to continue.

Use `/home/swfool/.codex/skills/orchestrate-task-cycle/scripts/result_contract.py` for deterministic validation.

`result_contract.py` is the stable CLI and `validate(target, result, mode)` facade. Reusable implementation lives under `scripts/result_contract_lib/`: `RuleContext` and the abstract `ContractRule`/`TargetContractRule` hierarchy own the extension contract, `RuleRegistry` composes ordered rules, common modules own configuration/access/integrity/task-routing helpers, and `rules/` owns one target-specific validator class per result family. Add or test a target rule through the registry instead of expanding the facade.

## Workflow

1. Choose the target: `governance`, `validation_set_plan`, `run`, `qualitative_review`, `validation_set_build`, `schema_pre_derive`, `derive`, `schema_post_derive`, `index`, `validate`, `issue`, `commit`, `report`, or `closeout_commit`.
2. Validate the owning skill result in `warn` mode by default.
3. Treat a missing or mismatched top-level canonical `step` as a ledger-envelope warning. Use `block` mode, or pass an explicit `--step <canonical-step>` to `$maintain-cycle-ledger`, before using the result JSON directly as a ledger event.
4. Use `block` mode when missing fields would corrupt the cycle transition, especially final report fields, `running` execution details, task-pack promotion provenance, candidate deletion, issue closure, or commit creation.
5. Append the contract result to the cycle ledger through `$maintain-cycle-ledger`.
6. Pass warnings downstream in the next subskill packet.

## Required Evidence

- `task_id` or a clear `not_applicable` reason for stages tied to a task.
- Top-level `step` matching the target when a result may be appended directly as a ledger event.
- `changed_files` for implementation/governance, validation, issue, commit, and report stages when files changed.
- `validation_verdict` and `progress_verdict` from validation onward.
- Owning-skill result statuses such as run `success` belong in the result contract; cycle ledger lifecycle status normalization belongs to `$maintain-cycle-ledger`.
- `blockers` as an explicit list, using an empty list when no blockers remain.
- `evidence_paths` for run, schema, index, validation, issue, commit, dashboard, and report stages.
- For `qualitative_review`, require reviewer routing, reviewed artifacts, direct read scope, qualitative findings, direction recommendations, output-delta handoff fields, blocker taxonomy delta, no-overclaim flags, and evidence paths. Do not accept a main-coordinator substitute as the reviewer; when reviewer delegation is unavailable, require a blocked, partial, or not-applicable result with `reviewer_delegation_unavailable_reason`.
- For `validation_set_plan` and `validation_set_build`, require scenario coverage fields when the acceptance packet supplied `acceptance_scenarios`: each scenario must be `covered`, `scenario_uncovered`, or blocked with a missing premise-satisfying input reason.
- For `run`, require `command_argv` for live executions, or explicit `command_provenance_missing=true`. A summarized command string is not enough for baseline/reproduction eligibility.
- For `run`, `validate`, or any gate/validator result that returns blockers, require actionable blocker fields when the result claims the blocker is actionable or resolved: violated relation, observed scalar values, expected relation, or minimum input delta. For multi-input relation failures, preserve abstract input-key names and any `authorization_contract_repair_candidate`. Otherwise preserve `blocker_opacity`.
- For `loopback_audit`, preserve Part J findings as fail-closed routing evidence: uncovered or inverted acceptance scenarios, missing command provenance, repeated blocker opacity, stochastic exact/floor infeasibility, and first-fire credit ownership.
- For `loopback_audit`, preserve Part K findings as routing evidence: stale expectation anchors, missing expectation anchors, parity-unverified comparisons, failed gating adoption axes, measured-but-disqualified candidates, resolution downgrades, and report-key divergence.
- For `loopback_audit`, preserve Part L findings as routing evidence: stale-lane passes, stale decision measurements, producer-starved gating axes, portfolio quota restrictions, cycle-unreachable targets, basis-overclaimed metrics, and surface-field defect matrices.
- For `loopback_audit`, preserve Part M findings as routing evidence: harvest-gate lane/scale/contract incompatibility, unaudited risky harvest gates, high-cost destructive disposition blocks, reharvest-before-rerun requirements, mutually unsatisfiable predicate/directive contracts, and sample-as-universe misuse.
- For `derive`, verify that active Part J findings constrain the selected task kind: scenario supply for `scenario_uncovered`, code/contract repair for `acceptance_inversion`, argv repair or rerun for `command_provenance_missing`, blocker-contract repair for repeated same-gate `blocker_opacity`, and contract revision/descope/escalation for `predetermined_unreachable` or `floor_edge_envelope`.
- For `derive`, verify that active Part K findings constrain the selected task kind: expectation rebaseline or fail-close for `expectation_lineage_stale`; parity-axis resolution or provisional status for `parity_unverified`; axis-classification work for `majority_vote_adoption` without `adoption_axis_classification`; gating-axis repair, rejection, or measured-but-disqualified preservation for failed `gating` axes; resolution restoration or contract revision for repeated `resolution_downgrade`; and report/schema/sync repair for `report_key_divergence`.
- For `derive`, verify that active Part L findings constrain the selected task kind: current-lane rerun/revalidation for `pass_on_stale_lane`; fresh measurement or no-impact proof for `decision_metadata_revision`; producer-supply work for `axis_starved_by_missing_producer`; producer/envelope/long-run/descope/terminal/escalation for restrictive `portfolio_quota_exceeded`; long-run launch/harvest, throughput improvement, descope, terminal, or escalation for `unreachable_within_cycle`; basis-compatible measurement or downgrade-aware contract repair for `basis_overclaim`; and producer/field repair or residual scope for nonzero `surface_field_defect_matrix`.
- For `derive`, verify that active Part M findings constrain the selected task kind: harvest-gate repair/mitigation or explicit risk acceptance for non-degradable `lane_incompatible`, `scale_incompatible`, or `contract_conflict`; quarantine/reharvest-path supply or gate repair before rerun for high-cost verifier/governance failures; predicate/directive reconciliation for `mutually_unsatisfiable_contract`; and full-collection supply or sample-only contract revision for `sample_as_universe_misuse`.
- For `validate`, reject `complete` when Part J gates are unresolved: uncovered/inverted scenarios, required command provenance missing, claimed-resolved opaque blockers, stochastic infeasible contracts without revision/descope/escalation, or double-counted `instrumentation_first_fire`.
- For `validate`, reject `complete` or `advanced` when Part K gates are unresolved: stale expectation lineage without rebaseline/descope, final comparison/adoption with `parity_unverified`, majority-vote adoption without axis classification, failed gating axes or `measured_but_disqualified`, high-resolution contracts satisfied only by unresolved `resolution_downgrade`, or `report_key_divergence`.
- For `validate`, reject `complete` or `advanced` when Part L gates are unresolved: current-lane claims from `pass_on_stale_lane`, measurement/adoption from `decision_metadata_revision`, verifier-like progress on `axis_starved_by_missing_producer`, verifier-like work during restrictive `portfolio_quota_exceeded`, smoke/launch-only completion under `unreachable_within_cycle`, independently verified progress from `basis_overclaim`, or review pass consumption with unresolved nonzero `surface_field_defect_matrix`.
- For `validate`, reject `complete` or `advanced` when Part M gates are unresolved: long-run launch/harvest consumed incompatible harvest gates without repair or risk acceptance, high-cost non-safety artifacts were destructively disposed instead of quarantined, rerun occurred before available reharvest, predicate/directive contracts remain mutually unsatisfiable, or truncated/sample collections were consumed as closed-world universes.
- For `validate` and `report`, reject pass/close consumption when `report_key_divergence=true` or when the deterministic scan finds the same terminal report key at multiple JSON paths with different values. Matching duplicate keys are schema debt and warn-only; divergent values are blocking because the consumer cannot know which copy is truth.
- Reject close/adoption/high-water consumption when `report_body_divergence=true` or required actual-body truth is `not_evaluated`. Body divergence compares the actual artifact's canonical body projection to a report; key divergence compares duplicate terminal-key bindings. Do not collapse them.
- For `advanced`, require the close owner's `authoritative_progress_verdict: advanced` and verify it does not upgrade loopback's `authoritative_semantic_progress=false` or any hard stop. Actual body truth, report convergence, artifact class, freshness/current lane, required consumer contexts, and verifier completeness must all be evaluated and satisfied when required.
- Treat consumer-context conformance as external probe evidence. A root import, hook-name string, metric name, or adapter self-attestation is not wiring evidence; required rows need `consumer_context_id`, `adapter_loaded`, `required_hook_callable`, `hook_signature_compatible`, `return_contract_valid`, and `probe_evidence_id`.
- `commit_role`, `commit_status`, and `evidence_paths` for commit results.
- `commit_hash` and `commit_subject` for created commits; `commit_skipped_reason` for skipped, blocked, or failed commits.
- `task_pack_status`, `task_pack_path`, and `task_pack_item_id` or `promoted_item_id` when derivation or reporting promotes the next task from `.task/task_pack/`.
- `has_supplied_input_delta` plus `supplied_input_artifact_paths` or `produced_domain_delta=true` when a derive result relies on positive input delta.
- `provider_reattempt_disposition` when `provider_reattempt_required=true`; terminal/provider-family sealing is invalid while bounded retry/probe is still required.
- Dual-track terminal blocker evidence when `detect_progress_loop status=block` forces terminal state.
- `consolidation_candidate_registered` or selected consolidation work when `command_surface_budget.consolidation_candidate_required=true`.
- `tracked_artifacts` for `closeout_commit` results.
- `acceptance_scenario_gate`, `command_provenance_gate`, `blocker_actionability_gate`, `stochastic_feasibility_gate`, and `instrumentation_first_fire_gate` for validation results when the corresponding source fields appeared earlier in the cycle.
- `expectation_lineage_gate`, `comparison_parity_gate`, `adoption_axis_gate`, `resolution_downgrade_gate`, and `report_key_integrity_gate` for validation results when the corresponding Part K source fields appeared earlier in the cycle.
- `lane_identity_gate`, `decision_freshness_gate`, `gating_axis_producer_gate`, `portfolio_quota_gate`, `cycle_reachability_gate`, `metric_basis_gate`, and `surface_field_review_gate` for validation results when the corresponding Part L source fields appeared earlier in the cycle.
- `harvest_contract_preflight_gate`, `disposal_proportionality_gate`, `contract_satisfiability_gate`, and `collection_consumption_gate` for validation results when the corresponding Part M source fields appeared earlier in the cycle.

## Guardrails

- Do not infer success from missing data.
- Do not use this skill to override an owning skill verdict.
- Do not let green tests satisfy a missing `acceptance_scenario_gate`.
- Do not let summarized commands or `...` satisfy command provenance.
- Do not treat opaque blockers as actionable contract evidence.
- Do not let stochastic infeasibility findings be reported as ordinary retry blockers.
- Do not let `instrumentation_first_fire` be counted twice in result contracts.
- Do not let stale expectation anchors, parity-unverified comparisons, majority-vote adoption without axis classification, failed gating adoption axes, or resolution-downgraded surrogate proof be consumed as final pass/close evidence.
- Do not let a report with divergent duplicate terminal keys support pass, close, adoption, baseline, comparison, or high-water movement.
- Do not let stale-lane passes, stale decision measurements, producer-starved gating axes, restrictive verifier-like quota excess, cycle-unreachable smoke/launch evidence, basis-overclaimed metrics, or unresolved surface-field defect matrices be consumed as final pass/close/progress evidence.
- Do not let incompatible or unaudited risky harvest gates, destructive high-cost non-safety disposition, rerun-before-reharvest, mutually unsatisfiable predicate/directive contracts, or sample-as-universe misuse be consumed as final pass/close/progress evidence.
- Do not let the deterministic result-contract script be weaker than the SKILL.md contract; when Part J fields are present, it must emit at least warning-level findings for invalid stage transitions.
- Do not let the deterministic result-contract script be weaker than the SKILL.md contract; when Part K fields are present, it must emit at least warning-level findings, and `report_key_divergence` must be blocking for pass/close targets.
- Do not let the deterministic result-contract script be weaker than the SKILL.md contract; when Part L fields are present, it must emit at least warning-level findings, and stale-lane pass or cycle-unreachable completion must be blocking for pass/close targets.
- Do not let the deterministic result-contract script be weaker than the SKILL.md contract; when Part M fields are present, it must emit at least warning-level findings, and sample-as-universe misuse, mutually unsatisfiable contracts, destructive high-cost disposition, or risky harvest consumption must be blocking for pass/close targets.
- Treat contract output as orchestration evidence only; it is not a replacement for validation or issue tracking.
