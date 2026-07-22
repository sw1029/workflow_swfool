#!/usr/bin/env python3
"""Compatibility facade for the modular task-state index implementation."""
from __future__ import annotations

# Imports intentionally retain the historical module namespace for callers.
# ruff: noqa: F401

import argparse
import copy
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Iterator

from record_agent_work_log.integrity import inspect_agent_log_store
from .migration.api import (
    load_sealed_events_if_present,
    validate_current_suffix_event,
)
from .state.contracts import (
    INDEX_FORMAT_VERSION,
    INDEX_SCHEMA_VERSION,
    LIFECYCLE_STATUSES,
    NON_ACTIVE_STATUSES,
    PREFIXES,
    SUPPORTED_EVENT_KINDS,
    TASK_SCAN_PRESERVED_NONEXECUTABLE_STATUSES,
)
from .state.storage import (
    _THREAD_LOCKS,
    _THREAD_LOCKS_GUARD,
    _ensure_index_unlocked,
    _fsync_directory,
    _thread_lock,
    atomic_write_bytes,
    atomic_write_text,
    ensure_index,
    fcntl,
    id_stamp,
    immutable_snapshot_path,
    index_lock,
    jsonl_path,
    lock_path,
    markdown_path,
    now_iso,
    read_title,
    rel_path,
    sha256_file,
    slugify,
    task_dir,
)
from .state.events import (
    _append_events_unlocked,
    _current_projection_hint,
    _infer_legacy_event_kind,
    _lineage_identities,
    _load_events_for_audit_unlocked,
    _load_events_unlocked,
    _read_existing_events,
    _safe_malformed_reason,
    _version,
    append_event,
    find_existing_id,
    load_events,
    load_events_for_audit,
    load_events_read_only,
    make_id,
    merge_state,
    normalize_and_validate_event,
    parse_key_value,
    parse_links,
    path_records,
    stable_path_id,
    validate_event,
    versioned_event,
)
from .state.event_batch_validation import validate_completed_task_alias_batch
from .state.artifacts import (
    advice_pointer_file,
    discover_standard_artifacts,
    extract_advice_fields,
    extract_issue_fields,
    extract_schema_fields,
    extract_task_pack_fields,
    infer_advice_status,
    infer_issue_status,
    infer_miss_status,
    infer_schema_status,
    normalize_bounded_markdown_scalar,
    select_external_advice_scan_id,
)
from .state.render import (
    _generated_at_from_markdown,
    _markdown_projection_matches,
    _rebuild_markdown_unlocked as _rebuild_markdown_unlocked_impl,
    _render_markdown_payload,
    escape_md,
    rebuild_markdown as _rebuild_markdown_impl,
)
from .state.service import (
    link_item as _link_item_impl,
    scan_artifacts as _scan_artifacts_impl,
    upsert_item as _upsert_item_impl,
)
from .state.audit import (
    add_issue,
    audit_index as _audit_index_impl,
    issue_matches_focus,
    severity_counts,
    summarize_audit,
    write_audit_report,
)
from .state.transition_plan import (
    apply_transition_plan,
    build_transition_plan,
    load_request_json,
    publish_transition_plan,
    settle_transition_no_effect,
    verify_transition_plan,
)
from .state.transition_external_cli import (
    external_prepare_from_args,
    register_external_settlement_parser,
)
from .state.transition_compiler import (
    compile_transition_intent,
    load_transition_intent,
    verify_transition_compilation,
)


