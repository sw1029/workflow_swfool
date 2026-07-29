"""No-follow readers for durable continuation artifacts."""

from __future__ import annotations

import errno
import os
from pathlib import Path
import stat

from .contracts import ContinuationContractError


MAX_CONTINUATION_ARTIFACT_BYTES = 4 * 1024 * 1024
_DIRECTORY_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_FILE_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)


def _read_descriptor(descriptor: int, *, label: str) -> bytes:
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode):
        raise ContinuationContractError(f"{label} must be a regular file")
    if metadata.st_size > MAX_CONTINUATION_ARTIFACT_BYTES:
        raise ContinuationContractError(f"{label} exceeds the size limit")
    chunks: list[bytes] = []
    remaining = MAX_CONTINUATION_ARTIFACT_BYTES + 1
    while remaining:
        chunk = os.read(descriptor, min(remaining, 64 * 1024))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    payload = b"".join(chunks)
    if len(payload) > MAX_CONTINUATION_ARTIFACT_BYTES:
        raise ContinuationContractError(f"{label} exceeds the size limit")
    return payload


def read_named_bytes_no_follow(
    directory_descriptor: int,
    name: str,
    *,
    label: str,
) -> bytes:
    """Read one regular child without following its final symlink."""

    try:
        descriptor = os.open(name, _FILE_FLAGS, dir_fd=directory_descriptor)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise ContinuationContractError(
                f"{label} must not be a symlink"
            ) from exc
        raise
    try:
        return _read_descriptor(descriptor, label=label)
    finally:
        os.close(descriptor)


def read_bytes_no_follow(path: Path, *, label: str) -> bytes:
    """Read a named file through a no-follow immediate-parent handle."""

    try:
        parent_descriptor = os.open(path.parent, _DIRECTORY_FLAGS)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise ContinuationContractError(
                f"{label} parent must not be a symlink"
            ) from exc
        raise
    try:
        return read_named_bytes_no_follow(
            parent_descriptor,
            path.name,
            label=label,
        )
    finally:
        os.close(parent_descriptor)


def _open_sessions_directory(root: Path) -> tuple[int | None, Path]:
    """Open the fixed sessions directory one no-follow component at a time."""

    directory = root / ".task" / "authorization" / "sessions"
    descriptor = os.open(root, _DIRECTORY_FLAGS)
    try:
        for part in (".task", "authorization", "sessions"):
            try:
                child = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
            except FileNotFoundError:
                os.close(descriptor)
                return None, directory
            except OSError as exc:
                if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                    raise ContinuationContractError(
                        "session artifact path traverses a symlink"
                    ) from exc
                raise
            os.close(descriptor)
            descriptor = child
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    return descriptor, directory


def scan_session_files(root: Path, filename: str) -> list[tuple[Path, bytes]]:
    """Read immediate session artifacts and reject symlinked session parents."""

    sessions_descriptor, directory = _open_sessions_directory(root)
    if sessions_descriptor is None:
        return []
    rows: list[tuple[Path, bytes]] = []
    try:
        for name in sorted(os.listdir(sessions_descriptor)):
            metadata = os.stat(
                name,
                dir_fd=sessions_descriptor,
                follow_symlinks=False,
            )
            if stat.S_ISLNK(metadata.st_mode):
                raise ContinuationContractError(
                    "session artifact parent must not be a symlink"
                )
            if not stat.S_ISDIR(metadata.st_mode):
                continue
            try:
                session_descriptor = os.open(
                    name,
                    _DIRECTORY_FLAGS,
                    dir_fd=sessions_descriptor,
                )
            except FileNotFoundError:
                continue
            except OSError as exc:
                if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                    raise ContinuationContractError(
                        "session artifact parent must not be a symlink"
                    ) from exc
                raise
            try:
                try:
                    payload = read_named_bytes_no_follow(
                        session_descriptor,
                        filename,
                        label=f"session {filename}",
                    )
                except FileNotFoundError:
                    continue
                rows.append((directory / name / filename, payload))
            finally:
                os.close(session_descriptor)
    finally:
        os.close(sessions_descriptor)
    return rows


__all__ = (
    "MAX_CONTINUATION_ARTIFACT_BYTES",
    "read_bytes_no_follow",
    "read_named_bytes_no_follow",
    "scan_session_files",
)
