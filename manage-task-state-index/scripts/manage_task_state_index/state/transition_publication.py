"""Directory-fd-based immutable publication for transition-owned sidecars."""
from __future__ import annotations

import errno
import os
from pathlib import Path
import secrets
import stat


OWNED_DIRECTORIES = {
    "scan_compilations",
    "scan_projection_intents",
    "scan_projection_receipts",
    "scan_receipts",
    "transition_plans",
    "transition_intents",
    "transition_receipts",
    "transition_pending_receipts",
    "transition_no_effect_receipts",
}


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )


def _owned_shape(path: Path) -> tuple[Path, str, str]:
    resolved_parent = path.parent
    directory = resolved_parent.name
    task_parent = resolved_parent.parent
    if (
        directory not in OWNED_DIRECTORIES
        or task_parent.name != ".task"
        or path.name != Path(path.name).name
        or not path.name
    ):
        raise ValueError("Immutable task-state path is not transition-owned")
    return task_parent.parent, directory, path.name


def ensure_owned_transition_directory(root: Path, directory: str) -> None:
    """Create one owned directory without following a replaced path component."""

    if directory not in OWNED_DIRECTORIES:
        raise ValueError("Unknown transition-owned directory")
    flags = _directory_flags()
    root_fd = os.open(root, flags)
    task_fd = -1
    directory_fd = -1
    current_task_fd = -1
    current_directory_fd = -1
    directory_created = False
    created_directory_identity: tuple[int, int] | None = None
    directory_identity: tuple[int, int] | None = None
    complete = False
    try:
        try:
            os.mkdir(".task", mode=0o700, dir_fd=root_fd)
        except FileExistsError:
            pass
        task_fd = os.open(".task", flags, dir_fd=root_fd)
        task_state = os.fstat(task_fd)
        task_identity = (task_state.st_dev, task_state.st_ino)
        try:
            os.mkdir(directory, mode=0o700, dir_fd=task_fd)
            directory_created = True
            created_state = os.stat(
                directory, dir_fd=task_fd, follow_symlinks=False
            )
            created_directory_identity = (created_state.st_dev, created_state.st_ino)
        except FileExistsError:
            pass
        directory_fd = os.open(directory, flags, dir_fd=task_fd)
        directory_state = os.fstat(directory_fd)
        directory_identity = (directory_state.st_dev, directory_state.st_ino)
        if not stat.S_ISDIR(directory_state.st_mode):
            raise ValueError("Transition-owned root must be a directory")
        if (
            created_directory_identity is not None
            and directory_identity != created_directory_identity
        ):
            raise ValueError("New transition-owned root changed before it was opened")
        current_task_fd = os.open(".task", flags, dir_fd=root_fd)
        current_task_state = os.fstat(current_task_fd)
        if (current_task_state.st_dev, current_task_state.st_ino) != task_identity:
            raise ValueError("Task-state root changed during owned-directory creation")
        current_directory_fd = os.open(directory, flags, dir_fd=current_task_fd)
        current_directory_state = os.fstat(current_directory_fd)
        if (
            current_directory_state.st_dev,
            current_directory_state.st_ino,
        ) != directory_identity:
            raise ValueError("Transition-owned root changed during directory creation")
        complete = True
    except OSError as exc:
        raise ValueError("Transition-owned directory path is unsafe") from exc
    finally:
        if directory_created and not complete and task_fd >= 0:
            candidate_fd = -1
            try:
                candidate_fd = os.open(directory, flags, dir_fd=task_fd)
                candidate_state = os.fstat(candidate_fd)
                candidate_identity = (candidate_state.st_dev, candidate_state.st_ino)
                owned_identity = created_directory_identity or directory_identity
                if candidate_identity == owned_identity:
                    os.rmdir(directory, dir_fd=task_fd)
                    os.fsync(task_fd)
            except OSError:
                pass
            finally:
                if candidate_fd >= 0:
                    os.close(candidate_fd)
        if current_directory_fd >= 0:
            os.close(current_directory_fd)
        if current_task_fd >= 0:
            os.close(current_task_fd)
        if directory_fd >= 0:
            os.close(directory_fd)
        if task_fd >= 0:
            os.close(task_fd)
        os.close(root_fd)


