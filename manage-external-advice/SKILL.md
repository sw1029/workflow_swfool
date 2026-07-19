---
name: manage-external-advice
description: "Manage non-goal-truth external advice Markdown for task and design direction correction. Use when Codex receives, imports, normalizes, injects, audits, applies, rejects, or retires external advice documents that should influence `$orchestrate-task-cycle`, `$task-doctor`, `.agent_goal`-using skills, task derivation, implementation governance, or validation without being treated as `.agent_goal` goal truth."
---

# Manage External Advice

## Overview

Use this skill to manage external advice as a separate non-GT workflow input under `.agent_advice/`. External advice can influence task direction and design choices, but it is never goal truth and must not be mixed into `.agent_goal/` without explicit user approval and the owning goal skill.

Canonical advice intake and lifecycle changes use `mutate_advice_lifecycle` in `authority.operations.json` and the shared [authority v2 contract](../manage-agent-authority/references/authority-v2-contract.md). Immutable intake-plan preparation/publication alone is the authority-free `prepare_advice_intake_plan`: it is a reversible, non-canonical local mutation that publishes a body-safe plan and one opaque content-addressed source snapshot, and it grants no permission to apply the plan. Advice content, existence, a published plan, or user interest does not grant task/action authority or permit a different lifecycle subject.

Read [advice-contract.md](references/advice-contract.md) when writing or auditing advice artifacts.

## Module Invocation

Run the registry from any working directory with both owning package roots because advice retirement delegates work-log publication to `$record-agent-work-log`:

```bash
SKILLS_ROOT="${CODEX_HOME:-$HOME/.codex}/skills"
PYTHONPATH="$SKILLS_ROOT/manage-external-advice/scripts:$SKILLS_ROOT/record-agent-work-log/scripts" \
python3 -m manage_external_advice registry --root . audit
```

## Storage Model

Use this workspace layout:

- `.agent_advice/raw/`: preserved external advice Markdown.
- `.agent_advice/active/`: normalized advice that must be considered by supported workflow skills.
- `.agent_advice/deferred/`: advice that remains plausible but is blocked by missing evidence, prerequisite work, or a pending user decision.
- `.agent_advice/applied/`: advice whose actionable directives were incorporated or otherwise retired with durable evidence.
- `.agent_advice/rejected/`: advice rejected because it conflicts with newer user instructions, GT, authority, safety, or repository facts.
- `.agent_advice/index.jsonl` and `.agent_advice/index.md`: advice-local lifecycle index.
- `.agent_advice/journal/intake/source_snapshots/`: non-canonical, digest-named intake sources used only to make a published plan independent of the caller's locator. These snapshots contain the raw input body; treat them with the same sensitivity as `.agent_advice/raw/`.

Use `$manage-task-state-index` after advice changes when `.task/` indexing exists so `external_advice` artifacts receive `adv-*` IDs and links.

Active or applied advice that influences a task cycle is tracked workflow evidence by default. Keep raw advice local-only only when it contains sensitive material or the user explicitly marks it external-only; in that case, track the normalized active/applied artifact when safe and record the raw local-only reason.

Root steering documents such as `task_advice.md`, `skill_advice.md`, and `task_doctor_steering.md` are not active advice by location alone. Intake them into `.agent_advice/active/` before expecting `$orchestrate-task-cycle` or `$derive-improvement-task` to consume them.

## Precedence

Apply this order:

1. System/developer instructions and active tool/sandbox permissions.
2. Latest explicit user instruction.
3. `.agent_goal/*.md` GT files and `.agent_goal/agent_authority.md`.
4. Repository facts, task/index/issue/schema evidence.
5. Active `.agent_advice/active/*.md` normalized advice.

If advice conflicts with a higher-priority source, reject or defer the advice instead of silently applying it.

## Domain Adapter Contract

Prefer repository-owned recurrence and consumption evidence over advice-local assumptions. The module, caller packet, or project contract may expose:

