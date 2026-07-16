#!/usr/bin/env python3
"""Compatibility facade for the modular task-state migration implementation."""
from __future__ import annotations

# Imports intentionally retain the historical module namespace for callers.
# ruff: noqa: F401

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Iterator

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from task_state_lib.migration.contracts import (  # noqa: E402
    ANCHOR_KIND,
    ARTIFACT_TYPES,
    CLASSIFICATIONS,
    EVENT_KINDS,
    INDEX_FORMAT_VERSION,
    INDEX_SCHEMA_VERSION,
    INFER_TOKEN,
    LIFECYCLE_STATUSES,
    MANIFEST_SCHEMA_VERSION,
    MAPPING_SCHEMA_VERSION,
    MIGRATION_EVENT_FIELD,
    MISSING_TOKEN,
    NON_ACTIVE_STATUSES,
    PLAN_SCHEMA_VERSION,
    PROJECTION_IMPACTS,
    RECEIPT_SCHEMA_VERSION,
    SEAL_KIND,
    TOOL_VERSION,
    MigrationError,
)
from task_state_lib.migration.storage import (  # noqa: E402
    _THREAD_LOCKS,
    _THREAD_LOCKS_GUARD,
    _atomic_json,
    _atomic_write,
    _canonical_bytes,
    _event_bytes,
    _fsync_dir,
    _index_lock,
    _index_path,
    _now,
    _read_json,
    _root_identity,
    _safe_ref,
    _sha256,
    _sha_file,
    _thread_lock,
    _validate_plan_anchors,
)
from task_state_lib.migration.mapping import (  # noqa: E402
    _infer_event,
    _mapping_entry,
    _normalize_links,
    _physical_lines,
    _preserve_legacy_token,
    _relative,
    _resolution_map,
    _token,
    _validate_current_event,
    _validate_mapping,
    validate_current_suffix_event,
    writer_sparse_upsert_kind,
)
from task_state_lib.migration.classification import (  # noqa: E402
    _bind_quarantine_corrections,
    _broken_links,
    _classify_rows,
    _correction_identity,
    _make_corrections,
    _manifest_payload,
    _merge_state,
    _normalize_legacy,
    _strict_reader_probe,
    _validate_quarantine_correction_bindings,
    _versioned,
)
from task_state_lib.migration.plan import (  # noqa: E402
    _plan_manifest,
    _validate_plan_contract,
    build_plan,
    inspect_store,
)
from task_state_lib.migration.transaction import (  # noqa: E402
    _anchor_event,
    _append_fsync,
    _apply_locked,
    _committed_for_plan,
    _committed_journal_payload,
    _completion_marker_payload,
    _crash,
    _find_anchor_lines,
    _matching_plan_anchor,
    _receipt_payload,
    _render_markdown,
    _stage_sidecars,
    _update_journal,
    _validate_journal_base,
    _validate_partial_tail_ownership,
    apply_plan as _apply_plan_impl,
    recover_transaction as _recover_transaction_impl,
)
from task_state_lib.migration.validation import (  # noqa: E402
    _current_projection,
    _forward_complete_anchored,
    _migration_boundary_projection,
    _normalized_events_from_plan,
    _validate_receipt_graph,
    load_sealed_events_if_present,
    validate_migration,
)


def apply_plan(
    root: Path,
    plan_path: Path,
    expected_plan_sha: str,
    expected_index_sha: str,
    *,
    dry_run: bool = False,
    recovery_status: str = "not_required",
) -> dict[str, Any]:
    return _apply_plan_impl(
        root,
        plan_path,
        expected_plan_sha,
        expected_index_sha,
        dry_run=dry_run,
        recovery_status=recovery_status,
        _index_lock_fn=_index_lock,
    )


def recover_transaction(root: Path, transaction_id: str) -> dict[str, Any]:
    return _recover_transaction_impl(
        root,
        transaction_id,
        _index_lock_fn=_index_lock,
    )


def _write_plan(path: Path, plan: dict[str, Any], root: Path) -> None:
    resolved = path.resolve()
    task_root = (root.resolve() / ".task").resolve()
    try:
        resolved.relative_to(task_root)
    except ValueError:
        pass
    else:
        raise MigrationError("Plan output must remain outside canonical .task state until apply")
    _atomic_write(resolved, _canonical_bytes(plan))


