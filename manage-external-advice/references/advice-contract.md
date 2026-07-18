# External Advice Contract

This contract defines `.agent_advice/` artifacts. Advice is direction evidence, not `.agent_goal` goal truth.

## Contents

- [Directory layout](#directory-layout)
- [Normalized advice template](#normalized-advice-template)
- [Lifecycle statuses](#lifecycle-statuses)
- [Clause consumption state](#clause-consumption-state)
- [Intake deduplication and directive identity](#intake-deduplication-and-directive-identity)
- [Applied container dispositions](#applied-container-dispositions)
- [Index fields](#index-fields)
- [Audit freshness gate](#audit-freshness-gate)
- [Precedence](#precedence)

## Directory Layout

```text
.agent_advice/
├── raw/
├── active/
├── deferred/
├── applied/
├── rejected/
├── journal/mark_applied/
├── index.jsonl
└── index.md
```

## Normalized Advice Template

```markdown
# External Advice

- advice_id: adv-YYYYMMDD-HHMMSS-slug
- status: active | applied | rejected | deferred
- not_goal_truth: true
- raw_source_path: .agent_advice/raw/YYYYMMDD-HHMMSS-slug.md
- received_at: <ISO-8601>
- normalized_at: <ISO-8601>
- scope: task | design | schema | validation | goal_context | mixed
- priority: low | normal | high
- source_label: src-sha256-<full-raw-sha256>

## Summary

<Short summary of the advice.>

## Extracted Claims

- <Claim with confidence or evidence note.>

## Actionable Directives

- directive_id: <explicit source ID, or dir-<full-raw-sha256>-<source ordinal>>
  directive_state: pending
  id_origin: explicit | source_digest_ordinal
  semantic_equivalence_claimed: false
  directive_text: <Directive that can influence task/design/workflow behavior.>
  declaration_kind: heading | directive_table | directive_id_block | inline_grouped_declaration | inline_declaration | raw_direct_fallback
  change_class: <source-declared class or null>
  selection_disposition: <source-declared disposition or null>
  grouping_only: true | false | null
  reference_classification: owning_clause_reference | null

## Measurable Targets

- directive_id: <stable directive id>
  metric: <abstract metric name or adapter-owned target label>
  comparator: <>, <=, >=, ==, contains, exists, or equivalent>
  target: <target value or condition>
  acceptance_text: <acceptance wording to copy into task.md or scope_fidelity>
  residual_policy: <how to preserve remaining scope if narrowed>

## Normalization Fidelity

- fidelity_status: ok | needs_review | degenerate
- fidelity_reason: <why the extraction is trustworthy or not>
- raw_direct_reference_required: true | false
- normalization_complete: true | false
- execution_plan_eligible: false
- canonical_declaration_count: <scalar>
- reference_echo_count: <scalar>
- raw_direct_fallback_used: true | false
- candidate_line_count: <deterministic extraction count when available>

## Advice Freshness

- advice_metrics_stale: true | false | unknown
- declared_output_fingerprints: []
- current_output_fingerprint: <fingerprint or unknown>
- re_advised_dead_hypothesis: true | false | unknown
- dead_hypothesis_claims: []
- freshness_reason: <why the advice is current, stale, or unknown>

## Conflicts

- <Conflict with user instruction, GT, authority, repo facts, or none.>

## Task Integration

- <How task.md, candidate_task, task-doctor, or derive should use this.>

## Workflow Contract Revisions

- in_place_revisions: []
- additive_new_surfaces: []
- exclusions: []
- count_key_hygiene: <generation-independent count-key rule, or none>
- required_gate_hooks: <acceptance-required gate hooks treated as verifier completeness, or none>
- goal_axis_completeness: <goal-axis mapping/pass completeness rule, or none>
- residual_gap_cost_policy: <value-per-cycle-cost comparison rule, or none>
- failure_autopsy_contract: <last_successful_stage plus scalar diagnostics or diagnostics_unavailable rule, or none>
- failure_surface_count_key: <root + dominant parameter + failure surface stage count-key rule, or none>
- instrumentation_supply_rule: <diagnostics_unavailable streak rule and observability-rationale exception, or none>
- verification_source_separation: <verification_input_paths disjointness/self_grounded rule, or none>
- frozen_envelope_thaw: <envelope_thaw_item requirement and thaw-condition/schedule rule, or none>
- ledger_unchanged_ref_policy: <unchanged_ref path+hash recording rule, or none>
- acceptance_scenario_contract: <scenario premise -> expected state injection rule, or none>
- command_provenance_policy: <full argv recording and redaction rule, or none>
- blocker_actionability_contract: <violated relation, observed values, expected relation/minimum delta requirement, or none>
- stochastic_acceptance_policy: <variance-aware exact-match/floor-edge rule, or none>
- instrumentation_first_fire_credit: <first-fire evidence credit and no-double-counting rule, or none>
- expectation_lineage_contract: <output-derived expectation anchor, designated baseline check, stale-anchor rebaseline/fail-close rule, or none>
- comparison_parity_contract: <parity axes and controlled/measured/unknown classification rule, or none>
- adoption_axis_contract: <gating/tradable axis classification and measured-but-disqualified rule, or none>
- resolution_downgrade_contract: <required versus observed evidence resolution and surrogate downgrade routing rule, or none>
- report_key_integrity_contract: <duplicate terminal key divergence and single-source report rule, or none>
- lane_identity_contract: <production lane/current decision lane binding and stale-lane pass downgrade rule, or none>
- decision_freshness_contract: <fresh current-lane measurement requirement after upstream contract changes, or none>
- gating_axis_producer_contract: <gating-axis starvation and producer-supply-first routing rule, or none>
- portfolio_quota_contract: <verifier-like to producer-like recent-work quota and restriction/warn mode, or none>
- cycle_reachability_contract: <acceptance scale, throughput evidence, unreachable-within-cycle, and long-run routing rule, or none>
- metric_basis_contract: <claimed metric basis versus consumed-input derivability and downgrade rule, or none>
- surface_field_review_contract: <surface field class coverage and scalar defect matrix review rule, or none>

## Design Integration

- <How architecture/schema/theory/governance should use this.>

## Application Gates

- <Evidence required before using the advice in work.>

## Evidence To Mark Applied

- <Task/schema/log/validation/issue evidence that can retire this advice.>

## Exclusions

- <What this advice must not cause.>
```

## Lifecycle Statuses

- `active`: normalized advice that must be considered by supported workflows.
- `applied`: directive was incorporated or made obsolete by a recorded decision with durable evidence.
- `rejected`: advice conflicts with a higher-priority source or is unsafe/unsupported.
- `deferred`: advice is plausible but blocked by missing evidence, user decision, or prerequisite work.

## Clause Consumption State

Advice-container lifecycle and per-clause consumption are separate. A clause may carry `pending|wired|verified` only as non-GT workflow metadata:

- `pending`: default. Copied wording, task creation, contract documentation, hook declaration, import success, or advice `applied` lifecycle alone remains pending.
- `wired`: a named external consumer invoked the clause-bound hook/value and used it in the decision path. For the derive consumer, store three closed lens receipt projections containing role, identity, status, input, ref/digest, and exact output fields plus the canonical synthesis projection as four distinct compact canonical JSON files under `.task/cycle/<cycle-id>/agent_receipts/`. Validation must receive a trusted workspace root, ignore result-authored root redirection, reopen regular non-symlink files without path escape, match exact bytes/digests, echo the decision identity, and record `durable_runtime_artifact_bound` provenance. Arbitrary hex, booleans, or nonexistent refs are not evidence.
- `verified`: all wired evidence plus distinct negative/happy producer-output files and complete outer forward-receipt files in the same store, expected/observed agreement for each path, different negative versus happy decision states, six distinct producer/verifier/invariant-owner IDs, four distinct producer/verifier receipt IDs, and all four bounded forward-test layers passing. The two outer refs and digests must differ. Documentation-only, a no-op fault, a shared identity/receipt, a symlink, or a caller-authored ref cannot establish it.

Cycle-local files establish exact durable content and distinct declared agent/receipt IDs only. They are not cryptographic proof that separate child processes produced those IDs. The workflow must still perform actual delegation and must leave the clause pending or wired when the requested agents or exact artifacts are unavailable.

Missing optional `consumption_state` output fails quiet. Malformed, conflicting, or self-attested positive state becomes `consumption_state_unverified`; it never creates pass, completion, authority, or advice verification. Store only opaque IDs, enums, hashes, and scalar defects in durable packets. Do not copy raw advice bodies, prompts, responses, source locators, or identifying metadata into a consumption receipt.

The active packet exposes `canonical_clause_ids` separately from `canonical_actionable_clause_ids`. Exclude grouping-only and deferred-by-default owners from the latter; include an explicitly named pending `actionable_child` under its source owner. The packet also exposes `source_digests`, `clause_source_digests`, `advice_packet_digest_basis`, and `advice_packet_digest`. The digest basis binds schema/applicability and, for every active advice ID, the raw-source digest, normalized-content digest, declared owner IDs, and actionable IDs.

When an applicable packet supplies a non-empty expected actionable set, a consumer must return exactly one row per expected ID, no external IDs, and exact packet/source digest echoes. Bind those echoes into any `wired|verified` consumer receipt SHA-256. Zero rows, missing IDs, duplicate rows, external IDs, a packet/basis mismatch, or an echo mismatch is unresolved advice-consumption debt and cannot support a positive derive, validation, report, promotion, or close claim. If no expected packet is supplied, or packet applicability is `not_applicable`, retain the existing fail-quiet behavior.

Run `unconsumed_advice_regression` comparison only when the caller supplies finalized recurrence/clause rows with opaque `recurrence_id`, `clause_id`, `finalized_clause_state`, and explicit `recurrence_observed`. Absence of this finalized state is not a regression and must fail quiet. The finding is warning-level non-GT debt; it does not change the underlying judgment gate.

## Intake Deduplication And Directive Identity

Compute the exact raw UTF-8 SHA-256 and inspect existing registry/raw content before creating directories, touching indexes, or writing raw/normalized files. An exact digest match returns the existing intake as `duplicate_exact_raw_source` with no filesystem mutation. Do not use summaries, normalized wording, token similarity, or model judgment for automatic deduplication.

The caller source locator is transient input, never durable metadata. Bind `source_id` and the compatibility field `source_label` to `src-sha256-<full-raw-sha256>` and mark the label policy `opaque_content_id`. The registry-owned `.agent_advice/raw/...` path is an allowed internal source reference. Do not persist an external absolute/relative input path, URI, user-data locator, or a title inferred from that locator or the raw first line. If the caller explicitly supplies a title, normalize Unicode/whitespace, reject path- or URI-like values, restrict the character set, and cap it at 80 characters; use `external-advice-<digest-prefix>` otherwise. Record whether the title used `caller_sanitized` or `opaque_fallback`.

Rendered workflow packets and lifecycle/work-log receipts may carry opaque IDs, hashes, scalar classifications, and the registry-owned raw reference, but they must not echo the transient locator, a raw-derived title, or the raw source body. When exact wording is necessary, a consumer follows `raw_source_path` under the owning store rather than copying the body into a packet or receipt. Normalized claims/directives remain bounded direction evidence subject to the fidelity rules; they are not a substitute for raw review when `raw_direct_reference_required=true`.

Preserve an explicit directive ID when the source actually supplies one. Otherwise derive `dir-<full-raw-sha256>-<source-order-ordinal>` and default the clause to `pending`. Two similar directives with different generated IDs are not semantically equivalent. Cross-container semantic equivalence/dedup is permitted only through an explicit matching directive ID or an explicit human/caller assertion recorded as such; never infer it from text similarity.

Parse canonical declarations before directive-like prose. Canonical declarations are ID-bearing directive headings, explicit `directive_id` blocks, ID declarations carrying clause metadata, and rows in a table whose header explicitly names a `Directive ID` column. A general matrix/table or prose occurrence of an already-declared ID is an `owning_clause_reference`; it must not create a duplicate directive. Distinct canonical declarations of the same ID are ambiguous and fail intake before raw, active, or index writes. Once structured declarations exist, their body belongs to the declared owner; do not manufacture digest-ordinal directives from each sentence. Raw-body heuristic fallback is reserved for unstructured advice and forces `needs_review` plus raw-source consultation.

## Applied Container Dispositions

`mark-applied` retires the advice container; it does not prove a clause `wired` or `verified`. Before any move, require one unique disposition row for every actionable `directive_id`. Allowed dispositions are `incorporated`, `retired`, and `residual`. Every row must cite a workspace-relative regular evidence file and its exact full SHA-256; missing, extra, duplicate, stale-digest, or opaque-only references reject the transition without moving the active file. A `residual` disposition cites the durable artifact that keeps the remaining obligation open.

The transition is a bounded recoverable publication, not a sequence of independently authoritative writes. Under the advice registry lock, create an immutable prepare record in `.agent_advice/journal/mark_applied/` whose operation digest binds the exact request digest, expected active-source path/content SHA-256, advice-local source event revision and event digest, and deterministic applied destination/content SHA-256. Keep the active source in place while staging the status-updated applied artifact. Write the `past_advice` log with `advice-operation:<operation_digest>` and an explicit statement that it becomes authoritative only when the matching canonical event exists; this permits recovery after the log writer commits but before the advice registry commits without misrepresenting container state.

Re-read the canonical JSONL and source after all staged artifacts exist. If either expected revision/digest or source content/path/status changed, do not publish. Otherwise atomically replace `.agent_advice/index.jsonl` with exactly one final `mark_applied` event carrying the operation digest, request digest, source CAS fields, applied digest, and work-log pointer. That event is the retirement authority and is published last; `.agent_advice/index.md` is explicitly a derived projection. After the event, remove only the exact source digest, rebuild the projection atomically, and publish an immutable commit receipt. A retry with the identical request resumes the prepare, recovers the operation-tagged log, reuses an exact staged artifact, or completes post-event cleanup without duplicate events/logs. A changed request, tampered journal/staged artifact, stale source CAS, or superseding lifecycle event fails closed. Do not generalize this into a cross-skill transaction engine.

## Index Fields

Record advice in `.agent_advice/index.jsonl` and `$manage-task-state-index`:

- artifact type: `external_advice`
- ID prefix: `adv-*`
- useful fields: `not_goal_truth`, `status`, `raw_source_path`, `scope`, `priority`, opaque `source_id|source_label`, `source_label_policy`, `title_policy`
- fidelity fields: `fidelity_status`, `fidelity_reason`, `raw_direct_reference_required`
- freshness fields: `advice_metrics_stale`, `declared_output_fingerprints`, `current_output_fingerprint`, `freshness_reason`
- root-cause freshness fields: `re_advised_dead_hypothesis`, `dead_hypothesis_claims`, `root_cause_ledger_path`
- measurable target fields: `directive_id`, `metric`, `comparator`, `target`, `acceptance_text`, `residual_policy`
- directive identity/state fields: `directives[]`, `directive_id`, `directive_state`, `id_origin`, `semantic_equivalence_claimed`, `semantic_dedup_policy`
- applied-container fields: `directive_dispositions[]`, `evidence_ref`, `evidence_sha256`, `container_lifecycle_separate_from_clause_state`
- workflow revision fields: `in_place_revisions`, `additive_new_surfaces`, `exclusions`, `count_key_hygiene`, `required_gate_hooks`, `goal_axis_completeness`, `residual_gap_cost_policy`, `failure_autopsy_contract`, `failure_surface_count_key`, `instrumentation_supply_rule`, `verification_source_separation`, `frozen_envelope_thaw`, `ledger_unchanged_ref_policy`, `acceptance_scenario_contract`, `command_provenance_policy`, `blocker_actionability_contract`, `stochastic_acceptance_policy`, `instrumentation_first_fire_credit`, `expectation_lineage_contract`, `comparison_parity_contract`, `adoption_axis_contract`, `resolution_downgrade_contract`, `report_key_integrity_contract`, `lane_identity_contract`, `decision_freshness_contract`, `gating_axis_producer_contract`, `portfolio_quota_contract`, `cycle_reachability_contract`, `metric_basis_contract`, `surface_field_review_contract`
- useful links: `advice_for`, `incorporated_into`, `applied_by`, `rejected_by`, `superseded_by`, `conflicts_with_goal`, `conflicts_with_authority`

## Audit Freshness Gate

When `python3 -m manage_external_advice registry audit` receives `--current-output-fingerprint` or `--current-output-fingerprint-json`, it must compare active advice fingerprint claims to the supplied current fingerprint and emit:

- `advice_freshness_gate.current_output_fingerprint`
- `advice_freshness_gate.declared_fingerprint_claims`
- `advice_freshness_gate.advice_metrics_stale`
- `advice_freshness_gate.stale_advice`
- `advice_freshness_gate.re_advised_dead_hypothesis`
- `advice_freshness_gate.dead_hypothesis_claims`
- warn-level `advice_metrics_stale` findings for each stale active advice item
- warn-level `re_advised_dead_hypothesis` findings for each active advice item that re-supplies an already attempted root-cause hypothesis with `terminal_outcome_changed=false`

This gate recommends refresh, deferral, rejection, current-evidence justification, or a required supplied input delta. It does not auto-promote advice to goal truth and does not by itself mark advice applied.

## Precedence

Advice is below system/developer/user instructions, `.agent_goal` GT, authority policy, and repository evidence. Never use advice to grant permissions or override safety, scope, schema, or validation rules.

If `fidelity_status` is `degenerate` or `needs_review`, downstream workflows must cite or inspect `raw_source_path` before applying directives. Normalized claims/directives alone are not sufficient application evidence in that state. Advice packets always carry `execution_plan_eligible: false`; complete normalization permits direction-evidence use only, while incomplete normalization is warning-only until the raw source is reviewed and the clause set is repaired or explicitly bounded.

If `advice_metrics_stale` is `true`, downstream workflows must refresh, defer, reject, or explicitly justify use against current repository evidence before relying on headline metric or fingerprint claims. Advice freshness is a warning gate, not goal truth.

If `re_advised_dead_hypothesis` is `true`, downstream workflows must not use that advice as fresh untried root-cause evidence unless it supplies a new input delta, authority change, or external-state change.

If advice includes measurable targets, downstream `$task-doctor` and `$derive-improvement-task` must carry them into task-pack `scope_fidelity` or `task.md` acceptance. Do not mark the advice applied merely because a narrowed pilot/plan/slice was completed; either the original target is met, or explicit descope with residual scope is recorded.

If advice includes workflow contract revisions, downstream workflows must keep them as non-GT in-place decision revisions unless the advice explicitly requests an additive surface and that surface is compatible with higher-priority instructions. For Part G/H-style advice, preserve abstract contracts without repo-specific names or thresholds: generation-dependent count keys are trace-only; acceptance-required gate hooks are `not_evaluated` when absent; review pass requires mapped axes for active measurable goals when `goal_axis_map` is available; residual-gap repair is compared by value per cycle cost when cycle-efficiency evidence exists; failure autopsy needs `last_successful_stage` plus scalar diagnostics or `diagnostics_unavailable`; loopback counting uses the failure-surface key when available; repeated unavailable diagnostics forces instrumentation supply or a concrete observability rationale; independently verified evidence requires disjoint `verification_input_paths` unless the axis is `self_grounded`; frozen unreachable envelopes require an `envelope_thaw_item`; and duplicate ledger packets should be referenced by `unchanged_ref(path+hash)`.

For Part K-style advice, preserve expectation/comparison lineage as abstract contracts only. Output-derived scalar expectations need `expectation_anchor` and current `designated_baseline` comparison before promotion; comparison/adoption tasks need `parity_axes` and `adoption_axis_classification`; `unknown` parity axes keep decisions `parity_unverified`; failed `gating` axes make candidates `measured_but_disqualified`; lower-resolution surrogate evidence is `resolution_downgrade`; and divergent duplicate report keys are `report_key_divergence`. Concrete surface discovery, axis definitions, thresholds, model/backend labels, report schemas, and metric names remain adapter or project-contract owned.

For Part L-style advice, preserve lane lineage and premise-supply contracts as abstract contracts only. Verifier/review/metric passes need lane binding before current-lane consumption; decision updates after upstream production-contract changes need fresh measurement or become `decision_metadata_revision`; starved gating axes route producer supply before verifier-like work; portfolio quota restrictions apply only when an adapter supplies the quota; cycle-unreachable scale targets route long-run launch/monitor/harvest, throughput improvement, descope, terminal blocker, or escalation; metric basis claims must be derivable from consumed inputs; and surface-field review covers adapter-supplied producer-written field classes with scalar defect matrices. Lane-key components, producer path maps, thresholds, units, basis taxonomies, field-class definitions, locators, and excerpt policies remain adapter, authority, or project-contract owned.
