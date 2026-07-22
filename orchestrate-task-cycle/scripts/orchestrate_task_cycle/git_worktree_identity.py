"""Bounded canonical Git status, index, mode, and content identities."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
from typing import Any, Iterable

from .git_worktree_files import path_content_identity


MAX_GIT_STATUS_BYTES = 8 * 1024 * 1024
MAX_GIT_IDENTITY_PATHS = 50_000
MAX_GIT_PATHSPEC_BYTES = 1024 * 1024
MAX_GIT_CONTENT_BYTES = 256 * 1024 * 1024
GIT_COMMAND_TIMEOUT_SECONDS = 20
_STATUS_ARGS = [
    "status",
    "--porcelain=v1",
    "-z",
    "--untracked-files=all",
    "--no-renames",
    "--",
    ".",
]


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _git_command_bytes(root: Path, args: list[str]) -> tuple[bytes | None, str | None]:
    try:
        result = subprocess.run(
            ["git", "--no-optional-locks", *args],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=GIT_COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        return None, "git_unavailable"
    except (OSError, subprocess.TimeoutExpired):
        return None, "git_command_failed"
    if result.returncode != 0:
        return None, "git_command_failed"
    if len(result.stdout) > MAX_GIT_STATUS_BYTES:
        return None, "git_command_output_limit_exceeded"
    return result.stdout, None


def _safe_git_path(raw: bytes) -> str | None:
    try:
        value = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None
    candidate = PurePosixPath(value)
    if (
        not value
        or value != candidate.as_posix()
        or candidate.is_absolute()
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        return None
    return value


def legacy_git_changed_paths(git: dict[str, Any] | None) -> list[str]:
    """Preserve the pre-v3 path projection for readers and fallback diagnostics."""

    source = git if isinstance(git, dict) else {}
    paths: set[str] = set()
    for line in source.get("diff_name_status") or []:
        parts = str(line).split("\t")
        paths.update(part for part in parts[1:] if part)
    paths.update(str(item) for item in source.get("untracked") or [] if str(item))
    for line in source.get("status_short_branch") or []:
        text = str(line)
        if text.startswith("## "):
            continue
        candidate = text[3:].strip() if len(text) > 3 else ""
        if " -> " in candidate:
            candidate = candidate.rsplit(" -> ", 1)[1]
        if candidate:
            paths.add(candidate)
    return sorted(
        path
        for path in paths
        if path != ".task/cycle" and not path.startswith(".task/cycle/")
    )


def _porcelain_records(raw: bytes) -> tuple[list[dict[str, str]], list[str]]:
    if not raw:
        return [], []
    fields = raw.split(b"\0")
    if fields[-1] != b"":
        return [], ["git_status_not_nul_terminated"]
    records: list[dict[str, str]] = []
    errors: list[str] = []
    seen: set[str] = set()
    for field in fields[:-1]:
        if len(field) < 4 or field[2:3] != b" ":
            errors.append("git_status_record_invalid")
            continue
        try:
            status = field[:2].decode("ascii", errors="strict")
        except UnicodeDecodeError:
            errors.append("git_status_record_invalid")
            continue
        path = _safe_git_path(field[3:])
        if path is None:
            errors.append("git_status_path_unsafe")
            continue
        if path == ".task/cycle" or path.startswith(".task/cycle/"):
            continue
        if path in seen:
            errors.append("git_status_path_duplicate")
            continue
        seen.add(path)
        records.append({"path": path, "status": status})
    return sorted(records, key=lambda item: item["path"]), sorted(set(errors))


def _index_identities(
    root: Path, paths: list[str]
) -> tuple[dict[str, str], list[str]]:
    if not paths:
        return {}, []
    argument_bytes = sum(len(path.encode("utf-8")) + 1 for path in paths)
    if argument_bytes > MAX_GIT_PATHSPEC_BYTES:
        return {}, ["git_pathspec_limit_exceeded"]
    raw, error = _git_command_bytes(
        root,
        ["--literal-pathspecs", "ls-files", "--stage", "-z", "--", *paths],
    )
    if error is not None or raw is None:
        return {}, [error or "git_index_query_failed"]
    fields = raw.split(b"\0")
    if fields[-1] != b"":
        return {}, ["git_index_not_nul_terminated"]
    wanted = set(paths)
    grouped: dict[str, list[dict[str, Any]]] = {path: [] for path in paths}
    errors: list[str] = []
    for field in fields[:-1]:
        if b"\t" not in field:
            errors.append("git_index_record_invalid")
            continue
        metadata, raw_path = field.split(b"\t", 1)
        path = _safe_git_path(raw_path)
        parts = metadata.split(b" ")
        if path is None or path not in wanted or len(parts) != 3:
            errors.append("git_index_record_invalid")
            continue
        try:
            mode = parts[0].decode("ascii", errors="strict")
            object_id = parts[1].decode("ascii", errors="strict")
            stage = int(parts[2].decode("ascii", errors="strict"))
        except (UnicodeDecodeError, ValueError):
            errors.append("git_index_record_invalid")
            continue
        if not _valid_index_record(mode, object_id, stage):
            errors.append("git_index_record_invalid")
            continue
        grouped[path].append(
            {"mode": mode, "object_id": object_id, "stage": stage}
        )
    identities = {path: _index_digest(values) for path, values in grouped.items()}
    return identities, sorted(set(errors))


def _valid_index_record(mode: str, object_id: str, stage: int) -> bool:
    return (
        len(mode) == 6
        and all(character in "01234567" for character in mode)
        and len(object_id) in {40, 64}
        and all(character in "0123456789abcdef" for character in object_id)
        and stage in {0, 1, 2, 3}
    )


def _index_digest(values: list[dict[str, Any]]) -> str:
    return _sha256(
        sorted(
            values,
            key=lambda item: (item["stage"], item["mode"], item["object_id"]),
        )
    )


def _unavailable(
    repository_state: str,
    error_codes: Iterable[str],
    *,
    total_count: int = 0,
    truncated: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "binding_status": "incomplete",
        "repository_state": repository_state,
        "total_count": total_count,
        "included_count": 0,
        "truncated": truncated,
        "path_set_sha256": None,
        "inventory_sha256": None,
        "item_alignment": "git.changed_paths.items",
        "items": [],
        "error_codes": sorted(set(error_codes)),
    }


def _not_worktree() -> dict[str, Any]:
    material = {"repository_state": "not_worktree", "entries": []}
    return {
        "schema_version": 1,
        "binding_status": "exact",
        "repository_state": "not_worktree",
        "total_count": 0,
        "included_count": 0,
        "truncated": False,
        "path_set_sha256": _sha256([]),
        "inventory_sha256": _sha256(material),
        "item_alignment": "git.changed_paths.items",
        "items": [],
        "error_codes": [],
    }


def _collect_rows(
    root: Path,
    records: list[dict[str, str]],
    index_identities: dict[str, str],
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    consumed_bytes = 0
    try:
        root_fd = os.open(
            root,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError:
        return [], ["git_workspace_open_failed"]
    try:
        for record in records:
            identity, consumed, error = path_content_identity(
                root_fd,
                record["path"],
                remaining_bytes=MAX_GIT_CONTENT_BYTES - consumed_bytes,
            )
            if error is not None or identity is None:
                return [], [error or "git_path_identity_failed"]
            consumed_bytes += consumed
            rows.append(
                {
                    **record,
                    **identity,
                    "index_identity_sha256": index_identities[record["path"]],
                }
            )
    finally:
        os.close(root_fd)
    return rows, []


def bind_git_worktree_identity(
    git: dict[str, Any] | None,
    root: Path | None,
    maximum: int,
    fallback_paths: list[str],
) -> tuple[list[str], dict[str, Any]]:
    """Return exact aggregate identity plus a model-bounded aligned row prefix."""

    if git is None:
        return fallback_paths, _unavailable(
            "not_collected", ["git_context_not_collected"]
        )
    if root is None or not root.is_dir():
        return fallback_paths, _unavailable(
            "unknown", ["git_workspace_unavailable"]
        )
    if git.get("inside_work_tree") is not True:
        commands = git.get("commands")
        command = (
            commands.get("rev_parse_inside") if isinstance(commands, dict) else None
        )
        if isinstance(command, dict) and isinstance(command.get("returncode"), int):
            return [], _not_worktree()
        return fallback_paths, _unavailable(
            "unknown", ["git_worktree_state_unavailable"]
        )
    raw_status, status_error = _git_command_bytes(root, _STATUS_ARGS)
    if status_error is not None or raw_status is None:
        return fallback_paths, _unavailable(
            "worktree", [status_error or "git_status_failed"]
        )
    records, errors = _porcelain_records(raw_status)
    paths = [record["path"] for record in records]
    if len(paths) > MAX_GIT_IDENTITY_PATHS:
        errors.append("git_identity_path_limit_exceeded")
    index_identities: dict[str, str] = {}
    if not errors:
        index_identities, index_errors = _index_identities(root, paths)
        errors.extend(index_errors)
    rows: list[dict[str, Any]] = []
    if not errors:
        rows, row_errors = _collect_rows(root, records, index_identities)
        errors.extend(row_errors)
    if errors:
        return paths, _unavailable(
            "worktree",
            errors,
            total_count=len(paths),
            truncated=len(paths) > maximum,
        )
    final_status, final_error = _git_command_bytes(root, _STATUS_ARGS)
    final_records: list[dict[str, str]] = []
    final_errors: list[str] = []
    if final_error is None and final_status is not None:
        final_records, final_errors = _porcelain_records(final_status)
    if final_error is not None or final_errors or final_records != records:
        return paths, _unavailable(
            "worktree",
            final_errors or [final_error or "git_status_changed_during_binding"],
            total_count=len(paths),
            truncated=len(paths) > maximum,
        )
    material = {"repository_state": "worktree", "entries": rows}
    return paths, {
        "schema_version": 1,
        "binding_status": "exact",
        "repository_state": "worktree",
        "total_count": len(rows),
        "included_count": min(len(rows), maximum),
        "truncated": len(rows) > maximum,
        "path_set_sha256": _sha256(paths),
        "inventory_sha256": _sha256(material),
        "item_alignment": "git.changed_paths.items",
        "items": [
            {key: value for key, value in row.items() if key != "path"}
            for row in rows[:maximum]
        ],
        "error_codes": [],
    }


__all__ = ["bind_git_worktree_identity", "legacy_git_changed_paths"]