def _rebuild_markdown_unlocked(
    root: Path,
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return _rebuild_markdown_unlocked_impl(root, events, now_fn=now_iso)


def rebuild_markdown(root: Path) -> dict[str, Any]:
    return _rebuild_markdown_impl(root, now_fn=now_iso)


def upsert_item(
    root: Path,
    item_type: str,
    path_value: str,
    status: str,
    title: str | None = None,
    item_id: str | None = None,
    parent_id: str | None = None,
    links: list[dict[str, str]] | None = None,
    fields: dict[str, str] | None = None,
    note: str | None = None,
    replace_existing: bool | None = None,
    retire_alias_ids: list[str] | None = None,
) -> dict[str, Any]:
    return _upsert_item_impl(
        root,
        item_type,
        path_value,
        status,
        title=title,
        item_id=item_id,
        parent_id=parent_id,
        links=links,
        fields=fields,
        note=note,
        replace_existing=replace_existing,
        retire_alias_ids=retire_alias_ids,
        _now_fn=now_iso,
    )


def scan_artifacts(root: Path, *, dry_run: bool = False) -> dict[str, Any]:
    return _scan_artifacts_impl(root, dry_run=dry_run, _now_fn=now_iso)


def link_item(
    root: Path,
    source_id: str,
    links: list[dict[str, str]],
    note: str | None = None,
) -> dict[str, Any]:
    return _link_item_impl(root, source_id, links, note, _now_fn=now_iso)


def audit_index(root: Path) -> dict[str, Any]:
    return _audit_index_impl(root, now_fn=now_iso)


def cmd_init(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    result = rebuild_markdown(root)
    print(json.dumps({"initialized": True, "evidence_status": "not_evaluated", **result}, ensure_ascii=False, indent=2))


def cmd_scan(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    read_only = bool(getattr(args, "dry_run", False) or getattr(args, "check", False))
    result = scan_artifacts(root, dry_run=read_only)
    result["mode"] = "check" if getattr(args, "check", False) else result["mode"]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if getattr(args, "check", False) and result.get("would_change") else 0


def cmd_add(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    result = upsert_item(
        root,
        args.type,
        args.path,
        args.status,
        title=args.title,
        item_id=args.id,
        parent_id=args.parent_id,
        links=parse_links(args.link),
        fields=parse_key_value(args.field),
        note=args.note,
        replace_existing=args.replace,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_link(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    try:
        result = link_item(root, args.source_id, parse_links(args.link), args.note)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_rebuild(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    print(json.dumps({"ok": True, **rebuild_markdown(root)}, ensure_ascii=False, indent=2))


def cmd_audit(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    audit = audit_index(root)
    if args.write_report:
        report_path = write_audit_report(root, audit)
        result = upsert_item(
            root,
            "audit",
            rel_path(root, report_path),
            "logged" if audit["issue_count"] == 0 else "partial",
            title="ID Consistency Audit",
            note=f"ID audit found {audit['issue_count']} issue(s).",
        )
        audit["report_path"] = rel_path(root, report_path)
        audit["audit_id"] = result["id"]
    if args.summary_only:
        summary = summarize_audit(audit, args.focus_path or [])
        if audit.get("report_path"):
            summary["report_path"] = audit["report_path"]
            summary["audit_id"] = audit.get("audit_id")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(audit, ensure_ascii=False, indent=2))


def cmd_plan_transition(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    try:
        intent_value = getattr(args, "intent", None)
        if intent_value is not None:
            if not args.at:
                raise ValueError("--at is required with --intent for deterministic replay")
            compilation = compile_transition_intent(
                root,
                load_transition_intent(intent_value),
                at=args.at,
            )
            request = compilation["request"]
            verify_transition_compilation(root, compilation)
        else:
            request = load_request_json(args.request_json)
        plan = build_transition_plan(root, request, at=args.at)
        if intent_value is not None:
            verify_transition_compilation(root, compilation)
        if args.dry_run:
            result = {
                "result_kind": "task_state_transition_plan_result",
                "schema_version": 1,
                "status": "dry_run",
                "plan_id": plan["plan_id"],
                "plan_ref": None,
                "plan_sha256": plan["plan_sha256"],
                "plan_content_sha256": hashlib.sha256(
                    json.dumps(
                        plan,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    ).encode("utf-8")
                ).hexdigest(),
                "plan_file_sha256": hashlib.sha256(
                    (
                        json.dumps(
                            plan,
                            ensure_ascii=False,
                            separators=(",", ":"),
                            sort_keys=True,
                        )
                        + "\n"
                    ).encode("utf-8")
                ).hexdigest(),
                "would_change": True,
                "mutation_performed": False,
                "plan": plan,
            }
        else:
            result = publish_transition_plan(root, plan, args.output)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


def cmd_compile_transition(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    try:
        result = compile_transition_intent(
            root,
            load_transition_intent(args.intent),
            at=args.at,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


def cmd_apply_plan(args: argparse.Namespace) -> None:
    try:
        result = apply_transition_plan(
            Path(args.root),
            args.plan,
            external_prepare=external_prepare_from_args(args),
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


def cmd_verify_plan(args: argparse.Namespace) -> None:
    try:
        result = verify_transition_plan(Path(args.root), args.plan, phase=args.phase)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


def cmd_settle_plan_no_effect(args: argparse.Namespace) -> None:
    try:
        result = settle_transition_no_effect(
            Path(args.root), args.plan, at=args.at
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Maintain .task/index.jsonl and .task/index.md.")
    parser.add_argument("--root", default=".", help="Workspace root.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize and rebuild the task state index.")
    init_parser.set_defaults(func=cmd_init)

    scan_parser = subparsers.add_parser("scan", help="Index standard task artifacts in the workspace.")
    scan_mode = scan_parser.add_mutually_exclusive_group()
    scan_mode.add_argument("--dry-run", action="store_true", help="Report pending scan changes without creating or modifying task-state files.")
    scan_mode.add_argument("--check", action="store_true", help="Run the read-only scan and exit 1 when publication would change task-state files.")
    scan_parser.set_defaults(func=cmd_scan)

    add_parser = subparsers.add_parser("add", help="Append an upsert event for one artifact.")
    add_parser.add_argument("--type", required=True, help="Artifact type.")
    add_parser.add_argument("--path", required=True, help="Workspace-relative artifact path.")
    add_parser.add_argument("--status", required=True, choices=sorted(LIFECYCLE_STATUSES), help="Lifecycle status.")
    add_parser.add_argument("--title", help="Short title.")
    add_parser.add_argument("--id", help="Explicit artifact ID.")
    add_parser.add_argument("--parent-id", help="Parent artifact ID.")
    add_parser.add_argument("--link", action="append", default=[], help="Relationship in rel:id or rel=id form.")
    add_parser.add_argument("--field", action="append", default=[], help="Structured metadata as key=value.")
    add_parser.add_argument("--note", help="Concise factual note.")
    add_parser.add_argument("--replace", action="store_true", help="Create a new semantic artifact ID and supersede the active same-path record.")
    add_parser.set_defaults(func=cmd_add)

    link_parser = subparsers.add_parser("link", help="Append relationship links to an existing artifact.")
    link_parser.add_argument("--source-id", required=True, help="Source artifact ID.")
    link_parser.add_argument("--link", action="append", required=True, help="Relationship in rel:id or rel=id form.")
    link_parser.add_argument("--note", help="Concise factual note.")
    link_parser.set_defaults(func=cmd_link)

    rebuild_parser = subparsers.add_parser("rebuild", help="Regenerate .task/index.md from JSONL.")
    rebuild_parser.set_defaults(func=cmd_rebuild)

    audit_parser = subparsers.add_parser("audit", help="Audit global ID consistency; optionally write and index a report.")
    audit_parser.add_argument("--write-report", action="store_true", help="Write .task/id_audit/*.md and index it.")
    audit_parser.add_argument("--summary-only", action="store_true", help="Print compact counts and focused issues instead of the full historical issue list.")
    audit_parser.add_argument("--focus-path", action="append", default=[], help="Limit emitted issues to workspace-relative paths or IDs while preserving global counts.")
    audit_parser.set_defaults(func=cmd_audit)

    plan_parser = subparsers.add_parser(
        "plan-transition",
        help="Build and optionally publish an immutable task-state event batch.",
    )
    plan_input = plan_parser.add_mutually_exclusive_group(required=True)
    plan_input.add_argument(
        "--request-json",
        help="JSON text or path with schema_version, events, and optional render/updated_at.",
    )
    plan_input.add_argument(
        "--intent",
        help="Compact lifecycle intent JSON text, '-', or a regular input file.",
    )
    plan_parser.add_argument(
        "--output",
        help="Workspace-relative immutable plan path; defaults under .task/transition_plans/.",
    )
    plan_parser.add_argument("--at", help="Fixed RFC3339 event timestamp.")
    plan_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the complete plan without creating task-state files.",
    )
    plan_parser.set_defaults(func=cmd_plan_transition)

    compile_parser = subparsers.add_parser(
        "compile-transition",
        help="Compile a compact lifecycle intent into a canonical event request.",
    )
    compile_parser.add_argument(
        "--intent",
        required=True,
        help="Compact lifecycle intent JSON text, '-', or a regular input file.",
    )
    compile_parser.add_argument(
        "--at",
        required=True,
        help="Fixed RFC3339 timestamp for deterministic replay.",
    )
    compile_parser.set_defaults(func=cmd_compile_transition)

    apply_parser = subparsers.add_parser(
        "apply-plan", help="CAS-apply one immutable task-state transition plan."
    )
    apply_parser.add_argument("--plan", required=True, help="Workspace-relative plan path.")
    apply_parser.add_argument("--external-prepare-ref")
    apply_parser.add_argument("--external-prepare-sha256")
    apply_parser.set_defaults(func=cmd_apply_plan)

    verify_parser = subparsers.add_parser(
        "verify-plan", help="Read-only verify plan integrity, CAS readiness, or replay state."
    )
    verify_parser.add_argument("--plan", required=True, help="Workspace-relative plan path.")
    verify_parser.add_argument(
        "--phase",
        choices=("planning", "apply"),
        default="apply",
        help="Check planning-time before anchors or apply-time expected anchors.",
    )
    verify_parser.set_defaults(func=cmd_verify_plan)

    settle_parser = subparsers.add_parser(
        "settle-plan-no-effect",
        help="Publish an immutable no-effect receipt for one stale untouched plan.",
    )
    settle_parser.add_argument(
        "--plan", required=True, help="Workspace-relative immutable plan path."
    )
    settle_parser.add_argument("--at", help="Fixed receipt timestamp for deterministic runs.")
    settle_parser.set_defaults(func=cmd_settle_plan_no_effect)
    register_external_settlement_parser(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = args.func(args)
    return int(result or 0)


if __name__ == "__main__":
    sys.exit(main())
