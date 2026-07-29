"""Reopen every file binding consumed by a terminal run projection."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
from typing import Any


class RunTerminalEvidenceError(ValueError):
    """Raised when terminal evidence is absent, mutable, or cross-bound."""


def _bound_path(root: Path, ref: str, label: str) -> Path:
    relative = PurePosixPath(ref)
    if relative.is_absolute() or ".." in relative.parts or "\\" in ref:
        raise RunTerminalEvidenceError(f"{label} ref is unsafe")
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise RunTerminalEvidenceError(f"{label} path contains a symlink")
    return current


def _sha256_regular_nofollow(path: Path, label: str) -> str:
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError as exc:
        raise RunTerminalEvidenceError(f"{label} is unavailable") from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise RunTerminalEvidenceError(f"{label} is not a regular file")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        closed = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    try:
        current = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise RunTerminalEvidenceError(f"{label} changed while opening") from exc
    identities = {
        (
            item.st_dev,
            item.st_ino,
            item.st_size,
            item.st_mtime_ns,
            item.st_ctime_ns,
        )
        for item in (opened, closed, current)
    }
    if len(identities) != 1 or not stat.S_ISREG(current.st_mode):
        raise RunTerminalEvidenceError(f"{label} changed while opening")
    return digest.hexdigest()


def _verify_binding(
    root: Path, binding: dict[str, str], label: str
) -> None:
    path = _bound_path(root, binding["ref"], label)
    if _sha256_regular_nofollow(path, label) != binding["sha256"]:
        raise RunTerminalEvidenceError(f"{label} digest does not match")


def verify_projection_evidence(
    root: str | Path, projection: dict[str, Any]
) -> None:
    """Reopen all evidence and artifact bindings without trusting labels."""

    workspace = Path(root).resolve(strict=True)
    rows: list[tuple[str, dict[str, str]]] = []
    harvest = projection["harvest"]["evidence_binding"]
    if harvest is not None:
        rows.append(("harvest evidence", harvest))
    failure = projection.get("failure")
    if isinstance(failure, dict):
        rows.append(("failure evidence", failure["evidence_binding"]))
    for collection in ("safe_surviving_artifacts", "discarded_artifacts"):
        for index, artifact in enumerate(projection[collection]):
            rows.append(
                (
                    f"{collection}[{index}]",
                    artifact["binding"],
                )
            )
    for label, binding in rows:
        _verify_binding(workspace, binding, label)


__all__ = (
    "RunTerminalEvidenceError",
    "verify_projection_evidence",
)
