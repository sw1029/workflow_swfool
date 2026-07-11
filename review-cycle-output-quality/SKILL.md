---
name: review-cycle-output-quality
description: "Run one read-only qualitative reviewer agent over task-cycle output artifacts after `$run-task-code-and-log` returns and before `$derive-improvement-task` selects the next task. Use when `$orchestrate-task-cycle` needs direct inspection of generated outputs, KG/candidate artifacts, reports, logs, dashboards, validation bundles, or other task products so the next-task direction can incorporate qualitative output quality without treating the review as goal truth or implementation authority."
---

# Review Cycle Output Quality

## Overview

Use this skill to add one direct qualitative output-review pass to a task cycle. It is a workflow evidence skill, not a goal-truth source, not a human-review substitute, and not an implementation escape hatch.

The caller should invoke it after `$run-task-code-and-log` returns execution evidence and before `$derive-improvement-task` builds the next task. The result should be passed into schema refresh, visible increment, portfolio planning, derivation, validation, dashboard, and final report packets when relevant.

## Invocation Contract

- Invoke exactly one read-only reviewer agent. Do not fan out multiple reviewers, create debate panels, or let the main coordinator silently replace the reviewer.
- Route the reviewer at Tier 4 with `model: gpt-5.6-terra` and `reasoning_effort: xhigh`. This read-only qualitative reviewer is capped at Tier 4 and must not use Sol. If the tool cannot enforce either field, preserve the request in the prompt, report prompt-only or inherited-unverified routing, and do not claim Terra execution. Do not use `ultra`.
- Keep the reviewer read-only. It may inspect task outputs, generated artifacts, logs, validation bundles, `.task/`, `.agent_log/`, `.schema/`, `.contract/`, `.issue/`, `.agent_advice/`, and source/output artifacts named by task/run evidence when authority permits.
- Do not let the reviewer edit implementation files, workflow artifacts, task state, issue state, schema records, commits, or advice lifecycle files.
- Do not read `.env`, credentials, private keys, raw secrets, or unrelated personal data. Do not persist raw provider prompts/responses/source bodies unless the task policy explicitly allows bounded local evidence.
- Do not pass raw/slim session transcripts or session-audit packet bodies as review artifacts. Session governance remains a separate noncanonical sidecar consumed at context/loopback/validation/issue/derive/report, not qualitative output evidence.
- When inspecting copyrighted or sensitive source/output content, summarize findings and store paths, hashes, counts, IDs, bounded span refs, and brief non-sensitive snippets only when safe.
- If no output artifact is available, content access is prohibited, or delegation is unavailable, return a structured `blocked`, `partial`, or `not_applicable` result instead of inventing qualitative evidence.

## Reviewer Prompt Shape

Give the single reviewer only task-local evidence needed to inspect the output:

- current or completed task ID and summary
- run result status, commands, evidence paths, and output artifact paths
- relevant authority policy and no-overclaim constraints
- relevant active non-GT advice packet
- relevant schema/contract summaries when they define output expectations
- expected acceptance criteria or quality dimensions

Ask the reviewer to directly open and inspect the named artifacts. The reviewer should compare actual artifact content against task intent and no-overclaim boundaries, then return a compact structured result. Do not pass the desired answer or prior diagnosis unless the task explicitly asks to verify a known finding.

## Domain Adapter Contract

Prefer caller-supplied adapter packets over reviewer-local domain assumptions. The reviewer may consume these optional hooks only through opaque ids, scalars, and enums:

- `substance_density(metric_id, **context) -> dict`: optional N1 helper returning `referent_meaning_ratio`, `opaque_surrogate_ratio`, and adapter-owned `floor` for a metric target. The adapter owns what counts as referent meaning, opaque surrogate, and threshold. If absent, fail quiet with `substance_density_unchecked=true` and keep existing semantic-readiness/substance review behavior.
- `output_body_locator(manifest, **context) -> dict`: optional S2 helper returning producer-declared body locations such as `body_dir`, `required_files`, opaque schema/layout ids, and optional evidence refs. Use it before any artifact-present or empty judgment. If declared required files exist at the producer-declared body location, do not mark the output `missing_or_empty` only because a fixed legacy path is empty. If the hook is absent or malformed, fail quiet to existing fixed-path lookup and record `path_binding=fixed_only` / `output_body_locator_unverified`; if manifest layout differs from reviewer expectations, record `layout_drift=true` and fall back to the producer-declared path without inventing repo-specific paths.
- `landed_feature_inventory(**context) -> dict`: optional P1 helper returning adapter-owned landed feature classes and the authorized set expected on a representative output. The reviewer compares only opaque class ids against output-manifest `feature_classes_present` when available. If absent, fail quiet and keep existing output-quality review behavior.
- `feature_presence_evidence(feature_class, artifact_root, **context) -> dict`: optional Q2 helper returning `presence_field`, `observed_count`, `min_count`, `artifact_body_present`, and optional opaque evidence ids for a representative output body. When supplied, P1 `present` is true only when `artifact_body_present=true` and `observed_count >= min_count`; metadata-only pointers, manifests, or other artifact existence cannot satisfy presence. If absent, fail quiet to existing P1 review and record `presence_basis=manifest_declaration_only` when the manifest is the only basis.

