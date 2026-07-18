# Execution Log Checklist

## Contents

- [Execution evidence](#execution-evidence)
- [Log field mapping](#log-field-mapping)
- [Status rules](#status-rules)
- [Run disposition fields](#run-disposition-fields)
- [Gate failure fields](#gate-failure-fields)
- [Producer progress claim fields](#producer-progress-claim-fields)
- [Part K lineage fields](#part-k-lineage-fields)
- [Part L lane and basis fields](#part-l-lane-and-basis-fields)
- [Redaction rules](#redaction-rules)

Use this checklist before writing the `.agent_log` entry through `$record-agent-work-log`.

## Execution Evidence

Capture:

- Workspace/cwd used for the run.
- Exact command line or code execution method.
- Full body-free `command_argv`: preserve argument names and nonsecret scalar values; redact secrets, body text, and token/hash-like values. Use `command_provenance_missing=true` if full argv is unavailable.
- Record full redacted argv once per live run packet. Downstream ledger events should cite the packet by path/hash or `unchanged_ref` instead of duplicating the argv body.
- Runtime/interpreter/environment if relevant.
- Input files, config files, arguments, and environment assumptions that affected the run.
- Exit code or completion status.
- For authorized long-term runs: PID, session/job ID, log path, checkpoint path, latest heartbeat or output tail, monitor command, stop command, and next recommended check.
- For task-cycle long-running branches: `long_run_branch=true`, `event_kind`, `long_run_role`, `run_id`, `owner_task_id`, `launch_cycle_id`, `workdir`, `output_dir`, `expected_completion_signal`, `expected_completion_artifacts`, `remaining_validation`, and residual/harvest task linkage when launch does not satisfy the original live-run target. For a cycle-unreachable launch, preserve the exact `cycle_reachability_gate`, open `residual_acceptance`, and a harvest plan bound to the same run, gate digest, scale ID, throughput-evidence ID, residual ID, and validation-predicate IDs.
- Short stdout/stderr summary, not full noisy output.
- Produced artifacts, changed files, generated reports, or missing expected outputs.
- Validation performed after execution.
- Fail-closed gate prechecks and pre-execution gate self-checks when present, using scalar fields only.
- Gate/validator blocker actionability when present: `violated_relation`, `observed_values`, `expected_relation`, `minimum_input_delta`, and abstract input-key names for multi-input relations; use `authorization_contract_repair_candidate=true` when a named single authorization input would make the precondition discoverable, and `blocker_opacity=true` for state-name-only reason codes.
- Failed-run `runtime_config_echo`, `config_origin`, and `config_overrides` when a caller/adapter exposes safe scalar settings.
- Execution `run_disposition`: `failed_closed`, `candidate_degraded`, or `candidate_written`, with safety violations, quality-vector scalars, degradation reasons, and verification flags when available.
- Producer self-reported progress or completion fields only as `observed_producer_claim`, never as authoritative progress evidence.
- Part K report/comparison fields when artifacts declare them: `expectation_anchor`, `designated_baseline`, `expectation_anchor_missing`, `expectation_lineage_stale`, `parity_axes`, `parity_axis_status`, `parity_unverified`, `adoption_axis_classification`, `required_output_classes`, `majority_vote_adoption`, `provisional_adoption`, `measured_but_disqualified`, `required_evidence_resolution`, `observed_evidence_resolution`, `resolution_downgrade`, `surrogate_resolution_basis`, `report_key_divergence`, and duplicate report-key path/value pairs.
- Part L run/report/metric fields when artifacts declare them: `production_lane_identity`, `current_decision_lane`, `lane_identity_missing`, `pass_on_stale_lane`, `measurement_run_id`, `upstream_contract_changed_since_measurement`, `stale_measurement_artifact`, `decision_metadata_revision`, `metric_basis_inputs`, `claimed_basis_class`, `consumed_input_classes`, `basis_overclaim`, `actual_basis_class`, and `basis_downgraded_fields`.
- For each actually invoked acceptance scenario, one exact-bound `premise_receipts` row containing opaque scenario/predicate IDs, premise evaluation status and satisfying-item count, invocation kind/descriptor, ordered typed body-free invocation components, the recomputed canonical invocation digest, input revision IDs, result digest, expected/observed terminal states, run ID, and evidence reference. CLI order uses `cmd:/subcommand:/flag:/mode:/ref:` tokens and any argv echo must match exactly; non-CLI rows use ordered action/parameter/ref IDs. Do not copy source paths, locators/entities, bodies, credentials, or untyped sensitive values into the receipt.

## Log Field Mapping

`task_intent`:

- User-requested code/command.
- Requested execution method.
- Expected purpose or output.

`work_performed`:

- Commands run in order.
- Exact redacted argv for each live command, or `command_provenance_missing=true`.
- Files inspected or created/changed.
- Environment selection and notable runtime details.
- Any safety redactions.

`result`:

- Status: success, running, partial, failed, or not_run.
- Exit code and key output summary.
- Active process metadata for `running` status.
- Artifacts produced or expected artifacts missing.
- Validation outcome.
- `failure_autopsy.classification`, `failure_autopsy.alternative_evidence_source`, and `failure_autopsy.gate_selfcheck` when a failure was autopsied.
- `command_provenance_missing` when argv was incomplete; note that the run is not valid reproduction/baseline evidence.
- `blocker_actionability` or `blocker_opacity` for gate/validator failures with reason codes.
- `failure_autopsy.runtime_config_echo`, `config_origin`, and `config_overrides` when available.
- `run_disposition`; preserve `candidate_degraded` as quality-miss evidence and `failed_closed` as unsafe discarded output.
- `observed_producer_claim` and scalar `split_brain_progress_claim` warning details when a producer self-report conflicts with adapter or strict output-delta evidence supplied by the caller.
- Part K warnings such as stale expectation anchors, parity-unverified comparison/adoption, measured-but-disqualified candidates, resolution downgrade, and report-key divergence when observed.
- Part L warnings such as stale-lane passes, stale measurement artifacts, decision metadata revisions, and basis overclaim when observed.

`shortcomings`:

- Missing code, missing inputs, ambiguous instructions, unsafe assumptions, command failure, timeout, skipped validation, unavailable dependencies, or unverified output.
- For `running` status: final completion and final validation still pending.
- For long-running launch/handoff status: original domain/live-run acceptance still pending unless startup/heartbeat is explicitly the whole expected result.
- Sensitive details omitted from the log.
- Producer progress labels were downgraded when present, and no close/progress verdict was inferred from them.
- A `candidate_degraded` output was preserved but not promoted, when applicable.
- A command with missing argv was not treated as reproducible baseline, when applicable.
- A state-name-only blocker was logged as opaque rather than actionable, when applicable.
- Any stale expectation, parity gap, gating-axis failure, resolution downgrade, or report-key divergence was logged as routing evidence and not promoted as success, when applicable.
- Any stale-lane pass, stale decision measurement, or basis overclaim was logged as routing evidence and not promoted as success, when applicable.

## Status Rules

- `success`: all requested execution steps completed and observed result matches the request.
- `running`: an authorized long-term run started, remains active, and has durable PID/session, log, monitor, and stop evidence, but final outputs or validation are not complete yet.
- `completed_pending_validation`: expected completion artifacts are present, but harvest validation has not yet consumed them; do not report success or completion from this status alone.
- `partial`: some work completed, but verification, outputs, dependencies, or follow-up remain.
- In `$orchestrate-task-cycle` ledgers, preserve this result status separately and record a completed `success` run stage as lifecycle `complete`.
- `failed`: the specified command or code ran and failed.
- `not_run`: execution did not happen because required code/method/input was missing or unsafe to infer.

## Run Disposition Fields

When a caller or adapter can classify output disposition, record:

- `run_disposition`: `failed_closed`, `candidate_degraded`, or `candidate_written`.
- `safety_violations`: safe scalar identifiers only.
- `quality_vector`: safe scalar quality axes.
- `degradation_reasons`: short scalar/enum reason codes for `candidate_degraded`.
- `verification_flags`: per-axis or per-row scalar flags when available.
- `disposition_unclassified`: warning when the classifier hook exists but required safety/quality scalars are missing.

Discard unsafe `failed_closed` artifacts. Preserve `candidate_degraded` artifacts as measurement evidence, but do not describe them as canonical baseline, success, or completion.

## Gate Failure Fields

For fail-closed or pre-execution gates, record only scalar-safe routing evidence:

- `gate_satisfiability`: `gate_id`, `satisfiable`, `reason`, `evidence_source`, `alternative_evidence_source`, and `classification`.
- `gate_selfcheck`: `gate_id`, `blocked_pre_exec`, `repo_owned_pre_exec_blocker`, `contradicting_evidence`, `trusted_evidence_source`, `prior_pass_observed`, `status`, and `classification`.
- `blocker_actionability`: `gate_id`, `reason_code`, `violated_relation`, `observed_values`, `expected_relation`, and `minimum_input_delta` when a gate/validator returns a blocker.
- `blocker_opacity`: true when only a state or reason code is available.
- `classification: self_inflicted_gate_defect` only when repository-owned pre-execution blocker provenance is confirmed and the gate artifact has contradiction evidence, a trusted alternative evidence source, or a prior pass.
- `status: warn_missing_repo_owned_confirmation` when contradiction evidence exists but repository-owned confirmation is absent.

## Producer Progress Claim Fields

When available, use adapter `producer_progress_claim_fields()` to identify producer-owned progress labels. If it is absent, treat conventional fields such as `progress_kind`, `effective_progress_kind`, `progress_verdict`, `goal_productive`, and `produced_domain_delta` as claims. Store the captured values under `observed_producer_claim`. Authoritative progress remains owned by adapter recomputation, loopback, output-delta, and completion validation.

## Part K Lineage Fields

When a run/report declares expectation or comparison lineage, record only safe scalar/id fields:

- `expectation_anchor`, `designated_baseline`, `expectation_anchor_missing`, and `expectation_lineage_stale`.
- `parity_axes`, `parity_axis_status`, and `parity_unverified`.
- `adoption_axis_classification`, `required_output_classes`, `majority_vote_adoption`, `provisional_adoption`, and `measured_but_disqualified`.
- `required_evidence_resolution`, `observed_evidence_resolution`, `resolution_downgrade`, and `surrogate_resolution_basis`.
- `report_key_divergence`, duplicate key paths, and duplicate scalar values.

Do not log raw report bodies, source text, provider payloads, or generated content while preserving these fields. Do not infer adoption, completion, baseline promotion, or high-water movement from these fields inside the execution skill.

## Part L Lane And Basis Fields

When a run/report/metric declares lane lineage or metric-basis evidence, record only safe scalar/id fields:

- `production_lane_identity`, `current_decision_lane`, `lane_identity_missing`, and `pass_on_stale_lane`.
- `measurement_run_id`, `upstream_contract_changed_since_measurement`, `stale_measurement_artifact`, and `decision_metadata_revision`.
- `metric_basis_inputs`, `claimed_basis_class`, `consumed_input_classes`, `basis_overclaim`, `actual_basis_class`, and `basis_downgraded_fields`.

Do not log lane-key component definitions, raw source text, prompt/provider bodies, or metric input bodies while preserving these fields. Do not infer current-lane adoption, fresh measurement progress, or independently verified high-water movement from these fields inside the execution skill.

## Redaction Rules

- Replace secrets and tokens with `[REDACTED]`.
- Summarize large outputs instead of embedding them.
- Avoid raw dataset excerpts, private transcripts, and large copyrighted text.
- Avoid raw runtime/provider payloads when recording `runtime_config_echo`; keep only scalar/enum effective settings and origins.
- Redact argv values only as needed; do not remove the flag or argument name.
