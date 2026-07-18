"""Immutable in-flight intent barrier for external-advice intake apply."""
from __future__ import annotations

import json
from pathlib import Path
import stat
from typing import Any

from .common import rel_path
from .intake_plan_contract import (
    canonical_intake_artifact_path,
    canonical_bytes,
    load_intake_plan,
    receipt_for_plan,
    receipt_status,
    regular_payload,
    sha256_bytes,
)
from .storage import advice_root, publish_immutable


INTENT_SCHEMA_VERSION = 1
INTENT_KIND = "external_advice_intake_apply_intent"


def intent_path(root: Path, plan_id: str) -> Path:
    return canonical_intake_artifact_path(root, plan_id, "intent")


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


def _load_intent(root: Path, path: Path) -> dict[str, Any]:
    payload = regular_payload(root, path)
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Invalid external-advice intake intent: {path}") from exc
    if not isinstance(value, dict):
        raise SystemExit("External-advice intake intent must be a JSON object")
    supplied = value.get("intent_content_sha256")
    body = {key: item for key, item in value.items() if key != "intent_content_sha256"}
    if (
        value.get("schema_version") != INTENT_SCHEMA_VERSION
        or value.get("intent_kind") != INTENT_KIND
        or supplied != sha256_bytes(canonical_bytes(body))
    ):
        raise SystemExit("External-advice intake intent integrity mismatch")
    if payload != canonical_bytes(value) + b"\n":
        raise SystemExit("External-advice intake intent file bytes are not canonical")
    return value


def publish_intake_intent(
    root: Path,
    plan: dict[str, Any],
    plan_ref: str,
    plan_file_sha256: str,
) -> bool:
    path = canonical_intake_artifact_path(
        root, str(plan["plan_id"]), "intent", ensure_parent=True
    )
    parent = path.parent
    if parent.exists() or parent.is_symlink():
        mode = parent.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise SystemExit("External-advice intake journal root must be a directory")
    intent = intent_for_plan(plan, plan_ref, plan_file_sha256)
    existed = path.exists() or path.is_symlink()
    publish_immutable(root, path, canonical_bytes(intent) + b"\n")
    return not existed


def intake_intent_status(
    root: Path,
    plan: dict[str, Any],
    plan_ref: str,
    plan_file_sha256: str,
) -> tuple[str, str | None]:
    """Return missing, current, or conflict for this plan's exact intent."""

    path = intent_path(root, str(plan["plan_id"]))
    if not path.exists() and not path.is_symlink():
        return "missing", None
    payload = regular_payload(root, path)
    digest = sha256_bytes(payload)
    try:
        observed = _load_intent(root, path)
    except SystemExit:
        return "conflict", digest
    expected = intent_for_plan(plan, plan_ref, plan_file_sha256)
    return ("current" if observed == expected else "conflict"), digest


def assert_no_pending_intake_intents(
    root: Path, *, allowed_plan_id: str | None = None
) -> None:
    directory = advice_root(root) / "journal" / "intake"
    if not directory.exists() and not directory.is_symlink():
        return
    mode = directory.lstat().st_mode
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise SystemExit("External-advice intake journal root must be a directory")
    for path in sorted(directory.glob("*.intent.json")):
        if path.is_symlink() or not path.is_file():
            raise SystemExit("Unsafe external-advice intake intent entry")
        intent = _load_intent(root, path)
        plan_path, plan, plan_file_sha256 = load_intake_plan(
            root, intent.get("plan_ref", "")
        )
        expected_intent = intent_for_plan(
            plan, rel_path(root, plan_path), plan_file_sha256
        )
        if intent != expected_intent:
            raise SystemExit("External-advice intake intent plan binding mismatch")
        receipt_path = canonical_intake_artifact_path(
            root, str(plan["plan_id"]), "receipt"
        )
        receipt = receipt_for_plan(plan, rel_path(root, plan_path), plan_file_sha256)
        status, _digest = receipt_status(root, receipt_path, receipt)
        if status == "conflict":
            raise SystemExit("External-advice intake intent has a conflicting receipt")
        if status == "current" or plan["plan_id"] == allowed_plan_id:
            continue
        raise SystemExit(
            "Pending external-advice intake intent requires recovery before another "
            f"registry write: {plan['plan_id']}"
        )