Do not define domain lexicons, identifier surface forms, source-language rules, feature-class meanings, or thresholds in this skill. Part N hooks not used by the reviewer, such as deliverable fingerprinting or persistence policy maps, should be preserved from caller packets for downstream skills rather than reinterpreted here. P1 is production-configuration regression accounting only; do not double-count it as Part L stale-lane consumption or N2 deliverable staleness.

## Quality Dimensions

Ask the reviewer to cover only dimensions relevant to the produced artifact:

- `artifact_presence`: expected outputs exist, are readable, and are in the intended location. For existence/empty judgments, first resolve the body through S2 `output_body_locator` when a producer manifest is supplied; producer-declared body files prevent `missing_or_empty` even if a fixed legacy directory is empty. When the hook is absent, keep the fixed-path legacy check but report `path_binding=fixed_only` / `output_body_locator_unverified`; when the manifest schema or layout id differs from reviewer expectations, report `layout_drift` and use the declared path fallback. Do not infer output-layer paths from project-specific names in this skill.
- `format_contract`: files parse and follow the expected schema, report, dashboard, KG, or validation shape.
- `content_coverage`: output covers the task's material requirements and important source/output regions.
- `semantic_quality`: labels, entities, relations, claims, summaries, visuals, or decisions are meaningful rather than generic or meta-process filler.
- `landed_feature_regression`: when `landed_feature_inventory` is supplied for a new representative output, compare authorized feature classes against Q2 `feature_presence_evidence` body counts when that hook is available; present requires the adapter-owned body field count to meet its minimum. If the body file is absent, set `artifact_body_missing=true`, fail-close the review verdict, and cap review-backed progress for that output at `governance_only`. If body evidence exists but only metadata pointers or other artifact existence support the class, count `synthesis_not_materialized`, set `feature_regression_count`, and preserve `feature_regressed_artifact=true`. If Q2 evidence is absent, fall back to the output manifest's `feature_classes_present`, set `presence_basis=manifest_declaration_only`, and keep existing P1 behavior. Set `feature_manifest_missing=true` when the manifest is absent and no body hook supplies presence. If the inventory hook is absent, fail quiet and do not infer feature classes locally.
- `semantic_readiness`: whether primary output semantics are ready enough to count as progress, or are capped by placeholder events, surface-only entities, unsupported relations, generic labels, or meta-process filler.
- `substance_delta`: whether the produced artifact contains real primary-output substance beyond validator/oracle/metric existence, using adapter/domain packet fields when supplied.
- `constraint_forced_vacuity`: whether a passed metric points at adapter-classified opaque surrogates or otherwise meaning-empty targets below the adapter-owned density floor. This is separate from tautological metric validity: G-OENV covers metrics that pass by construction, while N1 covers real measurements over empty targets.
- `vacuous_corrective`: whether corrective/backfill/reconciliation rows attempted work but resolved zero actual items.
- `degenerate_surface_language`: whether entities or events appear to be pronouns, Korean particles attached to common nouns, repeated generic nouns, placeholders, or surface strings without stable identity.
- `coverage_sufficiency`: whether `windows_covered` or equivalent source-window coverage satisfies the current task/rung; partial windows should cap progress when the rung requires full-window or multi-work coverage.
- `goal_axis_completeness`: when the caller or repository adapter supplies `goal_axis_map`, verify that every active measurable goal has at least one mapped `quality_vector` axis. Do not invent axes; report `pass_with_unobserved_axes=true` for goals whose mapped axis set is empty.
- `verification_source_separation`: when reviewing an independent verification artifact, report the verification input paths and verified artifact paths if observable. Treat zero disagreements as quality evidence only when those inputs are disjoint from the verified artifacts, unless the caller/adapter marks the axis `self_grounded`.
- `instrumentation_exercise`: when artifacts claim newly supplied diagnostics or instrumentation, report whether a fresh run id after the supply item recorded non-empty scalar fields, or whether the evidence is only `derived_from_existing_artifacts`.
- `acceptance_encoding`: when reviewing directive-derived reports, preserve visible `acceptance.quantifiers` and `evidence_kind`; do not treat report-only evidence as satisfying a live-run criterion.
- `verifier_surface_hardening`: when the reviewed artifact is another verifier, guard, consistency check, or report over the same target artifact without a fresh run id, report it as guard/report-only hardening rather than primary-output progress.
- `run_disposition`: when reviewing run outputs, distinguish `candidate_degraded` quality-miss evidence from `candidate_written` output and `failed_closed` unsafe discard.
- `surface_field_review`: when artifacts have source locators and the caller or adapter supplies `surface_field_classes`, sample the adapter-owned number of records and compare every producer-written surface string field class against the located source. Record scalar counts by field class and defect class; do not store excerpts unless authority explicitly permits them. If the field map is absent, report `field_class_map_missing` and fail quiet to existing review semantics.
- `output_delta`: when the caller supplies an output-delta contract packet, call the contract helper on produced artifact paths and report whether the repository-defined primary output layer actually changed.
- `validator_disagreement`: when the caller supplies strict runner validation plus output-delta evidence, compare their `semantic_progress` values. If runner validation says true while output-delta says false, report a block-level disagreement and return only an `observed_semantic_progress` claim. This review never owns the authoritative progress verdict.
- `coverage_quality_reconciliation`: when the caller supplies both loopback and output-delta G-COV evidence, report a block-level disagreement if `coverage_quality_delta_reconciliation_gate.status=block`; do not let the favorable G-COV source override inspected output quality.
- `observed_output_class`: when the caller supplies loop-breaker or output-delta evidence from `detect_progress_loop.py`, prefer the observed class over self-declared progress fields. Classify `metadata_only` and repeated `terminal_record` as governance-only unless independent artifact inspection proves a primary output delta.
- `evidence_traceability`: claims link to exact supporting paths, hashes, spans, logs, or validation records.
- `user_visible_quality`: output is understandable, useful, and not misleading for the target user or workflow.
- `no_overclaim`: output does not claim gold, readiness, legal/rights/ZKP/downstream status, or completion beyond evidence.
- `blocker_direction`: defects are classified into actionable next-task directions.

