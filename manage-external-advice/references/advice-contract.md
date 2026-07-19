# External Advice Contract

This contract defines `.agent_advice/` artifacts. Advice is direction evidence, not `.agent_goal` goal truth.

## Contents

- [Directory layout](#directory-layout)
- [Normalized advice template](#normalized-advice-template)
- [Lifecycle statuses](#lifecycle-statuses)
- [Clause consumption state](#clause-consumption-state)
- [Intake deduplication and directive identity](#intake-deduplication-and-directive-identity)
- [Immutable intake plan](#immutable-intake-plan)
- [Applied container dispositions](#applied-container-dispositions)
- [Disposition compilation](#disposition-compilation)
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
├── journal/intake/
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
  classification: <source-declared compatibility alias or null>
  consumption_state: pending | wired | verified | <source-declared non-actionable state>
  default_state: <source-declared default or null>
  target_owner: <source-declared consumer/owner or null>
  selection_disposition: <source-declared disposition or null>
  grouping_only: true | false | null
  reference_classification: owning_clause_reference | null

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
- freshness_reason: <why the advice is current, stale, or unknown>

## Conflicts

- <Conflict with user instruction, GT, authority, repo facts, or none.>

## Task Integration

- <How task.md, candidate_task, task-doctor, or derive should use this.>

## Design Integration

- <How architecture/schema/theory/governance should use this.>

## Application Gates

- <Evidence required before using the advice in work.>

## Evidence To Mark Applied

- <Task/schema/log/validation/issue evidence that can retire this advice.>

## Exclusions

- <What this advice must not cause.>
```

`Actionable Directives` is the sole normalized representation of workflow revisions. The registry event's `fields.directives[]` records are authoritative for machine consumption and use the same generic owner fields shown above. Do not synthesize a parallel workflow-revision section or promote document-local headings, numbered parts, packet keys, paths, metrics, or thresholds into this global contract. Keep concrete semantics in `directive_text`, the registry-owned raw source, and the targeted consumer's adapter or project contract.

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

## Immutable Intake Plan

`registry intake --source <workspace-file> --plan <workspace-plan-path>` publishes schema-v1 `external_advice_intake_plan` JSON plus one non-canonical, digest-named source snapshot without publishing canonical raw, active, JSONL, or Markdown advice state. The plan fixes the advice/plan IDs, RFC3339 timestamp, sanitized title policy, priority, opaque source ID, registry-owned raw/active destination paths, exact registry and Markdown pre/post digests, normalized-content digest, and registry-event digest. Use `registry intake --apply-plan <plan-path>` to apply it. A direct compatible `intake --source ...` call uses the same frozen plan/apply implementation internally.

Plan construction is read-only. Publication writes the validated input bytes once at `.agent_advice/journal/intake/source_snapshots/src-sha256-<full-raw-sha256>.md` and publishes the immutable plan. The plan JSON is body-safe: it binds that workspace-relative regular non-symlink opaque snapshot and its exact UTF-8 SHA-256; it does not contain raw advice text, normalized Markdown, the caller's locator, or the full registry event. The snapshot itself contains the raw body and therefore has the same confidentiality class as raw advice. The registry precondition binds both `before_sha256` and the exact byte length `before_size`. An stdin or outside-workspace source requires `--staging-ref` to an existing byte-identical workspace file. Apply reopens the opaque snapshot without following a final symlink, verifies the raw digest, deterministically rebuilds normalization with the fixed timestamp/identity metadata, recomputes the registry event, and requires both digests to match the plan before any canonical publication.

The self-hashed plan does not select arbitrary publication targets. Raw and normalized destinations must be exact direct children of `.agent_advice/raw/` and `.agent_advice/active/`, share one filename, bind `advice_id: adv-<filename-stem>`, and retain the deterministic plan/source/registry/Markdown identities. Absolute, dot-segment, outside-subtree, non-directory/symlink ancestor, non-regular/symlink leaf, non-lowercase digest, or internal identity/path mismatch fails closed before destination publication.

Under `.agent_advice/index.lock`, apply validates registry CAS, Markdown CAS, planned post-event registry digest, source binding, and destination conflicts before staging raw/normalized files. It publishes immutable `.agent_advice/journal/intake/<plan-id>.intent.json` before raw/active or event publication, then immutably publishes exact raw/normalized outputs, commits one plan-tagged canonical intake event, renders the index, and publishes `.agent_advice/journal/intake/<plan-id>.receipt.json`. Every normal advice-registry writer detects an unfinished intent and fails closed before suffix append; only recovery of the same plan may proceed. A duplicate discovered before plan creation remains a zero-write `duplicate_noop`; exact effect replay appends no event.

After a plan is frozen, apply may close without a canonical effect only when it proves under the same lock that this plan has no plan-tagged event, no own intent, and no plan-owned publication. The bounded cases are an exact duplicate already owned by another intake, a lost registry/Markdown CAS race, a changed or missing source, and a conflicting regular raw/active destination observed before intent publication. Apply then publishes the closed, self-hashed `external_advice_intake_no_effect_receipt` at the plan's canonical receipt path and returns `status|apply_status=settled_no_effect`. The receipt binds the exact plan ref/body/file digests, advice/plan IDs, closed reason codes, body-free registry/Markdown/source/destination observations, `plan_event_observed=false`, `plan_intent_observed=false`, and either an exact duplicate event/raw-file proof or a pre-canonical stale proof. Receipt publication is a journal mutation, but raw, active, JSONL, and projected advice state remain unchanged. Unsafe/symlink paths, an own or ambiguous intent, any partial/ambiguous plan-tagged event, or plan/intent/receipt tamper remains recovery-required or conflicting and never settles as no-effect.

Effect recovery proves that the first `before_size` registry bytes hash to `before_sha256`, the exact canonical planned event occurs immediately afterward, and every remaining byte is a canonical valid JSON-object suffix. No-effect replay similarly reopens the sealed registry observation as an exact historical prefix and requires every later byte to be a canonical valid unrelated suffix; duplicate settlements also reopen the exact bound event/raw file. Thus unrelated later suffixes do not erase either terminal proof. A changed prefix, interposed or duplicate plan-tagged event, invalid suffix, missing duplicate proof, or newly observed own intent remains blocked.

Immutable plan/snapshot preparation is the authority-free, reversible `prepare_advice_intake_plan` operation over `workflow_metadata` and `external_advice_staging`; the plan is a later authority subject, not a grant. Use `advice_intake_plan` as the preferred authority subject for separately authorized planned intake and retain `external_advice` for legacy direct lifecycle compatibility. The authoritative apply binding is `execution_result_binding.ref|sha256`, where SHA-256 is over the exact newline-bearing receipt file. `plan_sha256` and `receipt_content_sha256` are canonical body digests; `plan_file_sha256` and `receipt_file_sha256` are the exact immutable-file bindings.

Use `manage_external_advice.intake_plan.verify_intake_plan(root, plan_ref)` as the public read-only consumer contract. It reopens the exact plan file, source/destination safety at the pre-apply boundary, the unique committed event and historical prefix/suffix boundary, current raw binding, registry projection, and exact effect or no-effect receipt. Its explicit observation fields are `plan_effect_observed`, `plan_intent_observed`, `prestate_current`, and `no_effect_verified`. Only `already_applied` plus the returned `receipt_ref` and `receipt_file_sha256` is terminal effect evidence. Only `settled_no_effect`, `no_effect_verified=true`, both observed flags false, and the exact returned no-effect receipt binding is terminal no-effect evidence. `ready` permits fresh dispatch, `recovery_required` routes to same-plan recovery, and `stale|conflict` is nonterminal; none may be wrapped in an arbitrary coordinator result and reported as completion.

## Applied Container Dispositions

`mark-applied` retires the advice container; it does not prove a clause `wired` or `verified`. Before any move, require one unique disposition row for every actionable `directive_id`. Allowed dispositions are `incorporated`, `retired`, and `residual`. Every row must cite a workspace-relative regular evidence file and its exact full SHA-256; missing, extra, duplicate, stale-digest, or opaque-only references reject the transition without moving the active file. A `residual` disposition cites the durable artifact that keeps the remaining obligation open.

The transition is a bounded recoverable publication, not a sequence of independently authoritative writes. Under the advice registry lock, create an immutable prepare record in `.agent_advice/journal/mark_applied/` whose operation digest binds the exact request digest, expected active-source path/content SHA-256, advice-local source event revision and event digest, and deterministic applied destination/content SHA-256. Keep the active source in place while staging the status-updated applied artifact. Write the `past_advice` log with `advice-operation:<operation_digest>` and an explicit statement that it becomes authoritative only when the matching canonical event exists; this permits recovery after the log writer commits but before the advice registry commits without misrepresenting container state.

Re-read the canonical JSONL and source after all staged artifacts exist. If either expected revision/digest or source content/path/status changed, do not publish. Otherwise atomically replace `.agent_advice/index.jsonl` with exactly one final `mark_applied` event carrying the operation digest, request digest, source CAS fields, applied digest, and work-log pointer. That event is the retirement authority and is published last; `.agent_advice/index.md` is explicitly a derived projection. After the event, remove only the exact source digest, rebuild the projection atomically, and publish an immutable commit receipt. A retry with the identical request resumes the prepare, recovers the operation-tagged log, reuses an exact staged artifact, or completes post-event cleanup without duplicate events/logs. A changed request, tampered journal/staged artifact, stale source CAS, or superseding lifecycle event fails closed. Do not generalize this into a cross-skill transaction engine.

## Disposition Compilation

`render-disposition-template` returns the exact actionable directive IDs and advice/source binding without copying directive or source body text. Fill only the per-ID `disposition` and workspace-relative `evidence_ref`. `compile-dispositions` reopens each regular evidence file, computes its SHA-256, proves exact actionable-set coverage, and returns rows accepted by the existing disposition validator. The template or compilation is preparation, not lifecycle truth or clause-consumption evidence. A stale advice binding, missing/extra ID, unsupported disposition, unsafe path, or changed evidence fails before `mark-applied` mutates anything.

## Index Fields

Record advice in `.agent_advice/index.jsonl` and `$manage-task-state-index`:

- artifact type: `external_advice`
- ID prefix: `adv-*`
- useful fields: `not_goal_truth`, `status`, `raw_source_path`, `scope`, `priority`, opaque `source_id|source_label`, `source_label_policy`, `title_policy`
- fidelity fields: `fidelity_status`, `fidelity_reason`, `raw_direct_reference_required`
- freshness fields: `advice_metrics_stale`, `declared_output_fingerprints`, `current_output_fingerprint`, `freshness_reason`
- directive identity/state fields: `directives[]`, `directive_id`, `directive_text`, `directive_state`, `change_class|classification`, `consumption_state|default_state`, `target_owner`, selection/grouping/activation fields, `id_origin`, `semantic_equivalence_claimed`, `semantic_dedup_policy`
- applied-container fields: `directive_dispositions[]`, `evidence_ref`, `evidence_sha256`, `container_lifecycle_separate_from_clause_state`
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

The `re_advised_dead_hypothesis`, `dead_hypothesis_claims`, and `root_cause_ledger_path` values are audit-result fields, not deterministic intake-normalization or advice-registry fields. This gate recommends refresh, deferral, rejection, current-evidence justification, or a required supplied input delta. It does not auto-promote advice to goal truth and does not by itself mark advice applied.

## Precedence

Advice is below system/developer/user instructions, `.agent_goal` GT, authority policy, and repository evidence. Never use advice to grant permissions or override safety, scope, schema, or validation rules.

If `fidelity_status` is `degenerate` or `needs_review`, downstream workflows must cite or inspect `raw_source_path` before applying directives. Normalized claims/directives alone are not sufficient application evidence in that state. Advice packets always carry `execution_plan_eligible: false`; complete normalization permits direction-evidence use only, while incomplete normalization is warning-only until the raw source is reviewed and the clause set is repaired or explicitly bounded.

If `advice_metrics_stale` is `true`, downstream workflows must refresh, defer, reject, or explicitly justify use against current repository evidence before relying on headline metric or fingerprint claims. Advice freshness is a warning gate, not goal truth.

If `re_advised_dead_hypothesis` is `true`, downstream workflows must not use that advice as fresh untried root-cause evidence unless it supplies a new input delta, authority change, or external-state change.

If a canonical directive expresses a measurable target, downstream `$task-doctor` and `$derive-improvement-task` must consult its exact `directive_text` and, when fidelity requires it, the registry-owned raw source plus the named adapter or project contract. Preserve the original target in task-pack `scope_fidelity` or `task.md` acceptance, but do not infer or synthesize global `metric`, `comparator`, `target`, `acceptance_text`, or `residual_policy` fields. Do not mark the advice applied merely because a narrowed pilot, plan, or slice was completed; either the original target is met, or explicit descope with residual scope is recorded.

If advice revises workflow behavior, downstream workflows must consume the corresponding canonical directive owner as non-GT evidence. Route by `target_owner` when declared and interpret `directive_text` through the consumer's existing adapter or project contract. `change_class|classification` controls whether an existing owner is revised or an explicitly requested compatible surface may be added; selection, grouping, and activation fields remain source-owned constraints, while any other exclusion or detail stays in the directive text and owning raw source. Do not infer new schema keys from prose, local headings, or document numbering. When a detail is not safely represented by the generic owner record, consult the registry-owned raw source rather than duplicating the body into packets, receipts, or a second normalized section.
