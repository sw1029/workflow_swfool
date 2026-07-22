# Session Observation Contract

## Contents

- [Purpose](#purpose)
- [Trust model](#trust-model)
- [Packet schema](#packet-schema)
- [States and findings](#states-and-findings)
- [Binding and consumption](#binding-and-consumption)
- [Stop-hook compatibility](#stop-hook-compatibility)
- [Privacy](#privacy)
- [Repair boundary](#repair-boundary)
- [Index and failure semantics](#index-and-failure-semantics)

## Purpose

Record privacy-safe structural observations about one repository-local Codex or
Claude Code JSONL projection. Preserve hashes, counts, timestamp bounds, and fixed
parser findings without persisting message bodies.

Keep this artifact beside the governed workflow. Never insert it into the canonical
phase order.

## Trust model

Apply these invariants:

1. Set `not_goal_truth` and `not_validation_evidence` to `true`.
2. Never derive positive completion, progress, validation, authority, or blocker
   resolution from a transcript.
3. Never replace task, acceptance, run, ledger, validation, or authority records.
4. Allow an observation to raise a review candidate or reduce confidence.
5. Treat absence as unknown unless an independent canonical source establishes it.
6. Keep capture optional and fail-quiet unless caller policy or acceptance explicitly
   requires complete capture.
7. Interpret `block` as “do not consume this packet,” not “close-block the task.”

Do not include `close_required`. The canonical caller owns close policy.

## Packet schema

Use the closed schema accepted by the orchestration session-audit contract:

| Field | Contract |
| --- | --- |
| `format_version` | Integer `1` |
| `artifact_kind` | `session_governance_audit` |
| `parser_version` | `session-audit/1` |
| `audit_id` | Content-derived `audit-` identifier |
| `tool` | `codex` or `claude-code` |
| `session_id` | Safe explicit ID or source-path-derived ID |
| `source` | Relative path, SHA-256, byte size |
| `capture_mode` | Closed capture-mode vocabulary |
| `capture_status` | Closed capture-status vocabulary |
| `integrity_status` | Closed integrity vocabulary |
| `binding` | Explicit status and identifiers only when bound |
| `consumable` | Sidecar structural-consumption flag |
| `not_goal_truth` | Always `true` |
| `not_validation_evidence` | Always `true` |
| `repair_class` | Closed repair vocabulary |
| `auto_repair_allowed` | True only for derived metadata |
| `findings` | Fixed, body-free structural findings |
| `event_counts` | Non-negative closed counter map |
| `timestamp_bounds` | Normalized first and last timestamps |
| `evidence_paths` | Source path plus ordered event-hash URNs |

Reject unknown fields. In particular, reject workflow verdict, completion, progress,
authority, issue-resolution, and close-policy fields.

Compute `audit_id` from the canonical packet body excluding `audit_id`. Any mutation
therefore invalidates the ID.

Encode event hashes as `sha256:<digest>` entries after the source path in
`evidence_paths`. This preserves ordered line hashes without adding a body-bearing
top-level field.

## States and findings

Use capture modes:

- `conversation_projection` for supported user/assistant events.
- `structured_telemetry` only for a future explicit producer.
- `unknown` when no supported projection is established.

Use capture statuses:

- `complete` when every line is recognized, timestamps are valid, the tool agrees,
  and at least one event exists.
- `partial` when a supported projection exists but completeness is unknown.
- `quarantined` for malformed, unsupported, mixed-tool, raw, or tool-bearing data.
- `failed` for strict UTF-8 or bounded-size inspection failure.

Use `source_hash_only` for packets emitted by the bundled inspector.
`hash_chain_verified` requires a producer that actually checks a chain.
`unverified` cannot be consumable.

Use finding severity `warn` or `block` and evidence classes:

- `transcript_observation` for directly observed parser/capture properties.
- `absence_unknown` for missing observations.
- `cross_source_mismatch` and `canonical_fact` only as legacy/advisory labels in this packet. A separate comparator contract owns any actionable relation or canonical fact.

The bundled log-only producer emits only `transcript_observation` and
`absence_unknown`. Keep messages fixed. Include only line numbers, counts, bounded
limits, and closed labels as finding evidence.

Never include message text, malformed fragments, tool arguments, or results.

## Binding and consumption

Use binding status:

- `bound` only when a canonical caller supplies both `cycle_id` and `task_id`.
- `unbound` when neither is supplied.
- `ambiguous` when exactly one is supplied; do not persist the lone ID.

Never infer binding from transcript text or filenames.

Only `complete`, evaluated-integrity packets with `bound` binding may set
`consumable=true`. This means another component may read the observation. It never
means validation or completion passed.

Before consumption, validate the closed schema, content-derived ID, source snapshot,
non-authority flags, capture state, and binding state. The trusted collector must also
re-run the bundled producer validator and require an exact deterministic projection of
the current source. Its body-free projection records
`source_projection_verified=true`; a directly supplied packet never inherits that
collector provenance and cannot satisfy caller-required audit.

Treat packet-owned `cross_source_mismatch` and `canonical_fact` values as advisory
legacy observations. A separate deterministic comparator contract must own the
compared inputs, relation code, expected and observed scalars, binding, and comparator
version before any semantic mismatch can affect close. Verifying only a canonical
artifact path and hash does not establish that relation.

Never produce from this packet alone:

- `pass`, `advanced`, or `complete_verified`
- completed/failed task state
- authority grant
- resolved blocker or closed issue
- task-pack promotion
- commit, push, deployment, or external message

## Stop-hook compatibility

Use `python3 -P -m audit_session_governance capture` under the skill package `PYTHONPATH` as the optional Stop-hook producer.
Pass the repository root and tool explicitly on argv; pass the hook's safe
`session_id` and absolute `transcript_path` in its stdin JSON object. The producer
strictly bounds and decodes both inputs, rejects duplicate JSON keys, unsupported
schema versions, traversal, non-regular files, and symlinks in any source or output
path component. It rebuilds a minimal tool-native JSONL schema from user/assistant
text blocks only. It never retains raw lines, reasoning, tool arguments/results,
images, provider metadata, system/developer injections, or a verbatim fallback.

The producer atomically overwrites only `logs/<tool>/<safe-session>.jsonl`. Capture
mode writes nothing to stdout. Every logging failure reports a body-free diagnostic
to stderr, exits zero, and leaves any previous projection unchanged so the optional
hook cannot alter the agent session. Consume the projection only after that write has
completed, and keep this fail-quiet capture behavior separate from the auditor's
strict packet validation.

Do not add semantic comparison or repair work to the stop hook. Run inspection and any
cross-source review asynchronously so logging latency or failure cannot alter the agent
session. The source log still contains conversation text and remains sensitive even
though the audit packet is body-free; retention, access control, and deletion policy for
`logs/` are separate operational controls.

When repository policy keeps these artifacts off-chain, prefer the narrow root-anchored
ignore entries `/logs/codex/`, `/logs/claude-code/`, and `/.task/session_audit/` over a
broad `logs/` or `.task/` rule. Ignore rules do not remove already tracked paths from
the Git index; index changes require a separate reviewed operation.

## Privacy

Require a regular, non-symlink source inside the repository. Reject traversal, every
symlink component, and sources inside `.task/session_audit`.

Enforce a size limit before retaining decoded content. Decode strict UTF-8 and parse
one JSON object per line. Treat blank, malformed, unsupported, raw/tool, and mixed
input conservatively. Never copy raw input as fallback.

Persist only source/event hashes, counts, timestamp bounds, fixed finding data, safe
paths, and explicit binding. Do not persist message bodies, reasoning, tool payloads,
images, or copied metadata values.

## Repair boundary

Use repair classes:

- `none` for clean inspection packets; they authorize no repair.
- `derived_metadata_only` for deterministic index reconstruction.
- `proposal_only` for source or semantic changes requiring governance.

Set `auto_repair_allowed=false` on every inspection packet. Set it to `true` only on
the derived index, whose class is `derived_metadata_only`; the sole allowed operation
is deterministic reconstruction of `.task/session_audit/index.json`.

Keep source edits, fabricated events, task/acceptance/ledger changes, verdict changes,
issue closure, detector weakening, and external actions proposal-only. Route an
approved semantic change through its owning skill and fresh independent validation.

## Index and failure semantics

Store the deterministic derived index at `.task/session_audit/index.json`. Build it
only from valid local packet files, sort by `audit_id`, hash each packet, derive
`index_id` from canonical content, and omit wall-clock time.

Write a privacy-safe `partial`, `quarantined`, or `failed` packet when bounded
inspection can do so. Return success after writing it so optional capture remains
fail-quiet.

Reject traversal, symlinks, unsafe output state, invalid identifiers, and packet
tampering as command errors. Never weaken these failures into raw fallback behavior.