## Result Contract

Return a JSON-compatible summary and, when durable evidence is required, write a Markdown or JSON report under `.task/quality_review/<cycle-id>-direct-output-quality-review.{md,json}` through the owning workflow. The result must include:

```json
{
  "task_id": "task-* or unknown",
  "cycle_id": "cycle-* or unknown",
  "review_agent_count": 1,
  "agent_routing_applicability": "delegated|delegation_unavailable",
  "policy_id": "gpt-5.6-tiered-routing-v2",
  "profile_id": "qualitative_review",
  "routing_tier": 4,
  "requested_model": "gpt-5.6-terra",
  "requested_reasoning_effort": "xhigh",
  "routing_reason_codes": ["profile_default"],
  "routing_signals": {},
  "routing_signal_evidence": {},
  "routing_violations": [],
  "routing_enforcement": "enforced|prompt_only|inherited_unverified",
  "routing_limitation": "required unless enforced",
  "reviewer_routing": "structured routing evidence or limitation note",
  "review_status": "complete|partial|blocked|not_applicable",
  "quality_verdict": "acceptable|candidate_only|quality_blocked|unreviewable|not_applicable",
  "reviewed_artifacts": ["path-or-id"],
  "direct_read_scope": ["path-or-class"],
  "path_binding": "producer_declared|fixed_only|not_applicable",
  "layout_drift": false,
  "output_body_locator_unverified": false,
  "qualitative_findings": [
    {
      "severity": "high|medium|low|info",
      "dimension": "artifact_presence|format_contract|content_coverage|semantic_quality|landed_feature_regression|semantic_readiness|substance_delta|constraint_forced_vacuity|vacuous_corrective|degenerate_surface_language|coverage_sufficiency|goal_axis_completeness|surface_field_review|evidence_traceability|user_visible_quality|no_overclaim|blocker_direction",
      "summary": "concise finding",
      "evidence_refs": ["path:line, artifact id, hash, span ref, or log id"]
    }
  ],
  "direction_recommendations": ["next-task direction candidate"],
  "output_delta_status": "complete|not_applicable_no_contract|not_applicable_no_provider|blocked_provider_failed|blocked_provider_malformed",
  "observed_output_class": "node_edge_delta|metadata_only|terminal_record|unknown",
  "changed_vs_previous": false,
  "semantic_progress": false,
  "substance_delta_pass": false,
  "feature_manifest_missing": false,
  "artifact_body_missing": false,
  "presence_basis": "body_field_count|manifest_declaration_only|not_applicable",
  "synthesis_not_materialized": false,
  "feature_regression_count": 0,
  "feature_regressed_artifact": false,
  "constraint_forced_vacuity": false,
  "substance_density_unchecked": false,
  "referent_meaning_ratio": null,
  "opaque_surrogate_ratio": null,
  "substance_density_floor": null,
  "vacuity_cause": "production_constraint|missing_producer_capability|unknown|not_applicable",
  "surface_corrective_noop": false,
  "semantic_ready": "true|false|unknown",
  "placeholder_event_found": false,
  "surface_quality_suspected": false,
  "surface_entity_suspected": false,
  "quality_blocker_codes": ["surface_quality_suspected|surface_entity_suspected|coverage_insufficient|placeholder_event_found"],
  "relation_semantics_ready": "true|false|unknown",
  "produced_domain_delta": false,
  "metadata_only": true,
  "effective_progress_kind": "goal_productive|governance_only",
  "progress_cap": "goal_productive|governance_only|terminal_blocked",
  "cap_reason": "why the cap applies, or none",
  "output_delta_summary": {"repo-defined scalar counts": "only when available"},
  "validator_disagreement": false,
  "coverage_quality_delta_reconciliation_status": "pass|block|not_applicable",
  "goal_axis_completeness_gate": {
    "evaluation_status": "pass|fail|not_evaluated",
    "active_measurable_goals": [],
    "goal_axis_map": {},
    "unobserved_goal_axes": []
  },
  "verification_source_separation_gate": {
    "independent_source_separation_status": "pass|missing|overlap|blocked|not_evaluated",
    "verification_input_paths": [],
    "verified_artifact_paths": [],
    "self_grounded_axes": [],
    "independently_verified_downgraded_fields": []
  },
  "instrumentation_exercise_gate": {
    "instrumentation_exercise_required": false,
    "instrumentation_exercised": false,
    "instrumentation_run_id": null,
    "derived_from_existing_artifacts": false
  },
  "acceptance_encoding_gate": {
    "quantifiers_preserved": true,
    "evidence_kind": "live_run|derived_artifact|code_contract|report_only|not_applicable",
    "acceptance_diluted": false
  },
  "verifier_surface_hardening_gate": {
    "verifier_surface_hardening": false,
    "target_artifact_paths": [],
    "fresh_run_id_present": false
  },
  "run_disposition": "failed_closed|candidate_degraded|candidate_written|not_applicable",
  "surface_field_review_gate": {
    "surface_field_review_status": "pass|fail|not_evaluated",
    "surface_field_classes": [],
    "field_class_map_missing": false,
    "review_sample_count": 0,
    "surface_field_defect_matrix": {},
    "excerpt_policy": "counts_only|authority_allows_excerpts|not_applicable"
  },
  "pass_with_unobserved_axes": false,
  "observed_semantic_progress": false,
  "truth_basis": "independently_recomputed_actual_artifact|source_separated_verifier|current_transform_report|producer_report|carried_forward_report|workflow_status_claim|not_evaluated",
  "body_projection_fingerprint": null,
  "recomputed_fields": [],
  "source_artifact_ids": [],
  "current_artifact_id": null,
  "report_body_divergence": false,
  "verification_input_ids": [],
  "producer_input_ids": [],
  "verified_artifact_ids": [],
  "input_fingerprints": {},
  "evidence_provenance": "independently_verified|producer_attested|self_grounded|not_evaluated",
  "blocker_taxonomy_delta": ["quality_blocker|output_artifact_blocker|kg_core_blocker|claim_readiness_blocker|workflow_lifecycle_blocker|task_state_blocker"],
  "no_overclaim_flags": ["not_gold", "not_ready", "not_complete"],
  "evidence_paths": ["review report path or inspected artifact path"],
  "used_goal_truth": ["actual .agent_goal paths used, or empty"],
  "used_advice": ["actual .agent_advice paths used, or empty"],
  "advice_handling_rationale": "required when active advice exists but was not used"
}
```

