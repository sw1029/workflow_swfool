# Repo-Local Skill Adapters

This reference defines how `$orchestrate-task-cycle` discovers, consumes, schedules, and validates repository-scoped skills under `.codex/skills/`. These adapters are workflow capability evidence for the current repository only; they are not workspace goal truth.

## Contents

- [Core Rule](#core-rule)
- [Adapter Scan](#adapter-scan)
- [Adapter Consumption](#adapter-consumption)
- [Creation Or Update Routing](#creation-or-update-routing)
- [Adapter Validation](#adapter-validation)
- [Gap Analysis And Derive Handoff](#gap-analysis-and-derive-handoff)
- [Failure Handling](#failure-handling)

## Core Rule

Treat repository-scoped domain skills under `.codex/skills/` as optional adapters for domain vocabulary, artifact taxonomy, validation-set planning hints, command profiles, qualitative-review criteria, output-delta interpretation, code convention contracts, structure metrics, and derive candidate selection.

Adapters must not:

- become `.agent_goal` goal truth;
- grant authority, external/API permission, or human approval;
- bypass `$manage-agent-authority`, `.agent_advice` lifecycle rules, validation-set source-class rules, task-pack rules, result-contract gates, or anti-loop gates;
- prove task completion by themselves;
- patch repository implementation code outside `$task-md-agent-governance`.

## Adapter Scan

During `repo_skill_adapter_scan`, inspect only compact metadata:

- `.codex/skills/<skill-name>/SKILL.md` frontmatter;
- optional `.codex/skills/<skill-name>/adapter.manifest.json`;
- existence of optional `scripts/render_adapter_packet.py`;
- basic active/inactive/invalid status.

Do not load adapter body text, examples, long references, fixtures, or domain maps during the initial scan. Load them only when a phase packet says the detail is relevant.

Record the scan as `repo_skill_adapter_packet` with adapter ID/path/status, metadata summary, renderer availability, non-GT warning, and validation status when known.

## Adapter Consumption

Prefer deterministic phase packets:

```bash
python3 .codex/skills/<skill-name>/scripts/render_adapter_packet.py --phase <phase>
```

Use a rendered packet only for the phase it names. If no renderer exists, assemble a compact manual packet from metadata and safe summaries.

Adapters may inform these phases when applicable:

- `validation_set_plan`
- `governance`
- `run`
- `qualitative_review`
- `loopback_audit`
- `validation_set_build`
- `schema_pre_derive`
- `derive`
- `schema_post_derive`
- `validate`

Adapters may expose `code_convention_contract` as compact data. Keep project-specific naming rules, max LOC/depth/fan-out values, kernel/reuse roots, dependency DAGs, forbidden patterns, and semantic module placement rules inside the repo-owned adapter or `.agent_goal/conventions.md`; generic workflow skills consume only the contract shape and status.

If a repository also registers a loopback domain adapter, pass its declared path/status to `$audit-cycle-loopback`. A registered adapter that does not load is an `adapter_wiring_defect` or adapter load correction task, not evidence that no adapter exists. Keep this distinction in `repo_skill_gap_packet` so `$derive-improvement-task` does not schedule duplicate adapter creation.

Keep adapter-loaded references one level deep inside the adapter skill. Detailed domain maps, validation policies, command profiles, and examples belong in `references/`. Deterministic packet renderers, lint checks, or fixture-safe checks belong in `scripts/`.

## Creation Or Update Routing

Create or update repo-local adapters only through a separate active `task.md` selected by `$derive-improvement-task`. The next task must route implementation through `$task-md-agent-governance`, invoke `$skill-creator`, and place files under `.codex/skills/<skill-name>/` unless the user explicitly requests a global skill location.

Do not opportunistically edit `.codex/skills/` during a normal cycle. A derive result may only schedule adapter work by writing the next `task.md`, retained candidate, or task-pack item.

Use `$skill-creator` rules for adapter tasks:

- keep `SKILL.md` concise;
- split detailed reusable knowledge into first-level `references/`;
- add `scripts/` only for deterministic repeated or fragile operations;
- use `assets/` only for files used in produced outputs;
- avoid README, changelog, quick-reference, installation-guide, or process-history files;
- refresh `agents/openai.yaml` when UI discovery matters;
- validate with `quick_validate.py` when available;
- run adapter-local lint or a minimal forward-test when the adapter can affect future routing.

## Adapter Validation

When `.codex/skills/` changed in the current task, run `repo_skill_adapter_validate` before treating the adapter as consumable in later cycles.

Validation must check:

- folder/name alignment and lowercase hyphenated skill name;
- `SKILL.md` frontmatter has only `name` and `description`;
- concise `SKILL.md` body and progressive-disclosure links;
- no extraneous auxiliary documentation files;
- one-level `references/` organization;
- deterministic script executability or representative script execution when scripts were added;
- `agents/openai.yaml` consistency when present;
- `$skill-creator` `quick_validate.py` result when available;
- forward-test evidence or a recorded reason it was unsafe, unavailable, or unnecessary.

Treat validation failures as validation/derive blockers. The orchestrator must not patch the adapter directly; route correction through a selected task and `$task-md-agent-governance`.

## Gap Analysis And Derive Handoff

Build `repo_skill_gap_packet` before derivation when current-cycle evidence shows reusable friction:

- repeated domain lookup;
- repeated command/profile discovery;
- repeated validation/oracle/source-class ambiguity;
- repeated progress-classification uncertainty;
- missing or stale `code_convention_contract` when governance, code-structure audit, loopback, derive, or validation repeatedly needs repo-specific naming, reuse, dependency, depth, fan-out, or structure high-water rules;
- repeated mechanical shard, duplicate-helper, global-rebinding, dependency-direction, or reuse-layer ambiguity that generic workflow checks can only report warn-only;
- adapter validation failure;
- task_miss caused by missing repo-specific procedure;
- a known 2-5 task sequence that would otherwise reload long domain context.

The packet should include recommended adapter name, scope, target path, expected resources (`references`, `scripts`, `assets`), future consuming phases, and whether derive should create, update, defer, or reject adapter work.

For convention adapter gaps, include the missing contract fields abstractly, such as `reuse_roots`, `semantic_naming_rules`, `dependency_layers`, `max_tree_depth`, `max_dir_fan_out`, `max_file_loc`, `forbidden_name_patterns`, `structure_metrics`, and `high_water_axes`. Do not put project-specific values into the generic orchestrator skill.

Promote an adapter task only when reusable value is concrete. For one-off instructions, use `.agent_advice`, task acceptance criteria, or normal schema/contract notes instead.

Adapter work is usually `governance_only`. Treat it as goal-productive only when it directly unlocks a blocked validation/run/review/derive state or creates a validated deterministic packet/check tied to a current blocker.

If `$derive-improvement-task` selects adapter work, the selected task must name:

- adapter purpose and scope;
- proposed skill name;
- target path `.codex/skills/<skill-name>/`;
- expected resources;
- validation commands;
- future phases that will consume compact packets.

## Failure Handling

If adapter scan fails, record the invalid adapter path/status and continue without consuming it unless the active task requires adapter work.

If adapter validation fails, preserve the adapter files and logs, mark the adapter as not consumable for future routing, and derive a correction task or blocker.

If adapter packet rendering fails, fall back to metadata-only manual packets when safe. Otherwise mark the adapter phase packet as blocked and keep downstream decisions conservative.

If an adapter conflicts with `.agent_goal`, authority, active advice lifecycle, validation-set source-class rules, task-pack rules, or result-contract gates, ignore or reject the adapter packet for that phase and record the reason.
