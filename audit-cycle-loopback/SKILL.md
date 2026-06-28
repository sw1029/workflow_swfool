---
name: audit-cycle-loopback
description: "Compute conservative anti-loop progress packets for governed task cycles. Use after run and qualitative output review, before derivation, when Codex needs to detect same-family micro-hardening loops, distinguish jitter or lateral churn from semantic progress, update `.task/anti_loop/family_progress_registry.jsonl`, and pass an `anti_loop_progress_gate` packet into `$derive-improvement-task` without treating self-declared progress or `produced_domain_delta` as truth."
---

# Audit Cycle Loopback

## Overview

Use this skill to fill anti-loop inputs that downstream derivation already consumes: `changed_vs_previous`, `semantic_progress`, `terminal_outcome_changed`, `same_family_micro_hardening_count`, `effective_allowed_dispositions`, root-cause hypothesis ledger state, and validator/output-delta disagreement flags.

The skill is workflow evidence only. It is not goal truth, authority, validation evidence, human review, issue closure evidence, or readiness/gold promotion evidence.

## Workflow

1. Collect raw artifact paths from the run, qualitative review, and output-delta packet.
2. Run `scripts/anti_loop_gate_provider.py` with the cycle id, artifact family, semantic signature, suffix-normalized root key when known, provider request count, and artifact paths. When available, also pass loop-detection or portfolio gates with `--gate-state-json`, recent progress items with `--recent-progress-json`, strict runner validation with `--runner-validation-json`, and the output-delta packet with `--output-delta-json`.
   - Pass stable oracle/check identities with `--measurement-check-id` or `--measurement-check-ids-json` when the cycle introduces or first exercises a validator, oracle, metric, or reconstruction check.
   - Pass `--measurement-frontier` for first-observed frontiers such as `event_sequence_oracle`, `reconstruction_coverage`, `relation_class_filled`, or `story_vs_narrative_split`.
   - Pass `--blocker-signature` and `--blocker-rung` when qualitative review, loop detection, or a task pack identifies the current blocker and capability-ladder rung.
   - Pass root-cause hypotheses with `--root-cause-hypotheses-json` or `--hypothesized-root-cause`; mark `--root-cause-repair-attempted` only when the active task explicitly targeted that hypothesis. Domain adapters may instead expose `root_cause_hypotheses(...)`.
   - Keep `--detection-only-streak-cap` at the default `2` unless the active workflow explicitly records a different cap. This cap is root-family scoped and only controls detection-only repetition.
3. Write the resulting packet under `.task/cycle/<cycle-id>/packets/loopback_audit_packet.json` when `$orchestrate-task-cycle` owns durable cycle artifacts.
4. Pass the packet into `$derive-improvement-task` as `anti_loop_progress_gate`.
5. If the packet is `insufficient_evidence` or near the hard-stop threshold, optionally ask exactly one read-only reviewer to inspect the same raw artifacts and registry. Use the more conservative disposition when reviewer and producer disagree.

## Domain Adapter Contract

Prefer a repository-supplied domain adapter over producer-local domain assumptions. Pass it with `--domain-adapter <path.py>` or set `TASK_CYCLE_DOMAIN_ADAPTER_PATH`. The module may expose these functions with keyword parameters such as `root`, `artifact_paths`, `quality_vector`, `output_delta`, and `runner_validation`:

- `quality_vector(...) -> dict`: domain quality/coverage vector. It may return either the vector directly or `{quality_vector, evidence_paths, insufficient_reason}`.
- `substance_metrics(...) -> dict`: primary-output substance vector used by G-SUBSTANCE.
- `corrective_resolution(...) -> list|dict`: corrective/backfill lanes with `attempted` and `resolved` counts for G-VACUOUS.
- `facet_root_map(...) -> dict`: facet labels mapped to root families for G-FACET.
- `output_fingerprint(...) -> str`: current primary-output fingerprint for G-ADVICE-FRESH.
- `previous_accepted_fp(...) -> str|dict`: previous accepted primary-output fingerprint, and optionally previous quality/high-water vector, for R-GCOV baseline selection.
- `structure_metrics(...) -> dict`: optional entrypoint/module structure metrics such as LOC, command count, function count, or consolidation recommendation for S-STRUCT.
- `root_cause_hypotheses(...) -> list|dict`: domain-owned root-cause hypothesis slugs plus optional `repair_attempted`, `repair_task_id`, `local`, `bounded`, `provider_free`, `in_scope`, `authority_allowed`, and `actionable` booleans.

