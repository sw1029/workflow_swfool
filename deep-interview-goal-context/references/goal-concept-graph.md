# Goal Concept Graph Contract

## Contents

- [Purpose](#purpose)
- [Ownership](#ownership)
- [Node contract](#node-contract)
- [Relation contract](#relation-contract)
- [Mutability and decision ownership](#mutability-and-decision-ownership)
- [Interview and migration rules](#interview-and-migration-rules)
- [Downstream consumption](#downstream-consumption)
- [Validation](#validation)

## Purpose

Represent the user's core idea, bounded design freedom, and evidence-derived implementation choices without turning free-form interview prose into implicit authority. Keep this graph inside the existing goal artifacts:

- `goal_theory.md` owns the canonical node and relation table plus its canonical digest.
- `goal_architecture.md` owns the realization/consumer map for those same concept IDs.
- `goal_schema_contract.md` may constrain serialized fields or compatibility rules by concept ID.
- `agent_authority.md` owns only decision rights over an exact concept ID and digest. It must not redefine concept truth.

Do not create a fifth final goal artifact, a new workflow phase, or a repository-specific global vocabulary.

## Ownership

Use stable opaque IDs such as `concept-001`, `relation-001`, and `evidence-001`. Do not place raw prompts, source bodies, personal identifiers, corpus metadata, credentials, or sensitive transcript text in IDs or graph fields.

Treat the graph as confirmed goal truth only after the existing interview evidence review, user final confirmation, final critical review, and agent write-confirmation gates pass. Before that point it is a draft projection under `.interview/drafts/goal_theory.md` and `.interview/drafts/goal_architecture.md`.

## Node contract

Every node must include:

| Field | Contract |
| --- | --- |
| `concept_id` | Stable opaque ID. |
| `concept_class` | One closed class listed below. |
| `statement` | Bounded concept statement supported by interview or repository evidence. |
| `mutability` | `locked`, `user_change`, `agent_bounded`, `evidence_derived`, or `unclassified`. |
| `decision_owner` | `user_goal_owner`, `delegated_policy_steward`, `cycle_coordinator`, `executor`, or `unclassified`. |
| `required_source_rank` | `S0` through `S4`, or `unclassified`; this is a requirement, not a grant. |
| `risk_ceiling` | `R0` through `R3`, or `unclassified`. |
| `decision_class` | `D0` core goal, `D1` bounded design, `D2` task topology, `D3` action tactic, or `unclassified`. |
| `required_capabilities` | Sorted exact capability IDs; empty only when no authority-bearing change is possible. |
| `allowed_variation` | Closed choices, range, predicate, or `none`; never a vague “reasonable changes” grant. |
| `deterministic_rule` | Rule selecting among allowed choices, or an open-question ID. |
| `validation_predicate_ids` | Opaque predicates that can confirm the concept or its realization. |
| `consumer_ids` | Goal, schema, task, skill-operation, or runtime consumers. |
| `reversibility` | `reversible`, `conditionally_reversible`, `irreversible`, or `unclassified`. |
| `source_evidence_ids` | Opaque evidence IDs, not raw content. |
| `revision_id` | Monotonic or content-addressed revision ID. |
| `concept_digest` | Canonical digest of every field above except the digest itself. |

Use these concept classes:

- `core_invariant`: the central purpose or property whose removal changes the goal itself.
- `guardrail`: a safety, privacy, evidence, compatibility, or no-overclaim constraint.
- `bounded_design`: a user-approved option space in which an agent may choose deterministically.
- `implementation_variable`: a replaceable implementation choice with bounded compatibility obligations.
- `runtime_adaptive`: a value selected from current evidence or resource state under a named rule.
- `experimental_hypothesis`: a falsifiable candidate that is not goal truth until validated and adopted.
- `open_question`: an unresolved concept, owner, range, or relationship.

Do not convert an unanswered question into `bounded_design`, an implementation default into `core_invariant`, or an existing code path into a user-approved design merely because it exists.

## Relation contract

Every relation must include `relation_id`, `relation_type`, `from_concept_id`, `to_concept_id`, `relation_mutability`, `decision_owner`, `validation_predicate_ids`, `source_evidence_ids`, `revision_id`, and `relation_digest`.

Use only these relation types:

- `requires`
- `must_preserve`
- `constrains`
- `realizes`
- `may_vary_within`
- `alternative_to`
- `validated_by`
- `supersedes`
- `incompatible_with`
- `delegates_choice_to`
- `change_requires`

Classify relation mutability separately from node mutability. Two nodes may be individually variable while their `requires` or `incompatible_with` relation remains locked. A change to either endpoint does not silently rewrite the relation.

Reject dangling concept IDs, self-edges other than explicitly justified `validated_by`, duplicate semantic edges with different IDs, cycles in `supersedes`, and `delegates_choice_to` edges that give an owner more capability, risk, scope, duration, or use budget than the parent concept permits.

## Mutability and decision ownership

Interpret the decision dimensions as follows:

- `D0`: changing a core goal, core invariant, forbidden effect, or goal success definition. Require the user goal owner and exact current concept digest.
- `D1`: choosing or changing an approved bounded design envelope. A delegated steward may act only inside the exact options/range and capability scope.
- `D2`: task or task-pack topology, ordering, insertion, retirement, or recurring improvement policy. Require an operation-level authority decision; task authority does not imply action authority.
- `D3`: a concrete implementation or runtime tactic. Permit autonomous choice only when the graph supplies a deterministic rule and the operation manifest plus active lease cover it.

Higher source rank may narrow, suspend, revoke, or delegate within the same concept/capability lineage. It must not widen an unrelated capability namespace or change a locked concept by numeric rank alone.

Keep the following events typed and separate:

- granting or delegating authority;
- ratifying goal truth;
- accepting risk or cost;
- supplying an external input;
- selecting a design option.

One event must not stand in for another. In particular, an approved design option does not grant network access, and an available external input does not authorize its use.

## Interview and migration rules

Ask one question per invocation. Prefer questions that resolve, in order:

1. which concepts are core invariants or guardrails;
2. which options may vary and within what exact envelope;
3. which relationships must remain stable even when endpoints vary;
4. who owns each decision class;
5. which evidence determines runtime-adaptive choices;
6. which changes require a fresh user decision, risk confirmation, or external input.

For a legacy `.interview` or final goal set that lacks these fields:

- preserve the existing prose and final files;
- project only directly supported nodes and relations;
- mark missing class, owner, mutability, capability, or relation facts `unclassified`;
- create targeted follow-up questions for blocking `unclassified` fields;
- record a migration revision and source evidence IDs;
- do not claim that prior silence, prior implementation, or a later approval retroactively established an earlier concept or delegation.

Do not reopen a completed interview merely because optional graph detail is absent. Reopen only when a current downstream decision depends on an unclassified field or the user explicitly requests migration.

## Downstream consumption

Compile the graph into an autonomy envelope without copying graph truth into authority artifacts:

```text
exact concept/relation digest
  ∩ allowed variation and deterministic rule
  ∩ active operation manifest
  ∩ active non-revoked grant or lease
  ∩ current risk/cost and external-input state
  = bounded downstream choice
```

If any required term is missing, route `classification_repair`, a single targeted interview question, or a narrow planning task as appropriate. Do not infer permission from the most permissive remaining term.

Task derivation may choose among `bounded_design`, `implementation_variable`, and `runtime_adaptive` options only within their recorded envelope. It must request explicit goal-owner direction for `core_invariant` changes, preserve guardrails, and keep `experimental_hypothesis` work reversible and validation-bound.

## Validation

Before final write or authority compilation, verify:

- every node and relation has a stable ID, revision, evidence set, and recomputed digest;
- every reference resolves and every consumer points to the current or explicitly historical revision;
- core concepts and locked relations have user-supported evidence;
- agent-bounded choices have a closed range and deterministic rule;
- capability/rank/risk fields express requirements only and do not claim a grant;
- goal theory, architecture realization map, schema constraints, and authority decision-right references use identical concept IDs and digests;
- legacy migration contains no retrospective authority or invented user decision;
- no raw or sensitive source metadata appears in graph IDs or stored evidence summaries.
