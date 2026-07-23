"""Pinned descriptor traversal for selection-publication retention scans."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import stat
from typing import Iterator

from .selection_publication_gc_fs import (
    BoundDirectory,
    bound_directory,
    directory_flags,
    directory_identity,
    file_flags,
    file_signature,
    verify_directory_chain,
)


@dataclass(frozen=True)
class PinnedWalkFile:
    """A file yielded while all of its ancestor descriptors remain open."""

    ref: str
    parent_descriptor: int
    name: str
    metadata: os.stat_result


def _read_descriptor(descriptor: int, label: str, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        size = min(1024 * 1024, max_bytes + 1 - total)
        if size <= 0:
            raise ValueError(f"{label} exceeds its byte bound")
        chunk = os.read(descriptor, size)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > max_bytes:
            raise ValueError(f"{label} exceeds its byte bound")
    return b"".join(chunks)


def read_pinned_walk_file(
    value: PinnedWalkFile,
    label: str,
    *,
    max_bytes: int,
) -> bytes:
    """Read one fd-relative walk leaf and prove its entry stayed identical."""

    if value.metadata.st_size > max_bytes:
        raise ValueError(f"{label} exceeds its byte bound")
    try:
        descriptor = os.open(
            value.name, file_flags(), dir_fd=value.parent_descriptor
        )
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or file_signature(opened) != file_signature(value.metadata)
            ):
                raise ValueError(f"{label} changed during acquisition")
            payload = _read_descriptor(descriptor, label, max_bytes)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        visible = os.stat(
            value.name,
            dir_fd=value.parent_descriptor,
            follow_symlinks=False,
        )
    except OSError as exc:
        raise ValueError(f"{label} changed during acquisition") from exc
    if (
        file_signature(opened) != file_signature(after)
        or file_signature(after) != file_signature(visible)
    ):
        raise ValueError(f"{label} changed during acquisition")
    return payload


def walk_regular_files_fd(
    root: Path,
    *,
    start: str | PurePosixPath | None = None,
    skip_prefixes: tuple[tuple[str, ...], ...] = (),
    recursive: bool = True,
) -> Iterator[PinnedWalkFile]:
    """Walk regular files using only pinned descriptors after root acquisition."""

    root = root.resolve(strict=True)
    if start is None:
        descriptor = os.open(root, directory_flags())
        relative = PurePosixPath()
        identities = (directory_identity(descriptor),)
        manager: contextlib.AbstractContextManager[BoundDirectory] | None = None
    else:
        manager = bound_directory(root, start, create=False)
        directory = manager.__enter__()
        descriptor = directory.descriptor
        relative = directory.relative
        identities = directory.identities
    try:
        yield from _walk_directory_descriptor(
            descriptor,
            relative.parts,
            skip_prefixes=skip_prefixes,
            recursive=recursive,
        )
        verify_directory_chain(root, relative.parts, identities)
    finally:
        if manager is None:
            os.close(descriptor)
        else:
            manager.__exit__(None, None, None)


def _walk_directory_descriptor(
    descriptor: int,
    parts: tuple[str, ...],
    *,
    skip_prefixes: tuple[tuple[str, ...], ...],
    recursive: bool,
) -> Iterator[PinnedWalkFile]:
    before = os.fstat(descriptor)
    try:
        names = sorted(os.listdir(descriptor))
    except OSError as exc:
        raise ValueError(
            "selection-publication gc cannot enumerate a pinned directory"
        ) from exc
    if file_signature(before) != file_signature(os.fstat(descriptor)):
        raise ValueError(
            "selection-publication gc directory changed during enumeration"
        )
    for name in names:
        child_parts = (*parts, name)
        if any(child_parts[: len(prefix)] == prefix for prefix in skip_prefixes):
            continue
        metadata = _entry_metadata(descriptor, name)
        if stat.S_ISDIR(metadata.st_mode):
            if not recursive:
                raise ValueError(
                    "selection-publication CAS contains a nested directory"
                )
            yield from _walk_child_directory(
                descriptor,
                name,
                child_parts,
                metadata,
                skip_prefixes=skip_prefixes,
            )
        elif stat.S_ISREG(metadata.st_mode):
            yield PinnedWalkFile(
                PurePosixPath(*child_parts).as_posix(),
                descriptor,
                name,
                metadata,
            )
            _verify_visible_entry(descriptor, name, metadata)
        else:
            raise ValueError(
                "selection-publication gc refuses a non-regular workspace entry"
            )
    if file_signature(before) != file_signature(os.fstat(descriptor)):
        raise ValueError(
            "selection-publication gc directory changed during traversal"
        )


def _entry_metadata(descriptor: int, name: str) -> os.stat_result:
    try:
        return os.stat(name, dir_fd=descriptor, follow_symlinks=False)
    except OSError as exc:
        raise ValueError(
            "selection-publication gc entry changed during enumeration"
        ) from exc


def _verify_visible_entry(
    descriptor: int, name: str, expected: os.stat_result
) -> None:
    try:
        visible = os.stat(
            name, dir_fd=descriptor, follow_symlinks=False
        )
    except OSError as exc:
        raise ValueError(
            "selection-publication gc file changed during scan"
        ) from exc
    if file_signature(visible) != file_signature(expected):
        raise ValueError(
            "selection-publication gc file changed during scan"
        )


def _walk_child_directory(
    descriptor: int,
    name: str,
    child_parts: tuple[str, ...],
    metadata: os.stat_result,
    *,
    skip_prefixes: tuple[tuple[str, ...], ...],
) -> Iterator[PinnedWalkFile]:
    try:
        child = os.open(name, directory_flags(), dir_fd=descriptor)
    except OSError as exc:
        raise ValueError(
            "selection-publication gc directory became unsafe"
        ) from exc
    try:
        identity = (metadata.st_dev, metadata.st_ino)
        if directory_identity(child) != identity:
            raise ValueError(
                "selection-publication gc directory identity changed"
            )
        yield from _walk_directory_descriptor(
            child,
            child_parts,
            skip_prefixes=skip_prefixes,
            recursive=True,
        )
        visible = os.stat(
            name, dir_fd=descriptor, follow_symlinks=False
        )
        if directory_identity(child) != (visible.st_dev, visible.st_ino):
            raise ValueError(
                "selection-publication gc directory identity changed"
            )
    finally:
        os.close(child)


__all__ = ("PinnedWalkFile", "read_pinned_walk_file", "walk_regular_files_fd")
