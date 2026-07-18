"""Immutable storage primitives for legacy task-pack retirement overlays."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


MAX_RETIREMENT_ARTIFACT_BYTES = 4 * 1024 * 1024
RETIREMENT_ID = re.compile(r"^[a-z][a-z0-9-]{2,79}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
STORE_REF = ".task/task_pack_retirement"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def display_bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inside(root: Path, ref: str, label: str) -> tuple[Path, tuple[str, ...]]:
    if (
        not isinstance(ref, str)
        or not ref
        or ref != ref.strip()
        or "\\" in ref
        or "\x00" in ref
    ):
        raise ValueError(f"{label} requires a normalized workspace-relative ref")
    pure = PurePosixPath(ref)
    if (
        pure.is_absolute()
        or pure.as_posix() != ref
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise ValueError(f"{label} ref is unsafe")
    candidate = root.joinpath(*pure.parts)
    try:
        candidate.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} escapes the workspace") from exc
    return candidate, pure.parts


def safe_regular_file(
    root: Path,
    ref: str,
    label: str,
    *,
    expected_prefix: str | None = None,
    expected_ref: str | None = None,
) -> Path:
    root = root.resolve(strict=True)
    path, parts = _inside(root, ref, label)
    if expected_ref is not None and ref != expected_ref:
        raise ValueError(f"{label} ref does not match its deterministic location")
    if expected_prefix is not None and not ref.startswith(
        expected_prefix.rstrip("/") + "/"
    ):
        raise ValueError(f"{label} is outside its owned store")
    current = root
    for part in parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"{label} cannot traverse a symlink")
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise ValueError(f"{label} does not exist") from exc
    if not stat.S_ISREG(mode) or path.resolve(strict=True) != path:
        raise ValueError(f"{label} must be a non-symlink regular file")
    if path.stat().st_size > MAX_RETIREMENT_ARTIFACT_BYTES:
        raise ValueError(f"{label} exceeds the artifact size limit")
    return path


def read_bound_bytes(
    root: Path,
    binding: Any,
    label: str,
    *,
    expected_prefix: str | None = None,
    expected_ref: str | None = None,
) -> tuple[Path, bytes]:
    if not isinstance(binding, dict) or set(binding) != {"ref", "sha256"}:
        raise ValueError(f"{label} binding requires exactly ref and sha256")
    digest = str(binding.get("sha256") or "")
    if not SHA256.fullmatch(digest):
        raise ValueError(f"{label} binding has an invalid SHA-256")
    path = safe_regular_file(
        root,
        str(binding.get("ref") or ""),
        label,
        expected_prefix=expected_prefix,
        expected_ref=expected_ref,
    )
    body = path.read_bytes()
    if sha256_bytes(body) != digest:
        raise ValueError(f"{label} bytes do not match the bound SHA-256")
    return path, body


def read_bound_json(
    root: Path,
    binding: Any,
    label: str,
    *,
    expected_prefix: str | None = None,
    expected_ref: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    path, body = read_bound_bytes(
        root,
        binding,
        label,
        expected_prefix=expected_prefix,
        expected_ref=expected_ref,
    )
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must contain a UTF-8 JSON object") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return path, value


def _safe_directory(root: Path, parts: Iterable[str], *, create: bool) -> Path:
    current = root.resolve(strict=True)
    for part in parts:
        current /= part
        if current.is_symlink():
            raise ValueError("legacy retirement store cannot traverse a symlink")
        if current.exists():
            if not current.is_dir():
                raise ValueError("legacy retirement store component is not a directory")
        elif create:
            current.mkdir()
        else:
            return current
    return current


def store_root(root: Path, *, create: bool = False) -> Path:
    return _safe_directory(
        root,
        (".task", "task_pack_retirement"),
        create=create,
    )


def category_dir(root: Path, category: str, *, create: bool = False) -> Path:
    if category not in {
        "snapshots",
        "prepares",
        "overlays",
        "completions",
        "activations",
    }:
        raise ValueError("unknown legacy retirement artifact category")
    return _safe_directory(
        root,
        (".task", "task_pack_retirement", category),
        create=create,
    )


def artifact_ref(category: str, artifact_id: str) -> str:
    if not RETIREMENT_ID.fullmatch(artifact_id):
        raise ValueError("invalid legacy retirement artifact id")
    return f"{STORE_REF}/{category}/{artifact_id}.json"


def artifact_path(
    root: Path,
    category: str,
    artifact_id: str,
    *,
    create_parent: bool = False,
) -> Path:
    return category_dir(root, category, create=create_parent) / f"{artifact_id}.json"


def write_once(
    root: Path, category: str, artifact_id: str, body: bytes
) -> dict[str, str]:
    path = artifact_path(root, category, artifact_id, create_parent=True)
    if path.is_symlink():
        raise ValueError("legacy retirement artifact cannot be a symlink")
    digest = sha256_bytes(body)
    if path.exists():
        if not path.is_file() or sha256_file(path) != digest:
            raise ValueError("legacy retirement immutable artifact conflicts")
        return {"ref": artifact_ref(category, artifact_id), "sha256": digest}
    descriptor, temporary_value = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_value)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        temporary.unlink(missing_ok=True)
    if sha256_file(path) != digest:
        raise ValueError("legacy retirement artifact failed post-write verification")
    return {"ref": artifact_ref(category, artifact_id), "sha256": digest}


def scan_category(root: Path, category: str) -> list[Path]:
    directory = category_dir(root, category, create=False)
    if not directory.exists():
        return []
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("legacy retirement artifact directory is unsafe")
    result: list[Path] = []
    for path in sorted(directory.iterdir()):
        if path.name.startswith("."):
            continue
        if path.suffix != ".json" or path.is_symlink() or not path.is_file():
            raise ValueError("legacy retirement store contains an unexpected entry")
        if not RETIREMENT_ID.fullmatch(path.stem):
            raise ValueError(
                "legacy retirement store contains an invalid artifact name"
            )
        if path.stat().st_size > MAX_RETIREMENT_ARTIFACT_BYTES:
            raise ValueError("legacy retirement artifact exceeds the size limit")
        result.append(path)
    return result


def binding_for(root: Path, path: Path) -> dict[str, str]:
    return {
        "ref": path.relative_to(root.resolve(strict=True)).as_posix(),
        "sha256": sha256_file(path),
    }


__all__ = (
    "MAX_RETIREMENT_ARTIFACT_BYTES",
    "RETIREMENT_ID",
    "SHA256",
    "STORE_REF",
    "artifact_path",
    "artifact_ref",
    "binding_for",
    "canonical_sha256",
    "category_dir",
    "display_bytes",
    "read_bound_bytes",
    "read_bound_json",
    "safe_regular_file",
    "scan_category",
    "sha256_bytes",
    "sha256_file",
    "store_root",
    "write_once",
)
