# Schema Contract Format

Use `.schema/` as a workspace-local contract registry. When `.agent_goal/goal_schema_contract.md` exists, its minimum fields, application intent, mandatory application rules, and required causal relationships govern this format.

Use `.contract/` only as an auxiliary or legacy contract area when a repository already has it or a caller explicitly requests it. Keep `.schema/` as the canonical indexable registry and reconcile any `.contract/` records back to `.schema/` IDs, versions, and causal links.

## Layout

```text
.schema/
├── index.md
├── causal_map.md
├── contracts.jsonl
├── schemas/
│   └── <schema-id>.md
├── modules/
│   └── <module-path-slug>.md
├── scripts/
│   └── <script-path-slug>.md
└── contracts/
    └── <contract-id>.md
```

Use only the directories needed by the repository. Prefer one file per meaningful shared contract or component contract.

If `.contract/` is present, preserve its useful contract evidence but avoid divergent duplicate truth. A `.contract/` record should either link to a `.schema/` contract ID or be mirrored by a `.schema/contracts/<contract-id>.md` `needs_review` record until reconciled.

## Contract File Template

```markdown
# <Contract Name>

- contract_id: <stable-slug>
- type: schema | module_contract | script_contract | compatibility_note | needs_review
- status: active | deprecated | superseded | needs_review
- version: <semver or vYYYYMMDD-N>
- owner_path: <primary file or module path>
- target_modules:
  - <module path>
- target_scripts:
  - <script path>
- producers:
  - <module/script/function>
- consumers:
  - <module/script/function>
- inputs:
  - <field/file/argument and constraints>
- outputs:
  - <field/file/artifact and constraints>
- invariants:
  - <rule that callers depend on>
- compatibility:
  - backward_compatible: yes | no | unknown
  - breaking_change_from: <version or none>
  - compatible_with:
    - <contract id/version>
- validation:
  - <command, test, or review evidence>
- source_evidence:
  - <file path or line reference when known>
- updated_at: <date/time if available>

## Notes

<short factual notes; avoid copying large source/data excerpts>
```

These fields are the default minimum. If `.agent_goal/goal_schema_contract.md` adds stricter fields or mandatory rules, follow the goal-level document. If a required field is genuinely not applicable, write `not_applicable` and explain why rather than dropping the field.

## `causal_map.md`

Represent cross-component compatibility as directed edges:

```markdown
# Schema Causal Map

| Source | Relation | Target | Version Range | Compatibility | Evidence | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `scripts/build_index.py` | produces_schema | `schema:index-record` | `>=v20260522-1` | compatible | `tests/...` | JSONL records consumed by loader |
| `dataset_loader.py` | consumes_schema | `schema:index-record` | `>=v20260522-1` | compatible | review | Loader assumes `work_id` and `episode_id` |
```

Use these common relations:

- `contract_for`
- `schema_for`
- `module_contract_for`
- `script_contract_for`
- `depends_on`
- `produces_schema`
- `consumes_schema`
- `compatible_with`
- `breaks_contract`
- `supersedes_contract`
- `causes`
- `caused_by`

## `contracts.jsonl`

Use JSONL for append-only history when practical:

```json
{"event":"upsert","contract_id":"schema-index-record","version":"v20260522-1","status":"active","path":".schema/schemas/index-record.md","updated_at":"2026-05-22T00:00:00+09:00"}
```

Keep entries concise. Do not duplicate full Markdown contract bodies in JSONL.