- `consumption_state(advice_clause_id, **context) -> dict`: optional clause-consumption helper returning `state: pending|wired|verified`, the affected opaque blocker-signature family when known, and bounded evidence IDs/hashes. `wired` requires an actual consumer decision-path receipt whose closed lens/synthesis projections exist as safe cycle-local canonical JSON and whose `durable_runtime_artifact_bound` digest and decision-identity echo validate; copied wording, arbitrary booleans/hex, a task, a hook declaration, importability, nonexistent refs, or self-attestation remains `pending`. `verified` additionally requires distinct negative/happy producer-output and outer-receipt files with expected/observed agreement and different happy/negative states. These files prove exact content, not cryptographic child-process identity. If absent or malformed, fail quiet to the local advice registry state and emit `consumption_state_unverified` when a later packet attempts to consume or verify that clause; do not force any task or gate result from this hook alone.

Do not infer blocker families, hook wiring, or verification success from advice text, file names, or repository-specific vocabulary. `consumption_state` is separate from adapter hook debt: hook debt records a missing code/adapter contract, while clause-consumption evidence records whether a named advice clause has been wired and verified. Do not double-count one recurrence as both debts unless both facts are separately present.

## Workflow

Before retiring an advice container, compile the mechanical disposition rows from a small clause decision map. Render the exact actionable-ID template, decide only each clause's semantic disposition and evidence ref, and let the script reopen the evidence and derive its digest.

```bash
python3 -m manage_external_advice registry --root . \
  render-disposition-template --advice-id <id>
python3 -m manage_external_advice registry --root . \
  compile-dispositions --advice-id <id> --decision-map decisions.json
```

Prefer `mark-applied --decision-map decisions.json` over hand-authoring full disposition rows. Compilation never decides whether advice is incorporated, retired, or residual and never upgrades clause consumption state.

1. Intake raw advice.
   - Use `python3 -m manage_external_advice registry --root . intake --source <path.md> --title <title>` with the module path above when a local Markdown file is provided.
   - For deterministic review/apply separation, add `--plan .agent_advice/journal/intake/<name>.plan.json`; this authority-free prepare operation publishes a reversible, non-canonical body-safe plan plus one opaque content-addressed source snapshot. It freezes the advice ID, timestamp, registry-owned raw/active paths, source/raw/normalized/event digests, and registry/Markdown CAS anchors without writing canonical raw, active, registry, or Markdown artifacts. It cannot authorize apply. Apply later under the separately authorized `mutate_advice_lifecycle` operation with `intake --apply-plan <plan-path>`.
   - Plan construction is read-only. Plan publication copies the already validated bytes to `.agent_advice/journal/intake/source_snapshots/src-sha256-<full-raw-sha256>.md` and binds that opaque path. The plan JSON remains body-safe: it stores only this workspace-relative regular non-symlink snapshot reference, its raw SHA-256, fixed metadata/IDs/timestamp/paths, normalized SHA-256, and event SHA-256. It does not embed raw text, normalized Markdown, the caller locator, or the registry event. Apply reopens the snapshot, verifies exact UTF-8 bytes, deterministically normalizes again, and verifies both normalized and event digests before canonical publication.
   - Prefer `advice_intake_plan` as the authority subject for planned intake. Preserve `external_advice` as the compatibility subject for existing direct lifecycle calls. Apply returns `execution_result_binding: {ref, sha256}` using the exact immutable receipt file SHA-256; body digests are reported separately. A prepared plan that loses a concurrent CAS race, encounters a safely observed changed/missing source or conflicting regular destination before intent publication, or discovers an exact duplicate may publish a plan-bound `external_advice_intake_no_effect_receipt`. This receipt is a journal settlement only: it proves that this plan published no intent, plan-tagged event, raw artifact, or active artifact; it is not a canonical advice effect.
   - Coordinators that need to reopen an intake owner outcome must call the public read-only `manage_external_advice.intake_plan.verify_intake_plan(root, plan_ref)` contract. Treat `status=already_applied` as settled effect evidence and `status=settled_no_effect` plus `no_effect_verified=true` as settled no-effect evidence, always with the exact returned receipt ref/file digest. Inspect `plan_effect_observed`, `plan_intent_observed`, and `prestate_current`; `ready`, `recovery_required`, `stale`, and `conflict` are not completion. Do not substitute an arbitrary JSON result or the plan file itself for either receipt.
   - When a root steering doc is named or detected by an `orphan_advice_not_intaken` finding, intake that root file directly and keep the normalized active artifact under `.agent_advice/active/`.
   - Use `--source -` only when the user provided text in the current turn, it is safe to store, and `--staging-ref <workspace-relative-file>` names an existing byte-identical bounded UTF-8 source. An outside-workspace source likewise requires such a staging ref. Publication never persists the caller locator, but it does copy the raw body into the digest-named source-snapshot store; do not prepare a plan when that local staging is not permitted.
   - Preserve the raw document under `.agent_advice/raw/`.
   - Hash the exact raw UTF-8 text and check existing registry/raw content before creating directories, touching indexes, or writing files. On an exact digest match, return the existing intake without mutation. Do not infer semantic duplicates from similar wording.
   - Before any planned staging, validate registry and Markdown CAS, source digest, exact canonical `.agent_advice/raw/<file>.md` and `.agent_advice/active/<file>.md` destinations, every owned ancestor/leaf type, destination absence/exact replay, deterministic normalized/event digests, and planned post-event registry digest. Publish an immutable pending intake intent before raw/active or canonical event publication; every normal advice writer fails closed on an unfinished foreign intent. One unique exact committed event followed by interrupted index render or receipt publication is forward-recoverable even when a later unrelated suffix is present; rebuild the current full projection without discarding that suffix. Before any own intent or effect exists, a safe stale CAS/source/regular-destination observation may instead close as `settled_no_effect`; its sealed registry-prefix observation remains reopenable across valid unrelated suffixes. An own or ambiguous intent, any plan-tagged/partial event, unsafe path, or plan/intent/receipt tamper remains recovery-required or conflicting and never becomes no-effect.
   - Keep the caller's source locator transient. Persist `source_label`/`source_id` only as `src-sha256-<full-raw-digest>`; the plan may bind only its digest-named journal snapshot and lifecycle state may bind only the registry-owned `.agent_advice/raw/...` path. Never derive a durable title from the input path or raw first line. An explicit caller title may survive only after path/URI rejection, character normalization, and bounded truncation; otherwise use an opaque digest-derived fallback.
   - Do not store secrets, credentials, raw sensitive data, or large copyrighted excerpts.

