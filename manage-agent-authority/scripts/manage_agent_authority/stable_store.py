"""Directory-bound filesystem primitives for authority-owned artifacts."""

from __future__ import annotations

import contextlib
import fcntl
import os
from pathlib import Path
import stat
from typing import Iterator
import uuid


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
        raise SystemExit("Authority artifact ancestor is not a directory.")
    return observed.st_dev, observed.st_ino


def _file_signature(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _absolute(path: Path) -> Path:
    if not path.is_absolute():
        raise SystemExit("Authority artifact paths must be absolute.")
    if any(part in {"", ".", ".."} for part in path.parts[1:]):
        raise SystemExit("Authority artifact path must be canonical.")
    return path


def _open_directory(name: str | Path, *, dir_fd: int | None = None) -> int:
    try:
        return os.open(name, _directory_flags(), dir_fd=dir_fd)
    except OSError as exc:
        raise SystemExit(
            "Authority artifact ancestors must be stable real directories."
        ) from exc


@contextlib.contextmanager
def _parent_descriptor(
    path: Path, *, create: bool
) -> Iterator[tuple[Path, int | None, tuple[tuple[int, int], ...]]]:
    target = _absolute(path)
    descriptors: list[int] = []
    try:
        current = _open_directory(Path(target.anchor))
        descriptors.append(current)
        identities = [_identity(current)]
        for part in target.parent.parts[1:]:
            try:
                child = os.open(part, _directory_flags(), dir_fd=current)
            except FileNotFoundError:
                if not create:
                    yield target, None, tuple(identities)
                    return
                try:
                    os.mkdir(part, mode=0o700, dir_fd=current)
                except FileExistsError:
                    pass
                child = _open_directory(part, dir_fd=current)
            except OSError as exc:
                raise SystemExit(
                    "Authority artifact ancestors must be stable real directories."
                ) from exc
            descriptors.append(child)
            identities.append(_identity(child))
            current = child
        yield target, current, tuple(identities)
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _verify_parent(path: Path, expected: tuple[tuple[int, int], ...]) -> None:
    descriptors: list[int] = []
    try:
        current = _open_directory(Path(path.anchor))
        descriptors.append(current)
        observed = [_identity(current)]
        for part in path.parent.parts[1:]:
            current = _open_directory(part, dir_fd=current)
            descriptors.append(current)
            observed.append(_identity(current))
        if tuple(observed) != expected:
            raise SystemExit(
                "Authority artifact ancestor identity changed during access."
            )
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _read_leaf(
    parent: int, name: str, label: str, *, max_bytes: int | None = None
) -> bytes | None:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(name, flags, dir_fd=parent)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise SystemExit(f"{label} must be a regular non-symlink file.") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise SystemExit(f"{label} must be a regular non-symlink file.")
        if max_bytes is not None and (max_bytes < 1 or before.st_size > max_bytes):
            raise SystemExit(f"{label} exceeds the {max_bytes}-byte safety limit.")
        chunks: list[bytes] = []
        total = 0
        while True:
            read_size = 1024 * 1024
            if max_bytes is not None:
                read_size = min(read_size, max_bytes + 1 - total)
                if read_size <= 0:
                    raise SystemExit(
                        f"{label} exceeds the {max_bytes}-byte safety limit."
                    )
            chunk = os.read(descriptor, read_size)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if max_bytes is not None and total > max_bytes:
                raise SystemExit(f"{label} exceeds the {max_bytes}-byte safety limit.")
        after = os.fstat(descriptor)
        try:
            path_after = os.stat(name, dir_fd=parent, follow_symlinks=False)
        except OSError as exc:
            raise SystemExit(f"{label} changed during acquisition.") from exc
        if _file_signature(before) != _file_signature(after) or _file_signature(
            after
        ) != _file_signature(path_after):
            raise SystemExit(f"{label} changed during acquisition.")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _race_hook(stage: str, path: Path) -> None:
    """Test seam for deterministic ancestor-swap regressions."""

    _ = stage, path


def read_regular(
    path: Path,
    *,
    required: bool = True,
    label: str = "artifact",
    max_bytes: int | None = None,
) -> bytes | None:
    """Read exact bytes without following a replaced ancestor or leaf symlink."""

    with _parent_descriptor(path, create=False) as (target, parent, identities):
        if parent is None:
            if required:
                raise SystemExit(f"Required {label} is missing: {target}")
            return None
        payload = _read_leaf(parent, target.name, label, max_bytes=max_bytes)
        _race_hook("after_read", target)
        _verify_parent(target, identities)
        if payload is None and required:
            raise SystemExit(f"Required {label} is missing: {target}")
        return payload


def _write_payload(descriptor: int, payload: bytes, mode: int) -> None:
    os.fchmod(descriptor, mode)
    with os.fdopen(descriptor, "wb", closefd=False) as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def publish_immutable(path: Path, payload: bytes, *, mode: int = 0o600) -> bool:
    """Publish exact bytes once through a bound parent descriptor."""

    with _parent_descriptor(path, create=True) as (target, parent, identities):
        assert parent is not None
        _verify_parent(target, identities)
        existing = _read_leaf(parent, target.name, "Immutable authority artifact")
        _race_hook("after_existing_read", target)
        _verify_parent(target, identities)
        if existing is not None:
            if existing != payload:
                raise SystemExit(f"Conflicting authority artifact exists: {target}")
            return False
        temporary = f".{target.name}.{uuid.uuid4().hex}.tmp"
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        descriptor = os.open(temporary, flags, mode, dir_fd=parent)
        try:
            _write_payload(descriptor, payload, mode)
            _race_hook("before_link", target)
            _verify_parent(target, identities)
            try:
                os.link(
                    temporary,
                    target.name,
                    src_dir_fd=parent,
                    dst_dir_fd=parent,
                    follow_symlinks=False,
                )
            except FileExistsError:
                existing = _read_leaf(
                    parent, target.name, "Immutable authority artifact"
                )
                _race_hook("after_conflict_read", target)
                _verify_parent(target, identities)
                if existing != payload:
                    raise SystemExit(f"Conflicting authority artifact exists: {target}")
                return False
            os.fsync(parent)
            _verify_parent(target, identities)
        finally:
            os.close(descriptor)
            try:
                os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError:
                pass
    if read_regular(target, label="published authority artifact") != payload:
        raise SystemExit("Authority publication did not preserve exact bytes.")
    return True


def atomic_replace(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    """Replace one regular authority artifact through a bound parent."""

    with _parent_descriptor(path, create=True) as (target, parent, identities):
        assert parent is not None
        _verify_parent(target, identities)
        _read_leaf(parent, target.name, "Authority state target")
        temporary = f".{target.name}.{uuid.uuid4().hex}.tmp"
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        descriptor = os.open(temporary, flags, mode, dir_fd=parent)
        try:
            _write_payload(descriptor, payload, mode)
            _race_hook("before_replace", target)
            _verify_parent(target, identities)
            os.replace(temporary, target.name, src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
            _verify_parent(target, identities)
            if _read_leaf(parent, target.name, "Authority state target") != payload:
                raise SystemExit("Authority state replacement changed exact bytes.")
        finally:
            os.close(descriptor)
            try:
                os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError:
                pass


@contextlib.contextmanager
def locked_file(path: Path) -> Iterator[None]:
    """Hold the authority lock through a stable parent descriptor."""

    with _parent_descriptor(path, create=True) as (target, parent, identities):
        assert parent is not None
        _verify_parent(target, identities)
        flags = (
            os.O_CREAT
            | os.O_RDWR
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        try:
            descriptor = os.open(target.name, flags, 0o600, dir_fd=parent)
        except OSError as exc:
            raise SystemExit("Authority lock path is unsafe.") from exc
        with os.fdopen(descriptor, "a+b") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise SystemExit("Authority lock must be a regular file.")
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                _race_hook("after_lock", target)
                _verify_parent(target, identities)
                yield
                _verify_parent(target, identities)
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


__all__ = ["atomic_replace", "locked_file", "publish_immutable", "read_regular"]
