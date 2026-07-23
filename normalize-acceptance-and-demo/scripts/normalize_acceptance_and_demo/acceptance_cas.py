"""Stable no-follow publication for compiled acceptance artifacts."""

from __future__ import annotations

import os
import secrets
import stat
from collections.abc import Callable
from pathlib import Path

from .acceptance_identity import AcceptanceIdentityError


CAS_DIRECTORY_PARTS = (".task", "acceptance", "sha256")
RaceHook = Callable[[str, Path], None]


def _directory_open_flags() -> int:
    required = ("O_DIRECTORY", "O_NOFOLLOW")
    if any(not hasattr(os, name) for name in required):
        raise AcceptanceIdentityError(
            "compiled acceptance CAS publication requires no-follow directory support"
        )
    return (
        os.O_RDONLY
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )


def _directory_error(parent_fd: int, name: str) -> AcceptanceIdentityError:
    try:
        entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError:
        return AcceptanceIdentityError(
            "compiled acceptance CAS directory is not safely accessible"
        )
    if stat.S_ISLNK(entry.st_mode):
        return AcceptanceIdentityError(
            "compiled acceptance CAS directory must not traverse a symlink"
        )
    return AcceptanceIdentityError(
        "compiled acceptance CAS ancestor must be a directory"
    )


def _open_or_create_directory(parent_fd: int, name: str) -> int:
    flags = _directory_open_flags()
    try:
        return os.open(name, flags, dir_fd=parent_fd)
    except FileNotFoundError:
        try:
            os.mkdir(name, mode=0o755, dir_fd=parent_fd)
            os.fsync(parent_fd)
        except FileExistsError:
            pass
        except OSError as exc:
            raise AcceptanceIdentityError(
                "compiled acceptance CAS directory could not be created safely"
            ) from exc
        try:
            return os.open(name, flags, dir_fd=parent_fd)
        except OSError as exc:
            raise _directory_error(parent_fd, name) from exc
    except OSError as exc:
        raise _directory_error(parent_fd, name) from exc


def _open_cas_directory(
    root: Path,
) -> tuple[list[int], list[tuple[int, str, int]]]:
    flags = _directory_open_flags()
    descriptors: list[int] = []
    chain: list[tuple[int, str, int]] = []
    try:
        try:
            root_fd = os.open(root, flags)
        except OSError as exc:
            raise AcceptanceIdentityError(
                "workspace root is not a stable non-symlink directory"
            ) from exc
        descriptors.append(root_fd)
        parent_fd = root_fd
        for part in CAS_DIRECTORY_PARTS:
            child_fd = _open_or_create_directory(parent_fd, part)
            descriptors.append(child_fd)
            chain.append((parent_fd, part, child_fd))
            parent_fd = child_fd
        return descriptors, chain
    except BaseException:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        raise


