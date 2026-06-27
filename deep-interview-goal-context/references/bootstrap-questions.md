# Bootstrap Questions

Use these questions when the hard gate has passed but the user invoked only `$deep-interview-goal-context`, provided no raw prompt, or provided a weak prompt that does not describe the architecture/theory/schema-contract/agent-authority content to collect.

Do not ask all questions at once. Store them in `.interview/questions.md` and present the first 3-5 blocker questions.

## Weak Prompt Detection

Treat the raw prompt as absent or weak when it:

- Contains only the skill name or a generic command such as "start", "continue", "interview", or "fill architecture/theory/schema-contract/agent-authority".
- Does not identify repository areas, workflows, modules, data formats, algorithms, validation rules, or constraints.
- Repeats the goal of writing architecture/theory/schema-contract/agent-authority files without adding project-specific facts.

## Initial Bootstrap Batch

Use stable ids such as `bq-001`.

- id: bq-001
  status: pending
  priority: blocker
  target_file: all
  target_section: Scope
  question: What workspace paths, repository areas, dataset locations, and agent-authority decisions should be treated as in scope or out of scope for `goal_architecture.md`, `goal_theory.md`, `goal_schema_contract.md`, and `agent_authority.md`?
  why_needed: Establishes safe documentation boundaries before architecture, theory, schema-contract, or agent-authority claims are written.
  source: bootstrap

- id: bq-002
  status: pending
  priority: blocker
  target_file: goal_architecture.md
  target_section: Repository Structure
  question: Which directories, scripts, notebooks, or entry points should future agents treat as important for understanding this goal?
  why_needed: Allows architecture documentation to start from user-confirmed repository areas instead of invented structure.
  source: bootstrap

- id: bq-003
  status: pending
  priority: blocker
  target_file: goal_architecture.md
  target_section: Scripts And Entry Points
  question: What are the canonical workflows or commands, if any, that future agents should know before inspecting or running the repository?
  why_needed: Distinguishes real entry points from incidental files.
  source: bootstrap

- id: bq-004
  status: pending
  priority: blocker
  target_file: all
  target_section: Data, Artifacts, And Generated Outputs
  question: What data formats, artifact types, generated outputs, schema fields, module/script contracts, or protected raw-data areas should be documented or explicitly avoided?
  why_needed: Prevents unsupported data-flow and schema-contract claims and avoids copying sensitive or copyrighted raw content.
  source: bootstrap

- id: bq-005
  status: pending
  priority: blocker
  target_file: goal_theory.md
  target_section: Algorithms, Models, Or Mechanisms
  question: What technical logic, algorithms, heuristics, models, or conceptual rules should `goal_theory.md` explain, and which are still unknown?
  why_needed: Prevents the theory file from inventing rationale or algorithmic behavior.
  source: bootstrap

- id: bq-006
  status: pending
  priority: blocker
  target_file: all
  target_section: Validation Logic
  question: What evidence or validation criteria should prove that architecture/theory/schema-contract/agent-authority claims are correct: file evidence, command outputs, tests, counts, schemas, manual review, user confirmation, or approval records?
  why_needed: Defines the verification standard before final writing.
  source: bootstrap

- id: bq-007
  status: pending
  priority: blocker
  target_file: goal_schema_contract.md
  target_section: Minimum Contract Fields
  question: Which minimum schema/contract fields must future `.schema/` or `.contract/` records preserve for this goal, and which fields may be marked `not_applicable`?
  why_needed: Prevents `$manage-schema-contracts` from inventing or omitting required contract metadata.
  source: bootstrap

- id: bq-008
  status: pending
  priority: blocker
  target_file: goal_schema_contract.md
  target_section: Required Application Rules
  question: What versioning, target module/script, producer/consumer, compatibility, validation, and causal-map rules are mandatory for schema/contract governance?
  why_needed: Defines the rules that `.schema/` and `.contract/` management must satisfy after final write.
  source: bootstrap

- id: bq-009
  status: pending
  priority: blocker
  target_file: agent_authority.md
  target_section: Authority Baseline
  question: Should `agent_authority.md` default to the current coding agent's effective permissions, and are there any project-specific restrictions on API calls, network/external services, destructive actions, long-running runs, or approval requests?
  why_needed: Establishes that the authority file narrows or clarifies the active agent permissions instead of inventing new authority.
  source: bootstrap

- id: bq-010
  status: pending
  priority: blocker
  target_file: agent_authority.md
  target_section: Direction Freedom
  question: Which operating posture should future agents use by default: strict application, bounded variation, implementation-first, artifact/output-confirmation-first, quality-verification-first, conservative implementation, or another named profile?
  why_needed: Lets `$derive-improvement-task` and code-writing workers choose scope, variation, and validation posture consistently.
  source: bootstrap

- id: bq-011
  status: pending
  priority: important
  target_file: all
  target_section: Assumptions
  question: Which facts may future agents infer from repository evidence, and which decisions must remain open until the user confirms them?
  why_needed: Keeps inference boundaries explicit.
  source: bootstrap

- id: bq-012
  status: pending
  priority: important
  target_file: all
  target_section: Tradeoffs And Limits
  question: What actions are forbidden or risky during this interview and documentation process, such as editing datasets, running long jobs, installing packages, using network access, or storing raw text?
  why_needed: Converts operating constraints into durable documentation rules.
  source: bootstrap
