"""Filesystem layout and crash-safe registry state projection."""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import threading
from typing import Any

from .common import now_iso, rel_path, sha256_file, slugify, stamp
from .contracts import ADVICE_DIR
from .stable_store import (
    atomic_replace,
    ensure_parent,
    locked_file,
    publish_immutable,
    read_regular,
)


_THREAD_LOCKS: dict[str, threading.RLock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()
_LOCK_DEPTH = threading.local()


def advice_root(root: Path) -> Path:
    return root / ADVICE_DIR


def index_jsonl(root: Path) -> Path:
    return advice_root(root) / "index.jsonl"


def index_md(root: Path) -> Path:
    return advice_root(root) / "index.md"


def _thread_lock(root: Path) -> threading.RLock:
    key = str(root.resolve())
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.RLock())


def _depths() -> dict[str, int]:
    value = getattr(_LOCK_DEPTH, "values", None)
    if value is None:
        value = {}
        _LOCK_DEPTH.values = value
    return value


@contextlib.contextmanager
def registry_lock(root: Path):
    """Serialize registry mutations across threads and cooperating processes."""

    root = root.resolve()
    key = str(root)
    with _thread_lock(root):
        depths = _depths()
        if depths.get(key, 0):
            depths[key] += 1
            try:
                yield
            finally:
                depths[key] -= 1
            return
        lock_path = advice_root(root) / "index.lock"
        with locked_file(root, lock_path):
            depths[key] = 1
            try:
                yield
            finally:
                depths.pop(key, None)


def fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def ensure_dirs(root: Path) -> None:
    base = advice_root(root)
    ensure_parent(root, base / ".owned")
    for name in ("raw", "active", "deferred", "applied", "rejected"):
        ensure_parent(root, base / name / ".owned")
    registry = index_jsonl(root)
    if read_regular(
        root, registry, missing=None, label="Advice registry index"
    ) is None:
        publish_immutable(root, registry, b"")


def unique_advice_key(root: Path, title: str) -> tuple[str, str]:
    existing = merge_state(load_events(root))
    base = f"{stamp()}-{slugify(title)}"
    candidate = base
    suffix = 2
    while (
        f"adv-{candidate}" in existing
        or (advice_root(root) / "raw" / f"{candidate}.md").exists()
        or (advice_root(root) / "active" / f"{candidate}.md").exists()
    ):
        candidate = f"{base}-{suffix}"
        suffix += 1
    return f"adv-{candidate}", f"{candidate}.md"


def find_exact_raw_digest(root: Path, raw_sha256: str) -> dict[str, Any] | None:
    """Read existing registry/raw files without creating or updating anything."""

    registry = index_jsonl(root)
    if registry.is_file():
        with registry.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise SystemExit(
                        f"Invalid JSON in {registry} line {line_no}: {exc}"
                    ) from exc
                if isinstance(event, dict) and event.get("raw_sha256") == raw_sha256:
                    return {
                        "advice_id": event.get("advice_id"),
                        "raw_source_path": event.get("raw_source_path"),
                        "match_basis": "registry_raw_sha256",
                    }
    raw_root = advice_root(root) / "raw"
    if raw_root.is_dir():
        for candidate in sorted(raw_root.glob("*.md")):
            if (
                candidate.is_file()
                and not candidate.is_symlink()
                and sha256_file(candidate) == raw_sha256
            ):
                return {
                    "advice_id": None,
                    "raw_source_path": rel_path(root, candidate),
                    "match_basis": "raw_file_sha256",
                }
    return None


def parse_events(payload: bytes, path: Path) -> list[dict[str, Any]]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SystemExit(f"Invalid UTF-8 in {path}: {exc}") from exc
    events: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid JSON in {path} line {line_no}: {exc}") from exc
        if not isinstance(value, dict):
            raise SystemExit(f"Invalid JSON object in {path} line {line_no}.")
        events.append(value)
    return events


def registry_snapshot(root: Path) -> tuple[bytes, list[dict[str, Any]]]:
    ensure_dirs(root)
    path = index_jsonl(root)
    payload = read_regular(root, path, label="Advice registry index")
    return payload, parse_events(payload, path)


def load_events(root: Path) -> list[dict[str, Any]]:
    return registry_snapshot(root)[1]


def event_bytes(event: dict[str, Any]) -> bytes:
    return (json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def append_event(root: Path, event: dict[str, Any]) -> None:
    with registry_lock(root):
        from .intake_intent import assert_no_pending_intake_intents

        assert_no_pending_intake_intents(root)
        payload, _events = registry_snapshot(root)
        if payload and not payload.endswith(b"\n"):
            payload += b"\n"
        atomic_replace(root, index_jsonl(root), payload + event_bytes(event))


def merge_state(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    state: dict[str, dict[str, Any]] = {}
    for event in events:
        advice_id = event.get("advice_id")
        if not advice_id:
            continue
        current = state.setdefault(
            str(advice_id), {"advice_id": advice_id, "links": [], "fields": {}}
        )
        current.update(
            {
                key: value
                for key, value in event.items()
                if key not in {"links", "fields"}
            }
        )
        if isinstance(event.get("fields"), dict):
            current.setdefault("fields", {}).update(event["fields"])
        if isinstance(event.get("links"), list):
            seen = {
                (link.get("rel"), link.get("id"))
                for link in current.setdefault("links", [])
            }
            for link in event["links"]:
                if not isinstance(link, dict):
                    continue
                pair = (link.get("rel"), link.get("id"))
                if pair[0] and pair[1] and pair not in seen:
                    current["links"].append({"rel": pair[0], "id": pair[1]})
                    seen.add(pair)
    return state


def render_index_payload(
    state: dict[str, dict[str, Any]], generated_at: str
) -> bytes:
    lines = [
        "# External Advice Index",
        "",
        f"- Generated: {generated_at}",
        "- Projection only; canonical JSONL: `.agent_advice/index.jsonl`",
        f"- Advice count: {len(state)}",
        "",
        "| Advice ID | Status | Title | Normalized Path | Raw Source | Updated |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in sorted(
        state.values(),
        key=lambda row: (
            str(row.get("status", "")),
            str(row.get("advice_id", "")),
        ),
    ):
        values = [
            item.get("advice_id", ""),
            item.get("status", ""),
            item.get("title", ""),
            item.get("path", ""),
            item.get("raw_source_path", ""),
            item.get("updated_at", ""),
        ]
        lines.append(
            "| "
            + " | ".join(str(value).replace("|", "\\|") for value in values)
            + " |"
        )
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def rebuild_index(root: Path, *, generated_at: str | None = None) -> dict[str, Any]:
    with registry_lock(root):
        state = merge_state(load_events(root))
        payload = render_index_payload(state, generated_at or now_iso())
        atomic_replace(root, index_md(root), payload)
        return {
            "index_md": rel_path(root, index_md(root)),
            "advice_count": len(state),
        }