2. Normalize advice.
   - Create one active normalized Markdown file under `.agent_advice/active/`.
   - Parse Markdown structure before body wording. Treat an ID-bearing directive heading, an explicit `directive_id` block, an inline ID declaration with clause metadata, or a table whose header explicitly declares a `Directive ID` column as a canonical owner clause. Preserve its source order, `change_class|classification`, consumption/default state, grouping fields, activation rule, and selection disposition. A later matrix/table/prose occurrence of the same ID is an `owning_clause_reference`, not another declaration. Two distinct canonical declarations with the same ID fail intake before any registry write, even when their wording matches.
   - When canonical owner clauses exist, attach their explanatory body to those owners instead of emitting one generated directive per imperative sentence. Use raw body heuristics only for genuinely unstructured advice. A raw-direct-only extraction is `fidelity_status: needs_review`, sets `raw_direct_reference_required: true`, and cannot be consumed from the normalized packet alone.
   - Extract claims and actionable directives. Render bounded non-GT reminders for conflict checks, task/design integration, application gates, evidence to mark applied, and exclusions; do not present those generic reminders as source-extracted fields.
   - Preserve source-supplied directive IDs. Otherwise assign `dir-<full-raw-sha256>-<source-order-ordinal>`, record `id_origin: source_digest_ordinal`, set `semantic_equivalence_claimed: false`, and default the clause to `pending`. Only an explicit matching ID/assertion can claim cross-document semantic equivalence; never use fuzzy text matching as deduplication.
   - Use each canonical directive record as the sole normalized workflow-contract surface. Preserve source-declared `change_class|classification`, `consumption_state|default_state`, `target_owner`, `directive_text`, selection/grouping fields, and activation rules without inventing a parallel revision section. Interpret `classification` as a compatibility alias for `change_class`, while retaining both source-declared values. Keep explicit additive-zero constraints and instructions that a new detector, report, phase, or skill must not be added in the owning `directive_text` or raw source rather than synthesizing new global fields.
   - For each workflow or skill-advice directive, assign `consumption_state: pending` unless durable evidence already proves it is `wired` or `verified`. `wired` means the targeted consumer actually invoked and consumed the clause-bound value and the derive validator reopened the exact cycle-local lens/synthesis JSON artifacts before producing a `durable_runtime_artifact_bound` receipt with an exact decision-identity echo. Merely naming the clause/hook or supplying arbitrary/nonexistent refs is still `pending`. `verified` additionally needs separate cycle-local negative/happy producer outputs and complete outer receipts with distinct refs/digests and expected/observed agreement. Keep states as non-GT metadata and do not describe content binding as process attestation.
   - Keep domain semantics in `directive_text`, the owning raw source, and the named consumer's adapter or project contract. Do not promote document-local labels, numbered parts, metric names, thresholds, paths, model/backend names, or one-off packet keys into a global advice schema. If the generic record cannot safely represent an exact detail, require raw-source review instead of duplicating raw body or metadata into another normalized section.
   - Mark `not_goal_truth: true`.
   - When the raw advice declares headline metric snapshots, artifact fingerprints, or output fingerprints, record them under `Advice Freshness` and compare them with current repository/adapter output fingerprints when available. If they do not match, set `advice_metrics_stale: true` and require refresh, defer, or reject rationale before downstream workflows rely on those headline claims.
   - When the advice declares root-cause hypotheses, let `audit` compare them with `.task/anti_loop/root_cause_ledger.jsonl`. If a claimed hypothesis was already `repair_attempted` with `terminal_outcome_changed=false`, set `re_advised_dead_hypothesis: true` and do not use that advice as fresh untried evidence without a new supplied input delta.
   - Emit `Normalization Fidelity` with `fidelity_status`, `fidelity_reason`, `raw_direct_reference_required`, canonical declaration/reference counts, raw-direct fallback status, and `normalization_complete`. If extracted claims and actionable directives are identical, empty, metadata-only, or raw-direct-only, set `fidelity_status: degenerate|needs_review`, keep the advice active only as a warning-bearing packet, and require downstream workflows to consult the raw advice before applying it.
   - If the advice is too ambiguous to normalize, create a rejected or deferred record with the reason.