The adapter must keep domain-specific file paths, metric names, lexicons, and thresholds outside this skill. If no adapter is registered, the producer keeps the legacy repository fallback for `scripts/novel_kg_quality_metrics.py` or `NOVEL_KG_QUALITY_METRICS_PATH`, but missing substance metrics fail closed for measurement or capability-ladder promotion.

Use conservative defaults:

- Do not infer semantic quality from self-declared `produced_domain_delta`.
- Treat missing adapter output, low-confidence quality, malformed artifacts, or stale fingerprint claims as workflow blockers or warnings rather than progress.
- Keep domain lexicons, thresholds, source-language handling, placeholder rules, and OCR handling inside the adapter or repository-owned shared module.
- Do not hardcode project module paths, metric names, lexicon paths, or artifact filenames into this skill body or producer logic.

## Producer Command

```bash
python3 /home/swfool/.codex/skills/audit-cycle-loopback/scripts/anti_loop_gate_provider.py \
  --root . \
  --cycle-id cycle-YYYYMMDD-HHMMSS \
  --artifact-family primary_output \
  --semantic-signature source_to_output_execution \
  --root-key capability-ladder \
  --domain-adapter .task/domain_adapter.py \
  --provider-request-count 0 \
  --artifact-path path/to/primary-output.jsonl \
  --gate-state-json .task/cycle/cycle-YYYYMMDD-HHMMSS/packets/loopback_audit_packet.json \
  --output-delta-json .task/cycle/cycle-YYYYMMDD-HHMMSS/packets/output_delta_result.json \
  --runner-validation-json .task/run/run-id/validation.json \
  --measurement-check-id event-sequence-oracle-v1 \
  --measurement-frontier event_sequence_oracle \
  --blocker-signature timeline_order_ambiguous \
  --blocker-rung pov_timeline \
  --hypothesized-root-cause prompt_candidate_row_gate \
  --root-cause-actionable \
  --write-registry \
  --output .task/cycle/cycle-YYYYMMDD-HHMMSS/packets/loopback_audit_packet.json
```

Use `--artifact-paths-json` when a run packet already lists artifact paths.

## Packet Semantics

