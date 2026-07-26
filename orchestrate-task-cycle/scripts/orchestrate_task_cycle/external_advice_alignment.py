"""Canonical external-advice identity and bounded filesystem alignment."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
from typing import Any


HEADER_BYTES = 16 * 1024
HEADER_LINES = 80
NONACTIVE_STATUSES = frozenset({"applied", "deferred", "rejected"})
_HEADER_FIELD = re.compile(r"^\s*[-*]?\s*([a-zA-Z0-9_-]+)\s*:\s*(.*?)\s*$")
_PATH_FIELDS = (
    "missing_paths",
    "unexpected_paths",
    "ignored_nonactive_paths",
    "active_metadata_conflict_paths",
)


@dataclass(frozen=True)
class AdviceAlignmentResult:
    alignment: dict[str, Any]
    registry_active_count: int | None
    filesystem_active_files: tuple[Path, ...]
    canonical_existing_files: tuple[Path, ...]
    ignored_nonactive_files: tuple[Path, ...]
    active_metadata: dict[str, str]


def advice_inventory_status(
    root: Path,
    directory: Path,
    path: Path,
    alignment: AdviceAlignmentResult,
) -> str | None:
    relative = path.relative_to(directory)
    top_level = relative.parts[0].casefold() if relative.parts else ""
    if top_level == "journal":
        return "journal"
    if top_level == "active" and len(relative.parts) == 2:
        if path in alignment.ignored_nonactive_files:
            return alignment.active_metadata.get(
                path.relative_to(root).as_posix(), "deferred"
            )
        return "active"
    return top_level if top_level in {"applied", "deferred", "rejected", "raw"} else None


def _normalized_scalar(value: str) -> str:
    scalar = value.strip()
    while len(scalar) >= 2 and (
        (scalar[0] == scalar[-1] == "`")
        or (scalar[0] == scalar[-1] == '"')
        or (scalar[0] == scalar[-1] == "'")
    ):
        scalar = scalar[1:-1].strip()
    return scalar.casefold()


def _active_metadata(path: Path) -> tuple[str | None, bool | None, bool]:
    """Read only bounded header scalars; never return or retain document bodies."""

    if path.is_symlink():
        return None, None, True
    try:
        with path.open("rb") as handle:
            text = handle.read(HEADER_BYTES).decode("utf-8", errors="replace")
    except OSError:
        return None, None, True
    fields: dict[str, str] = {}
    for line in text.splitlines()[:HEADER_LINES]:
        match = _HEADER_FIELD.match(line)
        if match and match.group(1).casefold() in {"status", "not_active_record"}:
            fields[match.group(1).casefold()] = _normalized_scalar(match.group(2))
    status = fields.get("status")
    marker_text = fields.get("not_active_record")
    marker_present = marker_text is not None
    marker = (
        True
        if marker_text in {"true", "1", "yes"}
        else False
        if marker_text in {"false", "0", "no"}
        else None
    )
    conflict = marker_present and (
        marker is None
        or (marker is True and status not in NONACTIVE_STATUSES)
        or (marker is False and status in NONACTIVE_STATUSES)
    )
    return status, marker, conflict


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _valid_registry_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value or "\\" in value:
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or value != path.as_posix():
        return None
    if len(path.parts) != 3 or path.parts[:2] != (".agent_advice", "active"):
        return None
    if path.name in {"", ".", ".."} or path.suffix.casefold() != ".md":
        return None
    return value


def _bounded_paths(paths: list[str], maximum: int) -> list[str]:
    return sorted(set(paths))[:maximum]


def _registry_paths(
    packet: dict[str, Any],
) -> tuple[int, set[str], int, int]:
    raw_items = packet.get("used_advice")
    if not isinstance(raw_items, list):
        return 0, set(), 1, 0
    valid: list[str] = []
    invalid_count = 0
    for item in raw_items:
        path = _valid_registry_path(item.get("path") if isinstance(item, dict) else None)
        if path is None:
            invalid_count += 1
        else:
            valid.append(path)
    return len(raw_items), set(valid), invalid_count, len(valid) - len(set(valid))


def collect_advice_alignment(
    root: Path,
    directory: Path,
    packet: dict[str, Any] | None,
    *,
    index_exists: bool,
    max_paths: int,
) -> AdviceAlignmentResult:
    if max_paths < 1:
        raise ValueError("max_paths must be positive")
    active_dir = directory / "active"
    direct_files = (
        sorted(path for path in active_dir.glob("*.md") if path.is_file())
        if active_dir.is_dir()
        else []
    )
    filesystem_active: list[Path] = []
    ignored: list[Path] = []
    conflicts: list[Path] = []
    metadata: dict[str, str] = {}
    for path in direct_files:
        status, marker, conflict = _active_metadata(path)
        relative = _relative(root, path)
        if status:
            metadata[relative] = status
        if marker is True and status in NONACTIVE_STATUSES and not conflict:
            ignored.append(path)
            continue
        filesystem_active.append(path)
        if conflict:
            conflicts.append(path)

    filesystem_paths = {_relative(root, path) for path in filesystem_active}
    registry_count: int | None = None
    canonical_paths: set[str] = set()
    invalid_count = 0
    duplicate_count = 0
    if packet is not None:
        (
            registry_count,
            canonical_paths,
            invalid_count,
            duplicate_count,
        ) = _registry_paths(packet)
        missing = sorted(canonical_paths - filesystem_paths)
        unexpected = sorted(filesystem_paths - canonical_paths)
        status = (
            "mismatch"
            if (
                missing
                or unexpected
                or invalid_count
                or duplicate_count
                or conflicts
            )
            else "aligned"
        )
    else:
        missing = []
        unexpected = []
        status = (
            "unavailable"
            if index_exists or filesystem_active or conflicts
            else "not_applicable"
        )

    ignored_paths = [_relative(root, path) for path in ignored]
    conflict_paths = [_relative(root, path) for path in conflicts]
    path_groups = {
        "missing_paths": missing,
        "unexpected_paths": unexpected,
        "ignored_nonactive_paths": ignored_paths,
        "active_metadata_conflict_paths": conflict_paths,
    }
    alignment = {
        "status": status,
        "missing_count": len(missing),
        "unexpected_count": len(unexpected),
        "invalid_registry_path_count": invalid_count,
        "duplicate_registry_path_count": duplicate_count,
        "ignored_nonactive_count": len(ignored_paths),
        "active_metadata_conflict_count": len(conflict_paths),
        **{
            field: _bounded_paths(values, max_paths)
            for field, values in path_groups.items()
        },
        "paths_truncated": any(len(values) > max_paths for values in path_groups.values()),
    }
    canonical_existing = tuple(
        path
        for relative in sorted(canonical_paths)
        for path in (root / PurePosixPath(relative),)
        if path.is_file() and not path.is_symlink()
    )
    return AdviceAlignmentResult(
        alignment=alignment,
        registry_active_count=registry_count,
        filesystem_active_files=tuple(filesystem_active),
        canonical_existing_files=canonical_existing,
        ignored_nonactive_files=tuple(ignored),
        active_metadata=metadata,
    )


def bounded_alignment_projection(
    value: Any,
    max_paths: int,
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    projected = {
        key: value.get(key)
        for key in (
            "status",
            "missing_count",
            "unexpected_count",
            "invalid_registry_path_count",
            "duplicate_registry_path_count",
            "ignored_nonactive_count",
            "active_metadata_conflict_count",
        )
        if key in value
    }
    truncated = bool(value.get("paths_truncated"))
    for field in _PATH_FIELDS:
        raw = value.get(field)
        paths = sorted({item for item in raw or [] if isinstance(item, str)})
        projected[field] = paths[:max_paths]
        truncated = truncated or len(paths) > max_paths
    projected["paths_truncated"] = truncated
    return projected


def project_packet_advice_items(
    packet: dict[str, Any],
    directive_fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    actionable = {str(item) for item in packet.get("actionable_clause_ids") or []}
    items: list[dict[str, Any]] = []
    for item in packet.get("used_advice") or []:
        if not isinstance(item, dict):
            continue
        fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
        directives = fields.get("directives")
        directives = directives if isinstance(directives, list) else []
        items.append(
            {
                "advice_id": item.get("advice_id"),
                "path": item.get("path"),
                "source_digest": item.get("source_digest"),
                "normalized_content_digest": item.get("content_sha256"),
                "fidelity_status": fields.get("fidelity_status"),
                "raw_direct_reference_required": fields.get(
                    "raw_direct_reference_required"
                ),
                "directives": [
                    {
                        field: record.get(field)
                        for field in directive_fields
                        if field in record
                    }
                    for record in directives
                    if isinstance(record, dict)
                    and str(record.get("directive_id") or "") in actionable
                ],
            }
        )
    return items


def nonnegative_count(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        count = int(value)
    except (TypeError, ValueError):
        return default
    return count if count >= 0 else default


def advice_projection_status(
    normalized_status: Any,
    *,
    packet_present: bool,
    active_count: int,
    item_count: int,
    incomplete: bool,
    alignment: dict[str, Any] | None,
) -> str:
    status = str(normalized_status or ("available" if packet_present else "unavailable"))
    if not packet_present:
        return "unavailable" if status == "available" else status
    if status != "available":
        return "unavailable" if status == "not_applicable" else status
    if incomplete:
        return "incomplete"
    alignment_status = alignment.get("status") if alignment is not None else None
    if alignment_status == "unavailable":
        return "unavailable"
    if (
        active_count != item_count
        or alignment_status == "mismatch"
        or (alignment is not None and alignment_status != "aligned")
    ):
        return "registry_filesystem_mismatch"
    return "available"
