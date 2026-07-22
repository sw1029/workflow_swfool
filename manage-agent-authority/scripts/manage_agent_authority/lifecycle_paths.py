"""Canonical paths and bindings shared by authority lifecycle operations."""

from __future__ import annotations

from pathlib import Path

from .canonical import sha256_file
from .projection_contracts import AUTHORIZATION_ROOT


def artifact_binding(root: Path, path: Path) -> dict[str, str]:
    return {
        "ref": path.relative_to(root.resolve()).as_posix(),
        "sha256": sha256_file(path),
    }


def reservation_path(root: Path, reservation_id: str) -> Path:
    return root.resolve() / AUTHORIZATION_ROOT / "reservations" / f"{reservation_id}.json"


def reservation_state_path(root: Path, reservation_id: str) -> Path:
    return (
        root.resolve()
        / AUTHORIZATION_ROOT
        / "state"
        / "reservations"
        / f"{reservation_id}.json"
    )


__all__ = ("artifact_binding", "reservation_path", "reservation_state_path")
