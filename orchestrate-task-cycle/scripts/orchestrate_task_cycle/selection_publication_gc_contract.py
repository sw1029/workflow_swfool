"""Shared constants and canonical paths for selection-publication retention."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
import re


GC_SCHEMA_VERSION = 1
MAX_CANDIDATE_COUNT = 4096
MAX_CANDIDATE_BYTES = 64 * 1024 * 1024
MAX_SCAN_BYTES = 2 * 1024 * 1024 * 1024
MAX_SCAN_FILE_BYTES = 64 * 1024 * 1024
MAX_SCAN_FILES = 250_000
MAX_AUTHORITY_PACKET_BYTES = 4 * 1024 * 1024
CAS_LAYOUTS = (("blobs", "sha256"),)
REFERENCE_PATTERN = re.compile(
    rb"\.task/selection_publication/[A-Za-z0-9][A-Za-z0-9._/-]*"
)
PLAN_ID_PATTERN = re.compile(r"spgc-[0-9a-f]{64}")


def relative_ref(value: str | PurePosixPath, label: str) -> PurePosixPath:
    raw = value.as_posix() if isinstance(value, PurePosixPath) else str(value)
    path = PurePosixPath(raw)
    if (
        not raw
        or path.is_absolute()
        or path.as_posix() != raw
        or "\\" in raw
        or "\x00" in raw
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"{label} must be a canonical workspace-relative path")
    return path


def gc_relative(*parts: str) -> str:
    return PurePosixPath(
        ".task", "selection_publication", "gc", *parts
    ).as_posix()


def validate_plan_id(plan_id: str) -> str:
    if not PLAN_ID_PATTERN.fullmatch(plan_id):
        raise ValueError("invalid selection-publication gc plan id")
    return plan_id


def plan_path(root: Path, plan_id: str) -> Path:
    validate_plan_id(plan_id)
    return root / gc_relative("plans", f"{plan_id}.json")


def archive_path(root: Path, plan_id: str) -> Path:
    validate_plan_id(plan_id)
    return root / gc_relative("archives", f"{plan_id}.tar.gz")


def receipt_path(root: Path, plan_id: str) -> Path:
    validate_plan_id(plan_id)
    return root / gc_relative("receipts", f"{plan_id}.json")


def restore_receipt_path(root: Path, plan_id: str) -> Path:
    validate_plan_id(plan_id)
    return root / gc_relative("restores", f"{plan_id}.json")


__all__ = (
    "CAS_LAYOUTS",
    "GC_SCHEMA_VERSION",
    "MAX_AUTHORITY_PACKET_BYTES",
    "MAX_CANDIDATE_BYTES",
    "MAX_CANDIDATE_COUNT",
    "MAX_SCAN_BYTES",
    "MAX_SCAN_FILE_BYTES",
    "MAX_SCAN_FILES",
    "REFERENCE_PATTERN",
    "archive_path",
    "gc_relative",
    "plan_path",
    "receipt_path",
    "relative_ref",
    "restore_receipt_path",
)
