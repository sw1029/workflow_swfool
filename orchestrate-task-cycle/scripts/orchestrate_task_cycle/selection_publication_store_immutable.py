"""Race-safe immutable leaf publication for selection-related stores."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile

from .selection_publication_store import (
    _bounded_file_sha256,
    _fsync_dir,
    _sha256_bytes,
)


def _verify_exact(
    path: Path, payload: bytes, digest: str, label: str
) -> str:
    if _bounded_file_sha256(path, len(payload), label) != digest:
        raise ValueError(f"{label} conflicts with immutable transaction evidence")
    return digest


def _write_once_unlocked_with_status(
    path: Path, payload: bytes, label: str
) -> tuple[str, bool]:
    """Return the digest and whether this call won immutable publication."""

    digest = _sha256_bytes(payload)
    if path.exists() or path.is_symlink():
        _verify_exact(path, payload, digest, label)
        return digest, False
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_value = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_value)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError:
            _verify_exact(path, payload, digest, label)
            return digest, False
        _fsync_dir(path.parent)
        _verify_exact(path, payload, digest, label)
        return digest, True
    finally:
        temporary.unlink(missing_ok=True)


__all__: tuple[str, ...] = ()
