"""Safe immutable storage and one CAS pointer for terminal-wait baselines."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
from typing import Any, Iterator


try:
    import fcntl
except ImportError:  # pragma: no cover - POSIX is the production path.
    fcntl = None  # type: ignore[assignment]


STORE_REF = ".task/terminal_wait_baseline"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ARTIFACT_ID = re.compile(
    r"^(?:twbp|twbc|twba|twbr)-[0-9a-f]{32}$|^[0-9a-f]{64}$"
)
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_CATEGORY_ARTIFACTS = 4096


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def display_bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


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


def safe_regular_file(root: Path, ref: str, label: str) -> Path:
    root = root.resolve(strict=True)
    path, parts = _inside(root, ref, label)
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
    if path.stat().st_size > MAX_ARTIFACT_BYTES:
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
    ref = binding.get("ref")
    digest = binding.get("sha256")
    if (
        not isinstance(ref, str)
        or not isinstance(digest, str)
        or not SHA256.fullmatch(digest)
    ):
        raise ValueError(f"{label} binding has an invalid SHA-256")
    if expected_ref is not None and ref != expected_ref:
        raise ValueError(f"{label} ref does not match its deterministic location")
    if expected_prefix is not None and not ref.startswith(
        expected_prefix.rstrip("/") + "/"
    ):
        raise ValueError(f"{label} is outside its owned store")
    path = safe_regular_file(root, ref, label)
    with path.open("rb") as handle:
        body = handle.read(MAX_ARTIFACT_BYTES + 1)
    if len(body) > MAX_ARTIFACT_BYTES:
        raise ValueError(f"{label} exceeds the artifact size limit")
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


def _safe_directory(root: Path, parts: tuple[str, ...], *, create: bool) -> Path:
    current = root.resolve(strict=True)
    missing_parent = False
    for part in parts:
        current /= part
        if missing_parent:
            if create:
                current.mkdir()
            continue
        if current.is_symlink():
            raise ValueError("terminal-wait baseline store cannot traverse a symlink")
        if current.exists():
            if not current.is_dir():
                raise ValueError(
                    "terminal-wait baseline store component is not a directory"
                )
        elif create:
            current.mkdir()
        else:
            missing_parent = True
    return current


def store_root(root: Path, *, create: bool = False) -> Path:
    return _safe_directory(root, (".task", "terminal_wait_baseline"), create=create)


def category_dir(root: Path, category: str, *, create: bool = False) -> Path:
    if category not in {
        "subjects",
        "prepares",
        "snapshots",
        "completions",
        "activations",
        "pointers",
        "retirements",
    }:
        raise ValueError("unknown terminal-wait baseline artifact category")
    return _safe_directory(
        root,
        (".task", "terminal_wait_baseline", category),
        create=create,
    )


def artifact_ref(category: str, artifact_id: str) -> str:
    if not ARTIFACT_ID.fullmatch(artifact_id):
        raise ValueError("invalid terminal-wait baseline artifact id")
    return f"{STORE_REF}/{category}/{artifact_id}.json"


def artifact_path(
    root: Path,
    category: str,
    artifact_id: str,
    *,
    create_parent: bool = False,
) -> Path:
    return category_dir(root, category, create=create_parent) / f"{artifact_id}.json"


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
        _fsync_dir(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def write_once(
    root: Path, category: str, artifact_id: str, body: bytes
) -> dict[str, str]:
    path = artifact_path(root, category, artifact_id, create_parent=True)
    digest = sha256_bytes(body)
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file() or sha256_file(path) != digest:
            raise ValueError("terminal-wait baseline immutable artifact conflicts")
        return {"ref": artifact_ref(category, artifact_id), "sha256": digest}
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_value = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_value)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
            _fsync_dir(path.parent)
        except FileExistsError:
            if path.is_symlink() or not path.is_file() or sha256_file(path) != digest:
                raise ValueError("terminal-wait baseline immutable artifact conflicts")
    finally:
        temporary.unlink(missing_ok=True)
    if sha256_file(path) != digest:
        raise ValueError("terminal-wait baseline artifact failed verification")
    return {"ref": artifact_ref(category, artifact_id), "sha256": digest}


def current_path(root: Path, *, create_parent: bool = False) -> Path:
    return store_root(root, create=create_parent) / "current.json"


def read_current_bytes(root: Path) -> bytes | None:
    path = current_path(root)
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise ValueError("terminal-wait baseline current pointer is unsafe")
    if path.stat().st_size > MAX_ARTIFACT_BYTES:
        raise ValueError("terminal-wait baseline current pointer is oversized")
    with path.open("rb") as handle:
        body = handle.read(MAX_ARTIFACT_BYTES + 1)
    if len(body) > MAX_ARTIFACT_BYTES:
        raise ValueError("terminal-wait baseline current pointer is oversized")
    return body


def write_current(root: Path, body: bytes) -> dict[str, str]:
    path = current_path(root, create_parent=True)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("terminal-wait baseline current pointer is unsafe")
    _atomic_write(path, body)
    digest = sha256_bytes(body)
    if sha256_file(path) != digest:
        raise ValueError("terminal-wait baseline current pointer failed verification")
    return {"ref": f"{STORE_REF}/current.json", "sha256": digest}


def scan_category(root: Path, category: str) -> list[Path]:
    directory = category_dir(root, category)
    if not directory.exists():
        return []
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("terminal-wait baseline artifact directory is unsafe")
    result: list[Path] = []
    for path in directory.iterdir():
        if path.name.startswith("."):
            continue
        if len(result) >= MAX_CATEGORY_ARTIFACTS:
            raise ValueError(
                "terminal-wait baseline artifact category exceeds its entry limit"
            )
        if (
            path.suffix != ".json"
            or path.is_symlink()
            or not path.is_file()
            or not ARTIFACT_ID.fullmatch(path.stem)
        ):
            raise ValueError("terminal-wait baseline store has an unexpected entry")
        result.append(path)
    return sorted(result, key=lambda path: path.name)


@contextlib.contextmanager
def mutation_lock(root: Path) -> Iterator[None]:
    store = store_root(root, create=True)
    path = store / ".lock"
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("terminal-wait baseline lock is unsafe")
    with path.open("a+b") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


__all__ = (
    "MAX_CATEGORY_ARTIFACTS",
    "SHA256",
    "STORE_REF",
    "artifact_ref",
    "canonical_sha256",
    "current_path",
    "display_bytes",
    "mutation_lock",
    "read_bound_bytes",
    "read_bound_json",
    "read_current_bytes",
    "safe_regular_file",
    "scan_category",
    "sha256_bytes",
    "sha256_file",
    "write_current",
    "write_once",
)