def _cmd_inspect(args: argparse.Namespace) -> None:
    print(json.dumps(inspect_store(Path(args.root)), ensure_ascii=False, indent=2, sort_keys=True))


def _cmd_plan(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    plan = build_plan(
        root, args.expected_index_sha256, args.current_task_id, args.current_task_path,
        args.current_task_sha256, args.current_pack_id, args.current_pack_path,
        args.current_pack_sha256, Path(args.mapping_manifest),
    )
    _write_plan(Path(args.output_plan), plan, root)
    print(json.dumps({
        "planned": True, "mutation_performed_on_canonical_index": False,
        "plan": str(Path(args.output_plan).resolve()),
        "plan_sha256": _sha_file(Path(args.output_plan).resolve()),
        "migration_id": plan["migration_id"],
        "classification_counts": plan["classification_counts"],
        "unclassified_count": plan["unclassified_count"],
        "projection": plan["projection"],
        "expected_after_index_sha256": plan["expected_after_index_sha256"],
    }, ensure_ascii=False, indent=2, sort_keys=True))


def _cmd_apply(args: argparse.Namespace) -> None:
    result = apply_plan(
        Path(args.root), Path(args.plan), args.expected_plan_sha256,
        args.expected_index_sha256, dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


def _cmd_validate(args: argparse.Namespace) -> None:
    result = validate_migration(Path(args.root), Path(args.receipt), args)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


def _cmd_recover(args: argparse.Namespace) -> None:
    result = recover_transaction(Path(args.root), args.transaction_id)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect, plan, apply, validate, and recover sealed task-state legacy migrations."
    )
    parser.add_argument("--root", default=".", help="Workspace root.")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect_parser = commands.add_parser("inspect", help="Read-only exact token and row inventory.")
    inspect_parser.set_defaults(func=_cmd_inspect)

    migrate = commands.add_parser("migrate", help="Manage a sealed legacy-prefix migration.")
    migrate_commands = migrate.add_subparsers(dest="migrate_command", required=True)
    plan_parser = migrate_commands.add_parser("plan", help="Create a deterministic zero-canonical-mutation plan.")
    plan_parser.add_argument("--expected-index-sha256", required=True)
    plan_parser.add_argument("--current-task-id", required=True)
    plan_parser.add_argument("--current-task-path", required=True)
    plan_parser.add_argument("--current-task-sha256", required=True)
    plan_parser.add_argument("--current-pack-id", required=True)
    plan_parser.add_argument("--current-pack-path", required=True)
    plan_parser.add_argument("--current-pack-sha256", required=True)
    plan_parser.add_argument("--mapping-manifest", required=True)
    plan_parser.add_argument("--output-plan", required=True)
    plan_parser.set_defaults(func=_cmd_plan)

    apply_parser = migrate_commands.add_parser("apply", help="Apply one expected-hash-bound locked transaction.")
    apply_parser.add_argument("--plan", required=True)
    apply_parser.add_argument("--expected-plan-sha256", required=True)
    apply_parser.add_argument("--expected-index-sha256", required=True)
    apply_parser.add_argument("--dry-run", action="store_true")
    apply_parser.set_defaults(func=_cmd_apply)

    validate_parser = migrate_commands.add_parser("validate", help="Validate receipt, seal, prefix, projection, and appendability.")
    validate_parser.add_argument("--receipt", required=True)
    validate_parser.add_argument("--require-current-projection-evaluated", action="store_true")
    validate_parser.add_argument("--require-single-active-task", action="store_true")
    validate_parser.add_argument("--require-single-active-pack", action="store_true")
    validate_parser.add_argument("--require-appendable", action="store_true")
    validate_parser.set_defaults(func=_cmd_validate)

    recover_parser = migrate_commands.add_parser("recover", help="Recover or forward-complete one journaled transaction.")
    recover_parser.add_argument("--transaction-id", required=True)
    recover_parser.set_defaults(func=_cmd_recover)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except (MigrationError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True), file=os.sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
