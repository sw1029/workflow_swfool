"""Test-only seams for deterministic selection-GC race regression tests."""

from pathlib import Path


def race_hook(stage: str, path: Path) -> None:
    _ = stage, path


__all__ = ("race_hook",)
