"""Filesystem layout and crash-safe registry state projection."""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
from typing import Any

from .common import now_iso, rel_path, sha256_file, slugify, stamp
from .contracts import ADVICE_DIR

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows keeps in-process safety only.
    fcntl = None  # type: ignore[assignment]


_THREAD_LOCKS: dict[str, threading.RLock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()
_LOCK_DEPTH = threading.local()


def advice_root(root: Path) -> Path:
    return root / ADVICE_DIR


def index_jsonl(root: Path) -> Path:
    return advice_root(root) / "index.jsonl"


def index_md(root: Path) -> Path:
    return advice_root(root) / "index.md"


def _ensure_directory(path: Path, label: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise SystemExit(f"{label} must be a regular directory: {path}")


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
        _ensure_directory(advice_root(root), "Advice registry root")
        lock_path = advice_root(root) / "index.lock"
        if lock_path.exists() or lock_path.is_symlink():
            mode = lock_path.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
                raise SystemExit("Advice registry lock must be a regular file.")
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(lock_path, flags, 0o600)
        with os.fdopen(descriptor, "a+b", closefd=True) as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise SystemExit("Advice registry lock must be a regular file.")
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            depths[key] = 1
            try:
                yield
            finally:
                depths.pop(key, None)
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_replace(path: Path, payload: bytes, mode: int = 0o600) -> None:
    """Replace one regular file only after durable temporary publication."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        target_mode = path.lstat().st_mode
        if stat.S_ISLNK(target_mode) or not stat.S_ISREG(target_mode):
            raise SystemExit(f"Unsafe advice registry target: {path}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        fsync_directory(path.parent)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise


def publish_immutable(path: Path, payload: bytes, mode: int = 0o600) -> None:
    """Publish immutable bytes, accepting only an exact idempotent replay."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        target_mode = path.lstat().st_mode
        if stat.S_ISLNK(target_mode) or not stat.S_ISREG(target_mode):
            raise SystemExit(f"Unsafe immutable advice target: {path}")
        if path.read_bytes() != payload:
            raise SystemExit(f"Immutable advice publication conflict: {path}")
        return
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink() or not path.is_file() or path.read_bytes() != payload:
                raise SystemExit(f"Immutable advice publication conflict: {path}")
        fsync_directory(path.parent)
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)


def ensure_dirs(root: Path) -> None:
    base = advice_root(root)
    _ensure_directory(base, "Advice registry root")
    for name in ("raw", "active", "deferred", "applied", "rejected"):
        _ensure_directory(base / name, f"Advice {name} directory")
    registry = index_jsonl(root)
    if registry.exists() or registry.is_symlink():
        mode = registry.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise SystemExit("Advice registry index must be a regular file.")
    else:
        registry.touch()


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
    payload = path.read_bytes()
    return payload, parse_events(payload, path)


def load_events(root: Path) -> list[dict[str, Any]]:
    return registry_snapshot(root)[1]


def event_bytes(event: dict[str, Any]) -> bytes:
    return (json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def append_event(root: Path, event: dict[str, Any]) -> None:
    with registry_lock(root):
        payload, _events = registry_snapshot(root)
        if payload and not payload.endswith(b"\n"):
            payload += b"\n"
        atomic_replace(index_jsonl(root), payload + event_bytes(event))


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


def rebuild_index(root: Path) -> dict[str, Any]:
    with registry_lock(root):
        state = merge_state(load_events(root))
        lines = [
            "# External Advice Index",
            "",
            f"- Generated: {now_iso()}",
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
        atomic_replace(
            index_md(root), ("\n".join(lines).rstrip() + "\n").encode("utf-8")
        )
        return {
            "index_md": rel_path(root, index_md(root)),
            "advice_count": len(state),
        }
