"""Render selected-successor task-state transitions from exact source bindings."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import re
import stat
from typing import Any

from .events import load_events_read_only, merge_state
from .transition_plan import build_transition_plan, publish_transition_plan
from .transition_plan_contract import canonical_bytes, sha256_bytes, workspace_path


TASK_ID_LINE = re.compile(
    r"(?m)^\s*-\s*Task ID:\s*(?:`([^`\r\n]+)`|([^\s`\r\n]+))\s*$"
)
OPAQUE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")

# A decision receipt is a compact, body-free chain of bindings. The selected task
# source shares the publication owner's 32 MiB task-payload ceiling.
MAX_SELECTION_DECISION_BYTES = 256 * 1024
MAX_SELECTED_SUCCESSOR_TASK_BYTES = 32 * 1024 * 1024
_READ_CHUNK_BYTES = 1024 * 1024


def _binding(value: Any, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"ref", "sha256"}:
        raise ValueError(f"{label} requires exactly ref and sha256")
    ref, digest = value.get("ref"), value.get("sha256")
    if (
        not isinstance(ref, str)
        or not ref
        or not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError(f"{label} binding is invalid")
    return {"ref": ref, "sha256": digest}


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )


def _identity(descriptor: int) -> tuple[int, int]:
    observed = os.fstat(descriptor)
    if not stat.S_ISDIR(observed.st_mode):
        raise ValueError("Selected-successor input ancestor is not a directory")
    return observed.st_dev, observed.st_ino


def _signature(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _verify_directory_chain(
    root: Path, parts: tuple[str, ...], identities: tuple[tuple[int, int], ...]
) -> None:
    descriptors: list[int] = []
    try:
        current = os.open(root, _directory_flags())
        descriptors.append(current)
        observed = [_identity(current)]
        for part in parts:
            current = os.open(part, _directory_flags(), dir_fd=current)
            descriptors.append(current)
            observed.append(_identity(current))
        if tuple(observed) != identities:
            raise ValueError("Selected-successor input path changed during acquisition")
    except OSError as exc:
        raise ValueError(
            "Selected-successor input path changed during acquisition"
        ) from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _bounded_regular_bytes(
    root: Path, ref: str, label: str, max_bytes: int
) -> bytes:
    """Read at most max_bytes+1 through a stable no-follow directory chain."""

    path = workspace_path(root, ref)
    parts = path.relative_to(root).parts
    if not parts or max_bytes < 1:
        raise ValueError(f"{label} byte limit is invalid")
    descriptors: list[int] = []
    leaf_descriptor: int | None = None
    try:
        current = os.open(root, _directory_flags())
        descriptors.append(current)
        identities = [_identity(current)]
        for part in parts[:-1]:
            current = os.open(part, _directory_flags(), dir_fd=current)
            descriptors.append(current)
            identities.append(_identity(current))
        leaf_flags = (
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        leaf_descriptor = os.open(parts[-1], leaf_flags, dir_fd=current)
        before = os.fstat(leaf_descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"{label} must be a regular workspace file")
        if before.st_size > max_bytes:
            raise ValueError(f"{label} exceeds {max_bytes // 1024} KiB limit")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(leaf_descriptor, min(_READ_CHUNK_BYTES, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(leaf_descriptor)
        named = os.stat(parts[-1], dir_fd=current, follow_symlinks=False)
        if (
            len(payload) > max_bytes
            or _signature(before) != _signature(after)
            or _signature(after) != _signature(named)
        ):
            raise ValueError(f"{label} changed during bounded acquisition")
        _verify_directory_chain(root, parts[:-1], tuple(identities))
        return payload
    except FileNotFoundError as exc:
        raise ValueError(f"{label} does not exist") from exc
    except OSError as exc:
        raise ValueError(
            f"{label} must be a regular non-symlink workspace file"
        ) from exc
    finally:
        if leaf_descriptor is not None:
            os.close(leaf_descriptor)
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _read_bound(
    root: Path, value: Any, label: str, *, max_bytes: int
) -> tuple[dict[str, str], bytes]:
    binding = _binding(value, label)
    payload = _bounded_regular_bytes(root, binding["ref"], label, max_bytes)
    if sha256_bytes(payload) != binding["sha256"]:
        raise ValueError(f"{label} bytes differ from their binding")
    return binding, payload


def _decision_task_id(payload: bytes) -> tuple[str, str]:
    try:
        receipt = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Selection decision receipt must be JSON") from exc
    if not isinstance(receipt, dict):
        raise ValueError("Selection decision receipt must be an object")
    body = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    if (
        receipt.get("schema_version") not in {1, 2}
        or receipt.get("artifact_kind") != "selection_decision_receipt"
        or receipt.get("outcome") != "selected"
        or receipt.get("not_authority") is not True
        or receipt.get("mutation_performed") is not False
        or receipt.get("receipt_sha256") != sha256_bytes(canonical_bytes(body) + b"\n")
    ):
        raise ValueError("Selection decision receipt is not a sealed selected decision")
    task_id = receipt.get("selected_task_id")
    receipt_id = receipt.get("receipt_id")
    if (
        not isinstance(task_id, str)
        or not OPAQUE_ID.fullmatch(task_id)
        or not isinstance(receipt_id, str)
        or not OPAQUE_ID.fullmatch(receipt_id)
    ):
        raise ValueError("Selection decision receipt has an invalid selected task")
    return task_id, receipt_id


def _source_task_metadata(payload: bytes, ref: str) -> tuple[str, str]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Selected successor source must be UTF-8 Markdown") from exc
    task_id: str | None = None
    for match in TASK_ID_LINE.finditer(text):
        if task_id is not None:
            raise ValueError(
                "Selected successor source requires exactly one bounded Task ID"
            )
        task_id = match.group(1) or match.group(2)
    if task_id is None or not OPAQUE_ID.fullmatch(task_id):
        raise ValueError("Selected successor source requires exactly one bounded Task ID")
    fallback = Path(ref).stem.replace("-", " ").replace("_", " ")
    title = fallback
    for line in io.StringIO(text):
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()[:120] or fallback
            break
        if stripped:
            title = stripped[:120]
            break
    return task_id, title


def _current_task(state: dict[str, dict[str, Any]]) -> tuple[str, dict[str, Any]] | None:
    rows = [
        (item_id, item)
        for item_id, item in state.items()
        if item.get("type") == "task"
        and item.get("path") == "task.md"
        and item.get("status") not in {"archived", "deleted", "obsolete", "superseded"}
    ]
    if len(rows) > 1:
        raise ValueError("Current task alias identity is not unique")
    return rows[0] if rows else None


def prepare_selected_successor(
    root: Path,
    *,
    source_decision: dict[str, str],
    task_source: dict[str, str],
    at: str,
    publish: bool = True,
) -> dict[str, Any]:
    """Build the prospective schema-v2 plan without model-authored event JSON."""

    root = root.resolve()
    decision_binding, decision_payload = _read_bound(
        root,
        source_decision,
        "selection decision receipt",
        max_bytes=MAX_SELECTION_DECISION_BYTES,
    )
    task_binding, task_payload = _read_bound(
        root,
        task_source,
        "selected successor source",
        max_bytes=MAX_SELECTED_SUCCESSOR_TASK_BYTES,
    )
    selected_id, receipt_id = _decision_task_id(decision_payload)
    source_task_id, source_title = _source_task_metadata(
        task_payload, task_binding["ref"]
    )
    if source_task_id != selected_id:
        raise ValueError("Selected successor source differs from the decision task ID")
    existing, index_digest = load_events_read_only(root)
    state = merge_state(existing)
    predecessor = _current_task(state)
    if selected_id in state:
        raise ValueError("Selected successor ID is already present in task state")
    events: list[dict[str, Any]] = []
    links: list[dict[str, str]] = []
    if predecessor is not None:
        predecessor_id, _predecessor = predecessor
        events.append(
            {
                "event": "upsert",
                "id": predecessor_id,
                "status": "superseded",
                "links": [{"rel": "superseded_by", "id": selected_id}],
                "note": "selected_successor_predecessor",
            }
        )
        links.append({"rel": "supersedes", "id": predecessor_id})
    events.append(
        {
            "event": "upsert",
            "id": selected_id,
            "type": "task",
            "status": "active",
            "path": "task.md",
            "title": source_title,
            "content_sha256": task_binding["sha256"],
            "links": links,
            "fields": {
                "selection_decision_id": receipt_id,
                "selection_decision_ref": decision_binding["ref"],
                "selection_decision_sha256": decision_binding["sha256"],
                "prospective_source_ref": task_binding["ref"],
                "prospective_source_sha256": task_binding["sha256"],
            },
            "note": "selected_successor_activation",
        }
    )
    request = {
        "schema_version": 2,
        "updated_at": at,
        "render": True,
        "external_settlement_kind": "selection_publication",
        "artifact_sources": [{"target_ref": "task.md", "source": task_binding}],
        "events": events,
    }
    plan = build_transition_plan(root, request, at=at)
    predicted_ref = f".task/transition_plans/{plan['plan_id']}.json"
    predicted_digest = sha256_bytes(canonical_bytes(plan) + b"\n")
    published = publish_transition_plan(root, plan) if publish else None
    plan_binding = {
        "ref": published["plan_ref"] if published else predicted_ref,
        "sha256": published["plan_file_sha256"] if published else predicted_digest,
    }
    return {
        "result_kind": "task_state_selected_successor_preparation",
        "schema_version": 1,
        "status": (
            published["status"] if published else "dry_run"
        ),
        "selected_task_id": selected_id,
        "source_decision": decision_binding,
        "task_source": task_binding,
        "index_revision": {"ref": ".task/index.jsonl", "sha256": index_digest},
        "plan_id": plan["plan_id"],
        "plan_binding": plan_binding,
        "request_sha256": plan["request_sha256"],
        "logical_update_count": len(events),
        "event_count": len(plan["events"]),
        "mutation_performed": bool(published and published["mutation_performed"]),
    }


__all__ = (
    "MAX_SELECTED_SUCCESSOR_TASK_BYTES",
    "MAX_SELECTION_DECISION_BYTES",
    "prepare_selected_successor",
)
