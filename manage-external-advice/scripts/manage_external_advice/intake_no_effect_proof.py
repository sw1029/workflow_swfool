"""Historical prefix and duplicate proof for advice no-effect receipts."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .intake_plan_contract import (
    canonical_bytes,
    canonical_destination_path,
    regular_payload,
    sha256_bytes,
)
from .storage import event_bytes, parse_events


def duplicate_proof(
    root: Path,
    plan: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Bind one exact existing raw source without copying its body."""

    raw_sha256 = plan["raw"]["sha256"]
    for index, event in enumerate(events):
        if event.get("raw_sha256") != raw_sha256:
            continue
        path_value = event.get("raw_source_path")
        try:
            path = canonical_destination_path(root, path_value, kind="raw")
            payload = regular_payload(root, path)
        except SystemExit:
            return None
        if sha256_bytes(payload) != raw_sha256 or path_value == plan["raw"]["path"]:
            return None
        return {
            "advice_id": event.get("advice_id"),
            "event_index": index,
            "event_sha256": sha256_bytes(canonical_bytes(event)),
            "match_basis": "registry_raw_sha256",
            "raw_sha256": raw_sha256,
            "raw_source_path": path_value,
        }
    raw_root = root / ".agent_advice" / "raw"
    if not raw_root.exists() and not raw_root.is_symlink():
        return None
    if raw_root.is_symlink() or not raw_root.is_dir():
        raise SystemExit("External-advice raw store must be a regular directory")
    for candidate in sorted(raw_root.glob("*.md")):
        if candidate.is_symlink() or not candidate.is_file():
            raise SystemExit("Unsafe external-advice raw store entry")
        if sha256_bytes(candidate.read_bytes()) != raw_sha256:
            continue
        path_value = candidate.relative_to(root).as_posix()
        if path_value == plan["raw"]["path"]:
            return None
        return {
            "advice_id": None,
            "event_index": None,
            "event_sha256": None,
            "match_basis": "raw_file_sha256",
            "raw_sha256": raw_sha256,
            "raw_source_path": path_value,
        }
    return None


def historical_registry_proof(
    registry: bytes,
    events: list[dict[str, Any]],
    receipt: dict[str, Any],
    plan_id: str,
) -> bool:
    observed = receipt["registry_observation"]
    size = observed["size"]
    if (
        not isinstance(size, int)
        or isinstance(size, bool)
        or size < 0
        or size > len(registry)
    ):
        return False
    if sha256_bytes(registry[:size]) != observed["sha256"]:
        return False
    prefix = registry[:size]
    suffix_bytes = registry[size:]
    separator = b"\n" if prefix and not prefix.endswith(b"\n") else b""
    if separator:
        if not suffix_bytes.startswith(separator):
            return False
        suffix_payload = suffix_bytes[len(separator) :]
    else:
        suffix_payload = suffix_bytes
    try:
        suffix = parse_events(suffix_payload, Path("<intake-no-effect-suffix>"))
    except SystemExit:
        return False
    if suffix_bytes != separator + b"".join(event_bytes(row) for row in suffix):
        return False
    return not any(row.get("intake_plan_id") == plan_id for row in events)


def duplicate_proof_current(
    root: Path, events: list[dict[str, Any]], proof: dict[str, Any] | None
) -> bool:
    expected_keys = {
        "advice_id",
        "event_index",
        "event_sha256",
        "match_basis",
        "raw_sha256",
        "raw_source_path",
    }
    if not isinstance(proof, dict) or set(proof) != expected_keys:
        return False
    try:
        path = canonical_destination_path(root, proof["raw_source_path"], kind="raw")
        if sha256_bytes(regular_payload(root, path)) != proof["raw_sha256"]:
            return False
    except SystemExit:
        return False
    if proof["match_basis"] == "raw_file_sha256":
        return proof["event_index"] is None and proof["event_sha256"] is None
    index = proof["event_index"]
    if (
        proof["match_basis"] != "registry_raw_sha256"
        or not isinstance(index, int)
        or isinstance(index, bool)
        or not 0 <= index < len(events)
    ):
        return False
    event = events[index]
    return (
        sha256_bytes(canonical_bytes(event)) == proof["event_sha256"]
        and event.get("advice_id") == proof["advice_id"]
        and event.get("raw_source_path") == proof["raw_source_path"]
        and event.get("raw_sha256") == proof["raw_sha256"]
    )
