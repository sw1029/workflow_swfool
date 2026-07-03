from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .constants import *
from .values import *

def rel_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
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
    return records


def read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None


def file_digest(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def resolve_existing_paths(root: Path, raw_paths: list[str], limit: int = 160) -> list[Path]:
    paths: list[Path] = []
    seen: set[str] = set()
    for item in raw_paths:
        if len(paths) >= limit:
            break
        if not item or "://" in item or "*" in item:
            continue
        path = Path(item)
        if not path.is_absolute():
            path = root / path
        try:
            exists = path.exists()
        except OSError:
            exists = False
        if not exists:
            continue
        key = path.resolve().as_posix()
        if key in seen:
            continue
        paths.append(path)
        seen.add(key)
    return paths


def collect_path_values(value: Any, keys: set[str]) -> list[str]:
    return collect_by_key(value, keys | PATH_FIELD_NAMES)
