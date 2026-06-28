---
name: manage-external-advice
description: "Manage non-goal-truth external advice Markdown for task and design direction correction. Use when Codex receives, imports, normalizes, injects, audits, applies, rejects, or retires external advice documents that should influence `$orchestrate-task-cycle`, `$task-doctor`, `.agent_goal`-using skills, task derivation, implementation governance, or validation without being treated as `.agent_goal` goal truth."
---

# Manage External Advice

## Overview

Use this skill to manage external advice as a separate non-GT workflow input under `.agent_advice/`. External advice can influence task direction and design choices, but it is never goal truth and must not be mixed into `.agent_goal/` without explicit user approval and the owning goal skill.

Read [advice-contract.md](references/advice-contract.md) when writing or auditing advice artifacts.

## Storage Model

Use this workspace layout:

- `.agent_advice/raw/`: preserved external advice Markdown.
- `.agent_advice/active/`: normalized advice that must be considered by supported workflow skills.
- `.agent_advice/deferred/`: advice that remains plausible but is blocked by missing evidence, prerequisite work, or a pending user decision.
- `.agent_advice/applied/`: advice whose actionable directives were incorporated or otherwise retired with durable evidence.
- `.agent_advice/rejected/`: advice rejected because it conflicts with newer user instructions, GT, authority, safety, or repository facts.
- `.agent_advice/index.jsonl` and `.agent_advice/index.md`: advice-local lifecycle index.

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

## Workflow

1. Intake raw advice.
   - Use `scripts/advice_registry.py --root . intake --source <path.md> --title <title>` when a local Markdown file is provided.
   - When a root steering doc is named or detected by an `orphan_advice_not_intaken` finding, intake that root file directly and keep the normalized active artifact under `.agent_advice/active/`.
   - Use `--source -` only when the user provided text in the current turn and it is safe to store.
   - Preserve the raw document under `.agent_advice/raw/`.
   - Do not store secrets, credentials, raw sensitive data, or large copyrighted excerpts.

2. Normalize advice.
   - Create one active normalized Markdown file under `.agent_advice/active/`.
   - Extract claims, actionable directives, conflicts, task integration, design integration, application gates, evidence required to mark applied, and exclusions.
   - Mark `not_goal_truth: true`.
   - When the raw advice declares headline metric snapshots, artifact fingerprints, or output fingerprints, record them under `Advice Freshness` and compare them with current repository/adapter output fingerprints when available. If they do not match, set `advice_metrics_stale: true` and require refresh, defer, or reject rationale before downstream workflows rely on those headline claims.
   - When the advice declares root-cause hypotheses, let `audit` compare them with `.task/anti_loop/root_cause_ledger.jsonl`. If a claimed hypothesis was already `repair_attempted` with `terminal_outcome_changed=false`, set `re_advised_dead_hypothesis: true` and do not use that advice as fresh untried evidence without a new supplied input delta.
   - Emit `Normalization Fidelity` with `fidelity_status`, `fidelity_reason`, and `raw_direct_reference_required`. If extracted claims and actionable directives are identical, empty, or metadata-only, set `fidelity_status: degenerate|needs_review`, keep the advice active only as a warning-bearing packet, and require downstream workflows to consult the raw advice before applying it.
   - If the advice is too ambiguous to normalize, create a rejected or deferred record with the reason.

3. Inject advice into workflow packets.
   - Use `scripts/advice_registry.py --root . render-packet --format markdown|json`.
   - Pass active advice packet summaries to `$orchestrate-task-cycle`, `$task-doctor`, `$derive-improvement-task`, `$task-md-agent-governance`, `$validate-task-completion`, and `.agent_goal` management skills when they use goal context.
   - Require called skills to report `used_advice` separately from `used_goal_truth`.
   - When advice is used by a Git-backed workflow, classify the safe normalized active/applied advice file as an intentional workflow artifact for staging/commit unless a `local_only` reason is recorded.

4. Apply or reject advice.
   - Use `mark-applied` only after the advice directive has been incorporated into `task.md`, candidate tasks, schema/design records, implementation notes, or otherwise retired by durable evidence.
   - `mark-applied` writes a `past_advice` `.agent_log` entry and moves the normalized advice to `.agent_advice/applied/`.
   - Use `defer` when the advice is plausible but cannot be applied yet; record the missing evidence, prerequisite, or pending user decision.
   - Use `reject` when a conflict makes the advice unsuitable; record the conflict source and keep the raw artifact.

5. Audit and index.
   - Run `scripts/advice_registry.py --root . audit` after intake, apply, or reject.
   - When an adapter or loopback packet has a current output fingerprint, run `scripts/advice_registry.py --root . audit --current-output-fingerprint <fingerprint>` or `--current-output-fingerprint-json <packet.json>` so audit emits `advice_freshness_gate` and `advice_metrics_stale` findings.
   - When a root-cause ledger exists, audit also emits `re_advised_dead_hypothesis` and `dead_hypothesis_claims`; downstream workflows must refresh, defer, reject, or require a new input delta before treating that advice as untried root-cause provenance.
   - Treat root steering docs that remain outside `.agent_advice/active/` as warn-only orphan advice until they are intaken, deferred, rejected, or explicitly ignored with a recorded rationale.
   - Run `$manage-task-state-index scan` and `audit` when task-state artifacts exist.

## Skill Integration Contract

- `$orchestrate-task-cycle`: collect active advice at cycle start, include it in subskill packets, validate that active advice is not accidentally reported as GT, and report it as `비-GT 방향성 문서`.
- `$task-doctor`: may use active advice as an explicit direction source only when the user asks for task doctoring or names the advice; it must still archive `task.md` before replacement.
- `$derive-improvement-task`: treat active advice as planning evidence and explain whether selected or rejected advice affected the next task.
- `$derive-improvement-task`: if an active advice packet has `raw_direct_reference_required=true`, cite the raw advice path in `used_advice` and avoid relying on the normalized claims/directives alone.
- `$derive-improvement-task`: if an active advice packet or `anti_loop_progress_gate.advice_freshness_gate` reports `advice_metrics_stale=true`, refresh, defer, reject, or explicitly justify use against current repository evidence.
- `$derive-improvement-task`: if advice audit reports `re_advised_dead_hypothesis=true`, do not treat that advice as fresh untried root-cause evidence unless it supplies a new input delta, authority change, or external-state change.
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
- Do not mark advice applied without evidence or a recorded rationale.
- Do not mark advice applied when `fidelity_status: degenerate` unless the application evidence cites the raw advice path or records that the raw text was manually reviewed.
- Do not rely on stale headline metrics or fingerprint claims when `advice_metrics_stale: true`; refresh, defer, reject, or cite current evidence that supersedes the stale claim.
- Do not rely on advice as fresh untried root-cause evidence when `re_advised_dead_hypothesis: true`; require a supplied input delta or retire/defer/reject the advice.
- Do not leave used active/applied advice untracked in a Git-backed task cycle unless sensitivity or explicit user direction requires local-only handling and the reason is reported.
