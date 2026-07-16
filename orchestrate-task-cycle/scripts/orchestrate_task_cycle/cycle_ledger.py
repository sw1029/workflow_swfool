#!/usr/bin/env python3
"""Stable public facade for the modular cycle-ledger implementation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .ledger.artifact_evidence import annotate_artifact_refs, prior_artifact_refs
from .ledger.candidate_validation import (
    authoritative_final_from_axes,
    final_candidate_commit_material,
    normalize_final_candidate,
    validate_durable_payload_privacy,
    validate_durable_state_candidate,
)
from .ledger.constants import (
    CANONICAL_STEPS,
    CYCLE_ID_PATTERN,
    DEFAULT_STEPS,
    DURABLE_OPERATION_TYPES,
    DURABLE_STATE_MODES,
    EVENT_ID_PATTERN,
    FINALIZATION_POINTER_KIND,
    FINALIZATION_RECEIPT_KIND,
    FINALIZATION_SCHEMA_VERSION,
    FINALIZATION_SNAPSHOT_KIND,
    FINAL_CANDIDATE_KIND,
    LEDGER_FORMAT_VERSION,
    MIN_FIELDS,
    SENSITIVE_DURABLE_KEYS,
    SENSITIVE_DURABLE_KEY_PARTS,
    SHA256_PATTERN,
    STAGE_STATUS_NORMALIZATION,
    SUPPORTED_LEDGER_FORMAT_VERSIONS,
    TERMINAL_LATCH_KEY_VERSION,
    TERMINAL_OBSERVATION_FIELDS,
    VERDICT_AXES,
    VERDICT_AXIS_STATUSES,
)
from .ledger.event_model import (
    complete_event,
    default_cycle_id,
    make_event_id,
    normalize_stage_status,
    now_iso,
    request_fingerprint,
    truthy_delta,
    validate_event_envelope,
    validate_stored_event,
)
from .ledger.finalization import (
    finalize_candidate as _finalize_candidate,
    load_current_finalized_state,
    verify_finalization_receipt,
)
from .ledger.initialization import init_cycle as _init_cycle
from .ledger.reporting import render_markdown, summarize
from .ledger.repository import (
    append_event as _append_event,
    duplicate_event,
    read_all_cycle_events,
    read_events,
    read_events_unlocked,
    write_current as _write_current,
    write_current_unlocked as _write_current_unlocked,
)
from .ledger.support import (
    artifact_path,
    atomic_write_text,
    canonical_json_bytes,
    canonical_sha256,
    current_finalization_path,
    current_stage_path,
    cycle_dir,
    durable_append_json,
    file_sha256,
    finalization_snapshot_path,
    finalizations_dir,
    fsync_directory,
    immutable_write_bytes,
    initialization_path,
    ledger_lock,
    ledger_lock_path,
    ledger_path,
    load_json_value,
    normalize_list,
    read_initialization_metadata,
    rel_path,
    validate_cycle_id,
    validate_event_id,
)
from .ledger.terminal import (
    compact_terminal_observation,
    content_bound_material_delta,
    terminal_event_reference,
    terminal_latch_contract,
    terminal_latch_state,
    terminal_reopen_contract,
    verify_terminal_reopen_receipt,
)


__all__ = [
    "CANONICAL_STEPS",
    "CYCLE_ID_PATTERN",
    "DEFAULT_STEPS",
    "DURABLE_OPERATION_TYPES",
    "DURABLE_STATE_MODES",
    "EVENT_ID_PATTERN",
    "FINALIZATION_POINTER_KIND",
    "FINALIZATION_RECEIPT_KIND",
    "FINALIZATION_SCHEMA_VERSION",
    "FINALIZATION_SNAPSHOT_KIND",
    "FINAL_CANDIDATE_KIND",
    "LEDGER_FORMAT_VERSION",
    "MIN_FIELDS",
    "SENSITIVE_DURABLE_KEYS",
    "SENSITIVE_DURABLE_KEY_PARTS",
    "SHA256_PATTERN",
    "STAGE_STATUS_NORMALIZATION",
    "SUPPORTED_LEDGER_FORMAT_VERSIONS",
    "TERMINAL_LATCH_KEY_VERSION",
    "TERMINAL_OBSERVATION_FIELDS",
    "VERDICT_AXES",
    "VERDICT_AXIS_STATUSES",
    "annotate_artifact_refs",
    "append_event",
    "artifact_path",
    "atomic_write_text",
    "authoritative_final_from_axes",
    "canonical_json_bytes",
    "canonical_sha256",
    "compact_terminal_observation",
    "complete_event",
    "content_bound_material_delta",
    "current_finalization_path",
    "current_stage_path",
    "cycle_dir",
    "default_cycle_id",
    "duplicate_event",
    "durable_append_json",
    "file_sha256",
    "final_candidate_commit_material",
    "finalization_snapshot_path",
    "finalizations_dir",
    "finalize_candidate",
    "fsync_directory",
    "immutable_write_bytes",
    "init_cycle",
    "initialization_path",
    "ledger_lock",
    "ledger_lock_path",
    "ledger_path",
    "load_current_finalized_state",
    "load_json_value",
    "main",
    "make_event_id",
    "normalize_final_candidate",
    "normalize_list",
    "normalize_stage_status",
    "now_iso",
    "prior_artifact_refs",
    "read_all_cycle_events",
    "read_events",
    "read_events_unlocked",
    "read_initialization_metadata",
    "rel_path",
    "render_markdown",
    "request_fingerprint",
    "summarize",
    "terminal_event_reference",
    "terminal_latch_contract",
    "terminal_latch_state",
    "terminal_reopen_contract",
    "truthy_delta",
    "validate_cycle_id",
    "validate_durable_payload_privacy",
    "validate_durable_state_candidate",
    "validate_event_envelope",
    "validate_event_id",
    "validate_stored_event",
    "verify_finalization_receipt",
    "verify_terminal_reopen_receipt",
    "write_current",
    "write_current_unlocked",
]


def write_current_unlocked(
    root: Path,
    cycle_id: str,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    return _write_current_unlocked(root, cycle_id, events, atomic_writer=atomic_write_text)


def write_current(
    root: Path,
    cycle_id: str,
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return _write_current(root, cycle_id, events, atomic_writer=atomic_write_text)


def append_event(
    root: Path,
    cycle_id: str,
    event: dict[str, Any],
    allow_noncanonical_step: bool = False,
) -> dict[str, Any]:
    return _append_event(
        root,
        cycle_id,
        event,
        allow_noncanonical_step,
        atomic_writer=atomic_write_text,
        json_appender=durable_append_json,
    )


def init_cycle(
    root: Path,
    cycle_id: str | None,
    task_id: str | None,
    reason: str,
    terminal_state: dict[str, Any] | None = None,
    allow_missing_task_for_bootstrap: bool = False,
) -> dict[str, Any]:
    return _init_cycle(
        root,
        cycle_id,
        task_id,
        reason,
        terminal_state,
        allow_missing_task_for_bootstrap,
        atomic_writer=atomic_write_text,
        append_event=append_event,
    )


def finalize_candidate(root: Path, cycle_id: str, candidate: dict[str, Any]) -> dict[str, Any]:
    return _finalize_candidate(
        root,
        cycle_id,
        candidate,
        atomic_writer=atomic_write_text,
        immutable_writer=immutable_write_bytes,
    )


def _append_cli_event(args: argparse.Namespace) -> dict[str, Any]:
    event = load_json_value(args.event_json)
    for attr, key in (
        ("step", "step"),
        ("status", "status"),
        ("reason", "reason"),
        ("task_id", "task_id"),
        ("completed_task_id", "completed_task_id"),
        ("next_task_id", "next_task_id"),
        ("validation_verdict", "validation_verdict"),
        ("progress_verdict", "progress_verdict"),
        ("task_pack_id", "task_pack_id"),
        ("task_pack_item_id", "task_pack_item_id"),
        ("task_pack_path", "task_pack_path"),
        ("task_pack_status", "task_pack_status"),
        ("selected_task_source", "selected_task_source"),
        ("promoted_item_id", "promoted_item_id"),
        ("completed_item_id", "completed_item_id"),
        ("blocker_signature", "blocker_signature"),
        ("input_delta_gate", "input_delta_gate"),
        ("terminal_blocker", "terminal_blocker"),
        ("authority_policy", "authority_policy"),
        ("authority_policy_source", "authority_policy_source"),
    ):
        value = getattr(args, attr)
        if value is not None:
            event[key] = value
    if args.changed_file:
        event["changed_files"] = normalize_list(event.get("changed_files"), args.changed_file)
    if args.artifact:
        event["artifacts"] = normalize_list(event.get("artifacts"), args.artifact)
    if args.blocker:
        event["blockers"] = normalize_list(event.get("blockers"), args.blocker)
    return append_event(root=args.root, cycle_id=args.cycle_id, event=event, allow_noncanonical_step=args.allow_noncanonical_step)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Maintain .task/cycle/<cycle-id> stage ledger artifacts.")
    parser.add_argument("--root", default=".", help="Workspace root.")
    sub = parser.add_subparsers(dest="command", required=True)

    init_p = sub.add_parser("init", help="Initialize a cycle ledger.")
    init_p.add_argument("--cycle-id")
    init_p.add_argument("--task-id")
    init_p.add_argument("--allow-missing-task-for-bootstrap", action="store_true")
    init_p.add_argument("--reason", default="cycle ledger initialized")
    init_p.add_argument("--terminal-state-json", help="Optional terminal state used to suppress an unchanged full-cycle restart.")

    append_p = sub.add_parser("append", help="Append a stage event.")
    append_p.add_argument("--cycle-id", required=True)
    append_p.add_argument("--event-json", help="JSON object, JSON file path, or '-' for stdin.")
    append_p.add_argument("--step")
    append_p.add_argument("--status")
    append_p.add_argument("--reason")
    append_p.add_argument("--task-id")
    append_p.add_argument("--completed-task-id")
    append_p.add_argument("--next-task-id")
    append_p.add_argument("--changed-file", action="append", default=[])
    append_p.add_argument("--artifact", action="append", default=[])
    append_p.add_argument("--blocker", action="append", default=[])
    append_p.add_argument("--validation-verdict")
    append_p.add_argument("--progress-verdict")
    append_p.add_argument("--task-pack-id")
    append_p.add_argument("--task-pack-item-id")
    append_p.add_argument("--task-pack-path")
    append_p.add_argument("--task-pack-status")
    append_p.add_argument("--selected-task-source")
    append_p.add_argument("--promoted-item-id")
    append_p.add_argument("--completed-item-id")
    append_p.add_argument("--blocker-signature")
    append_p.add_argument("--input-delta-gate")
    append_p.add_argument("--terminal-blocker")
    append_p.add_argument("--authority-policy")
    append_p.add_argument("--authority-policy-source")
    append_p.add_argument(
        "--allow-noncanonical-step",
        action="store_true",
        help="Allow a noncanonical step and mark it as malformed/noncanonical evidence.",
    )

    render_p = sub.add_parser("render", help="Render a ledger summary.")
    render_p.add_argument("--cycle-id", required=True)
    render_p.add_argument("--format", choices=("json", "markdown"), default="markdown")
    render_p.add_argument("--write-dashboard", action="store_true")

    current_p = sub.add_parser("current", help="Refresh and print current_stage.json.")
    current_p.add_argument("--cycle-id", required=True)

    finalize_p = sub.add_parser("finalize", help="Atomically publish one validated final candidate.")
    finalize_p.add_argument("--cycle-id", required=True)
    finalize_p.add_argument("--candidate-json", required=True, help="JSON object, JSON file path, or '-' for stdin.")

    verify_p = sub.add_parser(
        "verify-finalization",
        help="Verify a finalization receipt against its immutable snapshot and current pointer.",
    )
    verify_p.add_argument("--cycle-id", required=True)
    verify_p.add_argument(
        "--receipt-json",
        required=True,
        help="Receipt or current-pointer JSON object, file path, or '-' for stdin.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    args.root = Path(args.root).resolve()
    if args.command == "init":
        result = init_cycle(
            args.root,
            args.cycle_id,
            args.task_id,
            args.reason,
            load_json_value(args.terminal_state_json),
            args.allow_missing_task_for_bootstrap,
        )
    elif args.command == "append":
        result = _append_cli_event(args)
    elif args.command == "render":
        summary = summarize(read_events(args.root, args.cycle_id))
        if args.write_dashboard:
            dashboard = cycle_dir(args.root, args.cycle_id) / "dashboard.md"
            atomic_write_text(dashboard, render_markdown(summary))
            summary["dashboard_path"] = rel_path(args.root, dashboard)
        if args.format == "markdown":
            sys.stdout.write(render_markdown(summary))
            return 0
        result = summary
    elif args.command == "current":
        result = write_current(args.root, args.cycle_id)
    elif args.command == "finalize":
        result = finalize_candidate(args.root, args.cycle_id, load_json_value(args.candidate_json))
    else:
        receipt_value = load_json_value(args.receipt_json)
        if receipt_value.get("kind") == FINALIZATION_POINTER_KIND and isinstance(receipt_value.get("receipt"), dict):
            receipt_value = receipt_value["receipt"]
        result = verify_finalization_receipt(args.root, args.cycle_id, receipt_value)

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
