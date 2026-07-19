"""Bounded filesystem helpers shared by cycle-context collectors."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def rel_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_title(path: Path) -> str:
    if path.is_file():
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    return stripped.lstrip("#").strip()[:120] or path.stem
                if stripped:
                    return stripped[:120]
        except OSError:
            pass
    return path.stem.replace("-", " ").replace("_", " ")


def file_info(root: Path, path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {
        "path": rel_path(root, path),
        "exists": path.exists(),
        "is_file": path.is_file(),
        "is_dir": path.is_dir(),
    }
    if path.exists():
        stat = path.stat()
        info.update(
            {
                "size_bytes": stat.st_size,
                "modified_at": dt.datetime.fromtimestamp(stat.st_mtime)
                .astimezone()
                .isoformat(timespec="seconds"),
            }
        )
    if path.is_file():
        info["sha256"] = sha256_file(path)
        info["title"] = read_title(path)
    return info


def count_jsonl_lines(path: Path) -> int:
    if not path.is_file():
        return 0
    count = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def read_json_file(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None


def read_jsonl_file(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    records.append(value)
    except OSError:
        return records
    return records[-limit:] if limit is not None else records


def limited_files(
    root: Path, files: list[Path], max_files: int
) -> list[dict[str, Any]]:
    ordered = sorted(
        files,
        key=lambda path: path.stat().st_mtime if path.exists() else 0,
        reverse=True,
    )
    return [file_info(root, path) for path in ordered[:max_files]]


def files_with_suffixes(directory: Path, suffixes: set[str]) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        path
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in suffixes
    )


def classify_text_status(path: Path, default: str = "open") -> str:
    name = path.name.lower()
    parts = {part.lower() for part in path.parts}
    if "resolved" in parts or "resolved" in name:
        return "resolved"
    if "deleted" in name:
        return "deleted"
    if "closed" in parts or "closed" in name:
        return "closed"
    if "archived" in parts or "archived" in name:
        return "archived"
    try:
        text = path.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return default
    for status in (
        "failed",
        "partial",
        "blocked",
        "in_progress",
        "still_open",
        "open",
        "resolved",
        "deleted",
        "obsolete",
        "closed",
        "archived",
        "passed",
        "complete",
    ):
        if f"status: {status}" in text or f"validation verdict: {status}" in text:
            return status
    return default


def extract_used_goal_truth_from_value(value: Any) -> list[str]:
    used: list[str] = []
    if isinstance(value, dict):
        for key in ("used_goal_truth", "gt_files", "goal_truth"):
            item = value.get(key)
            if isinstance(item, list):
                used.extend(str(entry) for entry in item)
        packet = value.get("packet")
        if isinstance(packet, dict):
            used.extend(extract_used_goal_truth_from_value(packet))
        for nested_key in ("latest_event", "steps"):
            used.extend(extract_used_goal_truth_from_value(value.get(nested_key)))
    elif isinstance(value, list):
        for item in value:
            used.extend(extract_used_goal_truth_from_value(item))
    return used


def latest_cycle_dirs(root: Path, max_files: int) -> list[Path]:
    cycle_root = root / ".task" / "cycle"
    if not cycle_root.is_dir():
        return []
    dirs = [path for path in cycle_root.iterdir() if path.is_dir()]
    return sorted(dirs, key=lambda path: path.stat().st_mtime, reverse=True)[:max_files]


__all__ = [
    "classify_text_status",
    "count_jsonl_lines",
    "extract_used_goal_truth_from_value",
    "file_info",
    "files_with_suffixes",
    "latest_cycle_dirs",
    "limited_files",
    "now_iso",
    "read_json_file",
    "read_jsonl_file",
    "read_title",
    "rel_path",
    "sha256_file",
]
