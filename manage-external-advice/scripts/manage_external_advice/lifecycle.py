"""Advice lifecycle transitions and durable retirement evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
from typing import Any

from record_agent_work_log.write import write_log

from .application_publication import publish_mark_applied
from .common import now_iso, rel_path, sha256_file, stamp
from .directive_dispositions import validate_directive_dispositions
from .storage import (
    advice_root,
    append_event,
    load_events,
    merge_state,
    rebuild_index,
)


def find_item(root: Path, advice_id: str) -> dict[str, Any]:
    state = merge_state(load_events(root))
    if advice_id in state:
        return state[advice_id]
    matches = [
        item for item in state.values() if str(item.get("path", "")).endswith(advice_id)
    ]
    if len(matches) == 1:
        return matches[0]
    raise SystemExit(f"Advice not found: {advice_id}")


def move_item(root: Path, item: dict[str, Any], target_dir: str) -> str:
    current = root / str(item.get("path", ""))
    if not current.is_file():
        raise SystemExit(f"Advice file missing: {current}")
    destination = advice_root(root) / target_dir / current.name
    if destination.exists():
        destination = advice_root(root) / target_dir / f"{stamp()}-{current.name}"
    shutil.move(str(current), str(destination))
    return rel_path(root, destination)


def update_advice_status(path: Path, status: str) -> None:
    if not path.is_file() or path.suffix.lower() != ".md":
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    updated = re.sub(
        r"^- status:\s*.*$", f"- status: {status}", text, count=1, flags=re.MULTILINE
    )
    if updated != text:
        path.write_text(updated, encoding="utf-8")


def write_past_advice_log(
    root: Path,
    item: dict[str, Any],
    evidence: str,
    note: str,
    *,
    operation_digest: str | None = None,
) -> str:
    advice_id = str(item.get("advice_id") or "unknown-advice")
    title = str(item.get("title") or advice_id)
    previous_path = str(item.get("path") or "unknown")
    raw_source_path = str(item.get("raw_source_path") or "unknown")
    operation_note = (
        " This is prepared evidence and becomes authoritative only when "
        ".agent_advice/index.jsonl contains the matching committed "
        f"mark_applied operation {operation_digest}."
        if operation_digest
        else ""
    )
    tags = ["past_advice", advice_id]
    if operation_digest:
        tags.append(f"advice-operation:{operation_digest}")
    result = write_log(
        argparse.Namespace(
            root=str(root),
            title=f"past_advice: {title}",
            status="informational",
            intent=f"Record durable retirement of external advice {advice_id}.",
            work=(
                f"Applied or retired advice from {previous_path}; "
                f"raw source reference: {raw_source_path}."
            ),
            result=f"Advice lifecycle evidence: {evidence}.{operation_note}",
            shortcomings=note or "No additional shortcomings recorded.",
            agent_note=[
                "Created by manage-external-advice through the integrity-bound work-log writer.",
                *(
                    [
                        "Canonical retirement authority is the matching operation event in .agent_advice/index.jsonl."
                    ]
                    if operation_digest
                    else []
                ),
            ],
            command=[],
            changed_file=[previous_path],
            follow_up=[],
            tag=tags,
            retention_class="governance-history",
            archive_reference=None,
            retention_exclusion_reason=None,
            sensitivity="internal",
            actor="manage-external-advice",
        )
    )
    return rel_path(root, Path(result["path"]))


def cmd_mark_applied(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    item = find_item(root, args.advice_id)
    dispositions = validate_directive_dispositions(
        root,
        item,
        args.directive_dispositions_json,
    )
    result = publish_mark_applied(
        root,
        item,
        dispositions,
        args.evidence,
        args.note,
        write_past_advice_log,
    )
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


def cmd_reject(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    item = find_item(root, args.advice_id)
    new_path = move_item(root, item, "rejected")
    update_advice_status(root / new_path, "rejected")
    event = {
        "event": "reject",
        "advice_id": item["advice_id"],
        "type": "external_advice",
        "status": "rejected",
        "title": item.get("title"),
        "path": new_path,
        "raw_source_path": item.get("raw_source_path"),
        "rejection_reason": args.reason,
        "updated_at": now_iso(),
        "content_sha256": sha256_file(root / new_path),
    }
    append_event(root, event)
    result = rebuild_index(root)
    print(
        json.dumps(
            {"status": "ok", "event": event, **result},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


def cmd_defer(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    item = find_item(root, args.advice_id)
    new_path = move_item(root, item, "deferred")
    update_advice_status(root / new_path, "deferred")
    event = {
        "event": "defer",
        "advice_id": item["advice_id"],
        "type": "external_advice",
        "status": "deferred",
        "title": item.get("title"),
        "path": new_path,
        "raw_source_path": item.get("raw_source_path"),
        "deferral_reason": args.reason,
        "updated_at": now_iso(),
        "content_sha256": sha256_file(root / new_path),
    }
    append_event(root, event)
    result = rebuild_index(root)
    print(
        json.dumps(
            {"status": "ok", "event": event, **result},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
