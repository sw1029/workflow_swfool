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
- `cross_source_mismatch` only after an independent canonical comparison.
- `canonical_fact` only from the canonical owner.

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
non-authority flags, capture state, and binding state.

Never produce from this packet alone:

- `pass`, `advanced`, or `complete_verified`
- completed/failed task state
- authority grant
- resolved blocker or closed issue
- task-pack promotion
- commit, push, deployment, or external message

## Stop-hook compatibility

Consume `logs/<tool>/<session-id>.jsonl` only after the existing stop-hook logger has
finished writing it. Keep the logger's fail-open session behavior separate from this
auditor's strict parser: a recognized slim projection may become `complete`, while a
verbatim fallback containing raw, tool, reasoning, metadata, mixed, or malformed lines
must be quarantined instead of being silently treated as a clean projection.

Do not add semantic comparison or repair work to the stop hook. Run inspection and any
cross-source review asynchronously so logging latency or failure cannot alter the agent
session. The source log still contains conversation text and remains sensitive even
though the audit packet is body-free; retention, access control, and deletion policy for
`logs/` are separate operational controls.

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
