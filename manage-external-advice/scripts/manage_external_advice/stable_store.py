"""Directory-bound filesystem primitives for external-advice artifacts."""

from __future__ import annotations

import contextlib
import fcntl
import os
from pathlib import Path, PurePosixPath
import stat
from typing import Any, Iterator
import uuid


_MISSING = object()
_ADVICE_ROOT = ".agent_advice"


def _relative(root: Path, path: str | Path) -> tuple[Path, PurePosixPath]:
    root_path = root.resolve(strict=True)
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            candidate = candidate.relative_to(root_path)
        except ValueError as error:
            raise SystemExit("External-advice path escapes the workspace") from error
    relative = PurePosixPath(candidate.as_posix())
    if (
        not relative.parts
        or relative.is_absolute()
        or relative.as_posix() != candidate.as_posix()
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise SystemExit("External-advice path must be canonical and workspace-relative")
    return root_path, relative


def _owned_relative(root: Path, path: str | Path) -> tuple[Path, PurePosixPath]:
    root_path, relative = _relative(root, path)
    if relative.parts[0] != _ADVICE_ROOT:
        raise SystemExit("External-advice publication must stay in its owned store")
    return root_path, relative


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _identity(descriptor: int) -> tuple[int, int]:
    observed = os.fstat(descriptor)
    if not stat.S_ISDIR(observed.st_mode):
        raise SystemExit("External-advice path ancestor is not a directory")
    return observed.st_dev, observed.st_ino


def _open_directory(name: str | Path, *, dir_fd: int | None = None) -> int:
    try:
        return os.open(name, _directory_flags(), dir_fd=dir_fd)
    except OSError as error:
        raise SystemExit(
            "External-advice path ancestors must be stable real directories"
        ) from error


@contextlib.contextmanager
def _parent_descriptor(
    root: Path,
    path: str | Path,
    *,
    create: bool,
) -> Iterator[tuple[Path, PurePosixPath, int | None, tuple[tuple[int, int], ...]]]:
    root_path, relative = _relative(root, path)
    descriptors: list[int] = []
    try:
        root_descriptor = _open_directory(root_path)
        descriptors.append(root_descriptor)
        identities = [_identity(root_descriptor)]
        current = root_descriptor
        for part in relative.parent.parts:
            try:
                child = os.open(part, _directory_flags(), dir_fd=current)
            except FileNotFoundError:
                if not create:
                    yield root_path, relative, None, tuple(identities)
                    return
                try:
                    os.mkdir(part, mode=0o700, dir_fd=current)
                except FileExistsError:
                    pass
                child = _open_directory(part, dir_fd=current)
            except OSError as error:
                raise SystemExit(
                    "External-advice path ancestors must be stable real directories"
                ) from error
            descriptors.append(child)
            identities.append(_identity(child))
            current = child
        yield root_path, relative, current, tuple(identities)
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _verify_directory_identity(
    root_path: Path,
    relative_parent: PurePosixPath,
    expected: tuple[tuple[int, int], ...],
) -> None:
    descriptors: list[int] = []
    try:
        current = _open_directory(root_path)
        descriptors.append(current)
        observed = [_identity(current)]
        for part in relative_parent.parts:
            current = _open_directory(part, dir_fd=current)
            descriptors.append(current)
            observed.append(_identity(current))
        if tuple(observed) != expected:
            raise SystemExit(
                "External-advice path ancestor identity changed during access"
            )
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _read_leaf(parent: int, name: str, label: str) -> bytes | None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise SystemExit(f"{label} must be a regular non-symlink file") from error
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise SystemExit(f"{label} must be a regular non-symlink file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    finally:
        os.close(descriptor)


def read_regular(
    root: Path,
    path: str | Path,
    *,
    missing: Any = _MISSING,
    label: str = "External-advice file",
) -> Any:
    """Read one regular file through stable directory descriptors."""

    with _parent_descriptor(root, path, create=False) as (
        root_path,
        relative,
        parent,
        identities,
    ):
        if parent is None:
            if missing is _MISSING:
                raise SystemExit(f"Required {label} is missing: {relative}")
            return missing
        payload = _read_leaf(parent, relative.name, label)
        _verify_directory_identity(root_path, relative.parent, identities)
        if payload is None:
            if missing is _MISSING:
                raise SystemExit(f"Required {label} is missing: {relative}")
            return missing
        return payload


def ensure_parent(root: Path, path: str | Path) -> None:
    """Create one owned parent chain without following symlinks."""

    root_path, relative = _owned_relative(root, path)
    with _parent_descriptor(root_path, relative, create=True) as (
        observed_root,
        observed_relative,
        parent,
        identities,
    ):
        assert parent is not None
        _verify_directory_identity(
            observed_root, observed_relative.parent, identities
        )


def _write_payload(descriptor: int, payload: bytes, mode: int) -> None:
    os.fchmod(descriptor, mode)
    with os.fdopen(descriptor, "wb", closefd=False) as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def publish_immutable(
    root: Path,
    path: str | Path,
    payload: bytes,
    mode: int = 0o600,
) -> bool:
    """Publish exact immutable bytes through one bound parent descriptor."""

    root_path, relative = _owned_relative(root, path)
    with _parent_descriptor(root_path, relative, create=True) as (
        observed_root,
        observed_relative,
        parent,
        identities,
    ):
        assert parent is not None
        _verify_directory_identity(
            observed_root, observed_relative.parent, identities
        )
        existing = _read_leaf(parent, observed_relative.name, "Immutable advice target")
        _verify_directory_identity(
            observed_root, observed_relative.parent, identities
        )
        if existing is not None:
            if existing != payload:
                raise SystemExit(
                    f"Immutable advice publication conflict: {observed_relative}"
                )
            return False
        temporary = f".{observed_relative.name}.{uuid.uuid4().hex}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary, flags, mode, dir_fd=parent)
        try:
            _write_payload(descriptor, payload, mode)
            _verify_directory_identity(
                observed_root, observed_relative.parent, identities
            )
            try:
                os.link(
                    temporary,
                    observed_relative.name,
                    src_dir_fd=parent,
                    dst_dir_fd=parent,
                    follow_symlinks=False,
                )
            except FileExistsError:
                existing = _read_leaf(
                    parent, observed_relative.name, "Immutable advice target"
                )
                _verify_directory_identity(
                    observed_root, observed_relative.parent, identities
                )
                if existing != payload:
                    raise SystemExit(
                        f"Immutable advice publication conflict: {observed_relative}"
                    )
                return False
            os.fsync(parent)
            _verify_directory_identity(
                observed_root, observed_relative.parent, identities
            )
        finally:
            os.close(descriptor)
            try:
                os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError:
                pass
    if read_regular(root_path, relative, label="Published immutable advice") != payload:
        raise SystemExit("Immutable advice publication did not preserve exact bytes")
    return True


def atomic_replace(
    root: Path,
    path: str | Path,
    payload: bytes,
    mode: int = 0o600,
) -> None:
    """Atomically replace one owned regular file through a bound parent."""

    root_path, relative = _owned_relative(root, path)
    with _parent_descriptor(root_path, relative, create=True) as (
        observed_root,
        observed_relative,
        parent,
        identities,
    ):
        assert parent is not None
        _verify_directory_identity(
            observed_root, observed_relative.parent, identities
        )
        _read_leaf(parent, observed_relative.name, "Advice registry target")
        temporary = f".{observed_relative.name}.{uuid.uuid4().hex}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary, flags, mode, dir_fd=parent)
        try:
            _write_payload(descriptor, payload, mode)
            _verify_directory_identity(
                observed_root, observed_relative.parent, identities
            )
            os.replace(
                temporary,
                observed_relative.name,
                src_dir_fd=parent,
                dst_dir_fd=parent,
            )
            os.fsync(parent)
            _verify_directory_identity(
                observed_root, observed_relative.parent, identities
            )
            if _read_leaf(
                parent, observed_relative.name, "Advice registry target"
            ) != payload:
                raise SystemExit("Advice registry replacement changed exact bytes")
        finally:
            os.close(descriptor)
            try:
                os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError:
                pass


@contextlib.contextmanager
def locked_file(root: Path, path: str | Path) -> Iterator[None]:
    """Hold one regular-file lock under a stable owned parent chain."""

    root_path, relative = _owned_relative(root, path)
    with _parent_descriptor(root_path, relative, create=True) as (
        observed_root,
        observed_relative,
        parent,
        identities,
    ):
        assert parent is not None
        _verify_directory_identity(
            observed_root, observed_relative.parent, identities
        )
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(observed_relative.name, flags, 0o600, dir_fd=parent)
        except OSError as error:
            raise SystemExit("External-advice lock path is unsafe") from error
        with os.fdopen(descriptor, "a+b") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise SystemExit("External-advice lock must be a regular file")
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                _verify_directory_identity(
                    observed_root, observed_relative.parent, identities
                )
                yield
            finally:
                try:
                    _verify_directory_identity(
                        observed_root, observed_relative.parent, identities
                    )
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


__all__ = [
    "atomic_replace",
    "ensure_parent",
    "locked_file",
    "publish_immutable",
    "read_regular",
]
