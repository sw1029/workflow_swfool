"""Opaque capabilities and in-process barrier proofs for store producers."""

from __future__ import annotations

import contextlib
from contextvars import ContextVar
import os
from pathlib import Path
import stat
from typing import Any, Iterator


_SELECTION_PUBLICATION_PRODUCER_CAPABILITY = object()
_SELECTION_PUBLICATION_GC_EXCLUSIVE_CAPABILITY = object()
_ACTIVE_REFERENCE_BARRIERS: ContextVar[tuple[tuple[str, str, int, int, int], ...]] = (
    ContextVar("selection_publication_reference_barriers", default=())
)


def _root_key(root: Path) -> str:
    return str(root.expanduser().absolute())


def _require_selection_publication_producer(value: Any) -> None:
    if value is not _SELECTION_PUBLICATION_PRODUCER_CAPABILITY:
        raise ValueError(
            "selection-publication mutation requires a registered producer capability"
        )


@contextlib.contextmanager
def _reference_barrier_proof(root: Path, mode: str, descriptor: int) -> Iterator[None]:
    if mode not in {"shared", "exclusive"}:
        raise ValueError("selection-publication barrier proof mode is invalid")
    observed = os.fstat(descriptor)
    if not stat.S_ISDIR(observed.st_mode):
        raise ValueError("selection-publication barrier proof root is not a directory")
    stack = _ACTIVE_REFERENCE_BARRIERS.get()
    token = _ACTIVE_REFERENCE_BARRIERS.set(
        (
            *stack,
            (
                _root_key(root),
                mode,
                descriptor,
                observed.st_dev,
                observed.st_ino,
            ),
        )
    )
    try:
        yield
    finally:
        _ACTIVE_REFERENCE_BARRIERS.reset(token)


def _active_reference_barrier_mode(root: Path) -> str | None:
    key = _root_key(root)
    modes = [
        mode
        for (
            observed_root,
            mode,
            _descriptor,
            _device,
            _inode,
        ) in _ACTIVE_REFERENCE_BARRIERS.get()
        if observed_root == key
    ]
    if "exclusive" in modes:
        return "exclusive"
    return "shared" if "shared" in modes else None


def _active_reference_barrier_descriptor(root: Path) -> int | None:
    """Duplicate the root inode pinned by the innermost active barrier."""

    key = _root_key(root)
    matches = [
        (descriptor, device, inode)
        for (
            observed_root,
            _mode,
            descriptor,
            device,
            inode,
        ) in _ACTIVE_REFERENCE_BARRIERS.get()
        if observed_root == key
    ]
    if not matches:
        return None
    descriptor, device, inode = matches[-1]
    try:
        duplicate = os.dup(descriptor)
        observed = os.fstat(duplicate)
    except OSError as exc:
        raise ValueError(
            "selection-publication pinned workspace root is unavailable"
        ) from exc
    if not stat.S_ISDIR(observed.st_mode) or (observed.st_dev, observed.st_ino) != (
        device,
        inode,
    ):
        os.close(duplicate)
        raise ValueError("selection-publication pinned workspace root identity changed")
    return duplicate


def _active_reference_barrier_root_for_path(path: Path) -> Path | None:
    """Return the innermost locked workspace lexically containing ``path``."""

    target = Path(os.path.abspath(os.fspath(path)))
    for observed_root, _mode, _descriptor, _device, _inode in reversed(
        _ACTIVE_REFERENCE_BARRIERS.get()
    ):
        root = Path(observed_root)
        try:
            relative = target.relative_to(root)
        except ValueError:
            continue
        if relative.parts:
            return root
    return None


def _require_selection_publication_gc_exclusive(value: Any, root: Path) -> None:
    if value is not _SELECTION_PUBLICATION_GC_EXCLUSIVE_CAPABILITY:
        raise ValueError(
            "selection-publication GC mutation requires the exclusive "
            "producer capability"
        )
    if _active_reference_barrier_mode(root) != "exclusive":
        raise ValueError(
            "selection-publication GC mutation requires a held exclusive "
            "reference barrier"
        )


def _require_selection_publication_lock(value: Any, root: Path) -> None:
    if value is _SELECTION_PUBLICATION_GC_EXCLUSIVE_CAPABILITY:
        _require_selection_publication_gc_exclusive(value, root)
        return
    _require_selection_publication_producer(value)
    if _active_reference_barrier_mode(root) != "shared":
        raise ValueError(
            "selection-publication lock requires a held shared reference barrier"
        )


__all__: tuple[str, ...] = ()
