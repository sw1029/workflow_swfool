"""Bound and rederive the complete filesystem input set for index audits."""

from __future__ import annotations

import contextlib
import hashlib
import os
from pathlib import Path
import stat
import tempfile
from typing import Any, Iterator

from .audit import audit_index
from .events import load_events_for_audit, merge_state
from .storage import existing_index_read_lock
from .transition_plan_contract import canonical_bytes, sha256_bytes


MAX_AUDIT_INPUT_FILES = 4096
MAX_AUDIT_INPUT_FILE_BYTES = 8 * 1024 * 1024
MAX_AUDIT_INPUT_TOTAL_BYTES = 64 * 1024 * 1024
MAX_AUDIT_DISCOVERY_ENTRIES = 8192
AUDIT_SNAPSHOT_ATTEMPTS = 3
_FIXED_FILES = {
    ".task/index.jsonl",
    ".task/index.md",
    ".task/index.lock",
    "task.md",
}
_DISCOVERY_ROOTS = (
    (".task/candidate_task", False, frozenset({".md"})),
    (".task/task_pack", False, frozenset({".json", ".md"})),
    (".task/task_miss", True, frozenset({".md"})),
    (".task/validation", False, frozenset({".md"})),
    (".task/id_audit", False, frozenset({".md"})),
    (".task/migrations", True, None),
    (".agent_log", True, None),
    (".agent_goal", False, frozenset({".md"})),
    (".interview", True, frozenset({".md"})),
    (".agent_advice", True, frozenset({".md"})),
    (".issue", True, frozenset({".md"})),
    (
        ".schema",
        True,
        frozenset({".md", ".json", ".jsonl", ".yaml", ".yml"}),
    ),
    (
        ".contract",
        True,
        frozenset({".md", ".json", ".jsonl", ".yaml", ".yml"}),
    ),
)


class AuditSnapshotRace(ValueError):
    """A retryable change observed while pinning audit input bytes."""


class _TraversalBudget:
    def __init__(self, maximum: int) -> None:
        self.maximum = maximum
        self.observed = 0

    def consume(self) -> None:
        self.observed += 1
        if self.observed > self.maximum:
            raise ValueError(
                "Task-index global discovery entry budget exceeded"
            )