- Treat `evidence_class: insufficient_evidence` as `hard_stop_required: true` and `recommended_disposition: conservative_hold`.
- Treat `semantic_progress: false` with `same_family_micro_hardening_count >= 3` as a hard stop for another same-family micro-hardening task.
- Treat `semantic_progress: true` as a reset for the same-family streak, but keep no-overclaim flags and downstream validation requirements intact.
- Treat `effective_allowed_dispositions` as the intersection of all active constraining gates plus safety valves `terminal_blocked` and `user_escalation`. Downstream derivation must choose a disposition inside this field when it is present.
- Treat `consolidation_streak >= consolidation_streak_cap` as blocking another consolidation disposition; consolidation is workflow progress and does not reduce goal distance by itself.
- Treat `validator_disagreement` findings as a hard stop: when strict runner validation says `semantic_progress=true` but output-delta says `false`, use `authoritative_semantic_progress=false` and do not count runner pass as goal-productive evidence.
- Treat `coverage_quality_delta_reconciliation_gate.status=block` as an R-GCOV hard stop: when output-delta G-COV and loopback G-COV disagree, or expose conflicting values for the same metric key, use the conservative block verdict and do not promote measurement or rung progress from the favorable G-COV alone.
- Treat `validator_integrity_gate.status=block` as a hard stop for validator-derived progress. A top-level validator pass must equal the AND of embedded sub-results, and declared population coverage must match inspected count.
- Treat `coverage_quality_delta_gate.quality_delta_pass=true` as the only G-COV path for measurement work to support `goal_productive`. The gate compares adapter-supplied quality/coverage axes against the previous high-water mark; legacy fallback axes may include counts or ratios such as named-event/entity, relation, or source-window coverage.
- Treat `substance_delta_gate.substance_delta_pass=false` or `status=missing` as G-SUBSTANCE fail-closed evidence. A validator, oracle, measurement check, or capability-ladder rung cannot be promoted from tool existence alone; require adapter-supplied substance delta or strict changed-and-semantic primary-output evidence.
- Treat `vacuous_corrective_gate.surface_corrective_noop=true` as G-VACUOUS evidence: attempted corrective/backfill lanes with `resolved=0` must be excluded from produced/semantic delta claims.
- Treat `facet_root_map_applied=true` as G-FACET evidence that adapter facet labels were collapsed before root-family caps. When no map exists, only conservative suffix/date/run/facet normalization applies.
- Treat `advice_freshness_gate.advice_metrics_stale=true` as a warn-level G-ADVICE-FRESH finding. Refresh, defer, or reject stale advice before using its headline metrics for next-task direction.
- Treat `structure_metrics_gate.structure_consolidation_recommended=true` as an S-STRUCT warning that Class C consolidation or module-boundary work may be a valid next-task direction when it reduces an overgrown entrypoint or command surface.
- Treat `measurement_progress=true` with `measurement_progress_allowed=false` as governance-only instrumentation. `measurement_progress_allowed=true` is valid only when the root-key and root-family measurement streaks are within cap and both G-COV and G-SUBSTANCE passed. Do not reinclude `goal_productive` for measurement-only work without quality/coverage and substance delta.
- Treat `provider_scale_dispatch_gate.dispatch_required=true` as a derive hard gate: if authority permits bounded extraction or scale execution, the next task must attempt it; otherwise it must terminal/user-escalate with the exact missing authority/input.
- Treat `blocker_mutation_kind=forward_mutation` as changed blocker-state progress only when `terminal_outcome_changed=true` from observed output-delta evidence. If the ladder rung changes but the terminal outcome does not, emit `forward_mutation_vacuous=true`, keep/raise the hard stop, and route to untried root-cause repair or terminal/user escalation.
- Treat `blocker_mutation_kind=facet_rename` as lateral churn, not forward mutation. Facet names, suffixes, dates, run directories, and version labels do not reset the root-family cap.
- Treat `requires_correction_or_terminal=true` as G-BALANCE: detection-only work has repeated for the same root blocker family while semantic progress remains false. Downstream derivation must choose correction/implementation work, `terminal_blocked`, or `user_escalation`; another validator, metric, gate, dashboard, lineage, or report is not goal-productive.
- Treat `untried_actionable_root_cause_exists=true` as a terminal-blocker veto. Downstream derivation must promote the untried local, bounded, provider-free, in-scope, authority-allowed hypothesis as the next goal-productive repair task instead of sealing the family.
- Treat `orphan_advice_not_intaken` findings as warn-only coherence findings: root steering docs such as `task_advice.md`, `skill_advice.md`, or `task_doctor_steering.md` need `$manage-external-advice intake` before derive can reliably consume them as active non-GT advice.
- Never use `produced_domain_delta`, `progress=advanced`, non-empty row counts, lineage, gap reports, task-state records, or renamed command families as truth by themselves.

## Registry Rules

The producer owns `.task/anti_loop/family_progress_registry.jsonl` and the additive root-cause ledger `.task/anti_loop/root_cause_ledger.jsonl`.

- Key rows by suffix-normalized `family_key`; do not include input fingerprints, run directories, timestamps, or sampled work ids in the key.
- Append or compact only this registry. Do not edit candidate outputs, task packs, issues, schema records, advice files, or implementation code.
- Append root-cause ledger rows idempotently by `(cycle_id, family_key, root_key, hypothesized_root_cause)`. The ledger is non-GT workflow evidence and records only whether a domain-owned hypothesis was attempted and whether the terminal outcome changed.
- Re-running the same `cycle_id` for the same `family_key` must be idempotent.
- On idempotent replay, preserve recorded measurement, blocker-mutation, disposition, consolidation, and finding fields from the existing registry row; do not let the replay treat its own check IDs or frontiers as already-known evidence and erase A1/A2 progress fields.
- Missing or malformed artifacts must not increment counters or update high-water marks.

## Reviewer Prompt

When a reviewer is needed, give it only the raw artifact paths, the registry path, and the producer packet. Ask it to determine whether the output contains real semantic movement or only placeholder events, surface entities, lateral work churn, or artifact jitter. Do not pass intended fixes or prior conclusions.
