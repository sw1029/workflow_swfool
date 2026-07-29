"""Locked, no-follow access to the tracked authority-session registry."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any, Iterator

from .session_lease import validate_session_lease


SESSION_PARTS = (".task", "authorization", "sessions")
_SESSION_LEASE_MAX_BYTES = 256 * 1024


class SessionRegistryError(ValueError):
    """Raised when session registry identity or uniqueness is unsafe."""


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )


@contextlib.contextmanager
def locked_session_registry(
    root: Path, *, create: bool, exclusive: bool
) -> Iterator[int | None]:
    """Bind and lock the one registry shared by all session identities."""

    descriptors: list[int] = []
    try:
        current = os.open(root, _directory_flags())
        descriptors.append(current)
        for part in SESSION_PARTS:
            try:
                child = os.open(part, _directory_flags(), dir_fd=current)
            except FileNotFoundError:
                if not create:
                    yield None
                    return
                try:
                    os.mkdir(part, mode=0o700, dir_fd=current)
                except FileExistsError:
                    pass
                try:
                    child = os.open(
                        part, _directory_flags(), dir_fd=current
                    )
                except OSError as exc:
                    raise SessionRegistryError(
                        "session registry ancestors must be real directories"
                    ) from exc
            except OSError as exc:
                raise SessionRegistryError(
                    "session registry ancestors must be real directories"
                ) from exc
            descriptors.append(child)
            current = child
        fcntl.flock(
            current, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        )
        try:
            yield current
        finally:
            fcntl.flock(current, fcntl.LOCK_UN)
    except OSError as exc:
        raise SessionRegistryError(
            "session registry must be a stable real directory"
        ) from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _file_signature(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _read_lease_from_parent(
    parent_descriptor: int, *, label: str
) -> dict[str, Any] | None:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(
            "session-lease.json", flags, dir_fd=parent_descriptor
        )
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise SessionRegistryError(
            f"{label} must be a regular non-symlink file"
        ) from exc
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size > _SESSION_LEASE_MAX_BYTES
        ):
            raise SessionRegistryError(
                f"{label} must be a bounded regular file"
            )
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(
                descriptor,
                min(1024 * 1024, _SESSION_LEASE_MAX_BYTES + 1 - total),
            )
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > _SESSION_LEASE_MAX_BYTES:
                raise SessionRegistryError(
                    f"{label} exceeds the safety limit"
                )
        after = os.fstat(descriptor)
        try:
            current = os.stat(
                "session-lease.json",
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise SessionRegistryError(
                f"{label} changed during read"
            ) from exc
        if (
            _file_signature(before) != _file_signature(after)
            or _file_signature(after) != _file_signature(current)
        ):
            raise SessionRegistryError(f"{label} changed during read")
        try:
            value = json.loads(b"".join(chunks).decode("utf-8"))
            return validate_session_lease(value)
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
            return None
    finally:
        os.close(descriptor)


def matching_session_leases_locked(
    root: Path,
    registry_descriptor: int,
    *,
    thread_binding: str | None,
) -> list[tuple[Path, dict[str, Any]]]:
    """Read valid leases without following registry child symlinks."""

    thread_sha = (
        hashlib.sha256(thread_binding.encode("utf-8")).hexdigest()
        if thread_binding
        else None
    )
    directory = root.joinpath(*SESSION_PARTS)
    rows: list[tuple[Path, dict[str, Any]]] = []
    with os.scandir(registry_descriptor) as entries:
        for entry in sorted(entries, key=lambda item: item.name):
            if entry.is_symlink():
                raise SessionRegistryError(
                    "session parent directory must not be a symlink"
                )
            if not entry.is_dir(follow_symlinks=False):
                continue
            try:
                parent = os.open(
                    entry.name,
                    _directory_flags(),
                    dir_fd=registry_descriptor,
                )
            except OSError as exc:
                raise SessionRegistryError(
                    "session parent directory changed during read"
                ) from exc
            try:
                lease = _read_lease_from_parent(
                    parent, label=f"session lease {entry.name}"
                )
            finally:
                os.close(parent)
            if lease is None:
                continue
            if (
                thread_sha is not None
                and lease["session_binding"]["thread_binding_sha256"]
                != thread_sha
            ):
                continue
            rows.append(
                (directory / entry.name / "session-lease.json", lease)
            )
    return rows


def scope_rows(
    rows: list[tuple[Path, dict[str, Any]]],
    *,
    workspace_identity: str,
    thread_binding: str,
    activation_evidence_id: str,
) -> list[tuple[Path, dict[str, Any]]]:
    """Select one workspace/thread/activation uniqueness scope."""

    thread_sha = hashlib.sha256(thread_binding.encode("utf-8")).hexdigest()
    return [
        (path, lease)
        for path, lease in rows
        if lease["session_binding"]["workspace_identity"]
        == workspace_identity
        and lease["session_binding"]["thread_binding_sha256"] == thread_sha
        and lease["session_binding"]["activation_evidence_id"]
        == activation_evidence_id
    ]


def reusable_scope_lease(
    rows: list[tuple[Path, dict[str, Any]]],
    *,
    provider: str,
    trust_class: str,
    approval_receipt: str | None,
) -> dict[str, Any] | None:
    """Resolve a compatible live owner, rejecting ambiguity or revival."""

    live = [
        lease
        for _path, lease in rows
        if lease["lifecycle"]["status"] == "live"
    ]
    if len(live) > 1:
        raise SessionRegistryError(
            "multiple live leases exist for the current thread and activation"
        )
    if live:
        existing = live[0]
        binding = existing["session_binding"]
        if (
            binding["provider"] == provider
            and trust_class == "agent_mediated_tty_narrowing"
            and binding["trust_class"] == trust_class
        ):
            return existing
        receipt_sha = (
            hashlib.sha256(approval_receipt.encode("utf-8")).hexdigest()
            if approval_receipt
            else None
        )
        if (
            binding["provider"] == provider
            and binding["trust_class"] == trust_class
            and binding["approval_receipt_sha256"] == receipt_sha
        ):
            return existing
        raise SessionRegistryError(
            "a differently bound live lease already owns the current "
            "thread and activation"
        )
    if rows:
        raise SessionRegistryError(
            "the session scope has reached a terminal state and cannot be revived"
        )
    return None


__all__ = (
    "SESSION_PARTS",
    "SessionRegistryError",
    "locked_session_registry",
    "matching_session_leases_locked",
    "reusable_scope_lease",
    "scope_rows",
)
