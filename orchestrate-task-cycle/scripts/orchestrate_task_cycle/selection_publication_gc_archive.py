"""Deterministic archive and candidate-handle helpers for selection GC."""

from __future__ import annotations

import contextlib
import gzip
import io
from pathlib import Path
import tarfile
from typing import Any, Iterator

from .selection_publication_gc_contract import (
    GC_SCHEMA_VERSION,
    MAX_CANDIDATE_BYTES,
    MAX_SCAN_FILE_BYTES,
)
from .selection_publication_gc_fs import (
    BoundParent,
    PinnedLeaf,
    bound_parent,
    open_pinned_leaf,
    read_relative,
)
from .selection_publication_gc_scan import validate_quiescent_state
from .selection_publication_store import _canonical_json, _sha256_bytes


def archive_bytes(
    plan: dict[str, Any],
    root: Path,
    *,
    candidate_payloads: dict[str, bytes] | None = None,
) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            manifest = _canonical_json(
                {
                    "schema_version": GC_SCHEMA_VERSION,
                    "kind": "selection_publication_gc_archive_manifest",
                    "plan_id": plan["plan_id"],
                    "candidates": plan["candidates"],
                }
            )
            _add_member(archive, "manifest.json", manifest)
            for row in plan["candidates"]:
                payload = (
                    candidate_payloads[row["ref"]]
                    if candidate_payloads is not None
                    else read_relative(
                        root,
                        row["ref"],
                        "selection-publication gc candidate",
                        max_bytes=MAX_CANDIDATE_BYTES,
                    )
                )
                assert payload is not None
                _add_member(archive, f"files/{row['ref']}", payload)
    return buffer.getvalue()


def _add_member(archive: tarfile.TarFile, name: str, payload: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(payload)
    info.mode = 0o600
    info.mtime = 0
    archive.addfile(info, io.BytesIO(payload))


def archive_payloads(
    archive: Path | bytes,
    plan: dict[str, Any],
    *,
    root: Path | None = None,
) -> dict[str, bytes]:
    payload = _archive_input(archive, root)
    values: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as handle:
            members = handle.getmembers()
            expected = {
                "manifest.json",
                *(f"files/{row['ref']}" for row in plan["candidates"]),
            }
            if len(members) != len(expected) or {
                member.name for member in members
            } != expected:
                raise ValueError("selection-publication gc archive entries differ")
            for member in members:
                if not member.isfile() or member.issym() or member.islnk():
                    raise ValueError(
                        "selection-publication gc archive entry is unsafe"
                    )
                extracted = handle.extractfile(member)
                if extracted is None:
                    raise ValueError(
                        "selection-publication gc archive entry is unreadable"
                    )
                values[member.name] = extracted.read(MAX_CANDIDATE_BYTES + 1)
    except (OSError, tarfile.TarError) as exc:
        raise ValueError(
            "selection-publication gc archive is unreadable"
        ) from exc
    _validate_archive_values(values, plan)
    return values


def _archive_input(archive: Path | bytes, root: Path | None) -> bytes:
    if isinstance(archive, bytes):
        return archive
    workspace = root if root is not None else archive.parents[4]
    payload = read_relative(
        workspace,
        archive.relative_to(workspace).as_posix(),
        "selection-publication gc archive",
        max_bytes=MAX_CANDIDATE_BYTES + MAX_SCAN_FILE_BYTES,
    )
    assert payload is not None
    return payload


def _validate_archive_values(
    payloads: dict[str, bytes], plan: dict[str, Any]
) -> None:
    expected_manifest = _canonical_json(
        {
            "schema_version": GC_SCHEMA_VERSION,
            "kind": "selection_publication_gc_archive_manifest",
            "plan_id": plan["plan_id"],
            "candidates": plan["candidates"],
        }
    )
    if payloads.pop("manifest.json", None) != expected_manifest:
        raise ValueError("selection-publication gc archive manifest differs")
    for row in plan["candidates"]:
        payload = payloads.get(f"files/{row['ref']}")
        if (
            payload is None
            or len(payload) != row["size_bytes"]
            or _sha256_bytes(payload) != row["sha256"]
        ):
            raise ValueError("selection-publication gc archive payload differs")


def validate_plan_state(root: Path, plan: dict[str, Any]) -> None:
    _state, current = validate_quiescent_state(root)
    if current != plan.get("state"):
        raise ValueError("selection-publication state changed after gc planning")


@contextlib.contextmanager
def candidate_handles(
    root: Path,
    plan: dict[str, Any],
    *,
    allow_missing: bool,
) -> Iterator[list[tuple[dict[str, Any], BoundParent, PinnedLeaf | None]]]:
    with contextlib.ExitStack() as stack:
        rows: list[
            tuple[dict[str, Any], BoundParent, PinnedLeaf | None]
        ] = []
        for row in plan["candidates"]:
            parent = stack.enter_context(
                bound_parent(root, row["ref"], create=False)
            )
            pinned = open_pinned_leaf(
                parent,
                "selection-publication gc candidate",
                required=not allow_missing,
                max_bytes=MAX_CANDIDATE_BYTES,
            )
            if pinned is not None:
                stack.callback(pinned.close)
            payload = pinned.payload if pinned is not None else None
            if payload is not None and (
                len(payload) != row["size_bytes"]
                or _sha256_bytes(payload) != row["sha256"]
            ):
                raise ValueError("selection-publication gc candidate drifted")
            rows.append((row, parent, pinned))
        yield rows


__all__ = (
    "archive_bytes",
    "archive_payloads",
    "candidate_handles",
    "validate_plan_state",
)
