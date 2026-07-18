"""Immutable in-flight intent barrier for task-state transition apply."""
from __future__ import annotations

import json
from pathlib import Path
import stat
from typing import Any

from .storage import rel_path
from .transition_plan_contract import (
    canonical_bytes,
    load_transition_plan,
    owned_transition_file,
    publish_immutable,
    receipt_for_plan,
    receipt_status,
    regular_payload,
    sha256_bytes,
)


INTENT_SCHEMA_VERSION = 1
INTENT_KIND = "task_state_transition_apply_intent"


def intent_path(root: Path, plan_id: str) -> Path:
    return owned_transition_file(
        root,
        "transition_intents",
        f"{plan_id}.json",
        create_parent=False,
    )


def intent_for_plan(
    plan: dict[str, Any], plan_ref: str, plan_file_sha256: str
) -> dict[str, Any]:
    body = {
        "schema_version": INTENT_SCHEMA_VERSION,
        "intent_kind": INTENT_KIND,
        "plan_id": plan["plan_id"],
        "plan_ref": plan_ref,
        "plan_sha256": plan["plan_sha256"],
        "plan_file_sha256": plan_file_sha256,
        "created_at": plan["created_at"],
    }
    return {**body, "intent_content_sha256": sha256_bytes(canonical_bytes(body))}


def _load_intent(path: Path) -> dict[str, Any]:
    payload = regular_payload(path)
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid task-state transition intent: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError("Task-state transition intent must be a JSON object")
    supplied = value.get("intent_content_sha256")
    body = {key: item for key, item in value.items() if key != "intent_content_sha256"}
    if (
        value.get("schema_version") != INTENT_SCHEMA_VERSION
        or value.get("intent_kind") != INTENT_KIND
        or supplied != sha256_bytes(canonical_bytes(body))
    ):
        raise ValueError("Task-state transition intent integrity mismatch")
    if payload != canonical_bytes(value) + b"\n":
        raise ValueError("Task-state transition intent file bytes are not canonical")
    return value


def publish_transition_intent(
    root: Path,
    plan: dict[str, Any],
    plan_ref: str,
    plan_file_sha256: str,
) -> bool:
    path = owned_transition_file(
        root,
        "transition_intents",
        f"{plan['plan_id']}.json",
        create_parent=True,
    )
    intent = intent_for_plan(plan, plan_ref, plan_file_sha256)
    return publish_immutable(path, canonical_bytes(intent) + b"\n")


def assert_no_pending_transition_intents(
    root: Path, *, allowed_plan_id: str | None = None
) -> None:
    directory = root.resolve() / ".task" / "transition_intents"
    if not directory.exists() and not directory.is_symlink():
        return
    mode = directory.lstat().st_mode
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise ValueError("Task-state transition intent root must be a directory")
    for path in sorted(directory.iterdir()):
        if path.suffix != ".json" or path.is_symlink() or not path.is_file():
            raise ValueError("Unsafe task-state transition intent entry")
        intent = _load_intent(path)
        plan_path, plan, plan_file_sha256 = load_transition_plan(
            root, intent.get("plan_ref", "")
        )
        expected_intent = intent_for_plan(
            plan, rel_path(root, plan_path), plan_file_sha256
        )
        if intent != expected_intent:
            raise ValueError("Task-state transition intent plan binding mismatch")
        receipt_path = owned_transition_file(
            root,
            "transition_receipts",
            f"{plan['plan_id']}.json",
            create_parent=False,
        )
        receipt = receipt_for_plan(plan, rel_path(root, plan_path), plan_file_sha256)
        status, _digest = receipt_status(receipt_path, receipt)
        if status == "conflict":
            raise ValueError("Task-state transition apply receipt conflict")
        if status == "current":
            from .events import load_events_read_only
            from .transition_recovery import (
                committed_boundary_valid,
                matching_events,
            )

            events, _ledger_digest = load_events_read_only(root)
            exact, conflict = matching_events(events, plan)
            if conflict or not exact or not committed_boundary_valid(root, plan, events):
                raise ValueError(
                    "Task-state transition receipt lacks its committed event batch"
                )
            continue
        if plan["plan_id"] == allowed_plan_id:
            continue
        raise ValueError(
            "Pending task-state transition intent requires recovery before another "
            f"index write: {plan['plan_id']}"
        )