3. Inject advice into workflow packets.
   - Use `python3 -m manage_external_advice registry --root . render-packet --format markdown|json` with the module path above.
   - Pass active advice packet summaries to `$orchestrate-task-cycle`, `$task-doctor`, `$derive-improvement-task`, `$task-md-agent-governance`, `$validate-task-completion`, and `.agent_goal` management skills when they use goal context.
   - Preserve the rendered `canonical_clause_ids`, `canonical_actionable_clause_ids`, per-clause/source SHA-256 bindings, `advice_packet_digest_basis`, and `advice_packet_digest` unchanged in the orchestrator context. Grouping-only and deferred-by-default owners are not active expected clauses; an explicit pending `actionable_child` is. The packet digest binds each advice ID, raw-source digest, normalized-content digest, declared owner set, and active actionable set.
   - Require every consuming result to emit exactly one `advice_consumption_states` row for each active expected clause and no other clause. Each row echoes the packet digest and its assigned source digest. An absent packet, an empty non-applicable packet, or explicit `applicability: not_applicable` fails quiet; an applicable packet with zero, missing, duplicate, external, or digest-mismatched rows remains blocking/pending debt and cannot support positive successor consumption.
   - Require called skills to report `used_advice` separately from `used_goal_truth`.
   - Render `execution_plan_eligible: false` for every advice packet. A complete normalized packet is direction evidence; it is not a task or execution plan. If any active item is incomplete, render `normalized_packet_use: warning_only_raw_review` and its opaque advice ID so `$task-doctor` and derivation consumers cannot plan from normalized claims alone.
   - Packet and lifecycle-receipt metadata may contain the opaque source ID and registry-owned raw reference, but must not echo the caller locator, a raw-derived title, or the raw source body. Exact wording remains reachable only through the owning raw store when the fidelity contract requires it.
   - When advice is used by a Git-backed workflow, classify the safe normalized active/applied advice file as an intentional workflow artifact for staging/commit unless a `local_only` reason is recorded.