def _safe_ref(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    raw = Path(value)
    if raw.is_absolute() or not raw.parts or ".." in raw.parts:
        raise ValueError("Task-index audit input path must be workspace-relative")
    return raw.as_posix()


def _walk_files(
    root: Path,
    start_ref: str,
    *,
    recursive: bool,
    suffixes: frozenset[str] | None,
    budget: _TraversalBudget,
) -> set[str]:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(root, flags)
    try:
        for part in Path(start_ref).parts:
            try:
                child = os.open(part, flags, dir_fd=descriptor)
            except FileNotFoundError:
                return set()
            except OSError as exc:
                raise ValueError(
                    f"Task-index audit root is unsafe: {start_ref}"
                ) from exc
            os.close(descriptor)
            descriptor = child
        return _walk_directory_descriptor(
            descriptor,
            prefix=start_ref,
            recursive=recursive,
            suffixes=suffixes,
            budget=budget,
        )
    finally:
        os.close(descriptor)


def _walk_directory_descriptor(
    descriptor: int,
    *,
    prefix: str,
    recursive: bool,
    suffixes: frozenset[str] | None,
    budget: _TraversalBudget,
    depth: int = 0,
) -> set[str]:
    if depth > 32:
        raise ValueError("Task-index audit discovery depth budget exceeded")
    try:
        entries = []
        for entry in os.scandir(descriptor):
            budget.consume()
            entries.append(entry)
            if len(entries) > MAX_AUDIT_INPUT_FILES:
                raise ValueError(
                    "Task-index audit directory entry budget exceeded"
                )
        entries.sort(key=lambda item: item.name)
    except OSError as exc:
        raise ValueError(f"Task-index audit root is unreadable: {prefix}") from exc
    found: set[str] = set()
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_flags |= getattr(os, "O_NOFOLLOW", 0)
    directory_flags |= getattr(os, "O_CLOEXEC", 0)
    for entry in entries:
        ref = f"{prefix}/{entry.name}"
        if entry.is_symlink():
            raise ValueError(
                f"Task-index audit input discovery must not traverse symlinks: {ref}"
            )
        if entry.is_dir(follow_symlinks=False):
            if recursive:
                child = os.open(entry.name, directory_flags, dir_fd=descriptor)
                try:
                    found.update(
                        _walk_directory_descriptor(
                            child,
                            prefix=ref,
                            recursive=True,
                            suffixes=suffixes,
                            budget=budget,
                            depth=depth + 1,
                        )
                    )
                finally:
                    os.close(child)
                if len(found) > MAX_AUDIT_INPUT_FILES:
                    raise ValueError(
                        "Task-index audit input file-count budget exceeded"
                    )
            continue
        if not entry.is_file(follow_symlinks=False):
            raise ValueError(f"Task-index audit input has unsupported type: {ref}")
        if suffixes is None or Path(entry.name).suffix.lower() in suffixes:
            found.add(ref)
            if len(found) > MAX_AUDIT_INPUT_FILES:
                raise ValueError(
                    "Task-index audit input file-count budget exceeded"
                )
    return found


def _open_parent(root: Path, ref: str) -> tuple[int, str]:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(root, flags)
    parts = Path(ref).parts
    try:
        for part in parts[:-1]:
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
    except FileNotFoundError:
        os.close(descriptor)
        return -1, parts[-1]
    except OSError as exc:
        os.close(descriptor)
        raise ValueError(
            f"Task-index audit input path has an unsafe ancestor: {ref}"
        ) from exc
    return descriptor, parts[-1]


def _absent_entry(ref: str) -> tuple[dict[str, Any], None]:
    return {"ref": ref, "kind": "absent"}, None


def _stat_token(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _reopen_canonical_leaf(
    root: Path,
    ref: str,
    *,
    parent_state: os.stat_result,
    expected: os.stat_result,
) -> None:
    reopened, leaf = _open_parent(root, ref)
    if reopened < 0:
        raise AuditSnapshotRace(
            f"Task-index audit input parent changed during capture: {ref}"
        )
    try:
        reopened_parent = os.fstat(reopened)
        if (
            reopened_parent.st_dev,
            reopened_parent.st_ino,
        ) != (parent_state.st_dev, parent_state.st_ino):
            raise AuditSnapshotRace(
                f"Task-index audit input parent changed during capture: {ref}"
            )
        try:
            current = os.stat(leaf, dir_fd=reopened, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise AuditSnapshotRace(
                f"Task-index audit input changed during capture: {ref}"
            ) from exc
        if not stat.S_ISREG(current.st_mode) or _stat_token(current) != _stat_token(
            expected
        ):
            raise AuditSnapshotRace(
                f"Task-index audit input changed during capture: {ref}"
            )
    finally:
        os.close(reopened)


def _regular_entry(
    root: Path,
    ref: str,
    *,
    byte_limit: int = MAX_AUDIT_INPUT_FILE_BYTES,
) -> tuple[dict[str, Any], bytes | None]:
    parent, leaf = _open_parent(root, ref)
    if parent < 0:
        return _absent_entry(ref)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    try:
        parent_state = os.fstat(parent)
        try:
            descriptor = os.open(leaf, flags, dir_fd=parent)
        except FileNotFoundError:
            return _absent_entry(ref)
        except OSError as exc:
            raise ValueError(
                f"Task-index audit input is not a safe regular file: {ref}"
            ) from exc
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise ValueError(
                    f"Task-index audit input is not a regular file: {ref}"
                )
            effective_limit = min(MAX_AUDIT_INPUT_FILE_BYTES, byte_limit)
            if before.st_size > effective_limit:
                raise ValueError(
                    f"Task-index audit input exceeds its byte budget: {ref}"
                )
            payload = bytearray()
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                payload.extend(chunk)
                if len(payload) > effective_limit:
                    raise ValueError(
                        f"Task-index audit input exceeds its byte budget: {ref}"
                    )
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        try:
            current = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise AuditSnapshotRace(
                f"Task-index audit input changed during capture: {ref}"
            ) from exc
        _reopen_canonical_leaf(
            root,
            ref,
            parent_state=parent_state,
            expected=current,
        )
    finally:
        os.close(parent)
    before_token = _stat_token(before)
    after_token = _stat_token(after)
    current_token = _stat_token(current)
    if before_token != after_token or after_token != current_token:
        raise AuditSnapshotRace(
            f"Task-index audit input changed during capture: {ref}"
        )
    body = bytes(payload)
    return {
        "ref": ref,
        "kind": "regular",
        "size_bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }, body


def _indexed_refs(root: Path) -> set[str]:
    events, _read_results = load_events_for_audit(root)
    state = merge_state(events)
    refs: set[str] = set()
    for item in state.values():
        ref = _safe_ref(item.get("path"))
        if ref is not None:
            refs.add(ref)
        fields = item.get("fields")
        if isinstance(fields, dict):
            snapshot_ref = _safe_ref(fields.get("snapshot_path"))
            if snapshot_ref is not None:
                refs.add(snapshot_ref)
    return refs


def _base_refs(root: Path) -> list[str]:
    refs = set(_FIXED_FILES)
    budget = _TraversalBudget(MAX_AUDIT_DISCOVERY_ENTRIES)
    for start_ref, recursive, suffixes in _DISCOVERY_ROOTS:
        refs.update(
            _walk_files(
                root,
                start_ref,
                recursive=recursive,
                suffixes=suffixes,
                budget=budget,
            )
        )
    if len(refs) > MAX_AUDIT_INPUT_FILES:
        raise ValueError("Task-index audit input file-count budget exceeded")
    return sorted(refs)


def _capture_refs(
    root: Path, refs: list[str]
) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    entries: list[dict[str, Any]] = []
    payloads: dict[str, bytes] = {}
    total_bytes = 0
    for ref in refs:
        remaining = MAX_AUDIT_INPUT_TOTAL_BYTES - total_bytes
        entry, payload = _regular_entry(root, ref, byte_limit=remaining)
        entries.append(entry)
        if payload is not None:
            payloads[ref] = payload
            total_bytes += len(payload)
    return entries, payloads


@contextlib.contextmanager
def _materialized_snapshot(
    payloads: dict[str, bytes],
) -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="task-index-audit-") as directory:
        snapshot_root = Path(directory)
        for ref, payload in sorted(payloads.items()):
            path = snapshot_root / ref
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        yield snapshot_root


def _indexed_refs_from_payloads(payloads: dict[str, bytes]) -> set[str]:
    with _materialized_snapshot(payloads) as snapshot_root:
        return _indexed_refs(snapshot_root)


def _capture(
    root: Path,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    root = root.resolve(strict=True)
    base_refs = _base_refs(root)
    base_entries, base_payloads = _capture_refs(root, base_refs)
    indexed_refs = _indexed_refs_from_payloads(base_payloads)
    refs = sorted(set(base_refs) | indexed_refs)
    if len(refs) > MAX_AUDIT_INPUT_FILES:
        raise ValueError("Task-index audit input file-count budget exceeded")
    entries, payloads = _capture_refs(root, refs)
    base_by_ref = {entry["ref"]: entry for entry in base_entries}
    final_by_ref = {entry["ref"]: entry for entry in entries}
    if any(final_by_ref.get(ref) != entry for ref, entry in base_by_ref.items()):
        raise AuditSnapshotRace(
            "Task-index base inputs changed while closing the audit snapshot"
        )
    if _indexed_refs_from_payloads(payloads) != indexed_refs:
        raise AuditSnapshotRace(
            "Task-index referenced-input closure changed during capture"
        )
    total_bytes = sum(len(payload) for payload in payloads.values())
    manifest = {
        "schema_version": 1,
        "artifact_kind": "task_index_audit_input_manifest",
        "entry_count": len(entries),
        "total_bytes": total_bytes,
        "entries": entries,
        "root_sha256": sha256_bytes(canonical_bytes(entries)),
    }
    return manifest, payloads


def audit_input_manifest(root: Path) -> dict[str, Any]:
    manifest, _payloads = _capture(root)
    return manifest


def read_bounded_regular(
    root: Path, ref: str, *, max_bytes: int
) -> bytes:
    """Open one workspace-relative file component-wise without following links."""

    if max_bytes < 1:
        raise ValueError("Bounded read requires a positive byte limit")
    normalized = _safe_ref(ref)
    if normalized is None or normalized != ref:
        raise ValueError("Bounded read requires a canonical workspace-relative ref")
    entry, payload = _regular_entry(
        root.resolve(strict=True),
        normalized,
        byte_limit=max_bytes,
    )
    if entry["kind"] != "regular" or payload is None:
        raise ValueError(f"Required bounded audit input is missing: {ref}")
    return payload


def _audit_captured(
    payloads: dict[str, bytes], *, audited_at: str
) -> dict[str, Any]:
    with _materialized_snapshot(payloads) as snapshot_root:
        return audit_index(snapshot_root, now_fn=lambda: audited_at)


def audit_with_snapshot(
    root: Path,
    *,
    audited_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run the audit between two equal bounded Merkle captures."""

    root = root.resolve(strict=True)
    for _attempt in range(AUDIT_SNAPSHOT_ATTEMPTS):
        with existing_index_read_lock(root):
            try:
                before, payloads = _capture(root)
                audit = _audit_captured(payloads, audited_at=audited_at)
                after, _after_payloads = _capture(root)
            except AuditSnapshotRace:
                continue
        if before == after:
            return before, audit
    raise ValueError("Task-index audit inputs changed during bounded snapshot")


__all__ = (
    "MAX_AUDIT_INPUT_FILES",
    "MAX_AUDIT_INPUT_FILE_BYTES",
    "MAX_AUDIT_INPUT_TOTAL_BYTES",
    "MAX_AUDIT_DISCOVERY_ENTRIES",
    "audit_input_manifest",
    "audit_with_snapshot",
    "read_bounded_regular",
)
