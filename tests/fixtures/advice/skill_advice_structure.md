# General Workflow Advice Fixture

현재 workflow에는 구조적으로 구분해야 할 owner clause와 reference matrix가 있다.

| Directive ID | Default state | 역할 |
|---|---|---|
| `SA-GEN-01-INPLACE-FIRST` | `pending` | existing behavior를 먼저 수정해야 한다 |
| `SA-GEN-02-ADDITIVE-ONLY-WITH-GAP` | `pending` | negative gap이 있을 때만 surface를 추가한다 |
| `SA-GEN-03-NO-NEW-SKILL-BY-DEFAULT` | `pending` | 신규 skill은 기본적으로 금지한다 |
| `SA-GEN-04-OPAQUE-SOURCE-METADATA` | `pending` | source metadata를 opaque ID로 보존한다 |
| `SA-GEN-05-NO-OVERCLAIM` | `pending` | local pass를 global pass로 승격하지 않는다 |

## Existing owner revisions

### SA-001 — Contract satisfiability owner
- change_class: `in_place_revision`
- consumption_state: `pending`
Owner body must remain part of SA-001 rather than a second directive.

### SA-002 — Premise receipt owner
- change_class: `conditional_additive_receipt`
- consumption_state: `pending`

### SA-003 — Exact artifact binding owner
- change_class: `in_place_revision`
- consumption_state: `pending`

### SA-004 — Scoped progress owner
- change_class: `conditional_additive_projection`
- consumption_state: `pending`

### SA-005 — Stable recurrence owner
- change_class: `in_place_revision`
- consumption_state: `pending`

### SA-006 — Typed finalization owner
- change_class: `conditional_additive_or_deferred`
- consumption_state: `pending`

### SA-007 — Consumer conformance owner
- change_class: `conditional_additive_receipt`
- consumption_state: `pending`

### SA-008 — Metric observation owner
- change_class: `in_place_revision`
- consumption_state: `pending`

### SA-009 — Producer starvation owner
- change_class: `in_place_revision`
- consumption_state: `pending`

### SA-009A — Prerequisite-chain owner
- change_class: `conditional_additive_projection`
- consumption_state: `pending`

### SA-010 — Authority classification owner
- change_class: `in_place_revision`
- consumption_state: `pending`

### SA-011 — Verification separation owner
- change_class: `in_place_revision`
- consumption_state: `pending`

### SA-012A — Decision freshness owner
- change_class: `in_place_revision`
- consumption_state: `pending`

### SA-012B — Conditional reachability owner
- change_class: `conditional_in_place_revision`
- consumption_state: `pending`
- selection_disposition_when_capability_absent: `deferred`

### SA-013 — Advice lifecycle grouping
- change_class: `existing_invariant_to_preserve`
- grouping_only: `true`
- actionable_child: `SA-013A-DOWNSTREAM-CONSUMER-WIRING`
- actionable_child_consumption_state: `pending`

### SA-014 — Lifecycle identity grouping
- change_class: `umbrella only`
- grouping_only: `true`

1. `SA-014A`, `consumption_state: pending`: Current and history identities must remain separate.
2. `SA-014B`, `consumption_state: pending`: Retained change must be classified from observed state.
3. `SA-014C`, `consumption_state: pending`, `selection_disposition: deferred_by_default`: Compact references remain conditional.

## Conditional additive group

- selection_disposition: `deferred_by_default`
- activation_rule: `activate only after an unrepresentable negative fixture`

### A-S01 — Scoped progress object
This surface must stay deferred until the parent activation rule is met.

### A-S02 — Consumer conformance receipt
This surface must stay deferred until the parent activation rule is met.

### A-S03 — Replayable operation envelope
This surface must stay deferred until the parent activation rule is met.

### A-S04 — Scenario injection
This surface must stay deferred until the parent activation rule is met.

### A-S05 — Prerequisite projection
This surface must stay deferred until the parent activation rule is met.

### A-S06 — Decision reconciliation
This surface must stay deferred until the parent activation rule is met.

## Reference matrix

| Clause | Consumer | Note |
|---|---|---|
| SA-001 | acceptance | owning clause reference only |
| SA-006 | finalizer | owning clause reference only |
| SA-001, SA-006 | validation | repeated reference is not a declaration |

## Final outcome clause

- directive_id: `SA-GEN-06-FINAL-OUTCOME-CLASSIFICATION`
- change_class: `proposed in-place decision revision`
- consumption_state: `pending`

This explicit declaration requires a bounded final classification decision.