4. Apply or reject advice.
   - Prefer `mark-applied --decision-map <json-or-path>` so the owner computes evidence digests; retain `--directive-dispositions-json` for compatibility and diagnostics. Every actionable directive still requires one semantic `incorporated|retired|residual` decision and a workspace-relative evidence file. Missing/extra rows, an opaque ref without a verifiable file, or stale evidence rejects the transition before the active artifact moves.
   - Keep registry lifecycle and clause consumption orthogonal: `mark-applied` may retire the advice container, but it does not by itself change any clause from `pending` to `wired` or `verified`.
   - `mark-applied` writes a content-bound `past_advice` entry through `$record-agent-work-log` and moves the normalized advice to `.agent_advice/applied/`; do not create orphan Markdown outside `.agent_log/index.jsonl`.
   - Treat `mark-applied` as one recoverable publication owned by this skill. Freeze the validated request plus the active source event revision/content digest in an immutable `.agent_advice/journal/mark_applied/` prepare record, stage the status-updated applied artifact, and bind the work log with the operation digest. Publish the canonical `mark_applied` JSONL event last by atomic replacement; staged files and the conditional work log are not retirement authority before that event exists.
   - On an interrupted `mark-applied`, retry the same command and exact disposition/evidence request. Reuse the operation-bound work log and journal, verify the frozen source CAS before commit, or finish source cleanup/index projection after an already committed event. Never append a second lifecycle event or log for the same operation; a changed request, source revision/digest, staged artifact, or journal digest fails closed.
   - Use `defer` when the advice is plausible but cannot be applied yet; record the missing evidence, prerequisite, or pending user decision.
   - Use `reject` when a conflict makes the advice unsuitable; record the conflict source and keep the raw artifact.

5. Audit and index.
   - Run `python3 -m manage_external_advice registry --root . audit` with the module path above after intake, apply, or reject.
   - When an adapter or loopback packet has a current output fingerprint, add `--current-output-fingerprint <fingerprint>` or `--current-output-fingerprint-json <packet.json>` so audit emits `advice_freshness_gate` and `advice_metrics_stale` findings.
   - When a root-cause ledger exists, audit also emits `re_advised_dead_hypothesis` and `dead_hypothesis_claims`; downstream workflows must refresh, defer, reject, or require a new input delta before treating that advice as untried root-cause provenance.
   - Only when a later cycle packet supplies finalized recurrence/clause state (`recurrence_id`, `clause_id`, `finalized_clause_state`, and explicit `recurrence_observed`) and the named recurring clause is not `verified`, emit `unconsumed_advice_regression` debt. Without that finalized state, fail quiet. Keep dependent judgment clauses marked `unenforced` when applicable and preserve a derive backlog item to consume or retire the clause. This is visibility only: do not fail-close the underlying judgment and do not create a new detector/report/phase.
   - Treat root steering docs that remain outside `.agent_advice/active/` as warn-only orphan advice until they are intaken, deferred, rejected, or explicitly ignored with a recorded rationale.
   - Run `$manage-task-state-index scan` and `audit` when task-state artifacts exist.

## Skill Integration Contract

