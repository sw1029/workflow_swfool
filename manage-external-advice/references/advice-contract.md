# External Advice Contract

This contract defines `.agent_advice/` artifacts. Advice is direction evidence, not `.agent_goal` goal truth.

## Directory Layout

```text
.agent_advice/
├── raw/
├── active/
├── deferred/
├── applied/
├── rejected/
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
- source_label: <human label>

## Summary

<Short summary of the advice.>

## Extracted Claims

- <Claim with confidence or evidence note.>

## Actionable Directives

- <Directive that can influence task/design/workflow behavior.>

## Normalization Fidelity

- fidelity_status: ok | needs_review | degenerate
- fidelity_reason: <why the extraction is trustworthy or not>
- raw_direct_reference_required: true | false
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

## Index Fields

Record advice in `.agent_advice/index.jsonl` and `$manage-task-state-index`:

- artifact type: `external_advice`
- ID prefix: `adv-*`
- useful fields: `not_goal_truth`, `status`, `raw_source_path`, `scope`, `priority`, `source_label`
- fidelity fields: `fidelity_status`, `fidelity_reason`, `raw_direct_reference_required`
- freshness fields: `advice_metrics_stale`, `declared_output_fingerprints`, `current_output_fingerprint`, `freshness_reason`
- root-cause freshness fields: `re_advised_dead_hypothesis`, `dead_hypothesis_claims`, `root_cause_ledger_path`
- useful links: `advice_for`, `incorporated_into`, `applied_by`, `rejected_by`, `superseded_by`, `conflicts_with_goal`, `conflicts_with_authority`

## Audit Freshness Gate

When `scripts/advice_registry.py audit` receives `--current-output-fingerprint` or `--current-output-fingerprint-json`, it must compare active advice fingerprint claims to the supplied current fingerprint and emit:

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

If `fidelity_status` is `degenerate` or `needs_review`, downstream workflows must cite or inspect `raw_source_path` before applying directives. Normalized claims/directives alone are not sufficient application evidence in that state.

If `advice_metrics_stale` is `true`, downstream workflows must refresh, defer, reject, or explicitly justify use against current repository evidence before relying on headline metric or fingerprint claims. Advice freshness is a warning gate, not goal truth.

If `re_advised_dead_hypothesis` is `true`, downstream workflows must not use that advice as fresh untried root-cause evidence unless it supplies a new input delta, authority change, or external-state change.
