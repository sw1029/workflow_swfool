"""Pinned-root adapters for registered selection-publication store writes."""

from __future__ import annotations

import contextlib
import os
from pathlib import Path, PurePosixPath
import stat
from typing import Iterator

from .selection_publication_gc_fs import (
    bound_directory,
    bound_parent,
    replace_relative,
    write_once_relative,
)
from .selection_publication_producer_capability import (
    _active_reference_barrier_root_for_path,
    _require_selection_publication_lock,
    _require_selection_publication_producer,
)


STORE_MARKERS = (".task", "selection_publication")
LOCK_REF = ".task/selection_publication/publication.lock"


def _lexical_path(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _store_marker_indexes(path: Path) -> list[int]:
    lexical = _lexical_path(path)
    parts = lexical.parts
    return [
        index
        for index in range(len(parts) - 1)
        if parts[index : index + 2] == STORE_MARKERS
    ]


def _has_store_marker(path: Path) -> bool:
    return bool(_store_marker_indexes(path))


def _protected_store_location(path: Path) -> tuple[Path, PurePosixPath] | None:
    lexical = _lexical_path(path)
    parts = lexical.parts
    indexes = _store_marker_indexes(path)
    if not indexes:
        return None
    if len(indexes) != 1:
        raise ValueError(
            "selection-publication store path has an ambiguous workspace root "
            "and cannot be auto-acquired"
        )
    store_index = indexes[0]
    root = Path(*parts[:store_index])
    relative = PurePosixPath(*parts[store_index:])
    return root, relative


def _active_location(path: Path) -> tuple[Path, PurePosixPath] | None:
    lexical = _lexical_path(path)
    root = _active_reference_barrier_root_for_path(lexical)
    if root is None:
        return None
    relative = lexical.relative_to(root)
    return root, PurePosixPath(relative.as_posix())


def _write_location(
    path: Path, producer_capability: object | None
) -> tuple[Path, PurePosixPath, bool] | None:
    if not _has_store_marker(path) and producer_capability is None:
        return None
    _require_selection_publication_producer(producer_capability)
    active = _active_location(path)
    if active is not None:
        return *active, False
    protected = _protected_store_location(path)
    if protected is None:
        raise ValueError(
            "registered selection-publication mutation requires a held "
            "reference barrier"
        )
    lexical_root, relative = protected
    try:
        root = lexical_root.expanduser().resolve(strict=True)
    except OSError as exc:
        raise ValueError("selection-publication workspace root is unavailable") from exc
    return root, relative, True


def replace_registered_path(
    path: Path,
    payload: bytes,
    label: str,
    *,
    producer_capability: object | None,
) -> bool:
    """Replace a registered path through its active workspace root descriptor."""

    location = _write_location(path, producer_capability)
    if location is None:
        return False
    root, relative, acquire = location
    if acquire:
        from .selection_publication_reference_barrier import (
            registered_producer_barrier,
        )

        with registered_producer_barrier(root, producer_capability=producer_capability):
            replace_relative(
                root,
                relative,
                payload,
                label,
                producer_capability=producer_capability,
            )
    else:
        replace_relative(
            root,
            relative,
            payload,
            label,
            producer_capability=producer_capability,
        )
    return True


def write_once_registered_path(
    path: Path,
    payload: bytes,
    label: str,
    *,
    producer_capability: object | None,
) -> tuple[str, bool] | None:
    """Publish one registered immutable leaf relative to the pinned root."""

    location = _write_location(path, producer_capability)
    if location is None:
        return None
    root, relative, acquire = location
    if acquire:
        from .selection_publication_reference_barrier import (
            registered_producer_barrier,
        )

        with registered_producer_barrier(root, producer_capability=producer_capability):
            return write_once_relative(
                root,
                relative,
                payload,
                label,
                producer_capability=producer_capability,
            )
    return write_once_relative(
        root,
        relative,
        payload,
        label,
        producer_capability=producer_capability,
    )


def create_store_directories(root: Path) -> Path:
    """Create the store below the active root fd and verify visible identity."""

    try:
        with bound_directory(
            root, ".task/selection_publication", create=True
        ) as directory:
            directory.verify()
    except ValueError as exc:
        if "cannot be a symlink" in str(exc):
            raise ValueError(
                "selection-publication store root cannot be a symlink"
            ) from exc
        if "must be a directory" in str(exc):
            raise ValueError(
                "selection-publication store root must be a directory"
            ) from exc
        raise ValueError("selection-publication store root is unsafe") from exc
    return root / ".task/selection_publication"


@contextlib.contextmanager
def publication_lock(root: Path, *, producer_capability: object) -> Iterator[None]:
    """Lock the publication leaf relative to the active pinned workspace."""

    _require_selection_publication_lock(producer_capability, root)
    create_store_directories(root)
    with bound_parent(root, LOCK_REF, create=False) as parent:
        parent.verify()
        flags = (
            os.O_RDWR
            | os.O_CREAT
            | os.O_APPEND
            | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0)
        )
        try:
            descriptor = os.open(parent.name, flags, 0o600, dir_fd=parent.descriptor)
        except OSError as exc:
            raise ValueError(
                "selection-publication lock must be a regular file"
            ) from exc
        try:
            observed = os.fstat(descriptor)
            if not stat.S_ISREG(observed.st_mode):
                raise ValueError("selection-publication lock must be a regular file")
            parent.verify()
            try:
                import fcntl
            except ImportError:  # pragma: no cover - POSIX is production.
                fcntl = None  # type: ignore[assignment]
            if fcntl is not None:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
            try:
                parent.verify()
                yield
                parent.verify()
            finally:
                if fcntl is not None:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


__all__: tuple[str, ...] = ()