- `$orchestrate-task-cycle`: collect active advice at cycle start, include its exact expected clause set plus packet/source digests in subskill packets, validate exact clause-row completeness before positive consumption, validate that active advice is not accidentally reported as GT, and report it as non-GT direction evidence using the surrounding language.
- `$task-doctor`: may use active advice as an explicit direction source only when the user asks for task doctoring or names the advice; it must still archive `task.md` before replacement.
- `$derive-improvement-task`: treat active advice as planning evidence and explain whether selected or rejected advice affected the next task.
- `$derive-improvement-task`: if an active advice packet has `raw_direct_reference_required=true`, cite the raw advice path in `used_advice` and avoid relying on the normalized claims/directives alone.
- `$derive-improvement-task`: if an active advice packet or `anti_loop_progress_gate.advice_freshness_gate` reports `advice_metrics_stale=true`, refresh, defer, reject, or explicitly justify use against current repository evidence.
- `$derive-improvement-task`: if advice audit reports `re_advised_dead_hypothesis=true`, do not treat that advice as fresh untried root-cause evidence unless it supplies a new input delta, authority change, or external-state change.
- `$derive-improvement-task` and `$orchestrate-task-cycle`: if advice audit reports `unconsumed_advice_regression`, treat it as backlog/debt evidence to wire, verify, defer, reject, or retire the named clause; do not treat it as GT, authority, or a separate progress gate.
- All consuming workflow skills: use the canonical directive owner and its generic record fields, route by `target_owner` when declared, and interpret `directive_text` through the consumer's existing adapter or project contract. Preserve the source `directive_id` and record fields in evidence; do not infer a global field taxonomy from document-local headings or labels.
- All consuming workflow skills: apply `change_class|classification` generically. Revise an existing owner in place when declared, introduce an additive surface only when the directive explicitly requires it and higher-priority contracts permit it, and honor activation, grouping, selection, or exclusion constraints expressed by the canonical directive and owning raw source without creating an advice-owned phase or schema.
- `$audit-cycle-loopback` and advice audit may both emit `advice_freshness_gate`; downstream workflows should treat either stale finding as warning-level evidence that headline advice metrics cannot be used without refresh, deferral, rejection, or current-evidence rationale.
- `$task-md-agent-governance`: include relevant active advice in worker and audit prompts as non-GT design/task constraints.
- `$validate-task-completion`: check whether task-referenced advice was applied, rejected, or deferred with evidence.
- `.agent_goal` management skills: may read advice as evidence, but must not promote it into `.agent_goal/*.md` without explicit user approval and the owning goal skill.

## Guardrails

- Do not treat advice as GT.
- Do not create `.agent_goal/advice*` files.
- Do not apply advice that conflicts with authority policy, latest user instruction, or repository evidence.
- Do not let advice edit implementation code directly; route implementation through `$task-md-agent-governance`.
- Do not delete raw advice unless the user explicitly requests deletion and the deletion is indexed/logged.
- Do not embed raw advice, normalized advice, a caller locator, or a full registry event in an intake plan or receipt. The separately published digest-named source snapshot may contain raw advice; bind it by exact digest and reopen that owner snapshot during apply.
- Do not infer no-effect from an exception or a missing final event alone. Require the exact immutable plan-bound no-effect receipt, `plan_effect_observed=false`, `plan_intent_observed=false`, `no_effect_verified=true`, a valid historical registry-prefix proof, and the exact receipt-file digest. A partial or ambiguous intent/event always fails closed or routes to same-plan recovery.
- Do not mark advice applied without evidence or a recorded rationale.
- Do not mark advice applied when `fidelity_status: degenerate` unless the application evidence cites the raw advice path or records that the raw text was manually reviewed.
- Do not rely on stale headline metrics or fingerprint claims when `advice_metrics_stale: true`; refresh, defer, reject, or cite current evidence that supersedes the stale claim.
- Do not rely on advice as fresh untried root-cause evidence when `re_advised_dead_hypothesis: true`; require a supplied input delta or retire/defer/reject the advice.
- Do not mark a clause `wired` solely because it was copied into a skill, task, contract, or declared hook. Require clause-bound consumer invocation and decision consumption evidence.
- Do not mark a clause `verified` from documentation, a single unit test, a hook declaration, container lifecycle state, or a retirement disposition. Require distinct fresh negative-boundary and happy-path decision receipts plus a content-bound clause consumer receipt. Retirement closes the obligation with evidence but does not rewrite its consumption state. Missing `consumption_state` evidence is `consumption_state_unverified`, not a pass.
- Do not turn repository-specific paths, metrics, thresholds, models, hardware, lane keys, report schemas, prompt text, commands, or document-local taxonomies into global advice fields. Preserve only the canonical generic directive record; leave concrete interpretation to the targeted adapter/project contract and exact wording to the registry-owned raw source.
- Do not leave used active/applied advice untracked in a Git-backed task cycle unless sensitivity or explicit user direction requires local-only handling and the reason is reported.
