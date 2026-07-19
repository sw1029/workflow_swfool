"""Normalize bounded selection-publication plans and target paths."""

from __future__ import annotations

import base64
import re
import stat
from pathlib import Path
from typing import Any

from .selection_publication_store import _sha256_bytes, _sha256_file


SCHEMA_VERSION = 1
SHA256 = re.compile(r"^[0-9a-f]{64}$")
OPAQUE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MAX_TARGET_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
OWNER_COMMITTED_PROJECTION_ROLES = {
    "past_task_archive",
    "agent_log_index_jsonl",
    "task_pack_state",
    "task_pack_render",
}
ROLE_PRIORITY = {
    "past_task_archive": 10,
    "agent_log_index_jsonl": 15,
    "task_pack_state": 20,
    "task_pack_render": 30,
    "advice_index_jsonl": 40,
    "advice_index_markdown": 50,
    "task_index_jsonl": 60,
    "task_index_markdown": 70,
    "task_alias": 100,
}


def _role_path_allowed(role: str, relative: Path) -> bool:
    value = relative.as_posix()
    if role == "task_alias":
        return value == "task.md"
    if role == "past_task_archive":
        return value.startswith(".agent_log/") and relative.suffix == ".md"
    if role == "agent_log_index_jsonl":
        return value == ".agent_log/index.jsonl"
    if role == "task_index_jsonl":
        return value == ".task/index.jsonl"
    if role == "task_index_markdown":
        return value == ".task/index.md"
    if role == "advice_index_jsonl":
        return value == ".agent_advice/index.jsonl"
    if role == "advice_index_markdown":
        return value == ".agent_advice/index.md"
    if role in {"task_pack_state", "task_pack_render"}:
        return relative.parent.as_posix() == ".task/task_pack" and relative.suffix == (
            ".json" if role == "task_pack_state" else ".md"
        )
    return False


def _target_path(root: Path, role: str, reference: str) -> Path:
    raw = Path(reference)
    if (
        not reference
        or raw.is_absolute()
        or ".." in raw.parts
        or not _role_path_allowed(role, raw)
    ):
        raise ValueError(
            f"selection-publication target is not allowed for role {role!r}"
        )
    current = root
    for part in raw.parts:
        current /= part
        if current.is_symlink():
            raise ValueError("selection-publication targets cannot traverse symlinks")
    resolved = current.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("selection-publication target escapes the workspace") from exc
    if resolved.exists() and not stat.S_ISREG(resolved.lstat().st_mode):
        raise ValueError(
            "selection-publication target must be a regular file or absent"
        )
    return resolved


def _decode_payload(target: dict[str, Any]) -> bytes:
    encoded = target.get("after_payload_b64")
    if not isinstance(encoded, str) or not encoded:
        raise ValueError("selection-publication target payload is missing")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError(
            "selection-publication target payload is invalid base64"
        ) from exc
    if len(payload) > MAX_TARGET_BYTES:
        raise ValueError("selection-publication target payload exceeds the size limit")
    return payload


def _normalize_plan(
    root: Path,
    raw: dict[str, Any],
    *,
    require_current_owner_projections: bool = True,
) -> dict[str, Any]:
    helper_owned = {"transaction_id", "predecessor_transaction_id"} & set(raw)
    if helper_owned:
        raise ValueError(
            "selection-publication transaction lineage fields are helper-owned"
        )
    if (
        raw.get("schema_version") != SCHEMA_VERSION
        or raw.get("kind") != "selection_publication_plan"
    ):
        raise ValueError("selection-publication plan contract is invalid")
    selection_id = str(raw.get("selection_id") or "")
    decision_id = str(raw.get("source_decision_id") or "")
    decision_sha = str(raw.get("source_decision_sha256") or "")
    if not OPAQUE_ID.fullmatch(selection_id) or not OPAQUE_ID.fullmatch(decision_id):
        raise ValueError("selection-publication plan requires bounded opaque ids")
    if not SHA256.fullmatch(decision_sha):
        raise ValueError("selection-publication source decision digest is invalid")
    raw_targets = raw.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        raise ValueError("selection-publication plan requires targets")
    roles: set[str] = set()
    references: set[str] = set()
    total = 0
    targets: list[dict[str, Any]] = []
    for raw_target in raw_targets:
        if not isinstance(raw_target, dict):
            raise ValueError("selection-publication target must be an object")
        role = str(raw_target.get("role") or "")
        reference = str(raw_target.get("target_ref") or "")
        if role in roles or reference in references:
            raise ValueError(
                "selection-publication target roles and paths must be unique"
            )
        _target_path(root, role, reference)
        before = raw_target.get("before_sha256")
        if before is not None and not SHA256.fullmatch(str(before)):
            raise ValueError("selection-publication target before digest is invalid")
        payload = _decode_payload(raw_target)
        total += len(payload)
        after_sha = _sha256_bytes(payload)
        if role in OWNER_COMMITTED_PROJECTION_ROLES:
            if before != after_sha:
                raise ValueError(
                    f"selection-publication role {role!r} must bind an owner-committed unchanged projection"
                )
            if require_current_owner_projections:
                current_sha = _sha256_file(_target_path(root, role, reference))
                if current_sha is None or current_sha != after_sha:
                    raise ValueError(
                        f"selection-publication role {role!r} must bind an owner-committed unchanged projection"
                    )
        targets.append(
            {
                "role": role,
                "target_ref": reference,
                "before_sha256": before,
                "after_sha256": after_sha,
                "after_payload_b64": base64.b64encode(payload).decode("ascii"),
            }
        )
        roles.add(role)
        references.add(reference)
    if "task_alias" not in roles:
        raise ValueError(
            "selection-publication requires the authoritative task_alias target"
        )
    archive_pair = {"past_task_archive", "agent_log_index_jsonl"}
    if bool(roles & archive_pair) and not archive_pair <= roles:
        raise ValueError(
            "past-task archive and .agent_log/index.jsonl projection must be published together"
        )
    if total > MAX_TOTAL_BYTES:
        raise ValueError("selection-publication total payload exceeds the size limit")
    targets.sort(key=lambda item: (ROLE_PRIORITY[item["role"]], item["target_ref"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "selection_publication_prepare",
        "selection_id": selection_id,
        "source_decision_id": decision_id,
        "source_decision_sha256": decision_sha,
        "targets": targets,
    }