Use `review_status` as the owning skill result status. When the orchestration ledger records this stage, use canonical lifecycle statuses such as `complete`, `partial`, `blocked`, `skipped`, or `not_applicable` and preserve the raw result status separately if needed.

## Integration Guidance

- Pass the result to `$manage-schema-contracts` before derivation when the review found schema, evidence, or artifact-contract gaps.
- Pass the result to `$record-visible-increment` as explanatory context only; it is not validation evidence by itself.
- Pass the result into `$derive-improvement-task` as `qualitative_review_packet`. The derivation portfolio packet should synthesize this review with run evidence, schema status, advice disposition, progress-loop detection, issues, misses, and goal alignment.
- When reviewing artifact presence or emptiness from a producer manifest, apply S2 path binding before judging output absence: if `output_body_locator` supplies declared `body_dir` and `required_files` and those files exist, report the output as present/readable rather than `missing_or_empty`; if the hook is absent, preserve the old fixed-path behavior but carry `path_binding=fixed_only` and `output_body_locator_unverified`; if layout drift is observed, warn with `layout_drift=true` and use the declared path fallback. Keep this as Part M/N input rebinding only; do not add a new detector or report.
- When `produced_domain_delta` is false, `changed_vs_previous` is false, `semantic_progress` is false, or `metadata_only` is true, require downstream derivation to treat the cycle as `governance_only` unless independent validated positive evidence proves otherwise. Do not let metadata-only measurement, non-empty counts, lineage, or gap reports masquerade as goal-productive output.
- When strict runner validation and output-delta disagree, carry source-separated evidence ids/fingerprints and set `observed_semantic_progress` to the conservative observation. `$audit-cycle-loopback` owns the pre-derive `authoritative_semantic_progress`; `$validate-task-completion` alone owns the close-time `authoritative_progress_verdict`.
- Prefer independently recomputed values from the actual artifact body over source-separated verifier results, current transform reports, producer reports, carried-forward reports, and workflow claims, in that order. Keep carried-forward values under `source_*` and current-transform values under `current_*`. If a required body projection cannot be recomputed, return `truth_basis: not_evaluated`; if its canonical fingerprint disagrees with the report, set `report_body_divergence: true`. This review reports the observation and must not close the task.
- Persist privacy-safe `verification_input_ids`, `producer_input_ids`, `verified_artifact_ids`, fingerprints, and provenance labels. Re-reading a producer scalar is `producer_attested`, not independent verification; a coupled verifier is `self_grounded`/`pass_with_coupled_verifier` and cannot move high-water.
- When `coverage_quality_delta_reconciliation_gate.status=block`, report the disagreement and cap measurement/oracle/rung progress unless strict changed-and-semantic primary-output evidence independently proves progress.
- When `substance_delta_gate` is supplied and `substance_delta_pass=false` or `status=missing`, cap measurement/oracle/rung progress at `governance_only` unless strict changed-and-semantic output-delta evidence independently proves primary-output progress.
- When `landed_feature_inventory` is supplied, use `feature_presence_evidence` as the Q2 body anchor when available. If `artifact_body_present=false` or the representative body file is missing, set `artifact_body_missing=true` and fail-close the landed-feature review instead of accepting manifest declarations. If the body exists but `observed_count < min_count`, or presence relies only on `metadata_only` pointers or other artifact existence, set `synthesis_not_materialized=true`, increment `feature_regression_count`, preserve `feature_regressed_artifact=true`, and cap all axis deltas derived from that artifact at `governance_only`. If the Q2 hook is absent, fail quiet to the existing manifest comparison, set `presence_basis=manifest_declaration_only`, and do not infer body fields locally. Do not double-count Q2 separately from P1; it is the present-condition for the same landed-feature inheritance gate.
- When `substance_density` is supplied for a passed link, coverage, or response metric, apply this N1 flow: metric passed -> density hook present? if no, set `substance_density_unchecked=true` and fail quiet to existing review semantics; if yes, compare `referent_meaning_ratio` with adapter `floor`; if below floor, set `constraint_forced_vacuity=true`, cap affected metric progress at `governance_only`, and route `vacuity_cause=production_constraint` to persistence-policy repair or `vacuity_cause=missing_producer_capability` to producer supply. If the metric itself is tautological, route through G-OENV instead of N1.
- When `vacuous_corrective_gate.surface_corrective_noop=true`, report `surface_corrective_noop: true`, cite the affected lanes, and do not count those attempted rows as semantic or produced output delta.
- When `goal_axis_map` is supplied and any active measurable goal has zero mapped axes, set `goal_axis_completeness_gate.evaluation_status=fail`, set `pass_with_unobserved_axes=true`, cite the unobserved goals, and cap review-backed progress for those goals. Recommend adapter axis supply, explicit residual scope, terminal blocker, or user escalation; do not let the review's overall pass wording consume the affected target.
- When `goal_axis_map` is absent, set `goal_axis_completeness_gate.evaluation_status=not_evaluated` or omit the gate. Missing optional axis mapping is fail-quiet unless acceptance/caller packets require it.
- When reviewing an artifact that claims independent verification, preserve `verification_input_paths`, `verified_artifact_paths`, and `self_grounded_axes` if they are present. If inputs are missing or overlap the verified artifacts, set `independent_source_separation_status=missing|overlap`, move affected fields into `independently_verified_downgraded_fields`, and do not treat zero disagreements as independently verified progress.
- When supplied instrumentation has not been exercised by a fresh run id with non-empty scalar fields, set `instrumentation_exercise_required=true` and do not treat the corresponding measurement/report as progress. Existing artifact reinterpretation is `derived_from_existing_artifacts`, not exercise.
- When an artifact satisfies a `live_run` criterion only through a derived artifact, code contract, or report, set `acceptance_diluted=true` and cap review-backed progress for that criterion.
- When the reviewed change is guard/verifier/report-only hardening over the same target artifact and no fresh run id exists, set `verifier_surface_hardening=true`; do not describe it as primary-output progress.
- When the run disposition is `candidate_degraded`, preserve it as quality-miss evidence and do not call it acceptable/canonical output unless independent verification evidence is supplied for the consumed axes.
- When `surface_field_classes` is supplied, cover every listed producer-written surface string field class, not only summaries or the most visible field. Set `surface_field_review_status=fail` when scalar defects are nonzero, preserve `surface_field_defect_matrix`, and recommend producer/field repair, residual descope, terminal blocker, or user escalation as appropriate. Missing field class maps are `field_class_map_missing=true` and fail quiet.
- When `surface_quality_suspected=true`, `semantic_ready=false`, `placeholder_event_found=true`, or `surface_entity_suspected=true` affects the primary output, set `progress_cap: governance_only` unless strict changed-and-semantic output-delta evidence independently proves primary-output progress.
- Do not double-count Part M and Part N: Part M harvest/preflight fields decide whether the execution-context exit contract was safe to consume; N1 decides whether the landed output target carries adapter-owned meaning after that exit. Preserve both when supplied, but use one blocking reason per affected progress claim.
- When pronoun-only, particle-attached, common-noun, placeholder, or repeated-generic labels affect primary entities/events, set `surface_quality_suspected=true`, set `surface_entity_suspected=true`, add both codes when applicable, and cap progress at `governance_only` unless strict changed-and-semantic output-delta evidence proves otherwise.
- When `windows_covered` is below the task/rung requirement, add `coverage_insufficient` to `quality_blocker_codes` and recommend full-window, multi-window, or multi-work extraction rather than another measurement surface.
- When `observed_output_class` is available, carry it into `qualitative_review_packet` and downstream derivation. Do not allow self-declared `produced_domain_delta=true` to override an observed `metadata_only` or repeated `terminal_record` classification.
- Require `$derive-improvement-task` to explain whether it incorporated, deferred, rejected, or found this review not applicable.
- Pass the result into `$validate-task-completion` as qualitative evidence, while preserving that it is agent review rather than direct human approval.
- Report this review in Korean cycle summaries as agent qualitative output review evidence when it affects the next task direction.

## Failure Handling

- If the reviewer cannot open required artifacts, return `review_status: blocked` or `partial` with missing paths and a direction recommendation to repair artifact persistence or run logging.
- If the run is `running`, review only startup/heartbeat/output artifacts that exist and mark final-output-dependent findings as pending.
- If the review finds that code must change, do not edit code. Return a recommendation for `$task-md-agent-governance` or next-task derivation.
- If active advice exists and is relevant, include it in `used_advice`. If not relevant, state `advice_not_applicable_reason` or `advice_handling_rationale`.
