# Label Adjudication

Use independent labelers only when deterministic or executable oracles cannot fully label the item.

## Process

1. Give each labeler only the item, allowed source locators/spans, public task criteria, no-overclaim rules, and source-class policy.
2. Keep labeler A and labeler B outputs independent.
3. Let an adjudicator compare votes, disagreement causes, evidence refs, and oracle feasibility.
4. Mark unresolved semantic disagreements as `needs_human_review` or `candidate`, not gold.
5. Write a `disagreement_report.json` when multiple labelers or adjudication is used.

## Label Status

- `candidate`: plausible but not accepted as stable.
- `accepted`: accepted for this validation tier.
- `rejected`: rejected during adjudication.
- `needs_human_review`: cannot be resolved without human judgment.
- `blocked`: source, authority, or evidence gap prevents labeling.

Use `human_reviewed` label type only when a human actually reviewed the label. Record a bounded `human_reviewer_ref` and at least one `evidence_refs` entry; without both, do not use the human-reviewed claim or gold tier.

To satisfy a required item/oracle pair that the deterministic runner cannot execute, additionally require `label_status: accepted`, JSON boolean `authoritative: true`, and `oracle_ids` naming that exact oracle. One adjudication covers only its explicit item/oracle pairs.
