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
    CURRENT_STAGE_PROJECTION_VERSION,
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
    STAGE_COMPILER_PROTOCOL_VERSION,
    STAGE_PREPARATION_SCHEMA_VERSION,
    SUPPORTED_LEDGER_FORMAT_VERSIONS,
    SUPPORTED_STAGE_COMPILER_PROTOCOL_VERSIONS,
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
from .ledger.pending_finalization import (
    FinalizationConflictError,
    load_pending_finalization_conflicts,
    pending_finalizations_dir,
    pending_resolutions_dir,
    resolve_pending_finalization_conflict,
)
from .ledger.operation_contract import (
    build_durable_operation,
    build_no_durable_state_change_candidate,
    build_typed_operations_candidate,
)
from .ledger.no_change_contract import (
    absent_target_state_digest,
    build_no_change_evidence,
    build_unchanged_target_observation,
)
from .ledger.cli_parser import build_parser as _build_parser
from .ledger.initialization import cli_init_protocol as _cli_init_protocol
from .ledger.initialization import init_cycle as _init_cycle
from .ledger.reporting import render_markdown, summarize
from .ledger.repository import (
    append_event as _append_event,
    duplicate_event,
    read_all_cycle_events,
    read_events,
    read_events_raw,
    read_events_unlocked,
    read_current_expanded,
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
    "CURRENT_STAGE_PROJECTION_VERSION",
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
    "FinalizationConflictError",
    "LEDGER_FORMAT_VERSION",
    "MIN_FIELDS",
    "SENSITIVE_DURABLE_KEYS",
    "SENSITIVE_DURABLE_KEY_PARTS",
    "SHA256_PATTERN",
    "STAGE_STATUS_NORMALIZATION",
    "STAGE_COMPILER_PROTOCOL_VERSION",
    "STAGE_PREPARATION_SCHEMA_VERSION",
    "SUPPORTED_LEDGER_FORMAT_VERSIONS",
    "SUPPORTED_STAGE_COMPILER_PROTOCOL_VERSIONS",
    "TERMINAL_LATCH_KEY_VERSION",
    "TERMINAL_OBSERVATION_FIELDS",
    "VERDICT_AXES",
    "VERDICT_AXIS_STATUSES",
    "annotate_artifact_refs",
    "absent_target_state_digest",
    "build_durable_operation",
    "build_no_change_evidence",
    "build_no_durable_state_change_candidate",
    "build_typed_operations_candidate",
    "build_unchanged_target_observation",
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
    "load_pending_finalization_conflicts",
    "load_json_value",
    "main",
    "make_event_id",
    "normalize_final_candidate",
    "normalize_list",
    "normalize_stage_status",
    "now_iso",
    "prior_artifact_refs",
    "pending_finalizations_dir",
    "pending_resolutions_dir",
    "read_all_cycle_events",
    "read_current_expanded",
    "read_events",
    "read_events_raw",
    "read_events_unlocked",
    "read_initialization_metadata",
    "rel_path",
    "render_markdown",
    "resolve_pending_finalization_conflict",
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
    *,
    stage_compiler_protocol_version: int = 1,
) -> dict[str, Any]:
    return _write_current_unlocked(
        root,
        cycle_id,
        events,
        protocol_version=stage_compiler_protocol_version,
        atomic_writer=atomic_write_text,
    )


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
    stage_compiler_protocol_version: int | None = None,
    stage_preparation_schema_version: int | None = None,
) -> dict[str, Any]:
    return _init_cycle(
        root,
        cycle_id,
        task_id,
        reason,
        terminal_state,
        allow_missing_task_for_bootstrap,
        stage_compiler_protocol_version,
        stage_preparation_schema_version,
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
            _cli_init_protocol(
                args.root,
                args.cycle_id,
                args.stage_compiler_protocol_version,
            ),
            args.stage_preparation_schema_version,
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
    elif args.command == "verify-finalization":
        receipt_value = load_json_value(args.receipt_json)
        if receipt_value.get("kind") == FINALIZATION_POINTER_KIND and isinstance(receipt_value.get("receipt"), dict):
            receipt_value = receipt_value["receipt"]
        result = verify_finalization_receipt(args.root, args.cycle_id, receipt_value)
    elif args.command == "pending-finalizations":
        pending = load_pending_finalization_conflicts(args.root, args.cycle_id)
        result = {
            "cycle_id": args.cycle_id,
            "state_commit_status": "recovery_required" if pending else "clear",
            "pending_finalization_conflicts": pending,
        }
    else:
        result = resolve_pending_finalization_conflict(
            args.root,
            args.cycle_id,
            args.pending_conflict_id,
            disposition=args.disposition,
            resolution_evidence_id=args.resolution_evidence_id,
            resolution_evidence_digest=args.resolution_evidence_digest,
            resolution_evidence_ref=args.resolution_evidence_ref,
            resolution_rationale_id=args.resolution_rationale_id,
            committed_finalization_token=args.committed_finalization_token,
        )

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
