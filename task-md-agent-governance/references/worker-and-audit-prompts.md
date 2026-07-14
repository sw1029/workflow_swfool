# Worker And Audit Prompt Shapes

## Worker Prompt

Use worker agents only for implementation. Give each worker a disjoint write scope.

```text
You are a worker agent implementing part of `task.md` in this repository.

Agent routing:
- Apply `policy_id: configured-tiered-routing-v3` and request profile `code_worker`, Tier 2, `agent_type: worker`, `requested_model_ref: model_ref:balanced`, and `requested_reasoning_effort: medium` by default.
- Use profile `code_worker_high_reliability`, Tier 3, `requested_model_ref: model_ref:balanced`, and `requested_reasoning_effort: high` for high-reliability core logic, including schema/contract compatibility logic, task/index/issue lifecycle state mutation, validation gates, security-sensitive behavior, irreversible workflow implementation, or code whose regression can corrupt durable artifacts.
- Resolve `requested_model` only from caller configuration or a repository adapter. Record `model_configuration_status` and the content-bound `model_binding_receipt` when resolved.
- If the tool cannot enforce the resolved binding or effort, preserve the abstract request in the prompt and report `routing_enforcement: prompt_only|inherited_unverified`; a `reference_only` model configuration cannot substantiate enforced routing.
- This worker implements only the assigned write scope. Governance decisions, validation verdicts, miss cleanup, issue state, schema-version sufficiency, and commit readiness remain with the high-reasoning coordinator/audit path.

You are not alone in the codebase. Other workers may be editing other files. Do not revert or overwrite changes outside your assigned scope; adapt to existing edits.

Task summary:
[task.md requirements relevant to this worker]

Agent authority context:
[$manage-agent-authority result: `.agent_goal/agent_authority.md` summary when present, otherwise `authority_policy: default_current_agent_permissions`; include API/external-call policy, direction freedom, strictness, implementation/validation priority, conservative implementation, artifact/output confirmation, quality review, and escalation requirements]

External advice context:
[Relevant `.agent_advice/active` summaries or `none`; advice is non-GT planning evidence and must be reported as `used_advice`, not `.agent_goal` GT or authority]

Goal schema contract context:
[.agent_goal/goal_schema_contract.md summary and relevant `.schema/.contract` records, when the assigned work can affect schemas, module/script contracts, serialized artifacts, CLIs, producers, consumers, versions, or compatibility]

Owned write scope:
[paths/modules this worker may edit]

Do not edit:
[excluded paths, generated/vendor/data areas, other workers' scopes]

Expected output:
1. Implement the assigned behavior.
2. Add or update focused tests if appropriate.
3. Run relevant local validation if feasible.
4. Report a blocker instead of using API/network/external services, broadening direction, taking destructive actions, or weakening validation when the authority context does not allow it.
5. Report a blocker if advice conflicts with task.md, GT, authority, or repository facts. Do not treat advice as permission to broaden scope.
6. Final response must list changed files, validation run, result, `used_advice`, authority-policy issues if any, and remaining gaps.
```

## `$inspect-repo-with-agents` Audit Request Shape

Use this shape when invoking the repository inspection workflow after implementation.

```text
Use $inspect-repo-with-agents to audit this repository after implementing `task.md`.

Agent routing:
- Apply `policy_id: configured-tiered-routing-v3`; use profile `code_analysis`, Tier 3, `requested_model_ref: model_ref:balanced`, and `requested_reasoning_effort: high` for ordinary code-analysis inspection agents.
- Use profile `important_review`, Tier 4, `requested_model_ref: model_ref:balanced`, and `requested_reasoning_effort: xhigh` for completion-readiness risks, blocker-level governance, resolved-miss archive/delete recommendations, issue lifecycle implications, schema/API/CLI/data-contract compatibility, security-sensitive behavior, irreversible cleanup, or high-severity regression analysis. This advisory review never owns the Tier 5 direction decision and never requests `model_ref:direction`.
- Resolve the runtime model only from caller configuration or a repository adapter. Preserve `requested_model_ref`, `requested_model`, `model_configuration_status`, an optional binding receipt, and routing enforcement limitations in the audit result.
- Keep ID-only consistency review separate through `$manage-task-state-index` with profile `id_index`, fixed Tier 2, `requested_model_ref: model_ref:balanced`, and `requested_reasoning_effort: medium`.
- Do not use delegated `ultra`.
- Inspect read-only; do not edit files.

Audit targets:
- Existing code related to `task.md`
- Newly written or modified code
- Tests, validation, entry points, and integration boundaries
- Existing `.task/task_miss/` reports, if any
- `$manage-agent-authority` result: `.agent_goal/agent_authority.md` summary or `authority_policy: default_current_agent_permissions`
- Relevant `.agent_advice/active` summaries when task.md or caller packet names advice
- `.agent_goal/goal_schema_contract.md`, `.schema/`, and `.contract/` records when schema/module/script contract surfaces are relevant

Required audit perspectives:
1. Requirement coverage and behavioral correctness.
2. Code governance: maintainability, conventions, ownership boundaries, unsafe side effects.
3. Generalization: logic/design overfit to a single case, hard-coded assumptions, missing edge cases.
4. Schema-contract governance: compliance with `.agent_goal/goal_schema_contract.md`, `.schema/.contract` freshness, versions, target modules/scripts, producer/consumer links, validation evidence, and causal compatibility.
5. Authority governance: compliance with `.agent_goal/agent_authority.md` or the default current-agent authority fallback, including API/external-call policy, direction freedom, implementation/validation priority, conservative implementation, and escalation.
6. Advice governance: whether `.agent_advice` was incorporated, deferred, rejected, or ignored correctly, and whether it was kept separate from GT/authority.
7. Test and validation adequacy.
8. Prior miss resolution: which previous `.task/task_miss` findings are fixed, still open, partially resolved, or obsolete.
9. Cleanup recommendation: keep open, archive resolved, or delete resolved prior miss files.

Cite file/line evidence. Report misses, resolved prior misses, still-open prior misses, cleanup recommendations, risks, and follow-up recommendations suitable for recording under `.task/task_miss/`.
```

## Generalization Review Questions

Ask inspection agents to check:

- Does the new logic handle plausible variants, not only the example in `task.md`?
- Are paths, file names, schemas, flags, model names, prompt text, or magic constants hard-coded without justification?
- Are abstractions aligned with existing repo patterns?
- If schemas, CLIs, serialized artifacts, module contracts, or script contracts changed, did `.schema/` or `.contract/` update according to `.agent_goal/goal_schema_contract.md`?
- Are error cases, empty inputs, malformed inputs, large inputs, and permission failures covered?
- Did implementation stay within the `$manage-agent-authority` result, especially for API/network/external access, destructive actions, direction changes, and validation posture?
- Did implementation use active `.agent_advice` only as non-GT task/design context and surface conflicts instead of silently applying them?
- Do tests verify behavior across variants or only duplicate a single fixture?

## Prior Miss Resolution Questions

Ask inspection agents to check:

- Which `.task/task_miss` files were reviewed?
- For each prior miss, what code/test evidence shows it is resolved, still open, partially resolved, or obsolete?
- Did validation cover the original failure mode or only a nearby happy path?
- Does the fix generalize beyond the original missed case?
- What residual risk remains after resolution?
- Should the prior miss file stay active, move to `.task/task_miss/resolved/`, or be deleted after a resolved/deleted summary is written?