def _assert_directory_chain(chain: list[tuple[int, str, int]]) -> None:
    for parent_fd, name, child_fd in chain:
        try:
            entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            opened = os.fstat(child_fd)
        except OSError as exc:
            raise AcceptanceIdentityError(
                "compiled acceptance CAS directory changed during publication"
            ) from exc
        if (
            not stat.S_ISDIR(entry.st_mode)
            or (entry.st_dev, entry.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            raise AcceptanceIdentityError(
                "compiled acceptance CAS directory changed or became a symlink "
                "during publication"
            )


def _read_existing_leaf(
    directory_fd: int, leaf: str, payload: bytes
) -> tuple[int, int] | None:
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(leaf, flags, dir_fd=directory_fd)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise AcceptanceIdentityError(
            "compiled acceptance CAS path contains a non-regular or symlink leaf"
        ) from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size != len(payload):
            raise AcceptanceIdentityError(
                "compiled acceptance CAS path contains conflicting bytes"
            )
        chunks: list[bytes] = []
        remaining = len(payload) + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        stable_identity = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) == (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if not stable_identity or b"".join(chunks) != payload:
            raise AcceptanceIdentityError(
                "compiled acceptance CAS path contains conflicting bytes"
            )
        return before.st_dev, before.st_ino
    finally:
        os.close(descriptor)


def _assert_leaf_identity(
    directory_fd: int, leaf: str, identity: tuple[int, int]
) -> None:
    try:
        current = os.stat(leaf, dir_fd=directory_fd, follow_symlinks=False)
    except OSError as exc:
        raise AcceptanceIdentityError(
            "compiled acceptance CAS leaf changed during publication"
        ) from exc
    if (
        not stat.S_ISREG(current.st_mode)
        or (current.st_dev, current.st_ino) != identity
    ):
        raise AcceptanceIdentityError(
            "compiled acceptance CAS leaf changed during publication"
        )


def _leaf_has_identity(
    directory_fd: int, leaf: str, identity: tuple[int, int]
) -> bool:
    try:
        current = os.stat(leaf, dir_fd=directory_fd, follow_symlinks=False)
    except OSError:
        return False
    return stat.S_ISREG(current.st_mode) and (
        current.st_dev,
        current.st_ino,
    ) == identity


def _create_temporary_leaf(directory_fd: int, leaf: str) -> tuple[int, str]:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    for _ in range(64):
        temporary = f".{leaf}.{secrets.token_hex(16)}.tmp"
        try:
            return os.open(temporary, flags, 0o600, dir_fd=directory_fd), temporary
        except FileExistsError:
            continue
        except OSError as exc:
            raise AcceptanceIdentityError(
                "compiled acceptance CAS temporary file could not be created safely"
            ) from exc
    raise AcceptanceIdentityError(
        "compiled acceptance CAS temporary filename attempts were exhausted"
    )


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise AcceptanceIdentityError(
                "compiled acceptance CAS temporary write made no progress"
            )
        view = view[written:]


def immutable_write(
    root: Path,
    path: Path,
    payload: bytes,
    *,
    race_hook: RaceHook,
) -> bool:
    """Publish exact bytes once while pinning every directory and leaf inode."""

    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise AcceptanceIdentityError(
            "compiled acceptance CAS path escapes the workspace"
        ) from exc
    if (
        len(relative.parts) != 4
        or relative.parts[:3] != CAS_DIRECTORY_PARTS
        or not relative.name.endswith(".json")
    ):
        raise AcceptanceIdentityError(
            "compiled acceptance CAS path is outside its fixed producer store"
        )

    descriptors, chain = _open_cas_directory(root)
    directory_fd = descriptors[-1]
    temporary: str | None = None
    published_identity: tuple[int, int] | None = None
    linked_by_writer = False
    try:
        _assert_directory_chain(chain)
        existing_identity = _read_existing_leaf(
            directory_fd, relative.name, payload
        )
        if existing_identity is not None:
            race_hook("after_existing_read", path)
            _assert_directory_chain(chain)
            _assert_leaf_identity(
                directory_fd, relative.name, existing_identity
            )
            return False

        temporary_fd, temporary = _create_temporary_leaf(
            directory_fd, relative.name
        )
        try:
            _write_all(temporary_fd, payload)
            os.fsync(temporary_fd)
            temporary_stat = os.fstat(temporary_fd)
            published_identity = (
                temporary_stat.st_dev,
                temporary_stat.st_ino,
            )
        finally:
            os.close(temporary_fd)

        race_hook("before_link", path)
        _assert_directory_chain(chain)
        try:
            os.link(
                temporary,
                relative.name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
            linked_by_writer = True
        except FileExistsError:
            published_identity = _read_existing_leaf(
                directory_fd, relative.name, payload
            )
            if published_identity is None:
                raise AcceptanceIdentityError(
                    "compiled acceptance CAS path raced with a missing leaf"
                )
        race_hook("after_link", path)
        _assert_directory_chain(chain)
        assert published_identity is not None
        _assert_leaf_identity(
            directory_fd, relative.name, published_identity
        )
        os.fsync(directory_fd)
        return linked_by_writer
    except BaseException:
        if (
            linked_by_writer
            and published_identity is not None
            and _leaf_has_identity(
                directory_fd, relative.name, published_identity
            )
        ):
            try:
                os.unlink(relative.name, dir_fd=directory_fd)
                os.fsync(directory_fd)
            except OSError:
                pass
        raise
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
        for descriptor in reversed(descriptors):
            os.close(descriptor)