def _open_directories(path: Path) -> tuple[int, int, int, tuple[int, int]]:
    root, directory, _filename = _owned_shape(path)
    flags = _directory_flags()
    root_fd = os.open(root, flags)
    task_fd = -1
    directory_fd = -1
    try:
        task_fd = os.open(".task", flags, dir_fd=root_fd)
        directory_fd = os.open(directory, flags, dir_fd=task_fd)
        state = os.fstat(directory_fd)
        if not stat.S_ISDIR(state.st_mode):
            raise ValueError("Transition-owned publication root is not a directory")
        return root_fd, task_fd, directory_fd, (state.st_dev, state.st_ino)
    except BaseException:
        if directory_fd >= 0:
            os.close(directory_fd)
        if task_fd >= 0:
            os.close(task_fd)
        os.close(root_fd)
        raise


def _read_at(directory_fd: int, filename: str) -> bytes | None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(filename, flags, dir_fd=directory_fd)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ValueError("Transition-owned immutable leaf is unsafe") from exc
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("Transition-owned immutable leaf must be regular")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    finally:
        os.close(descriptor)


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("Immutable transition publication made no write progress")
        view = view[written:]
    os.fsync(descriptor)


def _recheck_directory_identity(
    root_fd: int, directory: str, expected: tuple[int, int]
) -> None:
    flags = _directory_flags()
    task_fd = os.open(".task", flags, dir_fd=root_fd)
    current_fd = -1
    try:
        current_fd = os.open(directory, flags, dir_fd=task_fd)
        state = os.fstat(current_fd)
        if (state.st_dev, state.st_ino) != expected:
            raise ValueError("Transition-owned publication root changed during write")
    finally:
        if current_fd >= 0:
            os.close(current_fd)
        os.close(task_fd)


def _publish_posix(path: Path, payload: bytes) -> bool:
    root, directory, filename = _owned_shape(path)
    del root
    root_fd, task_fd, directory_fd, identity = _open_directories(path)
    temporary = f".{filename}.{secrets.token_hex(12)}.tmp"
    temporary_created = False
    final_created = False
    publication_complete = False
    try:
        current = _read_at(directory_fd, filename)
        if current is not None:
            if current != payload:
                raise ValueError("Immutable task-state transition file conflict")
            _recheck_directory_identity(root_fd, directory, identity)
            return False
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        descriptor = os.open(temporary, flags, 0o600, dir_fd=directory_fd)
        temporary_created = True
        try:
            _write_all(descriptor, payload)
        finally:
            os.close(descriptor)
        try:
            os.link(
                temporary,
                filename,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
            created = True
            final_created = True
        except FileExistsError:
            current = _read_at(directory_fd, filename)
            if current != payload:
                raise ValueError("Immutable task-state transition file conflict")
            created = False
        os.fsync(directory_fd)
        _recheck_directory_identity(root_fd, directory, identity)
        publication_complete = True
        return created
    finally:
        if final_created and not publication_complete:
            try:
                os.unlink(filename, dir_fd=directory_fd)
                os.fsync(directory_fd)
            except OSError as exc:
                if exc.errno != errno.ENOENT:
                    raise
        if temporary_created:
            try:
                os.unlink(temporary, dir_fd=directory_fd)
            except OSError as exc:
                if exc.errno != errno.ENOENT:
                    raise
        os.close(directory_fd)
        os.close(task_fd)
        os.close(root_fd)


def publish_immutable_file(path: Path, payload: bytes) -> bool:
    if os.name == "posix":
        try:
            return _publish_posix(path, payload)
        except OSError as exc:
            raise ValueError("Transition-owned immutable publication path is unsafe") from exc
    current = path.read_bytes() if path.is_file() and not path.is_symlink() else None
    if current is not None:
        if current != payload:
            raise ValueError("Immutable task-state transition file conflict")
        return False
    if path.exists() or path.is_symlink():
        raise ValueError("Transition-owned immutable leaf must be regular")
    path.write_bytes(payload)
    return True


__all__ = ["ensure_owned_transition_directory", "publish_immutable_file"]
