"""Guarded atomic and immutable writes for selection-publication GC."""

from __future__ import annotations

import contextlib
import os
from pathlib import Path, PurePosixPath
from typing import Iterator

from .selection_publication_gc_fs import (
    BoundParent,
    bound_parent,
    read_leaf,
    sha256_relative,
)
from .selection_publication_producer_capability import (
    _SELECTION_PUBLICATION_GC_EXCLUSIVE_CAPABILITY,
    _active_reference_barrier_mode,
    _require_selection_publication_gc_exclusive,
    _require_selection_publication_producer,
)
from .selection_publication_store import _sha256_bytes


@contextlib.contextmanager
def _write_authority(
    root: Path, producer_capability: object
) -> Iterator[None]:
    """Require a registered shared writer or a proved exclusive GC writer."""

    if producer_capability is _SELECTION_PUBLICATION_GC_EXCLUSIVE_CAPABILITY:
        _require_selection_publication_gc_exclusive(
            producer_capability, root
        )
        yield
        return
    _require_selection_publication_producer(producer_capability)
    active_mode = _active_reference_barrier_mode(root)
    if active_mode == "exclusive":
        raise ValueError(
            "selection-publication writes under the exclusive barrier require "
            "the GC-exclusive capability"
        )
    if active_mode == "shared":
        yield
        return
    from .selection_publication_reference_barrier import (
        reference_producer_barrier,
    )

    with reference_producer_barrier(root):
        yield


def _write_payload_unlocked(
    descriptor: int, payload: bytes, mode: int = 0o600
) -> None:
    os.fchmod(descriptor, mode)
    with os.fdopen(descriptor, "wb", closefd=False) as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def write_payload(
    descriptor: int,
    payload: bytes,
    mode: int = 0o600,
    *,
    root: Path,
    producer_capability: object,
) -> None:
    with _write_authority(root, producer_capability):
        _write_payload_unlocked(descriptor, payload, mode)


def _temporary_name(name: str, payload: bytes) -> str:
    return f".{name}.{os.getpid()}.{id(payload):x}.tmp"


def write_once_relative(
    root: Path,
    relative: str | PurePosixPath,
    payload: bytes,
    label: str,
    *,
    producer_capability: object,
) -> tuple[str, bool]:
    with _write_authority(root, producer_capability):
        digest = _sha256_bytes(payload)
        with bound_parent(root, relative, create=True) as parent:
            existing = read_leaf(parent, label, required=False)
            if existing is not None:
                if existing != payload:
                    raise ValueError(
                        f"{label} conflicts with immutable transaction evidence"
                    )
                return digest, False
            temporary = _temporary_name(parent.name, payload)
            flags = (
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | os.O_NOFOLLOW
                | getattr(os, "O_CLOEXEC", 0)
            )
            try:
                descriptor = os.open(
                    temporary, flags, 0o600, dir_fd=parent.descriptor
                )
                try:
                    _write_payload_unlocked(descriptor, payload)
                    created = _link_immutable(
                        parent, temporary, payload, label
                    )
                finally:
                    os.close(descriptor)
            finally:
                try:
                    os.unlink(temporary, dir_fd=parent.descriptor)
                except FileNotFoundError:
                    pass
        if not created:
            return digest, False
        if sha256_relative(root, relative, label) != digest:
            raise ValueError(f"{label} failed post-write verification")
        return digest, True


def replace_relative(
    root: Path,
    relative: str | PurePosixPath,
    payload: bytes,
    label: str,
    *,
    producer_capability: object,
) -> tuple[str, bool]:
    """Atomically replace one guarded regular leaf with exact bytes."""

    with _write_authority(root, producer_capability):
        digest = _sha256_bytes(payload)
        with bound_parent(root, relative, create=True) as parent:
            existing = read_leaf(parent, label, required=False)
            if existing == payload:
                return digest, False
            temporary = _temporary_name(parent.name, payload)
            flags = (
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | os.O_NOFOLLOW
                | getattr(os, "O_CLOEXEC", 0)
            )
            try:
                descriptor = os.open(
                    temporary, flags, 0o600, dir_fd=parent.descriptor
                )
                try:
                    _write_payload_unlocked(descriptor, payload)
                finally:
                    os.close(descriptor)
                parent.verify()
                os.replace(
                    temporary,
                    parent.name,
                    src_dir_fd=parent.descriptor,
                    dst_dir_fd=parent.descriptor,
                )
                os.fsync(parent.descriptor)
                parent.verify()
            finally:
                try:
                    os.unlink(temporary, dir_fd=parent.descriptor)
                except FileNotFoundError:
                    pass
        if sha256_relative(root, relative, label) != digest:
            raise ValueError(f"{label} failed post-replace verification")
        return digest, True


def _link_immutable(
    parent: BoundParent, temporary: str, payload: bytes, label: str
) -> bool:
    parent.verify()
    try:
        os.link(
            temporary,
            parent.name,
            src_dir_fd=parent.descriptor,
            dst_dir_fd=parent.descriptor,
            follow_symlinks=False,
        )
    except FileExistsError:
        existing = read_leaf(parent, label)
        if existing != payload:
            raise ValueError(
                f"{label} conflicts with immutable transaction evidence"
            )
        return False
    os.fsync(parent.descriptor)
    parent.verify()
    return True


__all__ = ("replace_relative", "write_once_relative", "write_payload")
