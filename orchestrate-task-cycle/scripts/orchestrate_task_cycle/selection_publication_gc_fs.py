"""Stable no-follow filesystem operations for selection-publication GC."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
import json
import os
from pathlib import Path, PurePosixPath
import stat
from typing import Any, Iterator, Sequence

from .selection_publication_gc_contract import (
    MAX_SCAN_FILE_BYTES,
    relative_ref,
)
from .selection_publication_store import _sha256_bytes


def directory_flags() -> int:
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("selection-publication gc requires O_DIRECTORY and O_NOFOLLOW")
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def file_flags() -> int:
    if not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("selection-publication gc requires O_NOFOLLOW")
    return os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def directory_identity(descriptor: int) -> tuple[int, int]:
    observed = os.fstat(descriptor)
    if not stat.S_ISDIR(observed.st_mode):
        raise ValueError("selection-publication gc ancestor is not a directory")
    return observed.st_dev, observed.st_ino


def file_signature(
    value: os.stat_result,
) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


class BoundParent:
    """A stable parent descriptor plus the identities of its visible chain."""

    def __init__(
        self,
        root: Path,
        relative: PurePosixPath,
        descriptor: int,
        identities: tuple[tuple[int, int], ...],
    ) -> None:
        self.root = root
        self.relative = relative
        self.descriptor = descriptor
        self.identities = identities

    @property
    def name(self) -> str:
        return self.relative.name

    def verify(self) -> None:
        verify_directory_chain(self.root, self.relative.parent.parts, self.identities)


class BoundDirectory:
    """One pinned directory and the identities of every visible ancestor."""

    def __init__(
        self,
        root: Path,
        relative: PurePosixPath,
        descriptor: int,
        identities: tuple[tuple[int, int], ...],
    ) -> None:
        self.root = root
        self.relative = relative
        self.descriptor = descriptor
        self.identities = identities

    def verify(self) -> None:
        verify_directory_chain(self.root, self.relative.parts, self.identities)


def verify_directory_chain(
    root: Path,
    parts: Sequence[str],
    identities: tuple[tuple[int, int], ...],
) -> None:
    """Reopen a visible chain without symlinks and compare every inode."""

    descriptors: list[int] = []
    try:
        current = os.open(root, directory_flags())
        descriptors.append(current)
        observed = [directory_identity(current)]
        for part in parts:
            current = os.open(part, directory_flags(), dir_fd=current)
            descriptors.append(current)
            observed.append(directory_identity(current))
    except OSError as exc:
        raise ValueError(
            "selection-publication gc ancestor changed or became unsafe"
        ) from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    if tuple(observed) != identities:
        raise ValueError(
            "selection-publication gc ancestor identity changed during access"
        )


@dataclass
class PinnedLeaf:
    """An open regular leaf bound to its visible directory entry and bytes."""

    parent: BoundParent
    descriptor: int
    signature: tuple[int, int, int, int, int, int]
    payload: bytes
    label: str

    def verify_visible(self) -> None:
        self.parent.verify()
        try:
            opened = os.fstat(self.descriptor)
            visible = os.stat(
                self.parent.name,
                dir_fd=self.parent.descriptor,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise ValueError(f"{self.label} changed after acquisition") from exc
        if (
            file_signature(opened) != self.signature
            or file_signature(visible) != self.signature
            or not stat.S_ISREG(visible.st_mode)
        ):
            raise ValueError(f"{self.label} changed after acquisition")

    def verify_bytes(self, *, max_bytes: int | None = None) -> None:
        self.verify_visible()
        os.lseek(self.descriptor, 0, os.SEEK_SET)
        payload = _read_descriptor(self.descriptor, self.label, max_bytes=max_bytes)
        after = os.fstat(self.descriptor)
        if payload != self.payload or file_signature(after) != self.signature:
            raise ValueError(f"{self.label} bytes changed after acquisition")
        self.verify_visible()

    def close(self) -> None:
        os.close(self.descriptor)


class MissingArtifactParent(ValueError):
    pass


@contextlib.contextmanager
def bound_parent(
    root: Path,
    relative: str | PurePosixPath,
    *,
    create: bool,
) -> Iterator[BoundParent]:
    target = relative_ref(relative, "selection-publication gc artifact ref")
    descriptors: list[int] = []
    try:
        from .selection_publication_producer_capability import (
            _active_reference_barrier_descriptor,
        )

        try:
            current = _active_reference_barrier_descriptor(root)
            if current is None:
                current = os.open(root, directory_flags())
        except OSError as exc:
            raise ValueError(
                "selection-publication gc workspace root is unsafe"
            ) from exc
        descriptors.append(current)
        identities = [directory_identity(current)]
        for part in target.parent.parts:
            try:
                child = os.open(part, directory_flags(), dir_fd=current)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, mode=0o700, dir_fd=current)
                except FileExistsError:
                    pass
                child = os.open(part, directory_flags(), dir_fd=current)
            except OSError as exc:
                raise ValueError(
                    "selection-publication gc ancestor must be a real directory"
                ) from exc
            descriptors.append(child)
            identities.append(directory_identity(child))
            current = child
        yield BoundParent(root, target, current, tuple(identities))
    except FileNotFoundError as exc:
        raise MissingArtifactParent(
            "selection-publication gc artifact parent is missing"
        ) from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _raise_unsafe_directory_component(
    parent_descriptor: int,
    name: str,
    cause: OSError,
) -> None:
    try:
        observed = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except OSError:
        raise ValueError(
            "selection-publication gc directory chain is unsafe"
        ) from cause
    if stat.S_ISLNK(observed.st_mode):
        raise ValueError(
            "selection-publication gc directory component cannot be a symlink"
        ) from cause
    if not stat.S_ISDIR(observed.st_mode):
        raise ValueError(
            "selection-publication gc directory component must be a directory"
        ) from cause
    raise ValueError("selection-publication gc directory chain is unsafe") from cause


@contextlib.contextmanager
def bound_directory(
    root: Path,
    relative: str | PurePosixPath,
    *,
    create: bool,
) -> Iterator[BoundDirectory]:
    target = relative_ref(relative, "selection-publication gc directory ref")
    descriptors: list[int] = []
    try:
        from .selection_publication_producer_capability import (
            _active_reference_barrier_descriptor,
        )

        current = _active_reference_barrier_descriptor(root)
        if current is None:
            current = os.open(root, directory_flags())
        descriptors.append(current)
        identities = [directory_identity(current)]
        for part in target.parts:
            try:
                child = os.open(part, directory_flags(), dir_fd=current)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, mode=0o700, dir_fd=current)
                except FileExistsError:
                    pass
                child = os.open(part, directory_flags(), dir_fd=current)
            except OSError as exc:
                _raise_unsafe_directory_component(current, part, exc)
            descriptors.append(child)
            identities.append(directory_identity(child))
            current = child
        yield BoundDirectory(root, target, current, tuple(identities))
    except FileNotFoundError as exc:
        raise MissingArtifactParent(
            "selection-publication gc directory is missing"
        ) from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def open_pinned_leaf(
    parent: BoundParent,
    label: str,
    *,
    required: bool = True,
    max_bytes: int | None = None,
) -> PinnedLeaf | None:
    """Open and acquire a leaf while retaining its file descriptor."""

    try:
        descriptor = os.open(parent.name, file_flags(), dir_fd=parent.descriptor)
    except FileNotFoundError:
        if required:
            raise ValueError(f"{label} is missing")
        return None
    except OSError as exc:
        raise ValueError(f"{label} must be a regular non-symlink file") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"{label} must be a regular non-symlink file")
        if max_bytes is not None and before.st_size > max_bytes:
            raise ValueError(f"{label} exceeds its byte bound")
        payload = _read_descriptor(descriptor, label, max_bytes=max_bytes)
        after = os.fstat(descriptor)
        visible = os.stat(parent.name, dir_fd=parent.descriptor, follow_symlinks=False)
        signature = file_signature(before)
        if signature != file_signature(after) or signature != file_signature(visible):
            raise ValueError(f"{label} changed during acquisition")
        parent.verify()
        return PinnedLeaf(parent, descriptor, signature, payload, label)
    except BaseException:
        os.close(descriptor)
        raise


def read_leaf(
    parent: BoundParent,
    label: str,
    *,
    required: bool = True,
    max_bytes: int | None = None,
) -> bytes | None:
    pinned = open_pinned_leaf(parent, label, required=required, max_bytes=max_bytes)
    if pinned is None:
        return None
    try:
        return pinned.payload
    finally:
        pinned.close()


def _read_descriptor(descriptor: int, label: str, *, max_bytes: int | None) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        size = 1024 * 1024
        if max_bytes is not None:
            size = min(size, max_bytes + 1 - total)
            if size <= 0:
                raise ValueError(f"{label} exceeds its byte bound")
        chunk = os.read(descriptor, size)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if max_bytes is not None and total > max_bytes:
            raise ValueError(f"{label} exceeds its byte bound")
    return b"".join(chunks)


def read_relative(
    root: Path,
    relative: str | PurePosixPath,
    label: str,
    *,
    required: bool = True,
    max_bytes: int | None = None,
) -> bytes | None:
    try:
        with bound_parent(root, relative, create=False) as parent:
            return read_leaf(parent, label, required=required, max_bytes=max_bytes)
    except MissingArtifactParent:
        if required:
            raise ValueError(f"{label} parent is missing")
        return None


def sha256_relative(
    root: Path, relative: str | PurePosixPath, label: str
) -> str | None:
    payload = read_relative(root, relative, label, required=False)
    return None if payload is None else _sha256_bytes(payload)


def read_json_relative(
    root: Path,
    relative: str | PurePosixPath,
    label: str,
    *,
    max_bytes: int = MAX_SCAN_FILE_BYTES,
) -> tuple[dict[str, Any], bytes]:
    payload = read_relative(root, relative, label, max_bytes=max_bytes)
    assert payload is not None
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value, payload


def artifact_binding(root: Path, relative: str | PurePosixPath) -> dict[str, str]:
    normalized = relative_ref(relative, "retention evidence ref").as_posix()
    digest = sha256_relative(root, normalized, "retention evidence")
    if digest is None:
        raise ValueError("retention evidence is missing")
    return {"ref": normalized, "sha256": digest}


def write_payload(
    descriptor: int,
    payload: bytes,
    mode: int = 0o600,
    *,
    root: Path,
    producer_capability: object,
) -> None:
    from .selection_publication_gc_write import write_payload as write

    write(
        descriptor,
        payload,
        mode,
        root=root,
        producer_capability=producer_capability,
    )


def write_once_relative(
    root: Path,
    relative: str | PurePosixPath,
    payload: bytes,
    label: str,
    *,
    producer_capability: object,
) -> tuple[str, bool]:
    from .selection_publication_gc_write import write_once_relative as write

    return write(
        root,
        relative,
        payload,
        label,
        producer_capability=producer_capability,
    )


def replace_relative(
    root: Path,
    relative: str | PurePosixPath,
    payload: bytes,
    label: str,
    *,
    producer_capability: object,
) -> tuple[str, bool]:
    from .selection_publication_gc_write import replace_relative as replace

    return replace(
        root,
        relative,
        payload,
        label,
        producer_capability=producer_capability,
    )


__all__ = (
    "BoundDirectory",
    "BoundParent",
    "PinnedLeaf",
    "artifact_binding",
    "bound_directory",
    "bound_parent",
    "directory_flags",
    "file_flags",
    "file_signature",
    "open_pinned_leaf",
    "read_json_relative",
    "read_leaf",
    "read_relative",
    "replace_relative",
    "sha256_relative",
    "write_once_relative",
    "write_payload",
    "verify_directory_chain",
)
