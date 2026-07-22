"""No-follow content identities for Git worktree paths."""

from __future__ import annotations

import hashlib
import os
from pathlib import PurePosixPath
import stat
from typing import Any


def _mode_identity(mode: int) -> str:
    return format(stat.S_IFMT(mode) | stat.S_IMODE(mode), "06o")


def _stat_signature(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _missing_identity() -> dict[str, Any]:
    return {
        "kind": "missing",
        "mode": None,
        "size_bytes": None,
        "content_sha256": None,
    }


def _open_parent(root_fd: int, path: str) -> tuple[int | None, str | None]:
    directory_fd = os.dup(root_fd)
    for component in PurePosixPath(path).parts[:-1]:
        try:
            next_fd = os.open(
                component,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=directory_fd,
            )
        except FileNotFoundError:
            os.close(directory_fd)
            return None, "missing"
        except OSError:
            os.close(directory_fd)
            return None, "git_path_parent_unsafe"
        os.close(directory_fd)
        directory_fd = next_fd
    return directory_fd, None


def _symlink_identity(
    directory_fd: int,
    name: str,
    observed: os.stat_result,
    remaining_bytes: int,
) -> tuple[dict[str, Any] | None, int, str | None]:
    try:
        target = os.fsencode(os.readlink(name, dir_fd=directory_fd))
        after = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except OSError:
        return None, 0, "git_symlink_read_failed"
    if _stat_signature(observed) != _stat_signature(after):
        return None, 0, "git_path_changed_during_binding"
    if len(target) > remaining_bytes:
        return None, 0, "git_content_limit_exceeded"
    return {
        "kind": "symlink",
        "mode": _mode_identity(observed.st_mode),
        "size_bytes": len(target),
        "content_sha256": hashlib.sha256(target).hexdigest(),
    }, len(target), None


def _regular_file_identity(
    directory_fd: int,
    name: str,
    observed: os.stat_result,
    remaining_bytes: int,
) -> tuple[dict[str, Any] | None, int, str | None]:
    if observed.st_size > remaining_bytes:
        return None, 0, "git_content_limit_exceeded"
    try:
        file_fd = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=directory_fd,
        )
    except OSError:
        return None, 0, "git_file_open_failed"
    try:
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode) or (
            before.st_dev,
            before.st_ino,
        ) != (observed.st_dev, observed.st_ino):
            return None, 0, "git_path_changed_during_binding"
        digest = hashlib.sha256()
        consumed = 0
        while True:
            chunk = os.read(
                file_fd,
                min(1024 * 1024, remaining_bytes - consumed + 1),
            )
            if not chunk:
                break
            consumed += len(chunk)
            if consumed > remaining_bytes:
                return None, 0, "git_content_limit_exceeded"
            digest.update(chunk)
        after = os.fstat(file_fd)
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except OSError:
        return None, 0, "git_file_read_failed"
    finally:
        os.close(file_fd)
    if not (
        _stat_signature(observed)
        == _stat_signature(before)
        == _stat_signature(after)
        == _stat_signature(current)
    ):
        return None, 0, "git_path_changed_during_binding"
    return {
        "kind": "regular_file",
        "mode": _mode_identity(observed.st_mode),
        "size_bytes": consumed,
        "content_sha256": digest.hexdigest(),
    }, consumed, None


def path_content_identity(
    root_fd: int,
    path: str,
    *,
    remaining_bytes: int,
) -> tuple[dict[str, Any] | None, int, str | None]:
    """Hash one relative path without following any symlink component."""

    directory_fd, parent_error = _open_parent(root_fd, path)
    if parent_error == "missing":
        return _missing_identity(), 0, None
    if parent_error is not None or directory_fd is None:
        return None, 0, parent_error or "git_path_parent_unsafe"
    try:
        name = PurePosixPath(path).parts[-1]
        try:
            observed = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            return _missing_identity(), 0, None
        except OSError:
            return None, 0, "git_path_stat_failed"
        if stat.S_ISLNK(observed.st_mode):
            return _symlink_identity(
                directory_fd, name, observed, remaining_bytes
            )
        if not stat.S_ISREG(observed.st_mode):
            return None, 0, "git_path_type_unsupported"
        return _regular_file_identity(
            directory_fd, name, observed, remaining_bytes
        )
    finally:
        os.close(directory_fd)


__all__ = ["path_content_identity"]
